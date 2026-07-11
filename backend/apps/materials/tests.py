"""
Testes do app materials.
seed_ligas_from_db: importa a base ASME II-D 2025 (chapas) como ligas INATIVAS de catálogo,
sem poluir o dropdown (ativas continuam as do seed_ligas) e escolhendo a linha CONSERVADORA.
"""
from datetime import date, timedelta
from io import StringIO

from django.contrib.auth.models import User
from django.core.management import call_command
from django.utils import timezone
from django_tenants.test.cases import TenantTestCase

from apps.accounts.models import UserProfile
from apps.audit.models import AccessLog
from apps.materials.models import Material, MaterialPrice, LigaMetalurgica
from apps.quotations.models import Customer, ItemMaterial, Quotation, QuotationItem


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
        self.empty_material = Material.objects.create(
            sigla="MAT-VAZIO",
            tipo="Material Sem Preco",
            norma="NORMA-Y",
            forma_padrao="barra",
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

    def test_detalhe_renderiza_precos_vigentes_por_forma(self):
        today = timezone.localdate()
        MaterialPrice.objects.create(
            material=self.material,
            forma="tubo",
            preco_brl_kg="20.00",
            fornecedor="Fornecedor Tubo",
            valid_from=today,
            valid_until=None,
        )
        MaterialPrice.objects.create(
            material=self.material,
            forma="barra",
            preco_brl_kg="30.00",
            fornecedor="Fornecedor Barra",
            valid_from=today,
            valid_until=None,
        )

        self.client.force_login(self.user)
        resp = self.client.get(f"/materiais/{self.material.pk}/")

        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "SA-179")
        self.assertContains(resp, "Preços vigentes por forma")
        self.assertContains(resp, "Chapa")
        self.assertContains(resp, "Tubo")
        self.assertContains(resp, "Barra")
        self.assertContains(resp, "R$ 12.34")
        self.assertContains(resp, "Fornecedor Atual")
        self.assertContains(resp, "R$ 20.00")
        self.assertContains(resp, "Fornecedor Tubo")
        self.assertContains(resp, "R$ 30.00")
        self.assertContains(resp, "Fornecedor Barra")
        self.assertContains(resp, "Vigente desde")

    def test_detalhe_material_sem_preco_mostra_estado_vazio(self):
        self.client.force_login(self.user)
        resp = self.client.get(f"/materiais/{self.empty_material.pk}/")

        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "MAT-VAZIO")
        self.assertContains(resp, "Sem preço vigente")

    def test_detalhe_mostra_preco_da_ultima_cotacao_por_forma(self):
        customer = Customer.objects.create(company_name="Cliente Teste")
        older = Quotation.objects.create(
            number="COT-0001",
            customer=customer,
            title="Cotação Antiga",
        )
        newer = Quotation.objects.create(
            number="COT-0002",
            customer=customer,
            title="Cotação Nova",
        )
        older_item = QuotationItem.objects.create(
            quotation=older,
            codigo_item="IT-001",
            descricao="Item Antigo",
        )
        newer_item = QuotationItem.objects.create(
            quotation=newer,
            codigo_item="IT-002",
            descricao="Item Novo",
        )
        ItemMaterial.objects.create(
            item=older_item,
            codigo_mp="MP-001",
            descricao="Material Antigo",
            material=self.material.sigla,
            forma="chapa",
            peso_bruto_kg="1.000",
            peso_liquido_kg="1.000",
            preco_kgf="7.5000",
            custo="7.50",
        )
        ItemMaterial.objects.create(
            item=newer_item,
            codigo_mp="MP-002",
            descricao="Material Novo",
            material=self.material.sigla,
            forma="chapa",
            peso_bruto_kg="1.000",
            peso_liquido_kg="1.000",
            preco_kgf="9.8700",
            custo="9.87",
        )

        self.client.force_login(self.user)
        resp = self.client.get(f"/materiais/{self.material.pk}/")

        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Última cotação")
        self.assertContains(resp, "COT-0002")
        self.assertContains(resp, "R$ 9.8700")

    def test_detalhe_sem_uso_na_ultima_cotacao_fica_vazio(self):
        self.client.force_login(self.user)
        resp = self.client.get(f"/materiais/{self.other_material.pk}/")

        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "MAT-EXTRA")
        self.assertNotContains(resp, "COT-")
        self.assertNotContains(resp, "R$ 9.8700")


class MaterialPriceEditViewTests(TenantTestCase):
    def setUp(self):
        self.client.defaults["HTTP_HOST"] = self.get_test_tenant_domain()
        call_command("seed_materials")
        self.today = timezone.localdate()
        self.material = Material.objects.get(sigla="SA-179")
        self.current_price = MaterialPrice.objects.create(
            material=self.material,
            forma="chapa",
            preco_brl_kg="12.34",
            fornecedor="Fornecedor Atual",
            valid_from=self.today - timedelta(days=15),
            valid_until=None,
        )
        self.editor = User.objects.create_user(username="gestor", password="senha-forte-123")
        UserProfile.objects.create(
            user=self.editor,
            full_name="Gestor",
            role=UserProfile.ROLE_GESTOR_COMERCIAL,
        )
        self.viewer = User.objects.create_user(username="viewer", password="senha-forte-123")
        UserProfile.objects.create(
            user=self.viewer,
            full_name="Viewer",
            role=UserProfile.ROLE_ORCAMENTISTA,
        )

    def test_post_novo_preco_fecha_vigente_cria_historico_e_audita(self):
        self.client.force_login(self.editor)

        resp = self.client.post(
            f"/materiais/{self.material.pk}/precos/chapa/",
            {
                "preco_brl_kg": "15.99",
                "fornecedor": "Fornecedor Novo",
            },
            HTTP_HX_REQUEST="true",
        )

        self.assertEqual(resp.status_code, 200)
        self.current_price.refresh_from_db()
        self.assertEqual(self.current_price.valid_until, self.today - timedelta(days=1))

        prices = list(MaterialPrice.objects.filter(material=self.material, forma="chapa").order_by("valid_from"))
        self.assertEqual(len(prices), 2)
        novo = prices[-1]
        self.assertEqual(novo.preco_brl_kg, "15.99")
        self.assertEqual(novo.fornecedor, "Fornecedor Novo")
        self.assertEqual(novo.valid_from, self.today)
        self.assertIsNone(novo.valid_until)

        log = AccessLog.objects.get(action="price_change")
        self.assertEqual(log.user, self.editor)
        self.assertEqual(log.resource_type, "MaterialPrice")
        self.assertEqual(log.resource_id, str(novo.pk))
        self.assertEqual(log.metadata["forma"], "chapa")
        self.assertEqual(log.metadata["anterior"], "12.34")
        self.assertEqual(log.metadata["novo"], "15.99")

    def test_post_sem_permissao_retorna_403_e_nao_altera_precos(self):
        self.client.force_login(self.viewer)

        resp = self.client.post(
            f"/materiais/{self.material.pk}/precos/chapa/",
            {
                "preco_brl_kg": "15.99",
                "fornecedor": "Fornecedor Novo",
            },
            HTTP_HX_REQUEST="true",
        )

        self.assertEqual(resp.status_code, 403)
        self.current_price.refresh_from_db()
        self.assertIsNone(self.current_price.valid_until)
        self.assertEqual(MaterialPrice.objects.filter(material=self.material, forma="chapa").count(), 1)
        self.assertFalse(AccessLog.objects.filter(action="price_change").exists())
