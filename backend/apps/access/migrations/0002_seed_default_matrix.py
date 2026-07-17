"""
Backfill retroativo: semeia a DEFAULT_MATRIX em cada schema de tenant durante
migrate_schemas --tenant. Idempotente (get_or_create) e reversível como no-op.
"""
from django.db import migrations


def forwards(apps, schema_editor):
    RolePermission = apps.get_model("access", "RolePermission")
    # Import do helper de seed (usa CAPABILITIES/DEFAULT_MATRIX estáticos do código).
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
