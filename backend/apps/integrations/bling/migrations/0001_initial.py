import encrypted_model_fields.fields
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = []

    operations = [
        migrations.CreateModel(
            name="BlingIntegrationConfig",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("provider", models.CharField(default="bling", editable=False, max_length=20, unique=True)),
                ("enabled", models.BooleanField(default=False)),
                ("client_id", encrypted_model_fields.fields.EncryptedCharField(blank=True)),
                ("client_secret", encrypted_model_fields.fields.EncryptedCharField(blank=True)),
                ("access_token", encrypted_model_fields.fields.EncryptedCharField(blank=True)),
                ("refresh_token", encrypted_model_fields.fields.EncryptedCharField(blank=True)),
                ("token_expires_at", models.DateTimeField(blank=True, null=True)),
                ("company_id", models.CharField(blank=True, max_length=100)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={
                "verbose_name": "Configuracao Bling",
                "verbose_name_plural": "Configuracoes Bling",
            },
        ),
    ]
