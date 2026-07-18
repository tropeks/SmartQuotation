"""
Backfill: semeia os 5 papéis built-in (viewer, orcamentista, engenheiro, gestor_comercial,
admin) em cada schema de tenant durante migrate_schemas --tenant. Idempotente; reversível
como no-op. `key` idêntica aos antigos enums de UserProfile.ROLE — o contrato de resolução
de permissão (matriz/cache/user_role) não muda. `requires_crea` só no engenheiro.
"""
from django.db import migrations


def forwards(apps, schema_editor):
    Role = apps.get_model("accounts", "Role")
    from apps.accounts.models import seed_roles

    seed_roles(model=Role)


def backwards(apps, schema_editor):
    # Não removemos papéis no downgrade (poderiam estar em uso por perfis).
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0004_role_and_crea_trait"),
    ]

    operations = [
        migrations.RunPython(forwards, backwards),
    ]
