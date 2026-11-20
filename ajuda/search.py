"""Busca simples normalizada, sem serviço externo, em artigos e passos.

Percorre apenas guias já autorizados, em lotes. O catálogo de documentação é
pequeno; uma busca full-text pode substituir esta função se ele crescer.
"""
import unicodedata


def normalize_text(value):
    return ''.join(char for char in unicodedata.normalize('NFKD', value.casefold()) if not unicodedata.combining(char))


def search_articles(articles, query):
    terms = normalize_text(query).split()
    if not terms:
        return articles
    matching_ids = []
    fields = ('title', 'summary', 'objective', 'prerequisites', 'content', 'expected_result', 'warnings')
    for article in articles.prefetch_related('steps').iterator(chunk_size=100):
        text = '\n'.join(str(getattr(article, field)) for field in fields)
        text += '\n' + '\n'.join(f'{step.title}\n{step.content}' for step in article.steps.all())
        normalized = normalize_text(text)
        if all(term in normalized for term in terms):
            matching_ids.append(article.pk)
    return articles.filter(pk__in=matching_ids)
