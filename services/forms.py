from django import forms
import django.utils.timezone
from django.forms import inlineformset_factory
from .models import (
    Client, ClientPhone, ClientEmail, Property, ServiceOrder,
    ServiceMedia, ServiceItem, ServiceOrderTeam, Professional,
    ProfessionalRole, ProfessionalScheduleBlock,
    ServiceOrderTask, ServicePayment, Product, StockMovement,
    Sale, SaleItem, Supplier, PaymentMethod, Expense, ProductComposition, ExpenseInstallment,
    FinanceSettings, SaleSettings, ProductVariant
)


def _safe_localtime(value):
    """
    django.utils.timezone.localtime() exige um datetime com timezone, mas em
    produção (USE_TZ = DEBUG = False) os DateTimeField vêm naive — horário
    local (America/Sao_Paulo) já salvo direto no banco, sem UTC. Nesse caso
    não precisa (nem pode) converter; só em dev (USE_TZ=True) o valor vem
    com timezone e precisa ser convertido para o horário local de exibição.
    """
    if value is None:
        return None
    return django.utils.timezone.localtime(value) if django.utils.timezone.is_aware(value) else value


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
        initial=ServiceOrderTask.TaskType.ORCAMENTO,
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
        fields = ['client', 'client_property', 'service_type', 'description', 'client_observation', 'estimated_value', 'origin_date', 'originator']
        widgets = {
            'client_property': forms.Select(attrs={
                'class': 'w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500 bg-white'
            }),
            'service_type': forms.Select(attrs={
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
                    self.initial['scheduled_at'] = _safe_localtime(first_task.scheduled_at).strftime('%Y-%m-%dT%H:%M')
                if first_task.scheduled_end_at:
                    self.initial['scheduled_end_at'] = _safe_localtime(first_task.scheduled_end_at).strftime('%Y-%m-%dT%H:%M')
                
                self.initial['send_whatsapp_confirmation'] = first_task.send_whatsapp_confirmation
                self.initial['whatsapp_confirmation_status'] = first_task.whatsapp_confirmation_status or ''
                if first_task.whatsapp_notification_sent_at:
                    self.initial['whatsapp_notification_sent_at'] = _safe_localtime(first_task.whatsapp_notification_sent_at).strftime('%Y-%m-%dT%H:%M')
                if first_task.whatsapp_confirmation_received_at:
                    self.initial['whatsapp_confirmation_received_at'] = _safe_localtime(first_task.whatsapp_confirmation_received_at).strftime('%Y-%m-%dT%H:%M')
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
            self.initial['scheduled_at'] = _safe_localtime(self.instance.scheduled_at).strftime('%Y-%m-%dT%H:%M')
        if self.instance.pk and self.instance.scheduled_end_at:
            self.initial['scheduled_end_at'] = _safe_localtime(self.instance.scheduled_end_at).strftime('%Y-%m-%dT%H:%M')
        if self.instance.pk and self.instance.whatsapp_notification_sent_at:
            self.initial['whatsapp_notification_sent_at'] = _safe_localtime(self.instance.whatsapp_notification_sent_at).strftime('%Y-%m-%dT%H:%M')
        if self.instance.pk and self.instance.whatsapp_confirmation_received_at:
            self.initial['whatsapp_confirmation_received_at'] = _safe_localtime(self.instance.whatsapp_confirmation_received_at).strftime('%Y-%m-%dT%H:%M')

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
        fields = ['client', 'client_property', 'service_type', 'status', 'is_recurrent', 'description', 'technical_notes', 'client_observation']
        widgets = {
            'client_property': forms.Select(attrs={
                'class': 'w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500 bg-white'
            }),
            'service_type': forms.Select(attrs={
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
            self.initial['whatsapp_notification_sent_at'] = _safe_localtime(self.instance.whatsapp_notification_sent_at).strftime('%Y-%m-%dT%H:%M')
        if self.instance.pk and self.instance.whatsapp_confirmation_received_at:
            self.initial['whatsapp_confirmation_received_at'] = _safe_localtime(self.instance.whatsapp_confirmation_received_at).strftime('%Y-%m-%dT%H:%M')


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
            'value', 'skip_auto_billing',
            'preferred_payment_method', 'preferred_installments',
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
            'value': forms.NumberInput(attrs={
                'step': '0.01', 'min': '0',
                'placeholder': 'Deixe em branco para usar a soma dos itens',
                'class': 'w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500'
            }),
            'preferred_payment_method': forms.Select(attrs={
                'class': 'w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500'
            }),
            'preferred_installments': forms.NumberInput(attrs={
                'min': '1',
                'class': 'w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500'
            }),
            'whatsapp_confirmation_status': forms.Select(attrs={'class': 'w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500'}),
            'whatsapp_notification_sent_at': forms.DateTimeInput(attrs={'type': 'datetime-local', 'class': 'w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500'}),
            'whatsapp_confirmation_received_at': forms.DateTimeInput(attrs={'type': 'datetime-local', 'class': 'w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500'}),
            'whatsapp_response_content': forms.Textarea(attrs={'rows': 2, 'class': 'w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500'}),
            'skip_auto_billing': forms.CheckboxInput(attrs={'class': 'switch-checkbox peer sr-only'}),
            'send_whatsapp_confirmation': forms.CheckboxInput(attrs={'class': 'switch-checkbox peer sr-only'}),
        }
        labels = {
            'task_type': 'Tipo de Etapa',
            'status': 'Status',
            'scheduled_at': 'Data Início (Agendamento)',
            'scheduled_end_at': 'Data Término (Agendamento)',
            'started_at': 'Iniciado em (Execução)',
            'finished_at': 'Finalizado em (Execução)',
            'notes': 'Observações',
            'skip_auto_billing': 'Não gerar cobrança automática ao concluir esta etapa',
            'preferred_payment_method': 'Forma de Pagamento',
            'preferred_installments': 'Parcelas',
            'send_whatsapp_confirmation': 'Enviar WhatsApp de Confirmação?',
            'whatsapp_confirmation_status': 'Status da Confirmação WhatsApp',
            'whatsapp_notification_sent_at': 'Notificação enviada em',
            'whatsapp_confirmation_received_at': 'Resposta recebida em',
            'whatsapp_response_content': 'Conteúdo da Resposta WhatsApp'
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['whatsapp_confirmation_status'].choices = [('', 'Selecione...')] + ServiceOrderTask.WhatsAppConfirmationStatus.choices
        self.fields['preferred_payment_method'].queryset = PaymentMethod.objects.filter(ativo=True).order_by('descricao')
        self.fields['preferred_payment_method'].empty_label = 'Selecione...'
        if self.instance.pk:
            if self.instance.scheduled_at:
                self.initial['scheduled_at'] = _safe_localtime(self.instance.scheduled_at).strftime('%Y-%m-%dT%H:%M')
            if self.instance.scheduled_end_at:
                self.initial['scheduled_end_at'] = _safe_localtime(self.instance.scheduled_end_at).strftime('%Y-%m-%dT%H:%M')
            if self.instance.started_at:
                self.initial['started_at'] = _safe_localtime(self.instance.started_at).strftime('%Y-%m-%dT%H:%M')
            if self.instance.finished_at:
                self.initial['finished_at'] = _safe_localtime(self.instance.finished_at).strftime('%Y-%m-%dT%H:%M')
            if self.instance.whatsapp_notification_sent_at:
                self.initial['whatsapp_notification_sent_at'] = _safe_localtime(self.instance.whatsapp_notification_sent_at).strftime('%Y-%m-%dT%H:%M')
            if self.instance.whatsapp_confirmation_received_at:
                self.initial['whatsapp_confirmation_received_at'] = _safe_localtime(self.instance.whatsapp_confirmation_received_at).strftime('%Y-%m-%dT%H:%M')

    def clean(self):
        cleaned_data = super().clean()
        billable_types = [
            ServiceOrderTask.TaskType.EXECUCAO,
            ServiceOrderTask.TaskType.GARANTIA,
            ServiceOrderTask.TaskType.RETORNO,
        ]
        if cleaned_data.get('task_type') in billable_types and not cleaned_data.get('preferred_payment_method'):
            self.add_error('preferred_payment_method', 'Selecione a forma de pagamento para esta etapa.')
        return cleaned_data

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
            'name', 'category', 'supplier', 'code', 'barcode', 'image', 
            'unit_type', 'format', 'type', 'preco_custo', 'preco_custo_total',
            'preco_venda_total', 'default_unit_price', 'current_stock', 'min_stock', 'max_stock', 'is_active',
            'ncm', 'cest', 'cfop_padrao', 'origem_mercadoria',
            'csosn', 'cst_icms', 'cst_pis', 'cst_cofins',
            'aliquota_ibpt_fed', 'aliquota_ibpt_est', 'aliquota_ibpt_mun'
        ]
        widgets = {
            'name': forms.TextInput(attrs={'class': 'w-full px-4 py-3 rounded-xl border border-slate-200 focus:ring-2 focus:ring-blue-500 focus:border-blue-500 outline-none transition-all'}),
            'category': forms.Select(attrs={'class': 'w-full px-4 py-3 rounded-xl border border-slate-200 focus:ring-2 focus:ring-blue-500 focus:border-blue-500 outline-none transition-all'}),
            'supplier': forms.Select(attrs={'class': 'w-full px-4 py-3 rounded-xl border border-slate-200 focus:ring-2 focus:ring-blue-500 focus:border-blue-500 outline-none transition-all'}),
            'code': forms.TextInput(attrs={'class': 'w-full px-4 py-3 rounded-xl border border-slate-200 focus:ring-2 focus:ring-blue-500 focus:border-blue-500 outline-none transition-all'}),
            'barcode': forms.TextInput(attrs={'class': 'w-full px-4 py-3 rounded-xl border border-slate-200 focus:ring-2 focus:ring-blue-500 focus:border-blue-500 outline-none transition-all'}),
            'unit_type': forms.Select(attrs={'class': 'w-full px-4 py-3 rounded-xl border border-slate-200 focus:ring-2 focus:ring-blue-500 focus:border-blue-500 outline-none transition-all'}),
            'format': forms.Select(attrs={'class': 'w-full px-4 py-3 rounded-xl border border-slate-200 focus:ring-2 focus:ring-blue-500 focus:border-blue-500 outline-none transition-all', 'onchange': 'toggleCompositionTab()'}),
            'type': forms.Select(attrs={'class': 'w-full px-4 py-3 rounded-xl border border-slate-200 focus:ring-2 focus:ring-blue-500 focus:border-blue-500 outline-none transition-all'}),
            'preco_custo': forms.NumberInput(attrs={'class': 'w-full px-4 py-3 rounded-xl border border-slate-200 focus:ring-2 focus:ring-blue-500 focus:border-blue-500 outline-none transition-all', 'step': '0.01'}),
            'preco_custo_total': forms.NumberInput(attrs={'class': 'w-full px-4 py-3 rounded-xl border border-slate-200 focus:ring-2 focus:ring-blue-500 focus:border-blue-500 outline-none transition-all', 'step': '0.01', 'readonly': 'readonly'}),
            'preco_venda_total': forms.NumberInput(attrs={'class': 'w-full px-4 py-3 rounded-xl border border-slate-200 focus:ring-2 focus:ring-blue-500 focus:border-blue-500 outline-none transition-all', 'step': '0.01', 'readonly': 'readonly'}),
            'default_unit_price': forms.NumberInput(attrs={'class': 'w-full px-4 py-3 rounded-xl border border-slate-200 focus:ring-2 focus:ring-blue-500 focus:border-blue-500 outline-none transition-all', 'step': '0.01'}),
            'current_stock': forms.NumberInput(attrs={'class': 'w-full px-4 py-3 rounded-xl border border-slate-200 bg-slate-50 font-mono focus:ring-2 focus:ring-blue-500 focus:border-blue-500 outline-none transition-all', 'step': '0.01'}),
            'min_stock': forms.NumberInput(attrs={'class': 'w-full px-4 py-3 rounded-xl border border-slate-200 focus:ring-2 focus:ring-amber-500 focus:border-amber-500 outline-none transition-all', 'step': '0.01', 'min': '0'}),
            'max_stock': forms.NumberInput(attrs={'class': 'w-full px-4 py-3 rounded-xl border border-slate-200 focus:ring-2 focus:ring-emerald-500 focus:border-emerald-500 outline-none transition-all', 'step': '0.01', 'min': '0'}),
            'is_active': forms.CheckboxInput(attrs={'class': 'w-5 h-5 text-emerald-600 border-slate-300 rounded focus:ring-emerald-500 transition-all cursor-pointer'}),
            'image': forms.ClearableFileInput(attrs={'class': 'hidden', 'accept': 'image/*'}),

            # Fiscais
            'ncm': forms.TextInput(attrs={'class': 'w-full px-4 py-3 rounded-xl border border-slate-200 focus:ring-2 focus:ring-blue-500 focus:border-blue-500 outline-none transition-all'}),
            'cest': forms.TextInput(attrs={'class': 'w-full px-4 py-3 rounded-xl border border-slate-200 focus:ring-2 focus:ring-blue-500 focus:border-blue-500 outline-none transition-all'}),
            'cfop_padrao': forms.TextInput(attrs={'class': 'w-full px-4 py-3 rounded-xl border border-slate-200 focus:ring-2 focus:ring-blue-500 focus:border-blue-500 outline-none transition-all'}),
            'origem_mercadoria': forms.Select(attrs={'class': 'w-full px-4 py-3 rounded-xl border border-slate-200 focus:ring-2 focus:ring-blue-500 focus:border-blue-500 outline-none transition-all'}),
            'csosn': forms.TextInput(attrs={'class': 'w-full px-4 py-3 rounded-xl border border-slate-200 focus:ring-2 focus:ring-blue-500 focus:border-blue-500 outline-none transition-all'}),
            'cst_icms': forms.TextInput(attrs={'class': 'w-full px-4 py-3 rounded-xl border border-slate-200 focus:ring-2 focus:ring-blue-500 focus:border-blue-500 outline-none transition-all'}),
            'cst_pis': forms.TextInput(attrs={'class': 'w-full px-4 py-3 rounded-xl border border-slate-200 focus:ring-2 focus:ring-blue-500 focus:border-blue-500 outline-none transition-all'}),
            'cst_cofins': forms.TextInput(attrs={'class': 'w-full px-4 py-3 rounded-xl border border-slate-200 focus:ring-2 focus:ring-blue-500 focus:border-blue-500 outline-none transition-all'}),
            'aliquota_ibpt_fed': forms.NumberInput(attrs={'class': 'w-full px-4 py-3 rounded-xl border border-slate-200 focus:ring-2 focus:ring-blue-500 focus:border-blue-500 outline-none transition-all', 'step': '0.01'}),
            'aliquota_ibpt_est': forms.NumberInput(attrs={'class': 'w-full px-4 py-3 rounded-xl border border-slate-200 focus:ring-2 focus:ring-blue-500 focus:border-blue-500 outline-none transition-all', 'step': '0.01'}),
            'aliquota_ibpt_mun': forms.NumberInput(attrs={'class': 'w-full px-4 py-3 rounded-xl border border-slate-200 focus:ring-2 focus:ring-blue-500 focus:border-blue-500 outline-none transition-all', 'step': '0.01'}),
        }


class ProductCompositionForm(forms.ModelForm):
    class Meta:
        model = ProductComposition
        fields = ['component', 'quantity']
        widgets = {
            'component': forms.Select(attrs={
                'class': 'w-full px-4 py-3 rounded-xl border border-slate-200 focus:ring-2 focus:ring-blue-500 focus:border-blue-500 outline-none transition-all component-select',
                'onchange': 'calculateCompositionTotals()'
            }),
            'quantity': forms.NumberInput(attrs={
                'class': 'w-full px-4 py-3 rounded-xl border border-slate-200 focus:ring-2 focus:ring-blue-500 focus:border-blue-500 outline-none transition-all quantity-input', 
                'step': '0.01',
                'oninput': 'calculateCompositionTotals()'
            }),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Filtra para mostrar apenas matéria prima por padrão
        self.fields['component'].queryset = Product.objects.filter(type=Product.Type.MATERIA_PRIMA)
        
        # Adiciona atributos de dados para facilitar o cálculo no frontend
        # Nota: Isso pode ser pesado se houver muitos produtos. 
        # Para performance ideal, usaríamos AJAX no onchange do select.
        # Mas como é restrito a MATERIA_PRIMA, vamos tentar por enquanto.
        choices = [('', 'Selecione um componente...')]
        for p in self.fields['component'].queryset:
            choices.append((p.id, p.name, {
                'data-cost': str(p.preco_custo),
                'data-price': str(p.default_unit_price)
            }))
        
        # Para o widget de Select do Django, passar os data-attrs exige customização ou JS.
        # Vamos usar JS para buscar os dados via AJAX em vez de sobrecarregar o HTML.


ProductCompositionFormSet = inlineformset_factory(
    Product, ProductComposition,
    form=ProductCompositionForm,
    extra=1,
    can_delete=True,
    fk_name='parent'
)


class ProductVariantForm(forms.ModelForm):
    class Meta:
        model = ProductVariant
        fields = ['name', 'code', 'additional_price', 'current_stock', 'min_stock', 'is_active']
        widgets = {
            'name': forms.TextInput(attrs={
                'class': 'w-full px-4 py-2.5 rounded-xl border border-slate-200 focus:ring-2 focus:ring-purple-500 focus:border-purple-500 outline-none transition-all text-sm',
                'placeholder': 'Ex: Azul P, Vermelho GG…',
            }),
            'code': forms.TextInput(attrs={
                'class': 'w-full px-4 py-2.5 rounded-xl border border-slate-200 focus:ring-2 focus:ring-purple-500 focus:border-purple-500 outline-none transition-all text-sm font-mono',
                'placeholder': 'SKU da variação',
            }),
            'additional_price': forms.NumberInput(attrs={
                'class': 'w-full px-4 py-2.5 rounded-xl border border-slate-200 focus:ring-2 focus:ring-purple-500 focus:border-purple-500 outline-none transition-all text-sm',
                'step': '0.01',
                'placeholder': '0,00',
            }),
            'current_stock': forms.NumberInput(attrs={
                'class': 'w-full px-4 py-2.5 rounded-xl border border-slate-200 focus:ring-2 focus:ring-purple-500 focus:border-purple-500 outline-none transition-all text-sm font-mono',
                'step': '0.01',
                'placeholder': '0',
            }),
            'min_stock': forms.NumberInput(attrs={
                'class': 'w-full px-4 py-2.5 rounded-xl border border-slate-200 focus:ring-2 focus:ring-amber-500 focus:border-amber-500 outline-none transition-all text-sm font-mono',
                'step': '0.01',
                'placeholder': '0',
            }),
            'is_active': forms.CheckboxInput(attrs={
                'class': 'rounded border-slate-300 text-purple-600 focus:ring-purple-500',
            }),
        }


ProductVariantFormSet = inlineformset_factory(
    Product, ProductVariant,
    form=ProductVariantForm,
    extra=1,
    can_delete=True,
)


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
    class Meta:
        model = Sale
        fields = [
            'client', 'status', 'discount', 'surcharge',
            'indicador_presenca', 'modalidade_frete', 'forma_pagamento_sefaz',
            'external_po_number', 'delivery_date', 'commission_rate',
            'notes_internal', 'notes_customer',
            'delivery_name', 'delivery_cep', 'delivery_address', 'delivery_number',
            'delivery_complement', 'delivery_neighborhood', 'delivery_city', 'delivery_state',
        ]
        widgets = {
            'client': forms.Select(attrs={'class': 'w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500 bg-white search-select'}),
            'status': forms.Select(attrs={'class': 'w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500'}),
            'discount': forms.NumberInput(attrs={'class': 'w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500', 'step': '0.01'}),
            'surcharge': forms.NumberInput(attrs={'class': 'w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500', 'step': '0.01'}),
            'indicador_presenca': forms.Select(attrs={'class': 'w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500'}),
            'modalidade_frete': forms.Select(attrs={'class': 'w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500'}),
            'forma_pagamento_sefaz': forms.Select(attrs={'class': 'w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500'}),
            'external_po_number': forms.TextInput(attrs={'class': 'w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500', 'placeholder': 'N° do pedido do cliente'}),
            'delivery_date': forms.DateInput(attrs={'class': 'w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500', 'type': 'date'}),
            'commission_rate': forms.NumberInput(attrs={'class': 'w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500', 'step': '0.01', 'min': '0', 'max': '100'}),
            'notes_internal': forms.Textarea(attrs={'class': 'w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500', 'rows': 3, 'placeholder': 'Observações internas (não aparecem para o cliente)'}),
            'notes_customer': forms.Textarea(attrs={'class': 'w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500', 'rows': 3, 'placeholder': 'Observações para o cliente (aparecem no recibo/PDF)'}),
            'delivery_name': forms.TextInput(attrs={'class': 'w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500', 'placeholder': 'Nome do destinatário'}),
            'delivery_cep': forms.TextInput(attrs={'class': 'w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500', 'placeholder': '00000-000'}),
            'delivery_address': forms.TextInput(attrs={'class': 'w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500', 'placeholder': 'Rua, Av...'}),
            'delivery_number': forms.TextInput(attrs={'class': 'w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500', 'placeholder': 'N°'}),
            'delivery_complement': forms.TextInput(attrs={'class': 'w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500', 'placeholder': 'Apto, Sala...'}),
            'delivery_neighborhood': forms.TextInput(attrs={'class': 'w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500', 'placeholder': 'Bairro'}),
            'delivery_city': forms.TextInput(attrs={'class': 'w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500', 'placeholder': 'Cidade'}),
            'delivery_state': forms.TextInput(attrs={'class': 'w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500', 'placeholder': 'UF', 'maxlength': '2'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['discount'].required = False
        self.fields['surcharge'].required = False
        self.fields['commission_rate'].required = False
        self.fields['external_po_number'].required = False
        self.fields['delivery_date'].required = False
        self.fields['notes_internal'].required = False
        self.fields['notes_customer'].required = False
        for field in ['delivery_name', 'delivery_cep', 'delivery_address', 'delivery_number',
                      'delivery_complement', 'delivery_neighborhood', 'delivery_city', 'delivery_state']:
            self.fields[field].required = False

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
            'tarifa_minima', 'tarifa_fixa', 'prazo_recebimento', 'codigo_sefaz', 'ativo',
            'integra_gateway',
        ]
        widgets = {
            'descricao': forms.TextInput(attrs={'class': 'w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500', 'placeholder': 'Ex: Cartão de Crédito Visa'}),
            'tipo_provedor': forms.Select(attrs={'class': 'w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500'}),
            'tarifa_porcentagem': forms.NumberInput(attrs={'class': 'w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500', 'step': '0.01'}),
            'tarifa_minima': forms.NumberInput(attrs={'class': 'w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500', 'step': '0.01'}),
            'tarifa_fixa': forms.NumberInput(attrs={'class': 'w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500', 'step': '0.01'}),
            'prazo_recebimento': forms.NumberInput(attrs={'class': 'w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500'}),
            'codigo_sefaz': forms.TextInput(attrs={'class': 'w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500', 'placeholder': 'Ex: 03'}),
            'ativo': forms.CheckboxInput(attrs={'class': 'h-4 w-4 text-blue-600 focus:ring-blue-500 border-gray-300 rounded'}),
            'integra_gateway': forms.CheckboxInput(attrs={'class': 'switch-checkbox peer sr-only'}),
        }

# --- EXPENSE FORMS ---

class ExpenseInstallmentForm(forms.ModelForm):
    class Meta:
        model = ExpenseInstallment
        fields = ['installment_number', 'amount', 'due_date']
        widgets = {
            'installment_number': forms.TextInput(attrs={'class': 'w-full px-2 py-1 border rounded-lg bg-gray-50', 'readonly': 'readonly'}),
            'amount': forms.NumberInput(attrs={'class': 'w-full px-2 py-1 border rounded-lg focus:ring-2 focus:ring-blue-500', 'step': '0.01'}),
            'due_date': forms.DateInput(
                format='%Y-%m-%d',
                attrs={'type': 'date', 'class': 'w-full px-2 py-1 border rounded-lg focus:ring-2 focus:ring-blue-500'}
            ),
        }

ExpenseInstallmentFormSet = inlineformset_factory(
    Expense, ExpenseInstallment,
    form=ExpenseInstallmentForm,
    extra=0,
    can_delete=False,
    min_num=1,
    validate_min=True
)


class ExpenseForm(forms.ModelForm):
    INPUT_CLASS = 'flex h-10 w-full rounded-md border border-slate-300 bg-transparent px-3 py-2 text-sm placeholder:text-slate-400 focus:outline-none focus:ring-2 focus:ring-slate-400 focus:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50'

    end_date = forms.DateField(
        required=False,
        label='Data de Fim da Recorrência',
        help_text='Deixe em branco para recorrência sem data de fim.',
        widget=forms.DateInput(format='%Y-%m-%d', attrs={'type': 'date'}),
    )

    class Meta:
        model = Expense
        fields = [
            'supplier', 'category', 'description', 'total_amount',
            'issue_date', 'is_recurrent', 'frequency', 'installments_count'
        ]
        widgets = {
            'supplier': forms.Select(attrs={'class': 'w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500 search-select'}),
            'category': forms.Select(attrs={'class': 'w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500'}),
            'description': forms.TextInput(attrs={'class': 'w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500'}),
            'total_amount': forms.NumberInput(attrs={'class': 'w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500', 'step': '0.01'}),
            'issue_date': forms.DateInput(
                format='%Y-%m-%d',
                attrs={'type': 'date', 'class': 'w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500'}
            ),
            'is_recurrent': forms.CheckboxInput(attrs={'class': 'h-4 w-4 text-blue-600 focus:ring-blue-500 border-gray-300 rounded'}),
            'frequency': forms.Select(attrs={'class': 'w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500'}),
            'installments_count': forms.NumberInput(attrs={'class': 'w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500', 'min': 1}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Pré-popula end_date ao editar uma despesa com regra de recorrência
        if self.instance and self.instance.pk and self.instance.recurrence_rule:
            self.fields['end_date'].initial = self.instance.recurrence_rule.end_date
        self.fields['end_date'].widget.attrs['class'] = self.INPUT_CLASS

    def clean(self):
        cleaned_data = super().clean()
        is_recurrent = cleaned_data.get('is_recurrent')
        frequency = cleaned_data.get('frequency')
        installments_count = cleaned_data.get('installments_count')

        if is_recurrent and not frequency:
            self.add_error('frequency', 'A frequência é obrigatória para despesas recorrentes.')

        if not is_recurrent and installments_count and installments_count > 1 and not frequency:
            self.add_error('frequency', 'A frequência é obrigatória se houver mais de uma parcela.')

        return cleaned_data


class FinanceSettingsForm(forms.ModelForm):
    class Meta:
        model = FinanceSettings
        fields = ['days_before_generation', 'enable_commission', 'auto_billing_on_task_completion']
        widgets = {
            'days_before_generation': forms.NumberInput(attrs={
                'class': 'flex h-10 w-full rounded-md border border-slate-300 bg-transparent px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-slate-400 focus:ring-offset-2',
                'min': 1,
                'max': 90,
            }),
            'enable_commission': forms.CheckboxInput(attrs={
                'class': 'h-4 w-4 text-blue-600 focus:ring-blue-500 border-slate-300 rounded',
            }),
            'auto_billing_on_task_completion': forms.CheckboxInput(attrs={
                'class': 'h-4 w-4 text-blue-600 focus:ring-blue-500 border-slate-300 rounded',
            }),
        }


class SaleSettingsForm(forms.ModelForm):
    class Meta:
        model = SaleSettings
        fields = ['billing_trigger_status']
        widgets = {
            'billing_trigger_status': forms.Select(attrs={
                'class': 'w-full rounded-lg border border-slate-300 bg-white px-3 py-2.5 text-sm font-medium text-slate-700 focus:outline-none focus:ring-2 focus:ring-slate-400 focus:border-slate-400 pr-8',
            }),
        }
