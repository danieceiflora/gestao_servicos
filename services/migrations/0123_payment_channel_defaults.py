from django.db import migrations


def configure_channels(apps, schema_editor):
    methods = apps.get_model('services', 'PaymentMethod').objects.using(schema_editor.connection.alias)
    methods.filter(tipo_provedor='BOLETO', integra_gateway=True).update(public_billing_enabled=True)
    methods.filter(tipo_provedor='PIX', pix_type='DYNAMIC').exclude(pos_behavior='DISABLED').update(
        pos_behavior='WAIT_GATEWAY',
    )


class Migration(migrations.Migration):
    dependencies = [('services', '0122_installment_pos_payment_behavior_and_more')]
    operations = [migrations.RunPython(configure_channels, migrations.RunPython.noop)]
