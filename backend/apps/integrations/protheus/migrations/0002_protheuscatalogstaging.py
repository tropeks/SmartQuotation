from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("integrations_protheus", "0001_initial"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="ProtheusCatalogStaging",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("provider", models.CharField(default="protheus", max_length=20)),
                (
                    "entity_type",
                    models.CharField(
                        choices=[("material", "Material"), ("supplier", "Supplier")],
                        max_length=20,
                    ),
                ),
                ("remote_code", models.CharField(max_length=100)),
                ("payload_hash", models.CharField(max_length=64)),
                ("payload", models.JSONField(blank=True, default=dict)),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("pending", "Pending"),
                            ("applied", "Applied"),
                            ("rejected", "Rejected"),
                            ("failed", "Failed"),
                        ],
                        default="pending",
                        max_length=20,
                    ),
                ),
                ("applied_object_model", models.CharField(blank=True, max_length=100)),
                ("applied_object_id", models.CharField(blank=True, max_length=50)),
                ("error_message", models.TextField(blank=True)),
                ("reviewed_at", models.DateTimeField(blank=True, null=True)),
                ("applied_at", models.DateTimeField(blank=True, null=True)),
                ("rejected_at", models.DateTimeField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "reviewed_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="protheus_catalog_reviews",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "source_run",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="catalog_staging_entries",
                        to="integrations_protheus.protheussyncrun",
                    ),
                ),
            ],
            options={
                "ordering": ["-created_at"],
            },
        ),
        migrations.AddConstraint(
            model_name="protheuscatalogstaging",
            constraint=models.UniqueConstraint(
                fields=("provider", "entity_type", "remote_code", "payload_hash"),
                name="uniq_protheus_catalog_staging_payload",
            ),
        ),
        migrations.AddIndex(
            model_name="protheuscatalogstaging",
            index=models.Index(fields=["entity_type", "status"], name="integration_entity__e48cfd_idx"),
        ),
        migrations.AddIndex(
            model_name="protheuscatalogstaging",
            index=models.Index(fields=["remote_code", "status"], name="integration_remote__c0d9b2_idx"),
        ),
    ]
