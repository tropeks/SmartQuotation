"""
Backfill retroativo: semeia a DEFAULT_MATRIX em cada schema de tenant durante
migrate_schemas --tenant (e nos schemas de teste do django-tenants, para que o
enforcement por capability funcione nos testes das demais apps). Idempotente
(get_or_create), reversível como no-op.

Os testes PRÓPRIOS da app access que criam linhas RolePermission específicas
(tests_enforcement, tests_matrix) limpam a tabela no setUp para ter slate limpo.
"""
from django.db import migrations


def forwards(apps, schema_editor):
    RolePermission = apps.get_model("access", "RolePermission")
    from apps.access.matrix import seed_access_matrix

    seed_access_matrix(model=RolePermission)


def backwards(apps, schema_editor):
    # Não removemos linhas no downgrade (poderiam conter customizações de admin).
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("access", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(forwards, backwards),
    ]
