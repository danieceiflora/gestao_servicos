from django import forms

from .models import SaleSettings


class PosSettingsForm(forms.ModelForm):
    class Meta:
        model = SaleSettings
        fields = ['pos_default_client']
        widgets = {'pos_default_client': forms.Select(attrs={'class': 'w-full rounded-xl border p-3'})}

    def clean_pos_default_client(self):
        client = self.cleaned_data.get('pos_default_client')
        if client:
            document = ''.join(filter(str.isdigit, client.document or ''))
            expected = 11 if client.client_type == 'PF' else 14
            if not client.name.strip() or len(document) != expected:
                raise forms.ValidationError('Selecione um cliente com nome e CPF/CNPJ preenchidos corretamente.')
        return client
