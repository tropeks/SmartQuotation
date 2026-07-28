"""
Testes puros dos helpers de Config de Engenharia v1 (C1/C2/C3) — sem Django/DB.

Estes helpers (apps.quotations.domain_params) espelham a conversão feita no Alpine do data
sheet. São a fonte-da-verdade do back-end; se divergirem do JS, o valor validado no servidor
sai diferente do que o usuário vê. Rodam em qualquer ambiente (SimpleTestCase, sem Postgres).
"""
from django.test import SimpleTestCase

from apps.quotations.domain_params import (
    baffle_cut_mm_to_pct,
    baffle_cut_pct_to_mm,
    desenvolvido_tubo_mm,
    precisa_emenda,
    u_bend_min_radius_mm,
)


class BaffleCutConversionTests(SimpleTestCase):
    """C1 — o campo do motor é a altura RESTANTE (hc = OD − corte), não a janela cortada.
    Logo restante = D × (1 − pct/100). O default do tenant é 25% de corte."""

    def test_25pct_de_corte_deixa_75pct_de_restante(self):
        # D interno 400 mm, corte 25% → restante 300 mm.
        self.assertEqual(baffle_cut_pct_to_mm(25.0, 400.0), 300.0)

    def test_roundtrip_pct_mm_pct(self):
        d = 416.8
        mm = baffle_cut_pct_to_mm(28.0, d)
        self.assertAlmostEqual(baffle_cut_mm_to_pct(mm, d), 28.0, places=1)

    def test_job_de_referencia_fica_em_faixa_fisica(self):
        # Referencial real: restante 300 mm, OD interno casco ~416,8 mm → ~28% de corte,
        # dentro da faixa TEMA (15–45%). Guarda contra a fórmula errada do plano (que daria ~75%).
        pct = baffle_cut_mm_to_pct(300.0, 416.8)
        self.assertTrue(15.0 <= pct <= 45.0, f"corte {pct}% fora da faixa física")
        self.assertAlmostEqual(pct, 28.0, delta=1.0)

    def test_sem_diametro_pct_zero(self):
        self.assertEqual(baffle_cut_mm_to_pct(300.0, 0.0), 0.0)


class TubeLengthEmendaTests(SimpleTestCase):
    """C2 — emenda quando o DESENVOLVIDO passa do maior comprimento comercial padrão.
    No feixe em U o tubo é dobrado ao meio → desenvolvido ≈ 2× a perna reta."""

    STD = [6100, 12000]

    def test_reto_desenvolvido_e_o_proprio_comprimento(self):
        self.assertEqual(desenvolvido_tubo_mm(5000.0, is_u=False), 5000.0)

    def test_u_desenvolvido_e_o_dobro(self):
        self.assertEqual(desenvolvido_tubo_mm(5000.0, is_u=True), 10000.0)

    def test_reto_curto_nao_precisa_emenda(self):
        self.assertFalse(precisa_emenda(6000.0, is_u=False, standard_lengths_mm=self.STD))

    def test_u_de_7m_por_perna_passa_de_12m_desenvolvido_e_emenda(self):
        # 7000 × 2 = 14000 > 12000 → emenda.
        self.assertTrue(precisa_emenda(7000.0, is_u=True, standard_lengths_mm=self.STD))

    def test_sem_padroes_nunca_emenda(self):
        self.assertFalse(precisa_emenda(99999.0, is_u=True, standard_lengths_mm=[]))


class UBendMinRadiusTests(SimpleTestCase):
    """C3 — raio mínimo da curva em U = fator × OD (TEMA RCB-2.3, default 1,5×OD)."""

    def test_default_factor_1_5(self):
        self.assertEqual(u_bend_min_radius_mm(19.05, 1.5), 28.58)

    def test_factor_configuravel(self):
        self.assertEqual(u_bend_min_radius_mm(25.4, 2.0), 50.8)
