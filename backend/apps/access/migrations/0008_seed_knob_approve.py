"""
Config de Engenharia V2 — F2. Backfill retroativo da capability nova `knob.approve`
(aprovar propostas de mudança de knobs sensíveis) em cada schema de tenant.

seed_access_matrix é get_or_create: cria SÓ as linhas RolePermission ausentes (as do code
novo) conforme a DEFAULT_MATRIX, sem tocar customizações já feitas por um admin. Idempotente;
reversível como no-op.
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
        ("access", "0007_approvalworkflow_self_approval_blocked"),
    ]

    operations = [
        migrations.RunPython(forwards, backwards),
    ]
