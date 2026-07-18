"""
Testes do invariante de compliance CREA (RBAC V2 M1): um papel que assina o estágio
técnico (approval.technical_sign) DEVE ter requires_crea=True — resolve o risco silencioso
descrito na issue #86.
"""
from django_tenants.test.cases import TenantTestCase as TestCase

from apps.accounts.models import Role, UserProfile
from apps.access.compliance import TECHNICAL_SIGN_CAP, technical_sign_compliance_ok
from apps.access.models import RolePermission


class TechnicalSignComplianceTests(TestCase):
    def test_seed_default_satisfaz_invariante(self):
        # A matriz-semente concede technical_sign só ao engenheiro, que tem requires_crea.
        for role_key in Role.objects.values_list("key", flat=True):
            self.assertTrue(
                technical_sign_compliance_ok(role_key),
                f"papel {role_key} viola o invariante technical_sign×requires_crea no seed",
            )

    def test_papel_sem_technical_sign_sempre_ok(self):
        self.assertTrue(technical_sign_compliance_ok(UserProfile.ROLE_ORCAMENTISTA))

    def test_violacao_technical_sign_sem_requires_crea(self):
        # Papel do zero SEM requires_crea recebendo technical_sign -> viola o invariante.
        Role.objects.create(key="comercial_x", name="Comercial X", requires_crea=False)
        RolePermission.objects.update_or_create(
            role="comercial_x", capability=TECHNICAL_SIGN_CAP, defaults={"allowed": True}
        )
        self.assertFalse(technical_sign_compliance_ok("comercial_x"))

    def test_conformidade_apos_ligar_requires_crea(self):
        role = Role.objects.create(key="comercial_y", name="Comercial Y", requires_crea=False)
        RolePermission.objects.update_or_create(
            role="comercial_y", capability=TECHNICAL_SIGN_CAP, defaults={"allowed": True}
        )
        self.assertFalse(technical_sign_compliance_ok("comercial_y"))
        role.requires_crea = True
        role.save(update_fields=["requires_crea"])
        self.assertTrue(technical_sign_compliance_ok("comercial_y"))
