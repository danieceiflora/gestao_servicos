"""Sincronização opt-in do conteúdo oficial; nunca adota ou apaga textos locais.

source_hash guarda o snapshot da última versão instalada, não o hash do novo
conteúdo do pacote. Assim, atualizar o pacote não autoriza sobrescrever uma
edição editorial. Não há --force. Categorias existentes são preservadas: não
há metadados de origem nelas que permitam distinguir edição local de versão.
"""

import hashlib
import json
from datetime import date

from django.core.management.base import BaseCommand, CommandError
from django.core.exceptions import ValidationError
from django.contrib.staticfiles import finders
from django.db import transaction
from django.db.models import Q

from ajuda.initial_content import ARTICLES, CATEGORIES
from ajuda.models import Article, ArticleStep, Category, ContextLink


ARTICLE_FIELDS = (
    "title", "slug", "summary", "objective", "prerequisites", "content",
    "expected_result", "warnings", "reviewed_at", "status", "audience",
    "featured", "sort_order", "video_url", "source_key",
)
STEP_FIELDS = ("title", "content", "image", "image_alt", "sort_order", "screenshot")


def _scalar(value):
    """Normalize DateField/FieldFile without opening storage or media URLs."""
    if isinstance(value, date):
        return value.isoformat()
    if hasattr(value, "name"):
        return value.name or ""
    return value


def content_hash(snapshot):
    """Deterministic SHA-256 of a snapshot; reusable by tests and tooling."""
    payload = json.dumps(snapshot, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _ordered_steps(steps):
    # Include every editable step field, excluding database-generated IDs.
    return sorted(steps, key=lambda step: (step["sort_order"], json.dumps(step, sort_keys=True, ensure_ascii=False)))


def article_snapshot(article):
    """Snapshot every managed editorial field, steps/media and context links.

    source_hash itself, IDs and timestamps are deliberately excluded. Category
    is identified by slug, not mutable display metadata shared by all articles.
    ContextLink is queried directly: no assumed reverse related_name.
    """
    snapshot = {field: _scalar(getattr(article, field)) for field in ARTICLE_FIELDS}
    snapshot["category"] = article.category.slug
    snapshot["steps"] = _ordered_steps([
        {field: _scalar(getattr(step, field)) for field in STEP_FIELDS}
        for step in article.steps.all()
    ])
    snapshot["screens"] = sorted(ContextLink.objects.filter(article=article).values_list("view_name", flat=True))
    return snapshot


def article_hash(article):
    """Return the installed article's current editorial hash."""
    return content_hash(article_snapshot(article))


def source_snapshot(source):
    """Build the equivalent snapshot from a version-controlled article dict."""
    snapshot = {field: _scalar(source[field]) for field in ARTICLE_FIELDS}
    snapshot["category"] = source["category"]
    snapshot["steps"] = _ordered_steps([
        {
            "title": step["title"], "content": step["content"],
            "image": step.get("image", ""), "image_alt": step.get("image_alt", ""),
            "screenshot": step.get("screenshot", ""),
            "sort_order": step["sort_order"],
        }
        for step in source["steps"]
    ])
    snapshot["screens"] = sorted(source["screens"])
    return snapshot


def sync_state(article, source):
    """Pure decision for an already-loaded article (no writes).

    Even a coincidentally identical local article without provenance is a
    conflict. A manually renamed official slug is found by source_key, then
    detected as an edit, not recreated under the original slug.
    """
    if article.source_key != source["source_key"] or not article.source_hash:
        return "conflict"
    current = article_snapshot(article)
    if content_hash(current) != article.source_hash:
        # Compatibilidade com o snapshot anterior ao campo screenshot. Só adota
        # o formato novo quando TODO o conteúdo antigo ainda corresponde ao hash
        # instalado e não existe print editado localmente. Não regrava edições.
        legacy = dict(current)
        legacy["steps"] = [{key: value for key, value in step.items() if key != "screenshot"} for step in current["steps"]]
        if any(step["screenshot"] for step in current["steps"]) or content_hash(legacy) != article.source_hash:
            return "conflict"
    # Extra guard: never transition a deliberately unpublished article or touch
    # attached media, even if a historical importer recorded those in its hash.
    if current["status"] != "PUBLISHED" or current["video_url"]:
        return "conflict"
    if any(step["image"] for step in current["steps"]):
        return "conflict"
    if content_hash(source_snapshot(source)) == article.source_hash:
        return "unchanged"
    return "update"


class Command(BaseCommand):
    help = "Instala/atualiza ajuda oficial sem sobrescrever edições locais. Execute explicitamente."

    def add_arguments(self, parser):
        group = parser.add_mutually_exclusive_group()
        group.add_argument("--check", action="store_true", help="Não escreve; falha se há conteúdo faltante, desatualizado ou em conflito.")
        group.add_argument("--dry-run", action="store_true", help="Mostra o que seria feito sem escrever.")

    def handle(self, *args, **options):
        self._validate_sources()
        read_only = options["check"] or options["dry_run"]
        counts = {"categories": 0, "create": 0, "update": 0, "unchanged": 0, "conflict": 0}
        blocked_categories = set()
        for source in CATEGORIES:
            if read_only:
                category = Category.objects.filter(slug=source["slug"]).first()
                missing = category is None
            else:
                category, missing = Category.objects.get_or_create(
                    slug=source["slug"], defaults={key: value for key, value in source.items() if key != "slug"},
                )
            if category is not None and category.module != source["module"]:
                blocked_categories.add(source["slug"])
                self.stdout.write(self.style.WARNING(
                    f"CONFLITO de acesso na categoria {source['slug']}: módulo local divergente; artigos oficiais não serão instalados nem atualizados."
                ))
            if missing:
                counts["categories"] += 1
                self.stdout.write(f"Categoria {'faltante' if read_only else 'criada'}: {source['slug']}")

        for source in ARTICLES:
            if source["category"] in blocked_categories:
                counts["conflict"] += 1
                continue
            # A transaction and row lock cover the ownership check and all
            # writes for this article. No global destructive synchronization.
            with transaction.atomic():
                candidates = Article.objects.filter(Q(slug=source["slug"]) | Q(source_key=source["source_key"]))
                if not read_only:
                    candidates = candidates.select_for_update()
                articles = list(candidates.select_related("category").order_by("pk")[:2])
                if len(articles) > 1:
                    state = "conflict"
                elif not articles:
                    state = "create"
                else:
                    state = sync_state(articles[0], source)
                counts[state] += 1
                if state == "conflict":
                    self.stdout.write(self.style.WARNING(f"CONFLITO preservado: {source['slug']} (edição local, mídia, status ou origem divergente)."))
                elif state in {"create", "update"}:
                    self.stdout.write(f"{'CRIAR' if state == 'create' else 'ATUALIZAR'}: {source['slug']}{' (sem escrita)' if read_only else ''}")
                    if not read_only:
                        self._write_article(articles[0] if articles else None, source)

        self.stdout.write(
            "Resumo: categorias faltantes/criadas={categories}; artigos novos={create}; "
            "atualizações={update}; inalterados={unchanged}; conflitos preservados={conflict}.".format(**counts)
        )
        if options["check"] and any(counts[key] for key in ("categories", "create", "update", "conflict")):
            raise CommandError("Ajuda oficial não sincronizada: execute sync_help_content e revise os conflitos sem sobrescrever edições locais.")

    def _write_article(self, article, source):
        # Called only within the per-article atomic block and after hash checks.
        values = {field: source[field] for field in ARTICLE_FIELDS}
        values["reviewed_at"] = date.fromisoformat(source["reviewed_at"]) if source["reviewed_at"] else None
        values["category"] = Category.objects.get(slug=source["category"])
        if article is None:
            article = Article.objects.create(**values)
        else:
            for key, value in values.items():
                setattr(article, key, value)
            article.save()
            # Safe only after comparing the full tracked snapshot, including
            # image names and alt text. No storage files are removed.
            article.steps.all().delete()
            ContextLink.objects.filter(article=article).delete()
        for step in source["steps"]:
            ArticleStep.objects.create(
                article=article, title=step["title"], content=step["content"],
                image=step.get("image", ""), image_alt=step.get("image_alt", ""),
                screenshot=step.get("screenshot", ""),
                sort_order=step["sort_order"],
            )
        for view_name in source["screens"]:
            ContextLink.objects.create(article=article, view_name=view_name)
        # Read the actual saved state: DateField conversion and relation defaults
        # must match the canonical source before recording ownership.
        article.refresh_from_db()
        installed_hash = article_hash(article)
        if installed_hash != content_hash(source_snapshot(source)):
            raise CommandError(f"Snapshot divergente ao instalar {source['slug']}; transação do artigo revertida.")
        article.source_hash = installed_hash
        article.save(update_fields=["source_hash"])

    @staticmethod
    def _validate_sources():
        category_slugs = [category["slug"] for category in CATEGORIES]
        slugs = [article["slug"] for article in ARTICLES]
        keys = [article["source_key"] for article in ARTICLES]
        if len(set(category_slugs)) != len(category_slugs) or len(set(slugs)) != len(slugs) or len(set(keys)) != len(keys):
            raise CommandError("Conteúdo oficial inválido: categorias, slugs e source_key precisam ser únicos.")
        for source in ARTICLES:
            if source["category"] not in category_slugs or not source["source_key"]:
                raise CommandError(f"Origem ou categoria inválida: {source['slug']}")
            if len(source["screens"]) != len(set(source["screens"])):
                raise CommandError(f"Contextos duplicados: {source['slug']}")
            # Validate dates and the tracked field contract before any write.
            if source["reviewed_at"]:
                date.fromisoformat(source["reviewed_at"])
            for step in source["steps"]:
                screenshot = step.get("screenshot", "")
                if screenshot:
                    try:
                        ArticleStep._meta.get_field('screenshot').run_validators(screenshot)
                    except ValidationError as error:
                        raise CommandError(f"Caminho de print inválido: {source['slug']}") from error
                    if not step.get("image_alt", "").strip() or not finders.find(screenshot):
                        raise CommandError(f"Print ausente ou sem descrição: {source['slug']} / {screenshot}")
            source_snapshot(source)
