from django import forms
from django.forms import inlineformset_factory
from .models import Client, ClientPhone, ClientEmail, Property, ServiceOrder, ServiceMedia, ServiceItem, ServiceOrderTeam, Professional, ProfessionalRole, ProfessionalAvailability, ProfessionalScheduleBlock

# --- UTILS FOR MULTIPLE UPLOAD ---

class MultipleFileInput(forms.ClearableFileInput):
    allow_multiple_selected = True

class MultipleFileField(forms.FileField):
    def __init__(self, *args, **kwargs):
        kwargs.setdefault("widget", MultipleFileInput())
        super().__init__(*args, **kwargs)

    def clean(self, data, initial=None):
        single_file_clean = super().clean
        if isinstance(data, (list, tuple)):
            result = [single_file_clean(d, initial) for d in data]
        else:
            result = [single_file_clean(data, initial)]
        return result

# --- CLIENT FORMS ---

class ClientForm(forms.ModelForm):
    class Meta:
        model = Client
        fields = ['name', 'cpf']
        widgets = {
            'name': forms.TextInput(attrs={
                'placeholder': 'Nome completo do cliente',
                'class': 'w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500'
            }),
            'cpf': forms.TextInput(attrs={
                'placeholder': '000.000.000-00', 
                'class': 'cpf-mask w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500'
            }),
        }

    def clean_cpf(self):
        cpf = self.cleaned_data.get('cpf')
        if cpf:
            cpf = ''.join(filter(str.isdigit, cpf))
            if len(cpf) != 11:
                raise forms.ValidationError("CPF deve conter 11 dígitos.")
        return cpf

class ClientPhoneForm(forms.ModelForm):
    class Meta:
        model = ClientPhone
        fields = ['phone', 'is_primary']
        widgets = {
            'phone': forms.TextInput(attrs={
                'placeholder': '(00) 00000-0000',
                'class': 'w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500'
            }),
        }

    def clean_phone(self):
        phone = self.cleaned_data.get('phone')
        if phone:
            phone = ''.join(filter(str.isdigit, phone))
            if len(phone) < 10 or len(phone) > 11:
                raise forms.ValidationError("Telefone deve conter 10 ou 11 dígitos (incluindo DDD).")
        return phone

PhoneFormSet = inlineformset_factory(
    Client, ClientPhone, 
    form=ClientPhoneForm,
    extra=1, 
    can_delete=True
)

EmailFormSet = inlineformset_factory(
    Client, ClientEmail, 
    fields=['email', 'is_primary'], 
    extra=1, 
    can_delete=True
)

# --- PROPERTY FORMS ---

class PropertyForm(forms.ModelForm):
    class Meta:
        model = Property
        fields = [
            'classification', 'cep', 'address', 'number', 
            'complement', 'neighborhood', 'city', 'state',
            'latitude', 'longitude'
        ]
        widgets = {
            'classification': forms.Select(attrs={'class': 'w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500'}),
            'cep': forms.TextInput(attrs={'placeholder': '00000-000', 'onblur': 'buscarCep(this.value)', 'class': 'cep-input w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500'}),
            'address': forms.TextInput(attrs={'class': 'w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500'}),
            'number': forms.TextInput(attrs={'class': 'w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500'}),
            'complement': forms.TextInput(attrs={'class': 'w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500'}),
            'neighborhood': forms.TextInput(attrs={'class': 'w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500'}),
            'city': forms.TextInput(attrs={'class': 'w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500'}),
            'state': forms.TextInput(attrs={'class': 'w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500'}),
            'latitude': forms.TextInput(attrs={'class': 'w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500', 'placeholder': 'Ex: -23.123456'}),
            'longitude': forms.TextInput(attrs={'class': 'w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500', 'placeholder': 'Ex: -46.123456'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance and self.instance.pk:
            if self.instance.latitude is None:
                self.initial['latitude'] = ''
            if self.instance.longitude is None:
                self.initial['longitude'] = ''

PropertyFormSet = inlineformset_factory(
    Client, Property,
    form=PropertyForm,
    extra=1,
    can_delete=True
)

# --- SERVICE ORDER FORMS ---

class ServiceOrderSchedulingForm(forms.ModelForm):
    SCHEDULING_TYPES = [
        ('INSPECTION', 'Vistoria Inicial / Orçamento'),
        ('EXECUTION', 'Execução de Serviço (Direto)'),
        ('WARRANTY', 'Retorno de Garantia'),
    ]
    
    scheduling_type = forms.ChoiceField(
        choices=SCHEDULING_TYPES,
        initial='INSPECTION',
        label="Finalidade do Agendamento",
        widget=forms.RadioSelect(attrs={'class': 'flex gap-4 p-2 bg-slate-50 rounded-xl border border-slate-100'})
    )

    client = forms.ModelChoiceField(
        queryset=Client.objects.all(),
        label="Cliente",
        required=True,
        widget=forms.Select(attrs={
            'class': 'w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500 bg-white search-select'
        })
    )

    class Meta:
        model = ServiceOrder
        fields = ['client', 'client_property', 'description', 'budget_scheduled_at', 'execution_scheduled_at']
        widgets = {
            'client_property': forms.Select(attrs={
                'class': 'w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500 bg-white'
            }),
            'description': forms.Textarea(attrs={
                'rows': 3, 
                'placeholder': 'Descreva o problema ou solicitação...',
                'class': 'w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500'
            }),
            'budget_scheduled_at': forms.DateTimeInput(attrs={
                'type': 'datetime-local',
                'class': 'w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500'
            }),
            'execution_scheduled_at': forms.DateTimeInput(attrs={
                'type': 'datetime-local',
                'class': 'w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500'
            }),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['client_property'].queryset = Property.objects.none()

        if 'client' in self.data:
            try:
                client_id = self.data.get('client')
                self.fields['client_property'].queryset = Property.objects.filter(client_id=client_id).order_by('address')
            except (ValueError, TypeError):
                pass
        elif self.instance.pk and hasattr(self.instance, 'client_property') and self.instance.client_property:
            self.fields['client'].initial = self.instance.client_property.client
            self.fields['client_property'].queryset = self.instance.client_property.client.properties.order_by('address')

        # Format dates for datetime-local input (YYYY-MM-DDTHH:MM)
        if self.instance.pk:
            if self.instance.budget_scheduled_at:
                self.initial['budget_scheduled_at'] = self.instance.budget_scheduled_at.strftime('%Y-%m-%dT%H:%M')
            if self.instance.execution_scheduled_at:
                self.initial['execution_scheduled_at'] = self.instance.execution_scheduled_at.strftime('%Y-%m-%dT%H:%M')

class ServiceOrderForm(forms.ModelForm):
    client = forms.ModelChoiceField(
        queryset=Client.objects.all(),
        label="Cliente",
        required=True,
        widget=forms.Select(attrs={
            'class': 'w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500 bg-white search-select'
        })
    )

    class Meta:
        model = ServiceOrder
        fields = ['client', 'client_property', 'status', 'description', 'technical_notes', 'budget_scheduled_at', 'execution_scheduled_at']
        widgets = {
            'client_property': forms.Select(attrs={
                'class': 'w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500 bg-white'
            }),
            'status': forms.Select(attrs={
                'class': 'w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500 bg-white'
            }),
            'description': forms.Textarea(attrs={
                'rows': 3, 
                'placeholder': 'Descreva o problema ou solicitação...',
                'class': 'w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500'
            }),
            'technical_notes': forms.Textarea(attrs={
                'rows': 3, 
                'placeholder': 'Notas técnicas da vistoria...',
                'class': 'w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500'
            }),
            'budget_scheduled_at': forms.DateTimeInput(attrs={
                'type': 'datetime-local',
                'class': 'w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500'
            }),
            'execution_scheduled_at': forms.DateTimeInput(attrs={
                'type': 'datetime-local',
                'class': 'w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500'
            }),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['client_property'].queryset = Property.objects.none()

        if 'client' in self.data:
            try:
                client_id = self.data.get('client')
                self.fields['client_property'].queryset = Property.objects.filter(client_id=client_id).order_by('address')
            except (ValueError, TypeError):
                pass
        elif self.instance.pk and hasattr(self.instance, 'client_property') and self.instance.client_property:
            self.fields['client'].initial = self.instance.client_property.client
            self.fields['client_property'].queryset = self.instance.client_property.client.properties.order_by('address')

        # Format dates for datetime-local input (YYYY-MM-DDTHH:MM)
        if self.instance.pk:
            if self.instance.budget_scheduled_at:
                self.initial['budget_scheduled_at'] = self.instance.budget_scheduled_at.strftime('%Y-%m-%dT%H:%M')
            if self.instance.execution_scheduled_at:
                self.initial['execution_scheduled_at'] = self.instance.execution_scheduled_at.strftime('%Y-%m-%dT%H:%M')

    def clean(self):
        cleaned_data = super().clean()
        budget_at = cleaned_data.get('budget_scheduled_at')
        execution_at = cleaned_data.get('execution_scheduled_at')
        
        # Lógica de validação de conflitos será implementada de forma centralizada 
        # para ser usada tanto aqui quanto na designação de equipe.
        return cleaned_data

class ProfessionalScheduleBlockForm(forms.ModelForm):
    class Meta:
        model = ProfessionalScheduleBlock
        fields = ['professional', 'start_at', 'end_at', 'reason', 'is_all_day']
        widgets = {
            'professional': forms.Select(attrs={'class': 'w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500'}),
            'start_at': forms.DateTimeInput(attrs={'type': 'datetime-local', 'class': 'w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500'}),
            'end_at': forms.DateTimeInput(attrs={'type': 'datetime-local', 'class': 'w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500'}),
            'reason': forms.TextInput(attrs={'class': 'w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500'}),
        }

class ServiceInspectionForm(forms.ModelForm):
    files = MultipleFileField(
        label="Fotos e Vídeos da Vistoria", 
        required=False,
        help_text="Selecione múltiplos arquivos para evidência."
    )

    class Meta:
        model = ServiceOrder
        fields = ['description', 'technical_notes']
        widgets = {
            'description': forms.Textarea(attrs={
                'rows': 3, 
                'placeholder': 'Relate o problema inicial...',
                'class': 'w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500'
            }),
            'technical_notes': forms.Textarea(attrs={
                'rows': 3, 
                'placeholder': 'Observações técnicas encontradas no local...',
                'class': 'w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500'
            }),
        }

class ServiceItemForm(forms.ModelForm):
    class Meta:
        model = ServiceItem
        fields = ['description', 'quantity', 'unit_price']
        widgets = {
            'description': forms.TextInput(attrs={
                'placeholder': 'Ex: Troca de disjuntor',
                'class': 'w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500'
            }),
            'quantity': forms.NumberInput(attrs={
                'class': 'w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500',
                'step': '0.01'
            }),
            'unit_price': forms.NumberInput(attrs={
                'class': 'w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500',
                'step': '0.01'
            }),
        }

ServiceItemFormSet = inlineformset_factory(
    ServiceOrder, ServiceItem,
    form=ServiceItemForm,
    extra=1,
    can_delete=True
)

# --- PROFESSIONAL FORMS ---

from .models import Professional, ProfessionalRole, ProfessionalAvailability

class ProfessionalForm(forms.ModelForm):
    roles = forms.ModelMultipleChoiceField(
        queryset=ProfessionalRole.objects.all(),
        widget=forms.CheckboxSelectMultiple(attrs={
            'class': 'grid grid-cols-2 gap-2 p-2'
        }),
        label="Funções"
    )

    class Meta:
        model = Professional
        fields = [
            'name', 'cpf', 'phone', 'email', 'roles', 
            'cep', 'address', 'number', 'complement', 
            'neighborhood', 'city', 'state', 'base_salary',
            'is_active', 'user'
        ]
        widgets = {
            'name': forms.TextInput(attrs={'class': 'w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500'}),
            'cpf': forms.TextInput(attrs={'class': 'cpf-mask w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500'}),
            'phone': forms.TextInput(attrs={'class': 'w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500'}),
            'email': forms.EmailInput(attrs={'class': 'w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500'}),
            'cep': forms.TextInput(attrs={'class': 'cep-input w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500', 'onblur': 'buscarCep(this.value)'}),
            'address': forms.TextInput(attrs={'class': 'w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500'}),
            'number': forms.TextInput(attrs={'class': 'w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500'}),
            'complement': forms.TextInput(attrs={'class': 'w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500'}),
            'neighborhood': forms.TextInput(attrs={'class': 'w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500'}),
            'city': forms.TextInput(attrs={'class': 'w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500'}),
            'state': forms.TextInput(attrs={'class': 'w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500'}),
            'base_salary': forms.NumberInput(attrs={'class': 'w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500', 'step': '0.01'}),
            'user': forms.Select(attrs={'class': 'w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500'}),
            'is_active': forms.CheckboxInput(attrs={'class': 'h-4 w-4 text-blue-600 focus:ring-blue-500 border-gray-300 rounded'}),
        }

    def clean_cpf(self):
        cpf = self.cleaned_data.get('cpf')
        if cpf:
            cpf = ''.join(filter(str.isdigit, cpf))
            if len(cpf) != 11:
                raise forms.ValidationError("CPF deve conter 11 dígitos.")
        return cpf

    def clean_phone(self):
        phone = self.cleaned_data.get('phone')
        if phone:
            phone = ''.join(filter(str.isdigit, phone))
            if len(phone) < 10 or len(phone) > 11:
                raise forms.ValidationError("Telefone deve conter 10 ou 11 dígitos (incluindo DDD).")
        return phone

AvailabilityFormSet = inlineformset_factory(
    Professional, ProfessionalAvailability,
    fields=['day_of_week', 'start_time', 'end_time'],
    extra=1,
    can_delete=True,
    widgets={
        'day_of_week': forms.Select(attrs={'class': 'w-full px-2 py-1 border rounded focus:ring-1 focus:ring-blue-500'}),
        'start_time': forms.TimeInput(attrs={'type': 'time', 'class': 'w-full px-2 py-1 border rounded focus:ring-1 focus:ring-blue-500'}),
        'end_time': forms.TimeInput(attrs={'type': 'time', 'class': 'w-full px-2 py-1 border rounded focus:ring-1 focus:ring-blue-500'}),
    }
)

ServiceOrderTeamFormSet = inlineformset_factory(
    ServiceOrder, ServiceOrderTeam,
    fields=['professional', 'role', 'category'],
    extra=1,
    can_delete=True,
    widgets={
        'professional': forms.Select(attrs={'class': 'w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500'}),
        'role': forms.Select(attrs={'class': 'w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500'}),
        'category': forms.HiddenInput(),
    }
)
