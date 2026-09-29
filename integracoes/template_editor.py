"""Validation and component assembly for the Meta template editor."""
import copy
import re

from django import forms
from django.core.exceptions import ValidationError
from django.core.validators import URLValidator


HEADER_TYPES = ('NONE', 'TEXT', 'IMAGE', 'VIDEO', 'DOCUMENT')
BUTTON_TYPES = ('URL', 'PHONE_NUMBER', 'QUICK_REPLY')


def error_message(error):
    if isinstance(error, dict):
        return error.get('error_user_msg') or error.get('message') or 'Erro desconhecido'
    return str(error)


def variables(text):
    keys = list(dict.fromkeys(re.findall(r'\{\{([^{}]+)\}\}', text)))
    return sorted(keys, key=int) if keys and all(k.isdigit() for k in keys) else keys


def initial_state(template):
    components = {c['type']: c for c in template.get('components', [])}
    header = components.get('HEADER', {})
    body = components.get('BODY', {})
    example = body.get('example', {})
    named = template.get('parameter_format') == 'NAMED'
    named_examples = {p['param_name']: p.get('example', '') for p in example.get('body_text_named_params', [])}
    body_examples = ([named_examples.get(key, '') for key in variables(body.get('text', ''))]
                     if named else (example.get('body_text') or [[]])[0])
    header_examples = header.get('example', {})
    header_example = ((header_examples.get('header_text_named_params') or [{}])[0].get('example', '')
                      if named else (header_examples.get('header_text') or [''])[0])
    return {
        'category': template.get('category', 'UTILITY'),
        'header_type': header.get('format', 'NONE'),
        'header_text': header.get('text', ''),
        'header_example': header_example,
        'body_text': body.get('text', ''),
        'body_examples': body_examples,
        'buttons': copy.deepcopy(components.get('BUTTONS', {}).get('buttons', [])),
    }


class TemplateEditForm(forms.Form):
    category = forms.ChoiceField(choices=[(v, v) for v in ('MARKETING', 'UTILITY', 'AUTHENTICATION')])
    header_type = forms.CharField()
    header_text = forms.CharField(required=False, max_length=60)
    header_example = forms.CharField(required=False)
    header_file = forms.FileField(required=False)
    body_text = forms.CharField(required=False, max_length=1024)
    body_examples = forms.JSONField(required=False)
    buttons = forms.JSONField(required=False)

    def __init__(self, *args, template, **kwargs):
        super().__init__(*args, **kwargs)
        for key, label in {'category': 'Categoria', 'header_type': 'Tipo de cabeçalho',
                           'header_text': 'Texto do cabeçalho', 'header_example': 'Exemplo do cabeçalho',
                           'header_file': 'Arquivo de exemplo', 'body_text': 'Conteúdo da mensagem',
                           'body_examples': 'Exemplos das variáveis', 'buttons': 'Botões'}.items():
            self.fields[key].label = label
        self.template = template
        self.original = initial_state(template)
        self.authentication = template.get('category') == 'AUTHENTICATION'
        self.header_locked = self.authentication or self.original['header_type'] not in HEADER_TYPES
        self.buttons_locked = self.authentication or any(b.get('type') not in BUTTON_TYPES for b in self.original['buttons'])
        for field, locked in [('header_type', self.header_locked), ('header_text', self.header_locked),
                              ('header_example', self.header_locked), ('buttons', self.buttons_locked),
                              ('body_text', self.authentication), ('body_examples', self.authentication),
                              ('category', self.authentication or template.get('status') == 'APPROVED')]:
            if locked:
                self.fields[field].disabled = True
                self.fields[field].initial = self.original[field]

    def clean(self):
        data = super().clean()
        if not self.authentication and 'body_text' in data:
            if not data['body_text']:
                self.add_error('body_text', 'Informe o conteúdo da mensagem.')
            self.validate_examples('body_text', data['body_text'], data.get('body_examples') or [])
        kind = data.get('header_type')
        if not self.header_locked:
            if kind not in HEADER_TYPES:
                self.add_error('header_type', 'Tipo de cabeçalho inválido.')
            elif kind == 'TEXT' and 'header_text' in data:
                if not data['header_text']:
                    self.add_error('header_text', 'Informe o texto do cabeçalho.')
                self.validate_examples('header_text', data['header_text'], [data.get('header_example', '')], header=True)
            elif kind in ('IMAGE', 'VIDEO', 'DOCUMENT'):
                file = data.get('header_file')
                if not file and kind != self.original['header_type']:
                    self.add_error('header_file', 'Envie um arquivo de exemplo para o novo tipo de cabeçalho.')
                if file:
                    allowed = {'IMAGE': ('image/jpeg', 'image/png'), 'VIDEO': ('video/mp4', 'video/3gpp'), 'DOCUMENT': ('application/pdf',)}
                    limit = {'IMAGE': 5, 'VIDEO': 16, 'DOCUMENT': 100}[kind] * 1024 * 1024
                    if file.content_type not in allowed[kind] or file.size > limit:
                        self.add_error('header_file', 'Formato ou tamanho de arquivo inválido para este cabeçalho.')
        if not self.buttons_locked and 'buttons' in data:
            try:
                data['buttons'] = self.validate_buttons(data.get('buttons') or [])
            except ValidationError as exc:
                self.add_error('buttons', exc)
        return data

    def validate_examples(self, field, text, examples, header=False):
        keys = variables(text)
        named = self.template.get('parameter_format') == 'NAMED'
        valid = (all(re.fullmatch(r'[a-z][a-z0-9_]*', key) for key in keys) if named
                 else keys == [str(n) for n in range(1, len(keys) + 1)])
        if not valid or (header and len(keys) > 1):
            self.add_error(field, 'Use variáveis válidas e sequenciais; o cabeçalho aceita apenas uma variável.')
        if keys and (not isinstance(examples, list) or len(examples) != len(keys)
                     or any(not isinstance(v, str) or not v.strip() for v in examples)):
            self.add_error(field, 'Preencha um exemplo para cada variável.')

    @staticmethod
    def validate_buttons(buttons):
        if not isinstance(buttons, list) or len(buttons) > 10:
            raise ValidationError('Informe no máximo 10 botões.')
        cleaned = []
        for button in buttons:
            if not isinstance(button, dict) or button.get('type') not in BUTTON_TYPES:
                raise ValidationError('Tipo de botão inválido.')
            text = button.get('text', '')
            if not isinstance(text, str) or not text.strip() or len(text) > 25:
                raise ValidationError('Cada botão precisa de um texto de até 25 caracteres.')
            item = {'type': button['type'], 'text': text.strip()}
            if item['type'] == 'URL':
                url = button.get('url', '')
                if not isinstance(url, str) or len(url) > 2000:
                    raise ValidationError('URL inválida.')
                URLValidator(schemes=['http', 'https'])(url.replace('{{1}}', 'exemplo'))
                if variables(url):
                    if variables(url) != ['1'] or not url.endswith('{{1}}') or url.count('{{1}}') != 1:
                        raise ValidationError('A URL dinâmica deve terminar com uma única variável {{1}}.')
                    examples = button.get('example', [])
                    if not isinstance(examples, list) or len(examples) != 1 or not isinstance(examples[0], str):
                        raise ValidationError('Informe a URL completa de exemplo do botão.')
                    URLValidator(schemes=['http', 'https'])(examples[0])
                    if not examples[0].startswith(url[:-5]) or examples[0] == url[:-5]:
                        raise ValidationError('O exemplo deve corresponder à URL com um valor no lugar da variável.')
                    item['example'] = examples
                item['url'] = url
            elif item['type'] == 'PHONE_NUMBER':
                phone = button.get('phone_number', '')
                if not isinstance(phone, str) or not re.fullmatch(r'\+[1-9]\d{6,14}', phone):
                    raise ValidationError('Informe o telefone com +, código do país e DDD, somente dígitos.')
                item['phone_number'] = phone
            cleaned.append(item)
        types = [b['type'] for b in cleaned]
        if types.count('URL') > 2 or types.count('PHONE_NUMBER') > 1:
            raise ValidationError('Use até dois botões de URL e um de telefone.')
        groups = [t == 'QUICK_REPLY' for t in types]
        if sum(a != b for a, b in zip(groups, groups[1:])) > 1:
            raise ValidationError('Mantenha os botões de resposta rápida juntos, antes ou depois dos demais.')
        return cleaned

    def components(self, api):
        """Call only after validation; upload only after all fields have passed."""
        data = self.cleaned_data
        original = {c['type']: copy.deepcopy(c) for c in self.template.get('components', [])}
        replacements = {}
        named = self.template.get('parameter_format') == 'NAMED'
        if not self.authentication:
            body = original.get('BODY', {'type': 'BODY'})
            body['text'] = data['body_text']
            body.pop('example', None)
            keys = variables(body['text'])
            if keys:
                body['example'] = ({'body_text_named_params': [dict(param_name=k, example=v) for k, v in zip(keys, data['body_examples'])]}
                                   if named else {'body_text': [data['body_examples']]})
            replacements['BODY'] = body
        if not self.header_locked:
            kind = data['header_type']
            header = None if kind == 'NONE' else {'type': 'HEADER', 'format': kind}
            if kind == 'TEXT':
                header['text'] = data['header_text']
                keys = variables(header['text'])
                if keys:
                    header['example'] = ({'header_text_named_params': [dict(param_name=keys[0], example=data['header_example'])]}
                                         if named else {'header_text': [data['header_example']]})
            elif kind in ('IMAGE', 'VIDEO', 'DOCUMENT'):
                if data.get('header_file'):
                    handle = api.upload_header_media(data['header_file'])
                    if not handle:
                        raise ValidationError('Não foi possível enviar a mídia à Meta. Selecione o arquivo novamente e tente outra vez.')
                    header['example'] = {'header_handle': [handle]}
                else:
                    header = original['HEADER']
            replacements['HEADER'] = header
        if not self.buttons_locked:
            replacements['BUTTONS'] = {'type': 'BUTTONS', 'buttons': data['buttons']} if data['buttons'] else None
        # Preserve unknown components and the original relative order.
        result = []
        for component in self.template.get('components', []):
            value = replacements.pop(component['type'], component)
            if value is not None:
                result.append(value)
        if replacements.get('HEADER'):
            result.insert(0, replacements['HEADER'])
        for kind in ('BODY', 'BUTTONS'):
            if replacements.get(kind):
                result.append(replacements[kind])
        return result
