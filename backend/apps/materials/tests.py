"""
Testes do app materials.
seed_ligas_from_db: importa a base ASME II-D 2025 (chapas) como ligas INATIVAS de catálogo,
sem poluir o dropdown (ativas continuam as do seed_ligas) e escolhendo a linha CONSERVADORA.
"""
from io import StringIO

from django.core.management import call_command
from django_tenants.test.cases import TenantTestCase

from apps.materials.models import LigaMetalurgica


class SeedLigasFromDbTest(TenantTestCase):
    def _run(self):
        out = StringIO()
        call_command("seed_ligas_from_db", stdout=out)
        return out.getvalue()

    def test_cria_varias_ligas_inativas(self):
        self._run()
        inativas = LigaMetalurgica.objects.filter(is_active=False)
        self.assertGreater(inativas.count(), 50)
        # nenhuma das ligas importadas deve entrar no dropdown
        self.assertTrue(all(l.ordem == 999 for l in inativas))

    def test_liga_conhecida_usa_curva_conservadora(self):
        self._run()
        liga = LigaMetalurgica.objects.get(codigo="SA-240-316L")
        self.assertFalse(liga.is_active)
        self.assertEqual(liga.norma, "ASME BPVC II-D (M)")
        self.assertEqual(liga.edicao, "2025")
        # a linha conservadora do SA-240 316L tem S(100°C) ≈ 96.3 (NÃO 115 da linha alta)
        self.assertAlmostEqual(float(liga.s_curva["100"]), 96.3, places=1)

    def test_idempotente(self):
        self._run()
        n1 = LigaMetalurgica.objects.count()
        self._run()
        n2 = LigaMetalurgica.objects.count()
        self.assertEqual(n1, n2)
