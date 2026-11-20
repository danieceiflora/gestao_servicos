from django.template import Context, Template
from django.test import RequestFactory, TestCase
from django.urls import resolve, reverse

from ajuda.models import Article, ArticleStep, Category, ContextLink
from services.models import User


class HelpViewTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.manager = User.objects.create_user(username='view-manager', role=User.Roles.MANAGER)
        cls.worker = User.objects.create_user(username='view-worker')
        cls.general = Category.objects.create(name='Primeiros passos', slug='primeiros-passos')
        cls.finance = Category.objects.create(name='Financeiro', slug='financeiro', module='financeiro')
        cls.public = Article.objects.create(category=cls.general, title='Como começar', slug='comecar', summary='Orientações iniciais', status='PUBLISHED', content='Texto <script>alert(1)</script>')
        ArticleStep.objects.create(article=cls.public, title='Passo de sincronização', content='Conferir pendências antes de sair')
        cls.secret = Article.objects.create(category=cls.finance, title='Cobrança restrita', slug='cobranca', content='segredo financeiro', status='PUBLISHED')
        cls.draft = Article.objects.create(category=cls.general, title='Rascunho', slug='rascunho')
        ContextLink.objects.create(article=cls.public, view_name='equipe_offline_app')
        ContextLink.objects.create(article=cls.secret, view_name='equipe_offline_app')

    def test_all_reading_routes_require_login(self):
        for url in (reverse('ajuda:index'), self.public.get_absolute_url(), self.general.get_absolute_url()):
            with self.subTest(url=url):
                self.assertRedirects(self.client.get(url), reverse('login') + '?next=' + url, fetch_redirect_response=False)

    def test_direct_link_does_not_bypass_module_access_or_publication(self):
        self.client.force_login(self.worker)
        for url in (self.secret.get_absolute_url(), self.draft.get_absolute_url(), self.finance.get_absolute_url(), '/ajuda/artigo/inexistente/'):
            with self.subTest(url=url):
                self.assertEqual(self.client.get(url).status_code, 404)

    def test_index_only_counts_visible_published_articles(self):
        self.client.force_login(self.worker)
        response = self.client.get(reverse('ajuda:index'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Como começar')
        self.assertNotContains(response, 'Cobrança restrita')
        self.assertNotContains(response, 'Rascunho')
        self.assertEqual([(item.slug, item.article_count) for item in response.context['categories']], [('primeiros-passos', 1)])
        self.assertIn('no-store', response.headers['Cache-Control'])

    def test_search_finds_step_text_without_leaking_finance(self):
        self.client.force_login(self.worker)
        response = self.client.get(reverse('ajuda:index'), {'q': 'pendências'})
        self.assertEqual(list(response.context['articles']), [self.public])
        response = self.client.get(reverse('ajuda:index'), {'q': 'segredo'})
        self.assertEqual(list(response.context['articles']), [])

    def test_search_is_accent_insensitive_and_all_terms_must_match(self):
        self.client.force_login(self.worker)
        response = self.client.get(reverse('ajuda:index'), {'q': 'orientacoes iniciais'})
        self.assertEqual(list(response.context['articles']), [self.public])
        response = self.client.get(reverse('ajuda:index'), {'q': 'orientacoes inexistente'})
        self.assertEqual(list(response.context['articles']), [])

    def test_filters_and_pagination_remain_bounded(self):
        self.client.force_login(self.manager)
        self.public.video_url = 'https://youtu.be/Abc_12-xyZ0'
        self.public.save()
        response = self.client.get(reverse('ajuda:index'), {'video': '1', 'category': self.general.slug, 'page': 'invalid'})
        self.assertEqual(list(response.context['articles']), [self.public])
        for i in range(13):
            Article.objects.create(category=self.general, title=f'Guia {i}', slug=f'guia-{i}', status='PUBLISHED')
        response = self.client.get(reverse('ajuda:index'), {'category': self.general.slug, 'page': '2'})
        self.assertEqual(response.context['articles'].number, 2)
        self.assertLessEqual(len(response.context['articles']), 12)

    def test_article_is_escaped_and_related_articles_respect_publication(self):
        self.client.force_login(self.worker)
        response = self.client.get(self.public.get_absolute_url())
        self.assertContains(response, '&lt;script&gt;alert(1)&lt;/script&gt;')
        self.assertNotContains(response, '<script>alert(1)</script>')
        self.assertNotIn(self.draft, response.context['related_articles'])
        self.assertContains(response, 'App do Técnico')

    def test_contextual_help_uses_same_visibility_and_exact_screen_name(self):
        request = RequestFactory().get('/app/')
        request.user = self.worker
        request.resolver_match = resolve('/app/')
        html = Template('{% load ajuda_tags %}{% contextual_help %}').render(Context({'request': request}))
        self.assertNotIn(self.public.title, html)
        self.assertNotIn(self.secret.title, html)
        self.assertIn('data-help-context-url=', html)
        request.resolver_match = resolve('/ajuda/')
        self.assertEqual(Template('{% load ajuda_tags %}{% contextual_help %}').render(Context({'request': request})).strip(), '')

    def test_operational_html_never_persists_restricted_context_titles(self):
        self.client.force_login(self.manager)
        response = self.client.get('/app/')
        self.assertNotContains(response, self.secret.title)
        self.assertNotContains(response, self.public.title)
        self.assertContains(response, '/ajuda/contexto/?screen=equipe_offline_app')

    def test_context_endpoint_checks_current_session_and_never_caches(self):
        url = '/ajuda/contexto/?screen=equipe_offline_app'
        self.assertEqual(self.client.get(url).status_code, 302)
        self.client.force_login(self.manager)
        response = self.client.get(url)
        self.assertContains(response, self.secret.title)
        self.assertIn('no-store', response.headers['Cache-Control'])
        self.client.force_login(self.worker)
        response = self.client.get(url)
        self.assertContains(response, self.public.title)
        self.assertNotContains(response, self.secret.title)
        self.assertIn('no-store', response.headers['Cache-Control'])

    def test_context_endpoint_unknown_screen_has_safe_empty_state(self):
        self.client.force_login(self.worker)
        response = self.client.get('/ajuda/contexto/', {'screen': '<script>bad()</script>'})
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, '<script>bad()</script>')
        self.assertContains(response, 'Nenhum tutorial disponível')

    def test_help_navigation_exists_in_manager_and_technician_layouts(self):
        for user in (self.manager, self.worker):
            self.client.force_login(user)
            response = self.client.get(reverse('ajuda:index'))
            self.assertContains(response, 'Ajuda e Tutoriais')

    def test_empty_state_and_search_input_are_safe(self):
        self.client.force_login(self.worker)
        response = self.client.get(reverse('ajuda:index'), {'q': '<script>bad()</script>'})
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, '<script>bad()</script>')
        self.assertEqual(len(response.context['articles']), 0)

    def test_search_form_retains_query_and_offers_clear_on_index_and_category(self):
        self.client.force_login(self.worker)
        for url in (reverse('ajuda:index'), self.general.get_absolute_url()):
            response = self.client.get(url, {'q': 'pendências'})
            self.assertContains(response, 'value="pendências"')
            self.assertContains(response, 'Limpar filtros')

    def test_category_navigation_respects_editorial_order(self):
        self.client.force_login(self.worker)
        first = Category.objects.create(name='Z início', slug='inicio', sort_order=10)
        last = Category.objects.create(name='A depois', slug='depois', sort_order=20)
        for category in (first, last):
            Article.objects.create(category=category, title=category.name, slug=category.slug, status='PUBLISHED')
        response = self.client.get(reverse('ajuda:index'))
        self.assertEqual([category.pk for category in response.context['categories']], [self.general.pk, first.pk, last.pk])
