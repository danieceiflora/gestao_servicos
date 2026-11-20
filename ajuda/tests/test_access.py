from django.contrib.auth.models import AnonymousUser, Permission
from django.test import TestCase

from ajuda.models import Article, Category
from services.models import User


class HelpAccessTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.manager = User.objects.create_user(username='help-manager', role=User.Roles.MANAGER)
        cls.worker = User.objects.create_user(username='help-worker')
        cls.staff = User.objects.create_user(username='help-editor', is_staff=True)
        for module in Category.Module.values:
            category = Category.objects.create(name=module, slug=module, module=module)
            Article.objects.create(category=category, title=module, slug=module, status='PUBLISHED')
        Article.objects.create(category=Category.objects.get(slug='geral'), title='Rascunho secreto', slug='draft')
        Article.objects.create(category=Category.objects.get(slug='geral'), title='Arquivado secreto', slug='archived', status='ARCHIVED')
        Article.objects.create(category=Category.objects.get(slug='geral'), title='Gestão restrita', slug='manager-only', status='PUBLISHED', audience='MANAGERS')
        Article.objects.create(category=Category.objects.get(slug='geral'), title='Somente colaborador', slug='worker-only', status='PUBLISHED', audience='COLLABORATORS')

    def visible_slugs(self, user):
        from ajuda.access import visible_articles
        return set(visible_articles(user).values_list('slug', flat=True))

    def test_anonymous_sees_no_content(self):
        self.assertEqual(self.visible_slugs(AnonymousUser()), set())

    def test_collaborator_only_sees_general_and_technician_guides(self):
        self.assertEqual(self.visible_slugs(self.worker), {'geral', 'tecnico', 'worker-only'})

    def test_manager_sees_business_guides_but_not_drafts(self):
        visible = self.visible_slugs(self.manager)
        self.assertIn('financeiro', visible)
        self.assertIn('producao', visible)
        self.assertIn('manager-only', visible)
        self.assertNotIn('draft', visible)
        self.assertNotIn('archived', visible)
        self.assertNotIn('worker-only', visible)

    def test_pos_operator_does_not_gain_finance_or_settings_guides(self):
        self.worker.user_permissions.add(Permission.objects.get(content_type__app_label='services', codename='operate_pos'))
        user = User.objects.get(pk=self.worker.pk)
        self.assertEqual(self.visible_slugs(user), {'geral', 'tecnico', 'pdv', 'worker-only'})

    def test_production_viewer_sees_production_not_finance(self):
        self.worker.user_permissions.add(Permission.objects.get(content_type__app_label='producao', codename='view_productionorder'))
        user = User.objects.get(pk=self.worker.pk)
        self.assertIn('producao', self.visible_slugs(user))
        self.assertNotIn('financeiro', self.visible_slugs(user))

    def test_staff_does_not_implicitly_gain_documentation_edit_permission(self):
        from ajuda.access import can_manage_help
        self.assertFalse(can_manage_help(self.staff))
        self.staff.user_permissions.add(Permission.objects.get(content_type__app_label='ajuda', codename='change_article'))
        self.assertTrue(can_manage_help(User.objects.get(pk=self.staff.pk)))

    def test_unknown_module_fails_closed(self):
        category = Category.objects.create(name='Desconhecido', slug='unknown', module='unknown')
        Article.objects.create(category=category, title='Desconhecido', slug='unknown', status='PUBLISHED')
        self.assertNotIn('unknown', self.visible_slugs(self.manager))

    def test_order_reader_sees_order_guides(self):
        self.worker.user_permissions.add(Permission.objects.get(content_type__app_label='services', codename='view_serviceorder'))
        self.assertIn('os', self.visible_slugs(User.objects.get(pk=self.worker.pk)))

    def test_inactive_user_cannot_read_published_articles(self):
        self.worker.is_active = False
        self.assertEqual(self.visible_slugs(self.worker), set())
