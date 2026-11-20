from django.core.validators import RegexValidator
from django.core.exceptions import ValidationError
from django.db import models
from django.urls import reverse
from django.templatetags.static import static
import re

from .video import validate_video_url

SCREENSHOT_PATH_PATTERN = r'\Ahelp/screenshots/[a-z0-9][a-z0-9_-]*\.webp\Z'


class Category(models.Model):
    class Module(models.TextChoices):
        GENERAL = 'geral', 'Primeiros passos'
        CLIENTS = 'clientes', 'Clientes'
        ORDERS = 'os', 'Ordens de serviço'
        TECHNICIAN = 'tecnico', 'App do técnico'
        SALES = 'vendas', 'Vendas'
        POS = 'pdv', 'Frente de caixa'
        STOCK = 'estoque', 'Estoque'
        FINANCE = 'financeiro', 'Financeiro'
        PRODUCTION = 'producao', 'Expedição / Produção'
        MAINTENANCE = 'manutencao', 'Manutenção'
        REPORTS = 'relatorios', 'Relatórios'
        FISCAL = 'fiscal', 'Fiscal'
        SETTINGS = 'configuracoes', 'Configurações'

    name = models.CharField('Nome', max_length=120)
    slug = models.SlugField('Identificador', max_length=140, unique=True)
    description = models.TextField('Descrição', blank=True)
    icon = models.CharField(
        'Ícone Lucide', max_length=50, default='book-open',
        validators=[RegexValidator(r'^[a-z][a-z0-9-]*$', 'Informe o nome de um ícone Lucide.')],
    )
    module = models.CharField('Módulo / acesso', max_length=20, choices=Module.choices, default=Module.GENERAL)
    sort_order = models.PositiveIntegerField('Ordem', default=0)

    class Meta:
        ordering = ['sort_order', 'name']
        verbose_name = 'Categoria de ajuda'
        verbose_name_plural = 'Categorias de ajuda'

    def __str__(self):
        return self.name

    def get_absolute_url(self):
        return reverse('ajuda:category', args=[self.slug])


class Article(models.Model):
    class Status(models.TextChoices):
        DRAFT = 'DRAFT', 'Rascunho'
        PUBLISHED = 'PUBLISHED', 'Publicado'
        ARCHIVED = 'ARCHIVED', 'Arquivado'

    class Audience(models.TextChoices):
        ALL = 'ALL', 'Todos com acesso ao módulo'
        MANAGERS = 'MANAGERS', 'Gestores'
        COLLABORATORS = 'COLLABORATORS', 'Colaboradores'

    category = models.ForeignKey(Category, on_delete=models.PROTECT, related_name='articles', verbose_name='Categoria')
    title = models.CharField('Título', max_length=200)
    slug = models.SlugField('Identificador', max_length=220, unique=True)
    summary = models.TextField('Resumo', blank=True)
    objective = models.TextField('Objetivo', blank=True)
    prerequisites = models.TextField('Antes de começar', blank=True)
    content = models.TextField('Explicação', blank=True, help_text='Texto simples. Use os passos abaixo para instruções e imagens. HTML não é executado.')
    expected_result = models.TextField('Resultado esperado', blank=True)
    warnings = models.TextField('Cuidados e problemas comuns', blank=True)
    video_url = models.URLField('Link do vídeo', max_length=500, blank=True, validators=[validate_video_url], help_text='Link HTTPS do YouTube ou Vimeo. Não cole código HTML. Vídeos externos exigem internet e têm suas próprias regras de acesso.')
    status = models.CharField('Situação', max_length=10, choices=Status.choices, default=Status.DRAFT, db_index=True)
    audience = models.CharField('Público', max_length=15, choices=Audience.choices, default=Audience.ALL)
    featured = models.BooleanField('Destaque', default=False)
    sort_order = models.PositiveIntegerField('Ordem', default=0)
    reviewed_at = models.DateField('Revisado em', blank=True, null=True)
    created_at = models.DateTimeField('Criado em', auto_now_add=True)
    updated_at = models.DateTimeField('Atualizado em', auto_now=True)
    source_key = models.CharField('Origem do guia oficial', max_length=220, blank=True, editable=False)
    source_hash = models.CharField('Versão sincronizada', max_length=64, blank=True, editable=False)

    class Meta:
        ordering = ['sort_order', 'title']
        verbose_name = 'Artigo de ajuda'
        verbose_name_plural = 'Artigos de ajuda'

    def __str__(self):
        return self.title

    def get_absolute_url(self):
        return reverse('ajuda:article', args=[self.slug])

    @property
    def cover_url(self):
        for step in self.steps.all():
            if step.illustration_url:
                return step.illustration_url
        return ''

    @property
    def illustrated_step_count(self):
        return sum(bool(step.image or re.fullmatch(SCREENSHOT_PATH_PATTERN, step.screenshot)) for step in self.steps.all())


class ArticleStep(models.Model):
    article = models.ForeignKey(Article, on_delete=models.CASCADE, related_name='steps', verbose_name='Artigo')
    title = models.CharField('Título', max_length=200)
    content = models.TextField('Instruções', blank=True)
    image = models.ImageField('Imagem', upload_to='ajuda/passos/%Y/%m/', blank=True)
    screenshot = models.CharField(
        'Print oficial', max_length=220, blank=True,
        validators=[RegexValidator(SCREENSHOT_PATH_PATTERN, 'Use um print WebP versionado em help/screenshots/.')],
        help_text='Captura real com dados demonstrativos, distribuída com o sistema. Imagem enviada pelo editor tem prioridade.',
    )
    image_alt = models.CharField('Descrição da imagem', max_length=255, blank=True)
    sort_order = models.PositiveIntegerField('Ordem', default=0)

    class Meta:
        ordering = ['sort_order', 'pk']
        verbose_name = 'Passo'
        verbose_name_plural = 'Passos'

    def __str__(self):
        return self.title

    def clean(self):
        super().clean()
        if (self.image or self.screenshot) and not self.image_alt.strip():
            raise ValidationError({'image_alt': 'Descreva a imagem para quem utiliza leitor de tela.'})

    @property
    def illustration_url(self):
        if self.image:
            return self.image.url
        if re.fullmatch(SCREENSHOT_PATH_PATTERN, self.screenshot):
            return static(self.screenshot)
        return ''


class ContextLink(models.Model):
    article = models.ForeignKey(Article, on_delete=models.CASCADE, related_name='context_links', verbose_name='Artigo')
    view_name = models.CharField(
        'Nome da rota da tela', max_length=150,
        validators=[RegexValidator(r'^[a-zA-Z0-9_:-]+$', 'Use o nome da rota, incluindo namespace quando houver.')],
        help_text='Ex.: service_order_list, equipe_offline_app ou producao:board. Não informe uma URL.',
    )

    class Meta:
        ordering = ['view_name']
        constraints = [models.UniqueConstraint(fields=['article', 'view_name'], name='ajuda_unique_article_screen')]
        verbose_name = 'Tela relacionada'
        verbose_name_plural = 'Telas relacionadas'

    def __str__(self):
        return self.view_name
