"""
Backfill: cria o fluxo default `of.convert` em cada schema de tenant e anexa a ele
os ApprovalStage existentes (o técnico built-in e quaisquer estágios legados). Idempotente;
reversível como no-op. Preserva 100% o comportamento de `is_convertible` (mesmos estágios).
"""
from django.db import migrations


def forwards(apps, schema_editor):
    ApprovalWorkflow = apps.get_model("access", "ApprovalWorkflow")
    ApprovalStage = apps.get_model("access", "ApprovalStage")
    from apps.access.workflow_templates import seed_workflow

    seed_workflow(wf_model=ApprovalWorkflow, stage_model=ApprovalStage)


def backwards(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("access", "0005_approvalworkflow_approvalstage_workflow"),
    ]

    operations = [
        migrations.RunPython(forwards, backwards),
    ]
