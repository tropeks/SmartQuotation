"""
Testes de RBAC V2 M1 — papéis como dado + trait requires_crea (resolve #86).

Cobre:
- os 5 papéis built-in são semeados com keys idênticas aos antigos enums;
- traits corretos (requires_crea só em engenheiro; is_admin_like só em admin);
- compliance CREA vem do TRAIT, não do nome literal do papel (regressão #86):
  um papel CUSTOM com requires_crea passa a exigir CREA sem nenhum "engenheiro" hard-coded;
- enforcement em clean() E save() (barra objects.create() direto).
"""
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django_tenants.test.cases import TenantTestCase as TestCase

from apps.accounts.models import DEFAULT_ROLES, Role, UserProfile


class SeededRolesTests(TestCase):
    def test_cinco_papeis_semeados_com_keys_dos_enums(self):
        keys = set(Role.objects.values_list("key", flat=True))
        self.assertTrue(
            {
                UserProfile.ROLE_VIEWER,
                UserProfile.ROLE_ORCAMENTISTA,
                UserProfile.ROLE_ENGENHEIRO,
                UserProfile.ROLE_GESTOR_COMERCIAL,
                UserProfile.ROLE_ADMIN,
            }.issubset(keys)
        )

    def test_traits_dos_built_in(self):
        eng = Role.objects.get(key=UserProfile.ROLE_ENGENHEIRO)
        admin = Role.objects.get(key=UserProfile.ROLE_ADMIN)
        orc = Role.objects.get(key=UserProfile.ROLE_ORCAMENTISTA)
        self.assertTrue(eng.requires_crea)
        self.assertFalse(eng.is_admin_like)
        self.assertTrue(admin.is_admin_like)
        self.assertFalse(admin.requires_crea)
        self.assertFalse(orc.requires_crea)

    def test_apenas_engenheiro_requires_crea_por_default(self):
        crea_roles = set(
            Role.objects.filter(requires_crea=True).values_list("key", flat=True)
        )
        self.assertEqual(crea_roles, {UserProfile.ROLE_ENGENHEIRO})

    def test_key_requires_crea_helper(self):
        self.assertTrue(Role.key_requires_crea(UserProfile.ROLE_ENGENHEIRO))
        self.assertFalse(Role.key_requires_crea(UserProfile.ROLE_ORCAMENTISTA))
        self.assertFalse(Role.key_requires_crea(""))
        self.assertFalse(Role.key_requires_crea("papel_inexistente"))

    def test_default_roles_espelha_enum(self):
        self.assertEqual(
            {r["key"] for r in DEFAULT_ROLES},
            {k for k, _ in UserProfile.ROLE},
        )


class CreaTraitEnforcementTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="zé", password="senha-forte-123")

    def test_save_barra_papel_requires_crea_sem_crea(self):
        with self.assertRaises(ValidationError):
            UserProfile.objects.create(
                user=self.user, full_name="Zé", role=UserProfile.ROLE_ENGENHEIRO, crea_number=""
            )

    def test_clean_barra_papel_requires_crea_sem_crea(self):
        profile = UserProfile(
            user=self.user, full_name="Zé", role=UserProfile.ROLE_ENGENHEIRO
        )
        with self.assertRaises(ValidationError):
            profile.full_clean()

    def test_papel_custom_com_requires_crea_exige_crea_sem_nome_engenheiro(self):
        # Regressão #86: compliance CREA acoplado ao TRAIT, não ao nome "engenheiro".
        # Um papel do zero (nome != engenheiro) com requires_crea passa a exigir CREA.
        Role.objects.create(key="tecnico_senior", name="Técnico Sênior", requires_crea=True)
        with self.assertRaises(ValidationError):
            UserProfile.objects.create(
                user=self.user, full_name="Zé", role="tecnico_senior", crea_number=""
            )
        # com CREA, o mesmo papel custom grava normalmente
        ok = UserProfile.objects.create(
            user=User.objects.create_user(username="zé2", password="senha-forte-123"),
            full_name="Zé 2",
            role="tecnico_senior",
            crea_number="SP-99999",
        )
        self.assertEqual(ok.role, "tecnico_senior")

    def test_papel_sem_requires_crea_nao_exige_crea(self):
        ok = UserProfile.objects.create(
            user=self.user, full_name="Zé Orc", role=UserProfile.ROLE_ORCAMENTISTA
        )
        self.assertEqual(ok.crea_number, "")
