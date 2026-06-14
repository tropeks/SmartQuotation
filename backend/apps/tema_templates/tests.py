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
                "esp_casco_mm": 9.5, "n_passes_tubos": 2, "rt_escopo": "Parcial",
                "classe_feixe": "CS", "classe_casco": "CS", "fluido_corrosivo": "Tubos",
                "fator_correcao_mo": 1.0}
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

    def test_a1_alerta_espessura_critico(self):
        """A1 (Wellington): pressão alta + casco fino → alerta crítico ASME UG-27."""
        r = self._post(pressao_projeto_bar=50, temperatura_projeto_c=150, esp_casco_mm=9.5)
        self.assertContains(r, "CRÍTICO")

    def test_a1_espessura_ok_sem_alerta(self):
        """A1: pressão baixa → espessura suficiente, sem alerta."""
        r = self._post(pressao_projeto_bar=10, temperatura_projeto_c=150, esp_casco_mm=9.5)
        self.assertNotContains(r, "CRÍTICO")

    def test_a1_duplex_procedencia(self):
        """A1: duplex tem S (ASME II-D 2025 licenciada) → verifica espessura e cita a procedência
        (rastreabilidade exigida p/ certificação ASME)."""
        from pricing_engine.asme import checar_espessura_casco
        avisos = checar_espessura_casco("DUPLEX", 30, 150, "Parcial", 764, 9.5, 3.0)
        self.assertTrue(any("CRÍTICO" in a for a in avisos))
        self.assertTrue(any("2025" in a for a in avisos))  # fonte normativa citada no aviso

    def test_a1_niquel_procedencia(self):
        """A1: níquel (Inconel 625 Grade 1, ASME II-D 2025 = 217 MPa) verifica e cita a fonte."""
        from pricing_engine.asme import tensao_admissivel, checar_espessura_casco
        self.assertAlmostEqual(tensao_admissivel("SB-443 N06625", 150), 217, places=0)
        avisos = checar_espessura_casco("NIQUEL", 60, 150, "Parcial", 764, 9.5, 3.0)
        self.assertTrue(any("2025" in a for a in avisos))

    def test_a1_ug27_modulo(self):
        """A1: módulo ASME — S interpola, E por escopo de RT, t_min UG-27 (máx circ/long)."""
        from pricing_engine.asme import tensao_admissivel, eficiencia_junta, t_min_ug27
        self.assertAlmostEqual(tensao_admissivel("SA-516 GR 70", 250), 138, places=1)
        self.assertEqual(eficiencia_junta("Total"), 1.0)
        self.assertGreater(t_min_ug27(5.0, 764, 138, 0.85), 9.5)  # 50 bar → > 9,5mm

    def test_a1_ug32_tampo(self):
        """A1 (Rom): tampo 2:1 fino dispara alerta UG-32 mesmo com casco ok."""
        from pricing_engine.asme import t_min_ug32_tampo, checar_espessura_casco
        self.assertGreater(t_min_ug32_tampo(5.0, 764, 138, 0.85), 0)
        avisos = checar_espessura_casco("CS", 20, 150, "Parcial", 764, 12, 3.0, esp_tampo_mm=5)
        self.assertTrue(any("tampo" in a.lower() for a in avisos))

    def test_solda_escala_com_espessura(self):
        """#2: dobrar a espessura do casco multiplica as horas de solda (≈ espessura²)."""
        from apps.tema_templates.services import estimate_complete, _physical_params
        base = estimate_complete("BEU")
        p = _physical_params("BEU", {"esp_casco_mm": 19.0, "comprimento_tubo_mm": 13000,
                                      "diametro_casco_mm": 764, "n_tubos": 68, "n_chicanas": 18})
        grosso = estimate_complete("BEU", params=p)
        self.assertGreater(grosso["custo_total"], base["custo_total"] + 5000)

    def test_liga_feixe_inox_sobe_so_mo_do_feixe(self):
        """Bimetálico: feixe inox sobe MO (lado feixe); material e MO do casco não mudam."""
        from apps.tema_templates.services import estimate_complete
        cs = estimate_complete("BEU")
        inox = estimate_complete("BEU", liga_por_lado={"feixe": 1.4, "casco": 1.0})
        self.assertGreater(inox["custo_mao_obra"], cs["custo_mao_obra"])
        self.assertAlmostEqual(inox["custo_material"], cs["custo_material"], places=2)

    def test_fluido_corrosivo_tubos_espelha_metalurgia_no_cabecote(self):
        """A2 (Wellington): corrosivo=Tubos → cabeçote herda a liga do feixe (custa mais)."""
        from apps.tema_templates.services import estimate_complete
        inox = {"feixe": 1.4, "casco": 1.0}
        dens = {"feixe": 1.0107, "casco": 1.0}
        preco = {"feixe": 4.5, "casco": 1.0}
        tubos = estimate_complete("BEU", liga_por_lado=inox, dens_por_lado=dens,
                                  preco_por_lado=preco, corrosivo="Tubos")
        casco = estimate_complete("BEU", liga_por_lado=inox, dens_por_lado=dens,
                                  preco_por_lado=preco, corrosivo="Casco")
        self.assertGreater(tubos["custo_total"], casco["custo_total"] + 5000)

    def test_corrosivo_default_nao_altera_referencia(self):
        """Default (CS em ambos os lados) → corrosivo não muda nada (gate 0,0%)."""
        from apps.tema_templates.services import estimate_complete
        a = estimate_complete("BEU", corrosivo="Tubos")
        b = estimate_complete("BEU", corrosivo="Casco")
        self.assertAlmostEqual(a["custo_total"], b["custo_total"], places=2)

    def test_densidade_niquel_sobe_peso_do_lado(self):
        """Densidade por liga: níquel no casco aumenta o peso (custo) do material do casco."""
        from apps.tema_templates.services import estimate_complete
        cs = estimate_complete("BEU")
        ni = estimate_complete("BEU", dens_por_lado={"casco": 8.80 / 7.85})
        self.assertGreater(ni["custo_material"], cs["custo_material"] + 1000)

    def test_scrap_espelho_40_pct(self):
        """B (Wellington): perda de espelho/chicana = 40%; tampo 20%; tubo 10%."""
        from pricing_engine.beu_geometry import perda_familia
        self.assertAlmostEqual(perda_familia("espelho"), 1.40, places=2)
        self.assertAlmostEqual(perda_familia("perfurado"), 1.40, places=2)
        self.assertAlmostEqual(perda_familia("tampo_2_1"), 1.20, places=2)
        self.assertAlmostEqual(perda_familia("tubo"), 1.10, places=2)

    def test_icms_formula_real_por_dentro(self):
        """B (Wellington): ICMS por dentro real = 1/(1−alíquota), sem o fudge 0,97."""
        from pricing_engine.permutador_quote import gross_up_icms
        self.assertAlmostEqual(gross_up_icms(9.0), 1.0 / (1.0 - 0.09), places=6)

    def test_rt_escopo_escala_ensaios(self):
        """B (Wellington): RT total > parcial > isento. O gabarito é Total (100%) = baseline,
        então Total ≈ referência e os escopos menores custam menos (raio-X param 'rt')."""
        from apps.tema_templates.services import estimate_complete, _physical_params
        ref = estimate_complete("BEU")
        base = {"comprimento_tubo_mm": 13000, "diametro_casco_mm": 764, "esp_casco_mm": 9.5,
                "n_tubos": 68, "n_chicanas": 18, "n_passes_tubos": 2}
        total = estimate_complete("BEU", params=_physical_params("BEU", {**base, "rt_escopo": "Total"}))
        parcial = estimate_complete("BEU", params=_physical_params("BEU", {**base, "rt_escopo": "Parcial"}))
        isento = estimate_complete("BEU", params=_physical_params("BEU", {**base, "rt_escopo": "Isento"}))
        self.assertGreater(total["custo_servicos"], parcial["custo_servicos"])
        self.assertGreater(parcial["custo_servicos"], isento["custo_servicos"])
        # Total é o baseline do gabarito → custo de serviços ≈ referência (≤1% de diferença)
        self.assertAlmostEqual(total["custo_servicos"], ref["custo_servicos"],
                               delta=ref["custo_servicos"] * 0.01)

    def test_espelho_geometrizavel_responde_a_dims(self):
        """Polimento agy §4: o espelho agora recomputa pela geometria no dims_override."""
        from apps.tema_templates.services import estimate_complete
        base = estimate_complete("BEU")
        maior = estimate_complete("BEU", dims_override={"ESPELHO FIXO": {"OD": 700}})
        self.assertGreater(maior["custo_material"], base["custo_material"])

    def test_flange_peso_da_tabela(self):
        """A3 Wellington: flange WN puxa peso real da tabela (Ø×rating×schedule)."""
        from pricing_engine.flanges import peso_flange
        self.assertAlmostEqual(peso_flange("600#", '8"', 80), 56.0, delta=0.5)
        self.assertAlmostEqual(peso_flange("600#", '10"', 40), 86.8, delta=0.5)

    def test_flange_maior_sobe_custo(self):
        """A3: trocar o flange por um maior (Ø) aumenta o material — não é mais chute."""
        from apps.tema_templates.services import estimate_complete
        base = estimate_complete("BEU")
        maior = estimate_complete("BEU", dims_override={"FLANGE": {"ND": '12"'}})
        self.assertGreater(maior["custo_material"], base["custo_material"] + 1000)

    def test_flange_maior_sobe_horas_de_solda(self):
        """A3 (Wellington): flange maior → mais horas de solda/montagem do bocal (não só material)."""
        from apps.tema_templates.services import estimate_complete
        base = estimate_complete("BEU")
        maior = estimate_complete("BEU", dims_override={"FLANGE": {"ND": '12"'}})
        self.assertGreater(maior["custo_mao_obra"], base["custo_mao_obra"] + 1000)

    def test_chicana_geometrizavel(self):
        """Refino: a chicana (perfurado) agora recomputa o peso pela geometria (dims_override)."""
        from apps.tema_templates.services import estimate_complete
        base = estimate_complete("BEU")
        maior = estimate_complete("BEU", dims_override={"TRANSVERSAL": {"LARG.": 600}})
        self.assertGreater(maior["custo_material"], base["custo_material"])

    def test_rasgos_escalam_com_passes(self):
        """Refino: mais passes de tubos → mais rasgos de partição (op usinada)."""
        from apps.tema_templates.services import estimate_complete
        base = estimate_complete("BEU")
        quatro = estimate_complete("BEU", params={"rasgos": 2.0})  # 4 passes vs ref 2
        self.assertGreater(quatro["custo_mao_obra"], base["custo_mao_obra"])

    def test_usinagem_espelho_segue_liga_do_feixe(self):
        """Polimento agy §4: usinar/furar espelho em inox segue a liga do FEIXE, não do casco."""
        from pricing_engine.permutador_quote import _lado_da_op
        self.assertEqual(_lado_da_op({"label": "ESPELHO - USINAR", "driver": None}), "feixe")
        self.assertEqual(_lado_da_op({"label": "USINAR RASGOS", "driver": "Nº RASGOS"}), "feixe")

    def test_preco_liga_sobe_material(self):
        """#agy 1.C: liga nobre multiplica o preço/kg da matéria-prima do lado (efeito dominante)."""
        from apps.tema_templates.services import estimate_complete
        cs = estimate_complete("BEU")
        feixe_inox = estimate_complete("BEU", preco_por_lado={"feixe": 4.5, "casco": 1.0})
        # o feixe (tubos+espelho) é boa parte do material → preço sobe forte
        self.assertGreater(feixe_inox["custo_material"], cs["custo_material"] + 10000)

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
