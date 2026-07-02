from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('integrations_sap_b1', '0005_sapb1exportlog'),
    ]

    operations = [
        migrations.AddField(
            model_name='sapb1exportlog',
            name='conflict',
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name='sapb1exportlog',
            name='conflict_reason',
            field=models.TextField(blank=True, default=''),
            preserve_default=False,
        ),
    ]
