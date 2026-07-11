"""
Testes do app materials.
seed_ligas_from_db: importa a base ASME II-D 2025 (chapas) como ligas INATIVAS de catálogo,
sem poluir o dropdown (ativas continuam as do seed_ligas) e escolhendo a linha CONSERVADORA.
"""
from datetime import date
from io import StringIO

from django.contrib.auth.models import User
from django.core.management import call_command
from django.utils import timezone
from django_tenants.test.cases import TenantTestCase

from apps.accounts.models import UserProfile
from apps.materials.models import Material, MaterialPrice, LigaMetalurgica


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


class MaterialListViewTests(TenantTestCase):
    def setUp(self):
        self.client.defaults["HTTP_HOST"] = self.get_test_tenant_domain()
        call_command("seed_materials")

        self.user = User.objects.create_user(username="orc", password="senha-forte-123")
        UserProfile.objects.create(
            user=self.user,
            full_name="Orc",
            role=UserProfile.ROLE_ORCAMENTISTA,
        )

        self.material = Material.objects.get(sigla="SA-179")
        self.other_material = Material.objects.create(
            sigla="MAT-EXTRA",
            tipo="Material Extra",
            norma="NORMA-X",
            forma_padrao="chapa",
        )

        today = timezone.localdate()
        MaterialPrice.objects.create(
            material=self.material,
            forma="chapa",
            preco_brl_kg="10.00",
            fornecedor="Fornecedor Antigo",
            valid_from=date(today.year - 1, today.month, today.day),
            valid_until=date(today.year, today.month, today.day - 1) if today.day > 1 else today,
        )
        MaterialPrice.objects.create(
            material=self.material,
            forma="chapa",
            preco_brl_kg="12.34",
            fornecedor="Fornecedor Atual",
            valid_from=today,
            valid_until=None,
        )
        MaterialPrice.objects.create(
            material=self.other_material,
            forma="tubo",
            preco_brl_kg="99.99",
            fornecedor="Fornecedor Extra",
            valid_from=today,
            valid_until=None,
        )

    def test_lista_autenticada_mostra_material_e_preco_vigente(self):
        self.client.force_login(self.user)
        resp = self.client.get("/materiais/")
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "SA-179")
        self.assertContains(resp, "12.34")
        self.assertContains(resp, "Fornecedor Atual")
        self.assertNotContains(resp, "10.00")

    def test_busca_filtra_por_sigla(self):
        self.client.force_login(self.user)
        resp = self.client.get("/materiais/", {"q": "MAT-EXTRA"})
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "MAT-EXTRA")
        self.assertNotContains(resp, '<td class="id">SA-179</td>')

    def test_anonimo_redireciona_para_login(self):
        resp = self.client.get("/materiais/")
        self.assertEqual(resp.status_code, 302)
        self.assertIn("/login/", resp.url)

    def test_usuario_sem_perfil_no_tenant_recebe_403(self):
        outsider = User.objects.create_user(username="outsider", password="senha-forte-123")
        self.client.force_login(outsider)
        resp = self.client.get("/materiais/")
        self.assertIn(resp.status_code, {302, 403})
