"""
Schema public — infraestrutura multi-tenant (django-tenants).
Versão mínima do bootstrap; TenantConfig completo vem na task de tenants.
"""
from django.db import models
from django_tenants.models import TenantMixin, DomainMixin


class Plan(models.Model):
    name = models.CharField(max_length=100)              # Starter, Professional, Enterprise
    max_users = models.IntegerField(default=10)
    max_quotations_month = models.IntegerField(null=True, blank=True)
    price_brl_monthly = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name


class Tenant(TenantMixin):
    name = models.CharField(max_length=255)              # nome da empresa cliente
    plan = models.ForeignKey(Plan, null=True, blank=True, on_delete=models.SET_NULL)
    is_active = models.BooleanField(default=True)
    trial_ends_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    auto_create_schema = True

    def __str__(self):
        return f"{self.name} ({self.schema_name})"


class Domain(DomainMixin):
    pass
