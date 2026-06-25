from django.db import migrations, models
import django.db.models.deletion
import uuid


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        ("materials", "0002_ligametalurgica"),
    ]

    operations = [
        migrations.CreateModel(
            name="ProtheusIntegrationConfig",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("provider", models.CharField(default="protheus", max_length=20, unique=True)),
                ("enabled", models.BooleanField(default=False)),
                ("base_url", models.URLField(blank=True)),
                ("company_code", models.CharField(blank=True, max_length=20)),
                ("branch_code", models.CharField(blank=True, max_length=20)),
                ("environment", models.CharField(blank=True, max_length=50)),
                ("auth_type", models.CharField(choices=[("basic", "Basic"), ("token", "Token")], default="basic", max_length=20)),
                ("username", models.CharField(blank=True, max_length=255)),
                ("password", models.CharField(blank=True, max_length=255)),
                ("token", models.CharField(blank=True, max_length=255)),
                ("timeout_seconds", models.PositiveIntegerField(default=30)),
                ("export_on_release", models.BooleanField(default=True)),
                ("pull_materials_enabled", models.BooleanField(default=True)),
                ("pull_suppliers_enabled", models.BooleanField(default=True)),
                ("pull_work_orders_enabled", models.BooleanField(default=True)),
                ("last_healthcheck_at", models.DateTimeField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={
                "verbose_name": "Configuracao Protheus",
                "verbose_name_plural": "Configuracoes Protheus",
            },
        ),
        migrations.CreateModel(
            name="ProtheusSupplier",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("supplier_code", models.CharField(max_length=100, unique=True)),
                ("legal_name", models.CharField(max_length=255)),
                ("cnpj", models.CharField(blank=True, max_length=18)),
                ("email", models.EmailField(blank=True, max_length=254)),
                ("phone", models.CharField(blank=True, max_length=50)),
                ("city", models.CharField(blank=True, max_length=100)),
                ("state", models.CharField(blank=True, max_length=2)),
                ("is_active", models.BooleanField(default=True)),
                ("payload", models.JSONField(blank=True, default=dict)),
                ("last_synced_at", models.DateTimeField(auto_now=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
            ],
            options={"ordering": ["supplier_code"]},
        ),
        migrations.CreateModel(
            name="ProtheusSyncRun",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("provider", models.CharField(default="protheus", max_length=20)),
                ("direction", models.CharField(choices=[("push", "Push"), ("pull", "Pull")], max_length=10)),
                ("entity_type", models.CharField(choices=[("work_order", "Work Order"), ("bom", "BOM"), ("material", "Material"), ("supplier", "Supplier")], max_length=20)),
                ("status", models.CharField(choices=[("pending", "Pending"), ("success", "Success"), ("failed", "Failed"), ("skipped", "Skipped")], default="pending", max_length=20)),
                ("trigger", models.CharField(default="manual", max_length=30)),
                ("idempotency_key", models.CharField(max_length=255, unique=True)),
                ("correlation_id", models.UUIDField(default=uuid.uuid4, editable=False)),
                ("local_model", models.CharField(blank=True, max_length=100)),
                ("local_id", models.CharField(blank=True, max_length=50)),
                ("remote_code", models.CharField(blank=True, max_length=100)),
                ("payload_hash", models.CharField(blank=True, max_length=64)),
                ("payload", models.JSONField(blank=True, default=dict)),
                ("result_payload", models.JSONField(blank=True, default=dict)),
                ("error_message", models.TextField(blank=True)),
                ("started_at", models.DateTimeField(auto_now_add=True)),
                ("finished_at", models.DateTimeField(blank=True, null=True)),
            ],
            options={
                "ordering": ["-started_at"],
                "indexes": [
                    models.Index(fields=["direction", "entity_type", "status"], name="integration_directi_3831b0_idx"),
                    models.Index(fields=["local_model", "local_id"], name="integration_local_m_4bb1a9_idx"),
                ],
            },
        ),
        migrations.CreateModel(
            name="ProtheusWorkOrderSnapshot",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("remote_code", models.CharField(max_length=100, unique=True)),
                ("title", models.CharField(blank=True, max_length=500)),
                ("customer_name", models.CharField(blank=True, max_length=255)),
                ("status", models.CharField(blank=True, max_length=50)),
                ("payload", models.JSONField(blank=True, default=dict)),
                ("last_synced_at", models.DateTimeField(auto_now=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
            ],
            options={"ordering": ["remote_code"]},
        ),
        migrations.CreateModel(
            name="ProtheusSyncBinding",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("provider", models.CharField(default="protheus", max_length=20)),
                ("entity_type", models.CharField(choices=[("work_order", "Work Order"), ("bom", "BOM"), ("material", "Material"), ("supplier", "Supplier")], max_length=20)),
                ("local_model", models.CharField(max_length=100)),
                ("local_id", models.CharField(max_length=50)),
                ("remote_id", models.CharField(blank=True, max_length=100)),
                ("remote_code", models.CharField(blank=True, max_length=100, null=True)),
                ("payload_hash", models.CharField(blank=True, max_length=64)),
                ("last_direction", models.CharField(choices=[("push", "Push"), ("pull", "Pull")], max_length=10)),
                ("source_of_truth", models.CharField(choices=[("smartquotation", "SmartQuotation"), ("protheus", "Protheus"), ("mixed", "Mixed")], default="mixed", max_length=20)),
                ("metadata", models.JSONField(blank=True, default=dict)),
                ("last_synced_at", models.DateTimeField(auto_now=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
            ],
            options={
                "indexes": [
                    models.Index(fields=["entity_type", "local_model", "local_id"], name="integration_entity__c206f4_idx"),
                    models.Index(fields=["entity_type", "remote_code"], name="integration_entity__fb4ac4_idx"),
                ],
                "constraints": [
                    models.UniqueConstraint(fields=("provider", "entity_type", "local_model", "local_id"), name="uniq_protheus_binding_local"),
                    models.UniqueConstraint(fields=("provider", "entity_type", "remote_code"), name="uniq_protheus_binding_remote_code"),
                ],
            },
        ),
        migrations.CreateModel(
            name="ProtheusBOMSnapshot",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("payload", models.JSONField(blank=True, default=dict)),
                ("last_synced_at", models.DateTimeField(auto_now=True)),
                ("work_order", models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name="bom_snapshot", to="integrations_protheus.protheusworkordersnapshot")),
            ],
        ),
        migrations.CreateModel(
            name="ProtheusSyncAttempt",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("sequence", models.PositiveSmallIntegerField()),
                ("status", models.CharField(choices=[("success", "Success"), ("failed", "Failed")], max_length=20)),
                ("request_payload", models.JSONField(blank=True, default=dict)),
                ("response_payload", models.JSONField(blank=True, default=dict)),
                ("error_message", models.TextField(blank=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("run", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="attempts", to="integrations_protheus.protheussyncrun")),
            ],
            options={
                "ordering": ["sequence", "created_at"],
                "constraints": [models.UniqueConstraint(fields=("run", "sequence"), name="uniq_protheus_attempt_sequence")],
            },
        ),
    ]
