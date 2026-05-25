from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('services', '0048_serviceordertask_send_whatsapp_confirmation_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='serviceordertask',
            name='chatwoot_confirmation_contact_id',
            field=models.CharField(blank=True, max_length=50, null=True, verbose_name='Chatwoot Contact ID (Confirmação)'),
        ),
        migrations.AddField(
            model_name='serviceordertask',
            name='chatwoot_confirmation_conversation_id',
            field=models.CharField(blank=True, max_length=50, null=True, verbose_name='Chatwoot Conversation ID (Confirmação)'),
        ),
        migrations.AddField(
            model_name='serviceordertask',
            name='chatwoot_confirmation_message_id',
            field=models.CharField(blank=True, max_length=50, null=True, verbose_name='Chatwoot Message ID (Confirmação)'),
        ),
    ]

