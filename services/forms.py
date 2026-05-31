from django import forms
import django.utils.timezone
from django.forms import inlineformset_factory
from .models import (
    Client, ClientPhone, ClientEmail, Property, ServiceOrder,
    ServiceMedia, ServiceItem, ServiceOrderTeam, Professional,
    ProfessionalRole, ProfessionalScheduleBlock,
    ServiceOrderTask, ServicePayment, Product, StockMovement,
    Sale, SaleItem, Supplier, PaymentMethod
)
from integracoes.models import SystemConfig

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
            if cleaned_data.get('cpf'):
                cpf = cleaned_data.get('cpf')
                cpf = ''.join(filter(str.isdigit, cpf))
                if len(cpf) != 11:
                    self.add_error('cpf', 'CPF deve conter 11 dígitos')
        
        elif client_type == 'PJ':
            if cleaned_data.get('cnpj'):
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
            'ibge_code', 'latitude', 'longitude'
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
            'ibge_code': forms.TextInput(attrs={'class': 'w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500', 'placeholder': 'Código IBGE'}),
            'latitude': forms.TextInput(attrs={'class': 'w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500', 'placeholder': 'Ex: -23.123456'}),
            'longitude': forms.TextInput(attrs={'class': 'w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500', 'placeholder': 'Ex: -46.123456'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['cep'].required = False
        self.fields['number'].required = False
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
    is_approved = forms.TypedChoiceField(
        label='Aprovado pelo Cliente',
        choices=[('', 'Selecione...'), (True, 'Aprovado'), (False, 'Reprovado')],
        coerce=lambda value: str(value).lower() in ('true', '1'),
        empty_value=False,
        required=False,
        widget=forms.Select(attrs={
            'class': 'w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500'
        })
    )

    payment_method = forms.ChoiceField(
        label='Método de Pagamento Preferencial',
        choices=[('', 'Selecione...')] + ServiceOrderTask.PAYMENT_METHODS,
        required=False,
        widget=forms.Select(attrs={
            'class': 'w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500'
        })
    )

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

    scheduled_end_at = forms.DateTimeField(
        label="Data Fim do Agendamento (Opcional)",
        required=False,
        widget=forms.DateTimeInput(attrs={
            'type': 'datetime-local',
            'class': 'w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500'
        })
    )

    send_whatsapp_confirmation = forms.BooleanField(
        label="Enviar WhatsApp de Confirmação?",
        required=False,
        initial=False,
        widget=forms.CheckboxInput(attrs={
            'class': 'h-4 w-4 text-blue-600 focus:ring-blue-500 border-gray-300 rounded'
        })
    )

    whatsapp_confirmation_status = forms.ChoiceField(
        choices=[('', 'Selecione...')] + ServiceOrderTask.WhatsAppConfirmationStatus.choices,
        label="Status da Confirmação WhatsApp",
        required=False,
        widget=forms.Select(attrs={'class': 'w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500'})
    )

    whatsapp_notification_sent_at = forms.DateTimeField(
        label="Notificação enviada em",
        required=False,
        widget=forms.DateTimeInput(attrs={'type': 'datetime-local', 'class': 'w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500'})
    )

    whatsapp_confirmation_received_at = forms.DateTimeField(
        label="Resposta recebida em",
        required=False,
        widget=forms.DateTimeInput(attrs={'type': 'datetime-local', 'class': 'w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500'})
    )

    whatsapp_response_content = forms.CharField(
        label="Conteúdo da Resposta WhatsApp",
        required=False,
        widget=forms.Textarea(attrs={'rows': 2, 'class': 'w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500'})
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
        required=False,
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
        fields = ['client', 'client_property', 'description', 'client_observation', 'estimated_value', 'origin_date', 'originator']
        widgets = {
            'client_property': forms.Select(attrs={
                'class': 'w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500 bg-white'
            }),
            'description': forms.Textarea(attrs={
                'rows': 3, 
                'placeholder': 'Descreva o problema ou solicitação...',
                'class': 'w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500'
            }),
            'client_observation': forms.Textarea(attrs={
                'rows': 3, 
                'placeholder': 'Observação para o cliente (orçamento)...',
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
        self.fields['origin_date'].required = False
        self.fields['originator'].required = False
        
        # Se está editando (já existe no banco), carregar dados da primeira task
        if self.instance and not self.instance._state.adding:
            first_task = self.instance.tasks.order_by('scheduled_at').first()
            if first_task:
                self.initial['task_type'] = first_task.task_type
                self.initial['is_approved'] = first_task.is_approved
                self.initial['payment_method'] = first_task.payment_method or ''
                if first_task.scheduled_at:
                    self.initial['scheduled_at'] = django.utils.timezone.localtime(first_task.scheduled_at).strftime('%Y-%m-%dT%H:%M')
                if first_task.scheduled_end_at:
                    self.initial['scheduled_end_at'] = django.utils.timezone.localtime(first_task.scheduled_end_at).strftime('%Y-%m-%dT%H:%M')
                
                self.initial['send_whatsapp_confirmation'] = first_task.send_whatsapp_confirmation
                self.initial['whatsapp_confirmation_status'] = first_task.whatsapp_confirmation_status or ''
                if first_task.whatsapp_notification_sent_at:
                    self.initial['whatsapp_notification_sent_at'] = django.utils.timezone.localtime(first_task.whatsapp_notification_sent_at).strftime('%Y-%m-%dT%H:%M')
                if first_task.whatsapp_confirmation_received_at:
                    self.initial['whatsapp_confirmation_received_at'] = django.utils.timezone.localtime(first_task.whatsapp_confirmation_received_at).strftime('%Y-%m-%dT%H:%M')
                self.initial['whatsapp_response_content'] = first_task.whatsapp_response_content
        else:
            self.initial['is_approved'] = ''
            self.initial['payment_method'] = ''
        
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
        elif hasattr(self, 'initial') and self.initial.get('client'):
            try:
                client_id = getattr(self.initial.get('client'), 'id', self.initial.get('client'))
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
        fields = [
            'task_type', 'status', 'scheduled_at', 'scheduled_end_at', 'notes',
            'send_whatsapp_confirmation', 'whatsapp_confirmation_status',
            'whatsapp_notification_sent_at', 'whatsapp_confirmation_received_at',
            'whatsapp_response_content'
        ]
        widgets = {
            'task_type': forms.Select(attrs={'class': 'w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500'}),
            'status': forms.Select(attrs={'class': 'w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500'}),
            'scheduled_at': forms.DateTimeInput(attrs={'type': 'datetime-local', 'class': 'w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500'}),
            'scheduled_end_at': forms.DateTimeInput(attrs={'type': 'datetime-local', 'class': 'w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500'}),
            'notes': forms.Textarea(attrs={'rows': 2, 'class': 'w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500'}),
            'whatsapp_confirmation_status': forms.Select(attrs={'class': 'w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500'}),
            'whatsapp_notification_sent_at': forms.DateTimeInput(attrs={'type': 'datetime-local', 'class': 'w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500'}),
            'whatsapp_confirmation_received_at': forms.DateTimeInput(attrs={'type': 'datetime-local', 'class': 'w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500'}),
            'whatsapp_response_content': forms.Textarea(attrs={'rows': 2, 'class': 'w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['whatsapp_confirmation_status'].choices = [('', 'Selecione...')] + ServiceOrderTask.WhatsAppConfirmationStatus.choices
        if self.instance.pk and self.instance.scheduled_at:
            self.initial['scheduled_at'] = django.utils.timezone.localtime(self.instance.scheduled_at).strftime('%Y-%m-%dT%H:%M')
        if self.instance.pk and self.instance.scheduled_end_at:
            self.initial['scheduled_end_at'] = django.utils.timezone.localtime(self.instance.scheduled_end_at).strftime('%Y-%m-%dT%H:%M')
        if self.instance.pk and self.instance.whatsapp_notification_sent_at:
            self.initial['whatsapp_notification_sent_at'] = django.utils.timezone.localtime(self.instance.whatsapp_notification_sent_at).strftime('%Y-%m-%dT%H:%M')
        if self.instance.pk and self.instance.whatsapp_confirmation_received_at:
            self.initial['whatsapp_confirmation_received_at'] = django.utils.timezone.localtime(self.instance.whatsapp_confirmation_received_at).strftime('%Y-%m-%dT%H:%M')

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
        fields = ['client', 'client_property', 'status', 'is_recurrent', 'description', 'technical_notes', 'client_observation']
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
            'client_observation': forms.Textarea(attrs={
                'rows': 3, 
                'placeholder': 'Observação para o cliente (orçamento)...',
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
        elif hasattr(self, 'initial') and self.initial.get('client'):
            try:
                client_id = getattr(self.initial.get('client'), 'id', self.initial.get('client'))
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
    description = forms.CharField(
        label="Descrição do Problema/Solicitação",
        required=False,
        widget=forms.Textarea(attrs={
            'rows': 3, 
            'placeholder': 'Descreva o problema ou solicitação...',
            'class': 'w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500'
        })
    )
    client_observation = forms.CharField(
        label="Observação para o Cliente",
        required=False,
        widget=forms.Textarea(attrs={
            'rows': 3, 
            'placeholder': 'Observação para o cliente (orçamento)...',
            'class': 'w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500'
        })
    )
    technical_notes = forms.CharField(
        label="Notas Técnicas Gerais",
        required=False,
        widget=forms.Textarea(attrs={
            'rows': 3, 
            'placeholder': 'Notas técnicas gerais...',
            'class': 'w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500'
        })
    )
    
    files = MultipleFileField(
        label="Fotos e Vídeos da Vistoria", 
        required=False,
        help_text="Selecione múltiplos arquivos para evidência."
    )

    class Meta:
        model = ServiceOrderTask
        fields = [
            'notes', 
            'send_whatsapp_confirmation',
            'whatsapp_confirmation_status',
            'whatsapp_notification_sent_at',
            'whatsapp_confirmation_received_at',
            'whatsapp_response_content'
        ]
        widgets = {
            'notes': forms.Textarea(attrs={
                'rows': 4, 
                'placeholder': 'Relate o que foi encontrado na vistoria...',
                'class': 'w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500'
            }),
            'whatsapp_confirmation_status': forms.Select(attrs={'class': 'w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500'}),
            'whatsapp_notification_sent_at': forms.DateTimeInput(attrs={'type': 'datetime-local', 'class': 'w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500'}),
            'whatsapp_confirmation_received_at': forms.DateTimeInput(attrs={'type': 'datetime-local', 'class': 'w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500'}),
            'whatsapp_response_content': forms.Textarea(attrs={'rows': 2, 'class': 'w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['whatsapp_confirmation_status'].choices = [('', 'Selecione...')] + ServiceOrderTask.WhatsAppConfirmationStatus.choices
        if self.instance.pk and self.instance.whatsapp_notification_sent_at:
            self.initial['whatsapp_notification_sent_at'] = django.utils.timezone.localtime(self.instance.whatsapp_notification_sent_at).strftime('%Y-%m-%dT%H:%M')
        if self.instance.pk and self.instance.whatsapp_confirmation_received_at:
            self.initial['whatsapp_confirmation_received_at'] = django.utils.timezone.localtime(self.instance.whatsapp_confirmation_received_at).strftime('%Y-%m-%dT%H:%M')


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
        fields = [
            'task_type', 'status', 'scheduled_at',
            'scheduled_end_at', 'started_at', 'finished_at', 'notes',
            'send_whatsapp_confirmation', 'whatsapp_confirmation_status',
            'whatsapp_notification_sent_at', 'whatsapp_confirmation_received_at',
            'whatsapp_response_content'
        ]
        widgets = {
            'task_type': forms.Select(attrs={
                'class': 'w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500'
            }),
            'status': forms.Select(attrs={
                'class': 'w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500'
            }),
            'scheduled_at': forms.DateTimeInput(attrs={
                'type': 'datetime-local',
                'class': 'w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500',
                'id': 'id_scheduled_at'
            }),
            'scheduled_end_at': forms.DateTimeInput(attrs={
                'type': 'datetime-local',
                'class': 'w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500',
                'id': 'id_scheduled_end_at'
            }),
            'started_at': forms.DateTimeInput(attrs={
                'type': 'datetime-local',
                'class': 'w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500',
                'id': 'id_started_at'
            }),
            'finished_at': forms.DateTimeInput(attrs={
                'type': 'datetime-local',
                'class': 'w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500',
                'id': 'id_finished_at'
            }),
            'notes': forms.Textarea(attrs={
                'rows': 3,
                'placeholder': 'Observações sobre esta etapa...',
                'class': 'w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500'
            }),
            'whatsapp_confirmation_status': forms.Select(attrs={'class': 'w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500'}),
            'whatsapp_notification_sent_at': forms.DateTimeInput(attrs={'type': 'datetime-local', 'class': 'w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500'}),
            'whatsapp_confirmation_received_at': forms.DateTimeInput(attrs={'type': 'datetime-local', 'class': 'w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500'}),
            'whatsapp_response_content': forms.Textarea(attrs={'rows': 2, 'class': 'w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500'}),
        }
        labels = {
            'task_type': 'Tipo de Etapa',
            'status': 'Status',
            'scheduled_at': 'Data Início (Agendamento)',
            'scheduled_end_at': 'Data Término (Agendamento)',
            'started_at': 'Iniciado em (Execução)',
            'finished_at': 'Finalizado em (Execução)',
            'notes': 'Observações',
            'send_whatsapp_confirmation': 'Enviar WhatsApp de Confirmação?',
            'whatsapp_confirmation_status': 'Status da Confirmação WhatsApp',
            'whatsapp_notification_sent_at': 'Notificação enviada em',
            'whatsapp_confirmation_received_at': 'Resposta recebida em',
            'whatsapp_response_content': 'Conteúdo da Resposta WhatsApp'
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['whatsapp_confirmation_status'].choices = [('', 'Selecione...')] + ServiceOrderTask.WhatsAppConfirmationStatus.choices
        if self.instance.pk:
            if self.instance.scheduled_at:
                self.initial['scheduled_at'] = django.utils.timezone.localtime(self.instance.scheduled_at).strftime('%Y-%m-%dT%H:%M')
            if self.instance.scheduled_end_at:
                self.initial['scheduled_end_at'] = django.utils.timezone.localtime(self.instance.scheduled_end_at).strftime('%Y-%m-%dT%H:%M')
            if self.instance.started_at:
                self.initial['started_at'] = django.utils.timezone.localtime(self.instance.started_at).strftime('%Y-%m-%dT%H:%M')
            if self.instance.finished_at:
                self.initial['finished_at'] = django.utils.timezone.localtime(self.instance.finished_at).strftime('%Y-%m-%dT%H:%M')
            if self.instance.whatsapp_notification_sent_at:
                self.initial['whatsapp_notification_sent_at'] = django.utils.timezone.localtime(self.instance.whatsapp_notification_sent_at).strftime('%Y-%m-%dT%H:%M')
            if self.instance.whatsapp_confirmation_received_at:
                self.initial['whatsapp_confirmation_received_at'] = django.utils.timezone.localtime(self.instance.whatsapp_confirmation_received_at).strftime('%Y-%m-%dT%H:%M')

class ServicePaymentForm(forms.ModelForm):
    class Meta:
        model = ServicePayment
        fields = ['amount', 'payment_method', 'paid_at', 'notes']
        widgets = {
            'amount': forms.NumberInput(attrs={'class': 'w-full px-3 py-2 border rounded-lg', 'step': '0.01'}),
            'payment_method': forms.Select(attrs={'class': 'w-full px-3 py-2 border rounded-lg'}),
            'paid_at': forms.DateTimeInput(attrs={'type': 'datetime-local', 'class': 'w-full px-3 py-2 border rounded-lg'}),
            'notes': forms.TextInput(attrs={'class': 'w-full px-3 py-2 border rounded-lg', 'placeholder': 'Ex: Transferência confirmada'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['paid_at'].initial = django.utils.timezone.now().strftime('%Y-%m-%dT%H:%M')

class ServiceOrderDiscountForm(forms.ModelForm):
    class Meta:
        model = ServiceOrder
        fields = ['discount']
        widgets = {
            'discount': forms.NumberInput(attrs={'class': 'w-full px-3 py-2 border rounded-lg', 'step': '0.01'}),
        }

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

# --- STOCK MANAGEMENT FORMS ---

class ProductForm(forms.ModelForm):
    class Meta:
        model = Product
        fields = [
            'name', 'category', 'supplier', 'code', 'barcode', 'image', 'unit_type', 'default_unit_price', 'current_stock', 'is_active',
            'ncm', 'cest', 'cfop_padrao', 'origem_mercadoria', 'csosn', 'cst_icms', 'cst_pis', 'cst_cofins',
            'aliquota_ibpt_fed', 'aliquota_ibpt_est', 'aliquota_ibpt_mun'
        ]
        widgets = {
            'name': forms.TextInput(attrs={'class': 'w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500'}),
            'category': forms.Select(attrs={'class': 'w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500'}),
            'supplier': forms.Select(attrs={'class': 'w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500'}),
            'code': forms.TextInput(attrs={'class': 'w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500'}),
            'barcode': forms.TextInput(attrs={'class': 'w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500'}),
            'image': forms.FileInput(attrs={'class': 'w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500'}),
            'unit_type': forms.Select(attrs={'class': 'w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500'}),
            'default_unit_price': forms.NumberInput(attrs={'class': 'w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500', 'step': '0.01'}),
            'current_stock': forms.NumberInput(attrs={'class': 'w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500', 'step': '0.01'}),
            'is_active': forms.CheckboxInput(attrs={'class': 'h-4 w-4 text-blue-600 focus:ring-blue-500 border-gray-300 rounded'}),
            # Fiscais
            'ncm': forms.TextInput(attrs={'class': 'w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500'}),
            'cest': forms.TextInput(attrs={'class': 'w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500'}),
            'cfop_padrao': forms.TextInput(attrs={'class': 'w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500'}),
            'origem_mercadoria': forms.Select(attrs={'class': 'w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500'}),
            'csosn': forms.TextInput(attrs={'class': 'w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500'}),
            'cst_icms': forms.TextInput(attrs={'class': 'w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500'}),
            'cst_pis': forms.TextInput(attrs={'class': 'w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500'}),
            'cst_cofins': forms.TextInput(attrs={'class': 'w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500'}),
            'aliquota_ibpt_fed': forms.NumberInput(attrs={'class': 'w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500', 'step': '0.01'}),
            'aliquota_ibpt_est': forms.NumberInput(attrs={'class': 'w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500', 'step': '0.01'}),
            'aliquota_ibpt_mun': forms.NumberInput(attrs={'class': 'w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500', 'step': '0.01'}),
        }

class StockMovementForm(forms.ModelForm):
    class Meta:
        model = StockMovement
        fields = ['product', 'quantity', 'movement_type', 'reason', 'service_order']
        widgets = {
            'product': forms.Select(attrs={'class': 'w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500'}),
            'quantity': forms.NumberInput(attrs={'class': 'w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500', 'step': '0.01'}),
            'movement_type': forms.Select(attrs={'class': 'w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500'}),
            'reason': forms.Select(attrs={'class': 'w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500'}),
            'service_order': forms.Select(attrs={'class': 'w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Se for uma saída, podemos querer filtrar OS abertas
        self.fields['service_order'].required = False

class ProductImportForm(forms.Form):
    OPERATION_CHOICES = [
        ('CATALOG', 'Gestão de Catálogo (Criar/Ativar/Inativar)'),
        ('STOCK', 'Atualização de Estoque (Ajuste de Saldo)'),
    ]
    
    operation_type = forms.ChoiceField(
        label="Tipo de Operação",
        choices=OPERATION_CHOICES,
        widget=forms.Select(attrs={'class': 'w-full px-3 py-2 border rounded-xl focus:ring-2 focus:ring-blue-500'})
    )
    file = forms.FileField(
        label="Arquivo (CSV ou Excel)",
        help_text="Selecione o arquivo correspondente ao modelo da operação escolhida.",
        widget=forms.FileInput(attrs={'class': 'w-full px-3 py-2 border rounded-xl focus:ring-2 focus:ring-blue-500', 'accept': '.csv, .xlsx'})
    )


# --- SALES (PDV) FORMS ---

class SaleForm(forms.ModelForm):
    installment_count = forms.ChoiceField(
        label="Parcelas",
        choices=[(str(i), f"{i}x") for i in range(1, 13)],
        initial='1',
        required=False,
        widget=forms.Select(attrs={'class': 'prominent-select'})
    )
    due_days = forms.IntegerField(
        label="Dias para Vencimento",
        initial=1,
        required=False,
        widget=forms.NumberInput(attrs={'class': 'w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500', 'min': 0})
    )

    class Meta:
        model = Sale
        fields = [
            'client', 'status', 'discount', 'surcharge',
            'indicador_presenca', 'modalidade_frete', 'forma_pagamento_sefaz'
        ]
        widgets = {
            'client': forms.Select(attrs={'class': 'w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500 bg-white search-select'}),
            'status': forms.Select(attrs={'class': 'w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500'}),
            'discount': forms.NumberInput(attrs={'class': 'w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500', 'step': '0.01'}),
            'surcharge': forms.NumberInput(attrs={'class': 'w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500', 'step': '0.01'}),
            'indicador_presenca': forms.Select(attrs={'class': 'w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500'}),
            'modalidade_frete': forms.Select(attrs={'class': 'w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500'}),
            'forma_pagamento_sefaz': forms.Select(attrs={'class': 'w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        config = SystemConfig.load()
        self.fields['due_days'].initial = config.billing_default_due_days
        self.fields['discount'].required = False
        self.fields['surcharge'].required = False

class SaleItemForm(forms.ModelForm):
    class Meta:
        model = SaleItem
        fields = ['product', 'quantity', 'unit_price', 'discount']
        widgets = {
            'product': forms.Select(attrs={'class': 'w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500 search-select product-select'}),
            'quantity': forms.NumberInput(attrs={'class': 'w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500 quantity-input', 'step': '0.01'}),
            'unit_price': forms.NumberInput(attrs={'class': 'w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500 price-input', 'step': '0.01'}),
            'discount': forms.NumberInput(attrs={'class': 'w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500 discount-input', 'step': '0.01'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['discount'].required = False

SaleItemFormSet = inlineformset_factory(
    Sale, SaleItem,
    form=SaleItemForm,
    extra=0,
    can_delete=True,
    min_num=1,
    validate_min=True
)

class PaymentMethodForm(forms.ModelForm):
    class Meta:
        model = PaymentMethod
        fields = [
            'descricao', 'tipo_provedor', 'tarifa_porcentagem', 
            'tarifa_fixa', 'prazo_recebimento', 'codigo_sefaz', 'ativo'
        ]
        widgets = {
            'descricao': forms.TextInput(attrs={'class': 'w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500', 'placeholder': 'Ex: Cartão de Crédito Visa'}),
            'tipo_provedor': forms.Select(attrs={'class': 'w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500'}),
            'tarifa_porcentagem': forms.NumberInput(attrs={'class': 'w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500', 'step': '0.01'}),
            'tarifa_fixa': forms.NumberInput(attrs={'class': 'w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500', 'step': '0.01'}),
            'prazo_recebimento': forms.NumberInput(attrs={'class': 'w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500'}),
            'codigo_sefaz': forms.TextInput(attrs={'class': 'w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500', 'placeholder': 'Ex: 03'}),
            'ativo': forms.CheckboxInput(attrs={'class': 'h-4 w-4 text-blue-600 focus:ring-blue-500 border-gray-300 rounded'}),
        }
