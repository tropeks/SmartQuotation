"""
RBAC V2 — M0. Backfill retroativo das capabilities novas de assinatura de estágio
(approval.technical_sign/commercial_sign/quality_sign/custom_sign_1..3) e role.manage
em cada schema de tenant.

seed_access_matrix é get_or_create: cria SÓ as linhas RolePermission ausentes (as dos
codes novos) conforme a DEFAULT_MATRIX, sem sobrescrever customizações já feitas por um
admin nas capabilities antigas. Idempotente; reversível como no-op. As capabilities novas
ainda NÃO são enforced (M0 é só catálogo + matriz) — nada de comportamento muda.
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
        ("access", "0003_seed_approval_stages"),
    ]

    operations = [
        migrations.RunPython(forwards, backwards),
    ]
