from django import forms

from services.models import Sale, ServiceOrderTask

from .models import ProductionSettings
from .services import BLOCKED_SALE_TRIGGERS, PRODUCTION_TASK_TYPES

CHECKBOX_CLASS = 'h-4 w-4 rounded border-slate-300 text-blue-600 focus:ring-blue-500'
SELECT_CLASS = (
    'w-full px-4 py-3 rounded-xl border border-slate-200 focus:ring-2 '
    'focus:ring-blue-500 focus:border-blue-500 outline-none transition-all text-sm'
)


def _sale_trigger_choices():
    """Rascunho e Cancelado ficam fora.

    Enquanto a venda é rascunho suas linhas ainda são apagadas e recriadas
    (`views_pos._save_cart`), e a ordem de produção perderia o vínculo com os
    itens pelo `source_key`.
    """
    return [c for c in Sale.Status.choices if c[0] not in BLOCKED_SALE_TRIGGERS]


def _task_trigger_choices():
    return [
        c for c in ServiceOrderTask.TaskStatus.choices
        if c[0] != ServiceOrderTask.TaskStatus.CANCELADO
    ]


class ProductionSettingsForm(forms.ModelForm):
    sale_trigger_statuses = forms.MultipleChoiceField(
        required=False, widget=forms.CheckboxSelectMultiple,
        label=ProductionSettings._meta.get_field('sale_trigger_statuses').verbose_name,
        help_text=ProductionSettings._meta.get_field('sale_trigger_statuses').help_text,
    )
    task_trigger_statuses = forms.MultipleChoiceField(
        required=False, widget=forms.CheckboxSelectMultiple,
        label=ProductionSettings._meta.get_field('task_trigger_statuses').verbose_name,
        help_text=ProductionSettings._meta.get_field('task_trigger_statuses').help_text,
    )

    class Meta:
        model = ProductionSettings
        fields = [
            'enabled', 'sale_trigger_statuses', 'task_trigger_statuses',
            'require_task_approval', 'skip_sale_linked_to_order', 'item_scope',
            'default_delivery_mode_sale', 'default_delivery_mode_order',
        ]
        widgets = {
            'enabled': forms.CheckboxInput(attrs={'class': CHECKBOX_CLASS}),
            'require_task_approval': forms.CheckboxInput(attrs={'class': CHECKBOX_CLASS}),
            'skip_sale_linked_to_order': forms.CheckboxInput(attrs={'class': CHECKBOX_CLASS}),
            'item_scope': forms.Select(attrs={'class': SELECT_CLASS}),
            'default_delivery_mode_sale': forms.Select(attrs={'class': SELECT_CLASS}),
            'default_delivery_mode_order': forms.Select(attrs={'class': SELECT_CLASS}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['sale_trigger_statuses'].choices = _sale_trigger_choices()
        self.fields['task_trigger_statuses'].choices = _task_trigger_choices()
        self.task_type_labels = ', '.join(
            str(ServiceOrderTask.TaskType(t).label) for t in PRODUCTION_TASK_TYPES
        )
        if self.instance and self.instance.pk:
            self.initial.setdefault('sale_trigger_statuses', self.instance.sale_trigger_statuses or [])
            self.initial.setdefault('task_trigger_statuses', self.instance.task_trigger_statuses or [])

    def clean_sale_trigger_statuses(self):
        return list(self.cleaned_data.get('sale_trigger_statuses') or [])

    def clean_task_trigger_statuses(self):
        return list(self.cleaned_data.get('task_trigger_statuses') or [])

    def clean(self):
        data = super().clean()
        if data.get('enabled') and not (
            data.get('sale_trigger_statuses') or data.get('task_trigger_statuses')
        ):
            raise forms.ValidationError(
                'Escolha ao menos um status de venda ou de etapa de OS, senão '
                'nenhuma ordem de produção será criada.'
            )
        return data


class DeliverForm(forms.Form):
    """Registro de saída. Os campos relevantes variam com o destino da OP."""

    delivered_to = forms.CharField(
        required=False, max_length=255, label='Entregue a',
        widget=forms.TextInput(attrs={'class': SELECT_CLASS, 'autocomplete': 'off'}),
    )
    carrier = forms.CharField(
        required=False, max_length=120, label='Transportadora',
        widget=forms.TextInput(attrs={'class': SELECT_CLASS, 'autocomplete': 'off'}),
    )
    tracking_code = forms.CharField(
        required=False, max_length=120, label='Código de rastreio',
        widget=forms.TextInput(attrs={'class': SELECT_CLASS, 'autocomplete': 'off'}),
    )
    delivery_notes = forms.CharField(
        required=False, label='Observações',
        widget=forms.Textarea(attrs={'class': SELECT_CLASS, 'rows': 2}),
    )
