"""
Backfill retroativo (T7): semeia os ApprovalStage default em cada schema de tenant
durante migrate_schemas --tenant (e nos schemas de teste do django-tenants). Semeia
apenas o estágio built-in `technical` (aprovação técnica CREA), required e travado.
Idempotente (update/get_or_create), reversível como no-op.
"""
from django.db import migrations


def forwards(apps, schema_editor):
    ApprovalStage = apps.get_model("access", "ApprovalStage")
    from apps.access.matrix import seed_approval_stages

    seed_approval_stages(model=ApprovalStage)


def backwards(apps, schema_editor):
    # Não removemos estágios no downgrade (poderiam conter customizações de admin).
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("access", "0002_seed_default_matrix"),
    ]

    operations = [
        migrations.RunPython(forwards, backwards),
    ]
