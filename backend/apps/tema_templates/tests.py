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

    def test_beu_mostra_custeio_completo(self):
        r = self._check("B", "E", "U")          # designação BEU = permutador completo custeável
        self.assertContains(r, "BEU")
        self.assertContains(r, "Custeio paramétrico")
        self.assertContains(r, "Custo total")

    def test_bem_mostra_custeio_completo(self):
        r = self._check("B", "E", "M")          # designação BEM = permutador completo custeável
        self.assertContains(r, "BEM")
        self.assertContains(r, "Custeio paramétrico")

    def test_data_sheet_get_prefilled(self):
        r = self.client.get("/tema/permutador/")
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "DATA SHEET")

    def _post(self, **over):
        data = {"designacao": "BEU", "n_tubos": 68, "comprimento_tubo_mm": 13000,
                "od_tubo_mm": 19.05, "esp_tubo_mm": 2.108, "n_chicanas": 18,
                "comprimento_casco_mm": 1631, "diametro_casco_mm": 764,
                "esp_casco_mm": 9.5, "classe_metalurgica": "CS", "fator_correcao_mo": 1.0}
        data.update(over)
        return self.client.post("/tema/permutador/", data)

    def test_data_sheet_post_recomputa(self):
        r = self._post()
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "Custo total")

    def test_data_sheet_mais_tubos_sobe_mao_de_obra(self):
        """Parametria plena: mais tubos → mais horas de fabricação (não só material)."""
        from apps.tema_templates.services import estimate_complete, _physical_params
        ref = estimate_complete("BEU")
        params = _physical_params("BEU", {"n_tubos": 136, "comprimento_tubo_mm": 13000,
                                           "diametro_casco_mm": 764, "n_chicanas": 18})
        maior = estimate_complete("BEU", params=params)
        self.assertGreater(maior["custo_mao_obra"], ref["custo_mao_obra"] + 500)

    def test_servicos_escalam_com_massa(self):
        """#3: tratamento térmico/consumíveis escalam com a massa (proxy D·L)."""
        from apps.tema_templates.services import estimate_complete
        ref = estimate_complete("BEU")
        maior = estimate_complete("BEU", params={"massa": 2.0, "solda": 2.0})
        self.assertGreater(maior["custo_servicos"], ref["custo_servicos"] + 1000)

    def test_layout_aviso_tubos_demais(self):
        """#4: muitos tubos num casco pequeno gera aviso de arranjo inviável."""
        r = self._post(n_tubos=500, diametro_casco_mm=400)
        self.assertContains(r, "inviável")

    def test_solda_escala_com_espessura(self):
        """#2: dobrar a espessura do casco multiplica as horas de solda (≈ espessura²)."""
        from apps.tema_templates.services import estimate_complete, _physical_params
        base = estimate_complete("BEU")
        p = _physical_params("BEU", {"esp_casco_mm": 19.0, "comprimento_tubo_mm": 13000,
                                      "diametro_casco_mm": 764, "n_tubos": 68, "n_chicanas": 18})
        grosso = estimate_complete("BEU", params=p)
        self.assertGreater(grosso["custo_total"], base["custo_total"] + 5000)

    def test_liga_inox_sobe_mao_de_obra(self):
        """#3: liga (inox) multiplica a MO de caldeiraria; material não muda."""
        from apps.tema_templates.services import estimate_complete
        cs = estimate_complete("BEU", liga_fator_mo=1.0)
        inox = estimate_complete("BEU", liga_fator_mo=1.3)
        self.assertAlmostEqual(inox["custo_mao_obra"], cs["custo_mao_obra"] * 1.3, places=0)
        self.assertAlmostEqual(inox["custo_material"], cs["custo_material"], places=2)

    def test_folga_cabecote_flutuante(self):
        """#5: cabeçote flutuante (S) exige folga radial maior que fixo (M)."""
        from pricing_engine.permutador_layout import folga_cabecote
        self.assertGreater(folga_cabecote("S"), folga_cabecote("M"))

    def test_designacao_nao_custeavel_sem_breakdown(self):
        r = self._check("A", "E", "L")          # AEL não tem custeio completo validado
        self.assertNotContains(r, "Custeio paramétrico · permutador completo")
        self.assertContains(r, "em validação")


class PermutadorEngineTests(TestCase):
    """Motor de custeio do permutador completo (via serviço, com cadeia de custos do tenant)."""

    GABARITO = {"BEU": 128160.0, "BEM": 119295.0}

    def test_estimate_complete_reconcilia_gabarito(self):
        from apps.tema_templates.services import estimate_complete
        for desig, gab in self.GABARITO.items():
            q = estimate_complete(desig)
            self.assertIsNotNone(q, desig)
            self.assertAlmostEqual(q["custo_total"], gab, delta=gab * 0.10)
            self.assertEqual(q["designacao_tema"], desig)
            self.assertGreater(q["custo_material"], 0)
            self.assertGreater(q["custo_mao_obra"], 0)

    def test_estimate_complete_none_para_nao_custeavel(self):
        from apps.tema_templates.services import estimate_complete
        self.assertIsNone(estimate_complete("AEL"))

    def test_bem_difere_de_beu(self):
        from pricing_engine.permutador_quote import quote_completo
        self.assertNotAlmostEqual(quote_completo("BEU")["custo_total"],
                                  quote_completo("BEM")["custo_total"], delta=1000)

    def test_dims_override_muda_custo_material(self):
        """Parametria de verdade (#1/#9): dobrar o comprimento do tubo aumenta o material."""
        from apps.tema_templates.services import estimate_complete
        base = estimate_complete("BEU")
        ref = estimate_complete("BEU", dims_override={
            "TUBOS DE TROCA TÉRMICA": {"COMPR.": 26000}})  # ~2× o comprimento de referência
        self.assertGreater(ref["custo_material"], base["custo_material"] + 1000)

    def test_densidade_inox_pesa_mais(self):
        """#5: mesmo componente em inox (AISI-304) pesa ~2% mais que em aço-carbono."""
        from pricing_engine.beu_geometry import peso_chapa_retangular
        from pricing_engine.materials import density
        carb = peso_chapa_retangular(9.5, 2400, 1631, rho=density("SA-516 GR 70"))
        inox = peso_chapa_retangular(9.5, 2400, 1631, rho=density("AISI-304"))
        self.assertGreater(inox, carb)

    def test_fator_mo_escala_mao_de_obra(self):
        from pricing_engine.beu_quote import quote_beu
        base = quote_beu()
        alto = quote_beu(fator_correcao_mo=1.20)
        # MO escala 20%; material e serviços não mudam
        self.assertAlmostEqual(alto["custo_mao_obra"], base["custo_mao_obra"] * 1.20, places=0)
        self.assertAlmostEqual(alto["custo_material"], base["custo_material"], places=2)
        self.assertAlmostEqual(alto["custo_servicos"], base["custo_servicos"], places=2)
