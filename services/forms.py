from django import forms
from django.forms import inlineformset_factory
from .models import (
    Client, ClientPhone, ClientEmail, Property, ServiceOrder,
    ServiceMedia, ServiceItem, ServiceOrderTeam, Professional,
    ProfessionalRole, ProfessionalScheduleBlock,
    ServiceOrderTask
)

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
        fields = [
            'client_type',
            'name',
            # PF
            'cpf',
            'rg',
            # PJ
            'trade_name',
            'cnpj',
            'state_registration',
            'municipal_registration',
            'contact_person',
        ]
        widgets = {
            'client_type': forms.RadioSelect(attrs={
                'class': 'client-type-radio'
            }),
            'name': forms.TextInput(attrs={
                'placeholder': 'Nome completo ou Razão Social',
                'class': 'w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500'
            }),
            # PF
            'cpf': forms.TextInput(attrs={
                'placeholder': '000.000.000-00',
                'class': 'cpf-mask w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500 pf-field',
                'data-mask': '000.000.000-00'
            }),
            'rg': forms.TextInput(attrs={
                'placeholder': 'RG',
                'class': 'w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500 pf-field'
            }),
            # PJ
            'trade_name': forms.TextInput(attrs={
                'placeholder': 'Nome Fantasia',
                'class': 'w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500 pj-field'
            }),
            'cnpj': forms.TextInput(attrs={
                'placeholder': '00.000.000/0000-00',
                'class': 'cnpj-mask w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500 pj-field',
                'data-mask': '00.000.000/0000-00'
            }),
            'state_registration': forms.TextInput(attrs={
                'placeholder': 'Inscrição Estadual',
                'class': 'w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500 pj-field'
            }),
            'municipal_registration': forms.TextInput(attrs={
                'placeholder': 'Inscrição Municipal',
                'class': 'w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500 pj-field'
            }),
            'contact_person': forms.TextInput(attrs={
                'placeholder': 'Nome do responsável/contato',
                'class': 'w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500 pj-field'
            }),
        }

    def clean(self):
        cleaned_data = super().clean()
        client_type = cleaned_data.get('client_type')
        
        if client_type == 'PF':
            # Pessoa Física: CPF obrigatório
            if not cleaned_data.get('cpf'):
                self.add_error('cpf', 'CPF é obrigatório para Pessoa Física')
            else:
                cpf = cleaned_data.get('cpf')
                cpf = ''.join(filter(str.isdigit, cpf))
                if len(cpf) != 11:
                    self.add_error('cpf', 'CPF deve conter 11 dígitos')
        
        elif client_type == 'PJ':
            # Pessoa Jurídica: CNPJ obrigatório
            if not cleaned_data.get('cnpj'):
                self.add_error('cnpj', 'CNPJ é obrigatório para Pessoa Jurídica')
            else:
                cnpj = cleaned_data.get('cnpj')
                cnpj = ''.join(filter(str.isdigit, cnpj))
                if len(cnpj) != 14:
                    self.add_error('cnpj', 'CNPJ deve conter 14 dígitos')
        
        return cleaned_data

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
    can_delete=True,
    max_num=10
)

EmailFormSet = inlineformset_factory(
    Client, ClientEmail, 
    fields=['email', 'is_primary'], 
    extra=1, 
    can_delete=True,
    max_num=10
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
        if self.instance and not self.instance._state.adding:
            if self.instance.latitude is None:
                self.initial['latitude'] = ''
            if self.instance.longitude is None:
                self.initial['longitude'] = ''

PropertyFormSet = inlineformset_factory(
    Client, Property,
    form=PropertyForm,
    extra=1,
    can_delete=True,
    max_num=10
)

# --- SERVICE ORDER FORMS ---

class ServiceOrderSchedulingForm(forms.ModelForm):
    """
    Formulário para criar uma OS e sua primeira Etapa (Task) simultaneamente.
    """
    task_type = forms.ChoiceField(
        choices=ServiceOrderTask.TaskType.choices,
        initial=ServiceOrderTask.TaskType.BUDGET,
        label="Finalidade do Agendamento",
        required=False,
        widget=forms.RadioSelect(attrs={'class': 'flex gap-4 p-2 bg-slate-50 rounded-xl border border-slate-100'})
    )

    scheduled_at = forms.DateTimeField(
        label="Data e Hora do Agendamento",
        widget=forms.DateTimeInput(attrs={
            'type': 'datetime-local',
            'class': 'w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500'
        })
    )

    client = forms.ModelChoiceField(
        queryset=Client.objects.all(),
        label="Cliente",
        required=True,
        widget=forms.Select(attrs={
            'class': 'w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500 bg-white search-select'
        })
    )
    
    originator = forms.ModelChoiceField(
        queryset=Professional.objects.none(),
        label="Vendedor/Originador",
        required=True,
        widget=forms.Select(attrs={
            'class': 'w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500 bg-white'
        })
    )
    
    origin_date = forms.DateField(
        label="Data de Origem",
        required=False,
        widget=forms.DateInput(
            format='%Y-%m-%d',
            attrs={
                'type': 'date',
                'class': 'w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500'
            }
        )
    )

    class Meta:
        model = ServiceOrder
        fields = ['client', 'client_property', 'description', 'estimated_value', 'origin_date', 'originator']
        widgets = {
            'client_property': forms.Select(attrs={
                'class': 'w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500 bg-white'
            }),
            'description': forms.Textarea(attrs={
                'rows': 3, 
                'placeholder': 'Descreva o problema ou solicitação...',
                'class': 'w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500'
            }),
            'estimated_value': forms.NumberInput(attrs={
                'step': '0.01',
                'placeholder': '0,00',
                'class': 'w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500'
            }),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['client_property'].queryset = Property.objects.none()
        
        # Se está editando (já existe no banco), tornar origin_date e originator readonly
        if self.instance and not self.instance._state.adding:
            self.fields['origin_date'].widget.attrs['readonly'] = True
            self.fields['origin_date'].widget.attrs['class'] += ' bg-slate-100 cursor-not-allowed'
            self.fields['originator'].disabled = True
            self.fields['originator'].required = False
            self.fields['originator'].widget.attrs['class'] += ' bg-slate-100 cursor-not-allowed'
        
        # Filtrar apenas profissionais com função "Vendedor"
        try:
            vendedor_role = ProfessionalRole.objects.filter(name__icontains='vendedor').first()
            if vendedor_role:
                qs = vendedor_role.professionals.filter(is_active=True)
            else:
                # Se não existir função "Vendedor", mostrar todos profissionais ativos
                qs = Professional.objects.filter(is_active=True)
                
            # Na edição, garantir que o originator atual seja exibido caso ele esteja inativo ou mude de função
            if self.instance and not self.instance._state.adding and self.instance.originator:
                qs = qs | Professional.objects.filter(pk=self.instance.originator.pk)
                
            self.fields['originator'].queryset = qs.distinct()
        except:
            self.fields['originator'].queryset = Professional.objects.filter(is_active=True)

        if 'client' in self.data:
            try:
                client_id = self.data.get('client')
                self.fields['client_property'].queryset = Property.objects.filter(client_id=client_id).order_by('address')
            except (ValueError, TypeError):
                pass
        elif self.instance and not self.instance._state.adding:
            try:
                if self.instance.client_property:
                    self.fields['client'].initial = self.instance.client_property.client
                    self.fields['client_property'].queryset = self.instance.client_property.client.properties.order_by('address')
            except ServiceOrder.client_property.RelatedObjectDoesNotExist:
                pass

class ServiceOrderTaskForm(forms.ModelForm):
    class Meta:
        model = ServiceOrderTask
        fields = ['task_type', 'status', 'scheduled_at', 'notes']
        widgets = {
            'task_type': forms.Select(attrs={'class': 'w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500'}),
            'status': forms.Select(attrs={'class': 'w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500'}),
            'scheduled_at': forms.DateTimeInput(attrs={'type': 'datetime-local', 'class': 'w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500'}),
            'notes': forms.Textarea(attrs={'rows': 2, 'class': 'w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance.pk and self.instance.scheduled_at:
            self.initial['scheduled_at'] = self.instance.scheduled_at.strftime('%Y-%m-%dT%H:%M')

# Equipe ligada à TASK
ServiceOrderTeamFormSet = inlineformset_factory(
    ServiceOrderTask, ServiceOrderTeam,
    fields=['professional', 'role'],
    extra=1,
    can_delete=True,
    max_num=10,
    widgets={
        'professional': forms.Select(attrs={'class': 'w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500'}),
        'role': forms.Select(attrs={'class': 'w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500'}),
    }
)

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
        fields = ['client', 'client_property', 'status', 'is_recurrent', 'description', 'technical_notes']
        widgets = {
            'client_property': forms.Select(attrs={
                'class': 'w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500 bg-white'
            }),
            'status': forms.Select(attrs={
                'class': 'w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500 bg-white'
            }),
            'is_recurrent': forms.CheckboxInput(attrs={
                'class': 'h-4 w-4 text-blue-600 focus:ring-blue-500 border-gray-300 rounded'
            }),
            'description': forms.Textarea(attrs={
                'rows': 3, 
                'placeholder': 'Descreva o problema ou solicitação...',
                'class': 'w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500'
            }),
            'technical_notes': forms.Textarea(attrs={
                'rows': 3, 
                'placeholder': 'Notas técnicas gerais...',
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
        elif self.instance and not self.instance._state.adding:
            try:
                if self.instance.client_property:
                    self.fields['client'].initial = self.instance.client_property.client
                    self.fields['client_property'].queryset = self.instance.client_property.client.properties.order_by('address')
            except ServiceOrder.client_property.RelatedObjectDoesNotExist:
                pass

class ServiceInspectionForm(forms.ModelForm):
    files = MultipleFileField(
        label="Fotos e Vídeos da Vistoria", 
        required=False,
        help_text="Selecione múltiplos arquivos para evidência."
    )

    class Meta:
        model = ServiceOrderTask
        fields = ['notes']
        widgets = {
            'notes': forms.Textarea(attrs={
                'rows': 4, 
                'placeholder': 'Relate o que foi encontrado na vistoria...',
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
    can_delete=True,
    max_num=50
)

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
            'work_schedule', 'is_active', 'user'
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
            'work_schedule': forms.Select(attrs={'class': 'w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500'}),
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

# --- TASK MANAGEMENT FORMS ---

class TaskScheduleForm(forms.ModelForm):
    """
    Formulário para adicionar ou editar uma Task em uma OS existente.
    """
    class Meta:
        model = ServiceOrderTask
        fields = ['task_type', 'scheduled_at', 'value', 'notes']
        widgets = {
            'task_type': forms.Select(attrs={
                'class': 'w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500'
            }),
            'scheduled_at': forms.DateTimeInput(attrs={
                'type': 'datetime-local',
                'class': 'calendar-input w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500',
                'id': 'id_scheduled_at'
            }),
            'value': forms.NumberInput(attrs={
                'class': 'w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500',
                'step': '0.01',
                'placeholder': '0.00'
            }),
            'notes': forms.Textarea(attrs={
                'rows': 3,
                'placeholder': 'Observações sobre esta etapa...',
                'class': 'w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500'
            }),
        }
        labels = {
            'task_type': 'Tipo de Etapa',
            'scheduled_at': 'Data e Hora',
            'value': 'Valor do Serviço (R$)',
            'notes': 'Observações'
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance.pk and self.instance.scheduled_at:
            self.initial['scheduled_at'] = self.instance.scheduled_at.strftime('%Y-%m-%dT%H:%M')

class TaskCancelForm(forms.Form):
    """
    Formulário para cancelar uma Task com justificativa.
    """
    cancel_reason = forms.CharField(
        label="Motivo do Cancelamento",
        widget=forms.Textarea(attrs={
            'rows': 3,
            'placeholder': 'Descreva o motivo do cancelamento desta etapa...',
            'class': 'w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500',
            'required': True
        })
    )
