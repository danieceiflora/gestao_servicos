from django.contrib import admin
from django.contrib.auth.models import Permission
from django.test import TestCase
from django.urls import reverse

from ajuda.models import Article, Category
from services.models import User


class HelpAdminTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        category = Category.objects.create(name='Geral', slug='geral')
        cls.article = Article.objects.create(category=category, title='Tutorial', slug='tutorial')
        cls.staff = User.objects.create_user(username='admin-help', is_staff=True, role=User.Roles.MANAGER)

    def test_articles_and_categories_are_registered(self):
        self.assertIn(Article, admin.site._registry)
        self.assertIn(Category, admin.site._registry)

    def test_manager_staff_without_documentation_permission_cannot_edit(self):
        self.client.force_login(self.staff)
        response = self.client.get(f'/admin/ajuda/article/{self.article.pk}/change/')
        self.assertEqual(response.status_code, 403)

    def test_editor_can_manage_steps_and_screen_links_with_article_permission(self):
        self.staff.user_permissions.add(Permission.objects.get(content_type__app_label='ajuda', codename='change_article'))
        self.client.force_login(User.objects.get(pk=self.staff.pk))
        response = self.client.get(f'/admin/ajuda/article/{self.article.pk}/change/')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'steps-TOTAL_FORMS')
        self.assertContains(response, 'context_links-TOTAL_FORMS')
        self.assertNotContains(response, 'name="source_hash"')

    def test_help_reader_cannot_post_changes(self):
        viewer = User.objects.create_user(username='help-viewer', is_staff=True)
        viewer.user_permissions.add(Permission.objects.get(content_type__app_label='ajuda', codename='view_article'))
        self.client.force_login(viewer)
        url = f'/admin/ajuda/article/{self.article.pk}/change/'
        self.assertEqual(self.client.get(url).status_code, 200)
        self.assertEqual(self.client.post(url, {'title': 'Ataque'}).status_code, 403)
        self.article.refresh_from_db()
        self.assertEqual(self.article.title, 'Tutorial')
