"""Testes do app tema_templates (catálogo + composição + compatibilidade)."""
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django_tenants.test.cases import TenantTestCase as TestCase

from apps.tema_templates.models import ComponentTemplate, check_compatibility
from apps.engineering_params.models import TenantParamConfig


class CheckCompatibilityTests(TestCase):
    """Regras de domínio TEMA puras (sem banco)."""

    def test_combinacao_classica_ael_sem_avisos(self):
        self.assertEqual(check_compatibility("A", "E", "L"), [])

    def test_frontal_n_exige_traseiro_n(self):
        avisos = check_compatibility("N", "E", "L")
        self.assertTrue(any("integral" in a for a in avisos))
        self.assertEqual(check_compatibility("N", "E", "N"), [])

    def test_traseiro_flutuante_gera_aviso(self):
        for r in ("P", "S", "T", "W"):
            self.assertTrue(any("flutuante" in a for a in check_compatibility("A", "E", r)),
                            f"esperava aviso flutuante p/ traseiro {r}")

    def test_u_tube_aviso(self):
        avisos = check_compatibility("B", "E", "U")
        self.assertTrue(any("feixe em U" in a for a in avisos))

    def test_kettle_k_combina_u_ou_t(self):
        # K com L → aviso de kettle
        self.assertTrue(any("kettle" in a for a in check_compatibility("A", "K", "L")))
        # K com U/T → sem o aviso de kettle (U ainda traz a nota informativa de feixe-em-U)
        self.assertFalse(any("kettle" in a for a in check_compatibility("A", "K", "U")))
        self.assertFalse(any("kettle" in a for a in check_compatibility("A", "K", "T")))

    def test_case_insensitive(self):
        self.assertEqual(check_compatibility("a", "e", "l"), [])


class SeedCatalogTests(TestCase):
    def test_seed_popula_todas_as_letras(self):
        call_command("seed_tema_catalog")
        self.assertEqual(ComponentTemplate.objects.filter(tema_part="front_head").count(), 5)
        self.assertEqual(ComponentTemplate.objects.filter(tema_part="shell").count(), 7)
        self.assertEqual(ComponentTemplate.objects.filter(tema_part="rear_head").count(), 8)
        # sub-componentes do feixe (tube_bundle, tubesheet, baffle, tie_rod, nozzle, flange)
        subs = ComponentTemplate.objects.exclude(
            tema_part__in=["front_head", "shell", "rear_head"]).count()
        self.assertEqual(subs, 6)

    def test_seed_idempotente(self):
        call_command("seed_tema_catalog")
        n1 = ComponentTemplate.objects.count()
        call_command("seed_tema_catalog")
        self.assertEqual(ComponentTemplate.objects.count(), n1)


class ComposeViewTests(TestCase):
    def setUp(self):
        call_command("seed_tema_catalog")
        User = get_user_model()
        User.objects.create_user(username="eng", password="x")
        self.client.defaults["HTTP_HOST"] = self.get_test_tenant_domain()
        self.client.login(username="eng", password="x")

    def _check(self, front, shell, rear):
        return self.client.post("/tema/compor/check/",
                                {"front": front, "shell": shell, "rear": rear})

    def test_catalogo_renderiza(self):
        r = self.client.get("/tema/catalogo/")
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "CATÁLOGO TEMA")

    def test_compose_designacao(self):
        r = self._check("A", "E", "L")
        self.assertContains(r, "AEL")
        self.assertContains(r, "compatível")

    def test_modo_warn_default_nao_bloqueia(self):
        r = self._check("A", "E", "S")        # flutuante → aviso
        self.assertNotContains(r, "BLOQUEADO")
        self.assertContains(r, "flutuante")

    def test_modo_block_bloqueia(self):
        cfg = TenantParamConfig.get_solo()
        cfg.tema_compat_mode = "block"
        cfg.save()
        r = self._check("A", "E", "S")
        self.assertContains(r, "BLOQUEADO")

    def test_modo_free_permite(self):
        cfg = TenantParamConfig.get_solo()
        cfg.tema_compat_mode = "free"
        cfg.save()
        r = self._check("A", "E", "S")
        self.assertNotContains(r, "BLOQUEADO")
        self.assertContains(r, "livre")
