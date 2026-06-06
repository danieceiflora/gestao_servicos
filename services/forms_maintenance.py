from django import forms
from .models import (
    AssetCategory, Asset, MaintenanceContract, MaintenanceVisit,
    Professional, Property, Client,
)

DAYS_CHOICES = [
    (0, 'Segunda'), (1, 'Terça'), (2, 'Quarta'),
    (3, 'Quinta'), (4, 'Sexta'), (5, 'Sábado'), (6, 'Domingo'),
]

INPUT_CLASS = 'flex w-full rounded-md border border-slate-200 bg-white px-3 py-2 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-slate-950 focus-visible:ring-offset-2 h-10'
TEXTAREA_CLASS = 'flex w-full rounded-md border border-slate-200 bg-white px-3 py-2 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-slate-950 focus-visible:ring-offset-2 min-h-[80px]'


class AssetCategoryForm(forms.ModelForm):
    class Meta:
        model = AssetCategory
        fields = ['name', 'icon', 'is_active']
        widgets = {
            'name': forms.TextInput(attrs={'class': INPUT_CLASS, 'placeholder': 'Ex: Piscina, Ar-Condicionado'}),
            'icon': forms.TextInput(attrs={'class': INPUT_CLASS, 'placeholder': 'Ex: droplets, wind, zap'}),
        }


class AssetForm(forms.ModelForm):
    client = forms.ModelChoiceField(
        queryset=Client.objects.all().order_by('name'),
        label='Cliente',
        widget=forms.Select(attrs={'class': INPUT_CLASS, 'id': 'id_client_asset'}),
        required=True,
    )

    class Meta:
        model = Asset
        fields = ['category', 'name', 'brand', 'model_name', 'serial_number', 'notes', 'is_active']
        widgets = {
            'category': forms.Select(attrs={'class': INPUT_CLASS}),
            'name': forms.TextInput(attrs={'class': INPUT_CLASS, 'placeholder': 'Ex: Piscina Principal, Split Sala'}),
            'brand': forms.TextInput(attrs={'class': INPUT_CLASS, 'placeholder': 'Ex: Hayward'}),
            'model_name': forms.TextInput(attrs={'class': INPUT_CLASS, 'placeholder': 'Ex: Super Pump VS'}),
            'serial_number': forms.TextInput(attrs={'class': INPUT_CLASS}),
            'notes': forms.Textarea(attrs={'class': TEXTAREA_CLASS, 'rows': 3}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['client_property'] = forms.ModelChoiceField(
            queryset=Property.objects.none(),
            label='Imóvel',
            widget=forms.Select(attrs={'class': INPUT_CLASS, 'id': 'id_property_asset'}),
        )
        # Explicitly set initial so Django doesn't try getattr(instance, 'client_property')
        # on the empty Asset() instance created by ModelForm (which raises RelatedObjectDoesNotExist).
        self.initial.setdefault('client_property', None)

        if self.instance and self.instance.pk and self.instance.client_property_id:
            prop = self.instance.client_property
            self.initial['client'] = prop.client
            self.initial['client_property'] = prop
            self.fields['client_property'].queryset = Property.objects.filter(client=prop.client)
        elif self.data.get('client'):
            try:
                client_id = self.data['client']
                self.fields['client_property'].queryset = Property.objects.filter(client_id=client_id)
            except (ValueError, TypeError):
                pass

    def save(self, commit=True):
        instance = super().save(commit=False)
        instance.client_property = self.cleaned_data['client_property']
        if commit:
            instance.save()
        return instance


class MaintenanceContractForm(forms.ModelForm):
    visit_days = forms.MultipleChoiceField(
        choices=DAYS_CHOICES,
        widget=forms.CheckboxSelectMultiple(),
        required=False,
        label='Dias de Visita',
        help_text='Selecione os dias para frequências semanais ou quinzenais.',
    )

    class Meta:
        model = MaintenanceContract
        fields = [
            'asset', 'primary_technician', 'monthly_value', 'commission_rate',
            'frequency', 'visit_days', 'description', 'start_date', 'end_date', 'status',
        ]
        widgets = {
            'asset': forms.Select(attrs={'class': INPUT_CLASS}),
            'primary_technician': forms.Select(attrs={'class': INPUT_CLASS}),
            'monthly_value': forms.NumberInput(attrs={'class': INPUT_CLASS, 'step': '0.01', 'min': '0'}),
            'commission_rate': forms.NumberInput(attrs={'class': INPUT_CLASS, 'step': '0.01', 'min': '0', 'max': '100'}),
            'frequency': forms.Select(attrs={'class': INPUT_CLASS}),
            'description': forms.Textarea(attrs={'class': TEXTAREA_CLASS, 'rows': 3}),
            'start_date': forms.DateInput(attrs={'class': INPUT_CLASS, 'type': 'date'}, format='%Y-%m-%d'),
            'end_date': forms.DateInput(attrs={'class': INPUT_CLASS, 'type': 'date'}, format='%Y-%m-%d'),
            'status': forms.Select(attrs={'class': INPUT_CLASS}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['primary_technician'].queryset = Professional.objects.filter(is_active=True).order_by('name')
        self.fields['asset'].queryset = Asset.objects.filter(is_active=True).select_related('client_property__client', 'category').order_by('name')
        if self.instance and self.instance.pk and self.instance.visit_days:
            self.initial['visit_days'] = [str(d) for d in self.instance.visit_days]

    def clean_visit_days(self):
        return [int(d) for d in self.cleaned_data.get('visit_days', [])]


class MaintenanceVisitForm(forms.ModelForm):
    class Meta:
        model = MaintenanceVisit
        fields = [
            'scheduled_date', 'executed_by', 'external_technician_name',
            'is_coverage', 'coverage_receives_commission', 'is_extra',
            'check_in_at', 'check_out_at', 'notes', 'status',
        ]
        widgets = {
            'scheduled_date': forms.DateInput(attrs={'class': INPUT_CLASS, 'type': 'date'}),
            'executed_by': forms.Select(attrs={'class': INPUT_CLASS}),
            'external_technician_name': forms.TextInput(attrs={'class': INPUT_CLASS, 'placeholder': 'Somente se não cadastrado'}),
            'check_in_at': forms.DateTimeInput(attrs={'class': INPUT_CLASS, 'type': 'datetime-local'}),
            'check_out_at': forms.DateTimeInput(attrs={'class': INPUT_CLASS, 'type': 'datetime-local'}),
            'notes': forms.Textarea(attrs={'class': TEXTAREA_CLASS, 'rows': 3}),
            'status': forms.Select(attrs={'class': INPUT_CLASS}),
        }

    def __init__(self, *args, **kwargs):
        self.contract = kwargs.pop('contract', None)
        super().__init__(*args, **kwargs)
        self.fields['executed_by'].queryset = Professional.objects.filter(is_active=True).order_by('name')
        self.fields['executed_by'].required = False
        if self.contract and not self.instance.pk:
            self.fields['executed_by'].initial = self.contract.primary_technician
