import json
from types import SimpleNamespace
from unittest.mock import Mock, patch

from django.contrib.messages.storage.fallback import FallbackStorage
from django.core.files.uploadedfile import SimpleUploadedFile
from django.template.loader import render_to_string
from django.test import RequestFactory, SimpleTestCase

from .template_editor import TemplateEditForm, initial_state
from .views import MetaCloudAPI, whatsapp_template_edit, whatsapp_template_list


def sample_template():
    return {'id': '123', 'name': 'aviso', 'category': 'UTILITY', 'status': 'APPROVED', 'language': 'pt_BR',
            'components': [
                {'type': 'HEADER', 'format': 'TEXT', 'text': 'Olá {{1}}', 'example': {'header_text': ['Ana']}},
                {'type': 'BODY', 'text': 'Pedido {{1}} e {{1}}', 'example': {'body_text': [['42']]}},
                {'type': 'FOOTER', 'text': 'Obrigado'},
                {'type': 'BUTTONS', 'buttons': [{'type': 'URL', 'text': 'Abrir', 'url': 'https://example.com/{{1}}', 'example': ['https://example.com/42']}]},
            ]}


def post_data(template=None, **changes):
    state = initial_state(template or sample_template())
    state.update(changes)
    return {key: json.dumps(value) if key in ('buttons', 'body_examples') else value for key, value in state.items()}


class TemplateComponentTests(SimpleTestCase):
    def build(self, template=None, files=None, **changes):
        template = template or sample_template()
        form = TemplateEditForm(post_data(template, **changes), files, template=template)
        self.assertTrue(form.is_valid(), form.errors)
        api = Mock()
        api.upload_header_media.return_value = 'new-handle'
        return form.components(api), api

    def test_text_examples_repeated_variables_and_footer(self):
        components, _ = self.build(header_text='Novo {{1}}', header_example='Bia', body_examples=['55'])
        self.assertEqual(components[0]['text'], 'Novo {{1}}')
        self.assertEqual(components[0]['example'], {'header_text': ['Bia']})
        self.assertEqual(components[1]['example'], {'body_text': [['55']]})
        self.assertEqual(components[2], sample_template()['components'][2])

    def test_header_and_buttons_can_be_removed(self):
        components, _ = self.build(header_type='NONE', buttons=[])
        self.assertEqual([c['type'] for c in components], ['BODY', 'FOOTER'])

    def test_header_added_to_template_without_header(self):
        template = sample_template()
        template['components'].pop(0)
        components, _ = self.build(template, header_type='TEXT', header_text='Novo')
        self.assertEqual(components[0], {'type': 'HEADER', 'format': 'TEXT', 'text': 'Novo'})

    def test_upload_each_media_type(self):
        for kind, mime, name in [('IMAGE', 'image/png', 'sample.png'), ('VIDEO', 'video/mp4', 'sample.mp4'), ('DOCUMENT', 'application/pdf', 'sample.pdf')]:
            with self.subTest(kind=kind):
                components, api = self.build(header_type=kind, files={'header_file': SimpleUploadedFile(name, b'content', mime)})
                self.assertEqual(components[0], {'type': 'HEADER', 'format': kind, 'example': {'header_handle': ['new-handle']}})
                api.upload_header_media.assert_called_once()

    def test_existing_media_preserved_without_upload(self):
        template = sample_template()
        template['components'][0] = {'type': 'HEADER', 'format': 'IMAGE', 'example': {'header_handle': ['old']}}
        components, api = self.build(template)
        self.assertEqual(components[0], template['components'][0])
        api.upload_header_media.assert_not_called()

    def test_new_media_requires_upload_and_matching_mime(self):
        for files in [None, {'header_file': SimpleUploadedFile('bad.txt', b'bad', 'text/plain')}]:
            form = TemplateEditForm(post_data(header_type='IMAGE'), files, template=sample_template())
            self.assertFalse(form.is_valid())
            self.assertIn('header_file', form.errors)

    def test_buttons_reorder_and_replace(self):
        buttons = [{'type': 'PHONE_NUMBER', 'text': 'Ligar', 'phone_number': '+5511999999999'},
                   {'type': 'URL', 'text': 'Site', 'url': 'https://example.com'},
                   {'type': 'QUICK_REPLY', 'text': 'Confirmar'}]
        components, _ = self.build(buttons=buttons)
        self.assertEqual(components[-1]['buttons'], buttons)

    def test_invalid_buttons(self):
        variants = [
            [{'type': 'OTP', 'text': 'x'}],
            [{'type': 'URL', 'text': 'Site', 'url': 'javascript:alert(1)'}],
            [{'type': 'URL', 'text': 'Site', 'url': 'https://example.com/{{1}}'}],
            [{'type': 'PHONE_NUMBER', 'text': 'Ligar', 'phone_number': '123'}],
            [{'type': 'QUICK_REPLY', 'text': 'x' * 26}],
            [{'type': 'QUICK_REPLY', 'text': 'x'}] * 11,
            [{'type': 'URL', 'text': 'x', 'url': 'https://example.com'}] * 3,
            [{'type': 'QUICK_REPLY', 'text': 'a'}, {'type': 'URL', 'text': 'b', 'url': 'https://example.com'}, {'type': 'QUICK_REPLY', 'text': 'c'}],
        ]
        for buttons in variants:
            with self.subTest(buttons=buttons):
                form = TemplateEditForm(post_data(buttons=buttons), template=sample_template())
                self.assertFalse(form.is_valid())
                self.assertIn('buttons', form.errors)

    def test_special_components_preserved_despite_forged_post(self):
        template = sample_template()
        template['components'][0] = {'type': 'HEADER', 'format': 'LOCATION'}
        template['components'][-1]['buttons'].append({'type': 'COPY_CODE', 'example': 'PROMO'})
        template['components'].append({'type': 'LIMITED_TIME_OFFER', 'limited_time_offer': {'text': 'Oferta'}})
        components, _ = self.build(template, header_type='NONE', buttons=[])
        self.assertEqual(components, template['components'])

    def test_authentication_components_preserved(self):
        template = sample_template()
        template['category'] = 'AUTHENTICATION'
        components, _ = self.build(template, body_text='Alterado', header_type='NONE', buttons=[])
        self.assertEqual(components, template['components'])

    def test_named_parameters(self):
        template = sample_template()
        template['parameter_format'] = 'NAMED'
        components, _ = self.build(template, header_text='Olá {{nome}}', header_example='Ana',
                                   body_text='Pedido {{pedido}}', body_examples=['42'])
        self.assertEqual(components[0]['example']['header_text_named_params'], [{'param_name': 'nome', 'example': 'Ana'}])
        self.assertEqual(components[1]['example']['body_text_named_params'], [{'param_name': 'pedido', 'example': '42'}])

    def test_invalid_examples_or_nonsequential_variables(self):
        for changes in [{'body_examples': []}, {'body_text': 'Pedido {{2}}'}, {'header_example': ''}]:
            form = TemplateEditForm(post_data(**changes), template=sample_template())
            self.assertFalse(form.is_valid())


class TemplateViewTests(SimpleTestCase):
    def setUp(self):
        self.factory = RequestFactory()
        config_patch = patch('integracoes.views.SystemConfig.load', return_value=SimpleNamespace(
            meta_waba_id='waba', meta_access_token='token', meta_phone_number_id='phone'))
        config_patch.start()
        self.addCleanup(config_patch.stop)
        api_patch = patch('integracoes.views.MetaCloudAPI')
        self.api = api_patch.start().return_value
        self.addCleanup(api_patch.stop)
        self.api.get_template.return_value = sample_template()

    def request(self, method='get', data=None, staff=True):
        request = getattr(self.factory, method)('/integracoes/whatsapp/modelos/', data or {})
        request.user = SimpleNamespace(is_authenticated=True, is_staff=staff)
        request.session = {}
        request._messages = FallbackStorage(request)
        return request

    def context(self, view, request, *args):
        with patch('integracoes.views.render') as render:
            view(request, *args)
        return render.call_args.args[2]

    def test_failed_update_keeps_inputs_and_allows_retry(self):
        for error in ['Falha de rede', {'message': 'Recusado'}]:
            self.api.update_template.return_value = {'error': error}
            request = self.request('post', post_data(header_text='Modificado'))
            context = self.context(whatsapp_template_edit, request, '123')
            self.assertEqual(context['editor_state']['header_text'], 'Modificado')
            self.assertTrue(context['retry'])
            self.assertIn(str(error if isinstance(error, str) else error['message']), str(list(request._messages)[0]))

    def test_success_omits_unchanged_category(self):
        self.api.update_template.return_value = {'success': True}
        response = whatsapp_template_edit(self.request('post', post_data()), '123')
        self.assertEqual(response.status_code, 302)
        self.assertIsNone(self.api.update_template.call_args.args[1])

    def test_invalid_post_does_not_upload_or_update(self):
        context = self.context(whatsapp_template_edit, self.request('post', post_data(buttons=[{'type': 'URL', 'text': ''}])), '123')
        self.assertTrue(context['form'].errors)
        self.api.upload_header_media.assert_not_called()
        self.api.update_template.assert_not_called()

    def test_get_error_string_redirects(self):
        self.api.get_template.return_value = {'error': 'Timeout'}
        self.assertEqual(whatsapp_template_edit(self.request(), '123').status_code, 302)

    def test_search_before_pagination_and_stable_order(self):
        self.api.get_templates.return_value = {'data': [dict(sample_template(), id=str(i), name=f'aviso_{i:03}') for i in reversed(range(45))]}
        context = self.context(whatsapp_template_list, self.request(data={'q': 'aprovado', 'page': 2}))
        self.assertEqual(context['page_obj'].paginator.count, 45)
        self.assertEqual(len(context['templates']), 20)
        self.assertEqual(context['templates'][0]['name'], 'aviso_020')
        context = self.context(whatsapp_template_list, self.request(data={'q': 'aviso_044'}))
        self.assertEqual(context['page_obj'].paginator.count, 1)

    def test_search_fields_labels_and_invalid_pages(self):
        self.api.get_templates.return_value = {'data': [sample_template()]}
        for query in ['123', 'PT_br', 'utilitario', 'APROVADO', 'aviso']:
            context = self.context(whatsapp_template_list, self.request(data={'q': query, 'page': 'bad'}))
            self.assertEqual(context['page_obj'].paginator.count, 1)
        context = self.context(whatsapp_template_list, self.request(data={'q': 'missing', 'page': '999'}))
        self.assertEqual(context['page_obj'].paginator.count, 0)

    def test_meta_error_distinct_from_empty_list(self):
        self.api.get_templates.return_value = {'error': {'message': 'Offline'}, 'data': []}
        context = self.context(whatsapp_template_list, self.request())
        self.assertTrue(context['sync_error'])
        self.assertIsNone(context['last_sync'])

    def test_staff_required(self):
        for view, args in [(whatsapp_template_list, ()), (whatsapp_template_edit, ('123',))]:
            self.assertEqual(view(self.request(staff=False), *args).status_code, 302)
        self.api.get_template.assert_not_called()
        self.api.get_templates.assert_not_called()

    def test_templates_render_and_escape_user_content(self):
        context = self.context(whatsapp_template_edit, self.request(), '123')
        context['editor_state']['header_text'] = '</script><script>alert(1)</script>'
        html = render_to_string('integracoes/whatsapp_template_edit.html', context)
        self.assertNotIn('</script><script>alert(1)</script>', html)
        self.assertIn('multipart/form-data', html)
        self.api.get_templates.return_value = {'data': [dict(sample_template(), id=str(i)) for i in range(21)]}
        context = self.context(whatsapp_template_list, self.request(data={'q': 'aviso'}))
        html = render_to_string('integracoes/whatsapp_template_list.html', context)
        self.assertIn('q=aviso&amp;page=2', html)


class MetaTemplateTransportTests(SimpleTestCase):
    @patch('integracoes.views.requests.get')
    def test_all_pages_and_error_on_later_page(self, get):
        first = Mock()
        first.json.return_value = {'data': [{'id': str(i)} for i in range(200)], 'paging': {'next': 'https://graph.facebook.com/next'}}
        second = Mock()
        second.json.return_value = {'data': [{'id': '201'}]}
        get.side_effect = [first, second]
        self.assertEqual(len(MetaCloudAPI('waba', 'token').get_templates()['data']), 201)
        second.json.return_value = {'error': {'message': 'Invalid token'}}
        get.side_effect = [first, second]
        result = MetaCloudAPI('waba', 'token').get_templates()
        self.assertEqual(result['error']['message'], 'Invalid token')
        self.assertEqual(result['data'], [])

    @patch('integracoes.views.requests.post')
    def test_update_payload_excludes_unchanged_category(self, post):
        MetaCloudAPI('waba', 'token').update_template('123', None, [{'type': 'BODY', 'text': 'Olá'}])
        self.assertEqual(post.call_args.kwargs['json'], {'components': [{'type': 'BODY', 'text': 'Olá'}]})
