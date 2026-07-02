from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('integrations_sap_b1', '0003_alter_sapb1integrationconfig_password'),
    ]

    operations = [
        migrations.AddField(
            model_name='sapb1integrationconfig',
            name='auto_export',
            field=models.BooleanField(default=False),
        ),
    ]
