# Generated manually for the isolated sap_b1 tenant app.
from django.db import migrations, models
import django.db.models.deletion
import django.utils.timezone
import uuid


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        ("production", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="SapB1IntegrationConfig",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("provider", models.CharField(default="sap_b1", editable=False, max_length=20, unique=True)),
                ("enabled", models.BooleanField(default=False)),
                ("base_url", models.URLField(blank=True)),
                ("company_db", models.CharField(blank=True, max_length=100)),
                ("username", models.CharField(blank=True, max_length=255)),
                ("password", models.CharField(blank=True, max_length=255)),
                ("timeout_seconds", models.PositiveIntegerField(default=30)),
                ("sync_sales_orders_enabled", models.BooleanField(default=True)),
                ("sync_boms_enabled", models.BooleanField(default=True)),
                ("last_healthcheck_at", models.DateTimeField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={
                "verbose_name": "Configuracao SAP B1",
                "verbose_name_plural": "Configuracoes SAP B1",
                "app_label": "integrations_sap_b1",
            },
        ),
        migrations.CreateModel(
            name="SapB1SyncRun",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("provider", models.CharField(default="sap_b1", max_length=20)),
                ("direction", models.CharField(choices=[("push", "Push")], max_length=10)),
                ("entity_type", models.CharField(choices=[("sales_order", "Sales Order"), ("bom", "BOM")], max_length=20)),
                ("status", models.CharField(choices=[("pending", "Pending"), ("processing", "Processing"), ("success", "Success"), ("failed", "Failed"), ("skipped", "Skipped")], default="pending", max_length=20)),
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
                "app_label": "integrations_sap_b1",
            },
        ),
        migrations.CreateModel(
            name="SapB1SyncBinding",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("provider", models.CharField(default="sap_b1", max_length=20)),
                ("entity_type", models.CharField(choices=[("sales_order", "Sales Order"), ("bom", "BOM")], max_length=20)),
                ("local_model", models.CharField(max_length=100)),
                ("local_id", models.CharField(max_length=50)),
                ("remote_code", models.CharField(blank=True, max_length=100)),
                ("payload_hash", models.CharField(blank=True, max_length=64)),
                ("last_direction", models.CharField(choices=[("push", "Push")], max_length=10)),
                ("source_of_truth", models.CharField(choices=[("smartquotation", "SmartQuotation"), ("sap_b1", "SAP B1"), ("mixed", "Mixed")], default="mixed", max_length=20)),
                ("metadata", models.JSONField(blank=True, default=dict)),
                ("last_synced_at", models.DateTimeField(auto_now=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
            ],
            options={
                "app_label": "integrations_sap_b1",
            },
        ),
        migrations.CreateModel(
            name="SapB1SyncAttempt",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("sequence", models.PositiveSmallIntegerField()),
                ("status", models.CharField(choices=[("success", "Success"), ("failed", "Failed")], max_length=20)),
                ("request_payload", models.JSONField(blank=True, default=dict)),
                ("response_payload", models.JSONField(blank=True, default=dict)),
                ("error_message", models.TextField(blank=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("run", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="attempts", to="integrations_sap_b1.sapb1syncrun")),
            ],
            options={
                "ordering": ["sequence", "created_at"],
                "app_label": "integrations_sap_b1",
            },
        ),
        migrations.AddIndex(
            model_name="sapb1syncrun",
            index=models.Index(fields=["direction", "entity_type", "status"], name="sap_b1_run_dir_ent_sta_idx"),
        ),
        migrations.AddIndex(
            model_name="sapb1syncrun",
            index=models.Index(fields=["local_model", "local_id"], name="sap_b1_run_local_idx"),
        ),
        migrations.AddIndex(
            model_name="sapb1syncbinding",
            index=models.Index(fields=["entity_type", "local_model", "local_id"], name="sap_b1_bind_local_idx"),
        ),
        migrations.AddIndex(
            model_name="sapb1syncbinding",
            index=models.Index(fields=["entity_type", "remote_code"], name="sap_b1_bind_remote_idx"),
        ),
        migrations.AddConstraint(
            model_name="sapb1syncbinding",
            constraint=models.UniqueConstraint(fields=["provider", "entity_type", "local_model", "local_id"], name="uniq_sap_b1_binding_local"),
        ),
        migrations.AddConstraint(
            model_name="sapb1syncbinding",
            constraint=models.UniqueConstraint(fields=["provider", "entity_type", "remote_code"], name="uniq_sap_b1_binding_remote_code"),
        ),
        migrations.AddConstraint(
            model_name="sapb1syncattempt",
            constraint=models.UniqueConstraint(fields=["run", "sequence"], name="uniq_sap_b1_attempt_sequence"),
        ),
    ]
