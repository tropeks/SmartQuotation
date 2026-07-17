"""
NO-OP intencional.

O seeding da DEFAULT_MATRIX foi movido para FORA das migrations, para (a) não
pré-semear os schemas de teste do django-tenants — o que quebrava os testes de
enforcement que criam linhas RolePermission específicas (colisão de unique) — e
(b) não acoplar código de app dentro de uma migration.

A matriz é semeada por:
  * `provision_tenant` (hook, tenants novos) — idempotente;
  * `manage.py tenant_command seed_access_matrix` (backfill de tenants existentes,
    passo de deploy, como os demais seeds do projeto).

Esta migration é mantida como no-op só para preservar o histórico já aplicado.
"""
from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("access", "0001_initial"),
    ]

    operations = []
