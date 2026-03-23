from django import forms
from django.forms import inlineformset_factory
from .models import Client, ClientPhone, ClientEmail, Property, ServiceOrder, ServiceMedia, ServiceItem, ServiceOrderTeam, Professional, ProfessionalRole, ProfessionalAvailability

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

PhoneFormSet = inlineformset_factory(
    Client, ClientPhone, 
    fields=['phone', 'is_primary'], 
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
            'latitude': forms.HiddenInput(),
            'longitude': forms.HiddenInput(),
        }

PropertyFormSet = inlineformset_factory(
    Client, Property,
    fields=[
        'classification', 'cep', 'address', 'number', 
        'complement', 'neighborhood', 'city', 'state',
        'latitude', 'longitude'
    ],
    extra=1,
    can_delete=True,
    widgets={
        'classification': forms.Select(attrs={'class': 'w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500'}),
        'cep': forms.TextInput(attrs={'placeholder': '00000-000', 'class': 'cep-input w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500'}),
        'address': forms.TextInput(attrs={'class': 'w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500'}),
        'number': forms.TextInput(attrs={'class': 'w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500'}),
        'complement': forms.TextInput(attrs={'class': 'w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500'}),
        'neighborhood': forms.TextInput(attrs={'class': 'w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500'}),
        'city': forms.TextInput(attrs={'class': 'w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500'}),
        'state': forms.TextInput(attrs={'class': 'w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500'}),
        'latitude': forms.HiddenInput(),
        'longitude': forms.HiddenInput(),
    }
)

# --- SERVICE ORDER FORMS ---

class ServiceOrderForm(forms.ModelForm):
    class Meta:
        model = ServiceOrder
        fields = ['status', 'description', 'technical_notes', 'scheduled_for']
        widgets = {
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
            'scheduled_for': forms.DateTimeInput(attrs={
                'type': 'datetime-local',
                'class': 'w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500'
            }),
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
    fields=['professional', 'role'],
    extra=1,
    can_delete=True,
    widgets={
        'professional': forms.Select(attrs={'class': 'w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500'}),
        'role': forms.Select(attrs={'class': 'w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500'}),
    }
)
