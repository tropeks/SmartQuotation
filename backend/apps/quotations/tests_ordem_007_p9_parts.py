"""
Ordem 007 — item 9 do escopo: a revisão de scope='parts' copia as QuotationPart da
cotação original; sem isso, a revisão sai com custo ZERO (achado da ordem 007).
"""
from decimal import Decimal
from django_tenants.test.cases import TenantTestCase

from apps.quotations.adapter import recompute
from apps.quotations.models import Customer, Quotation


class _PartsQuotationMixin:
    """Fixture compartilhada: uma cotação scope='parts' com uma QuotationPart inclusa e
    custeada (mesma composição de RevisaoDePartesCopiaQuotationPartTests)."""

    def _monta_cotacao_parts(self, sufixo=""):
        from datetime import date
        from apps.tema_templates.models import ComponentTemplate, ComponentOperation
        from apps.engineering_params.models import ProcessParameter, Rate
        from apps.materials.models import Material, MaterialPrice
        from apps.quotations.models import QuotationPart

        mat, _ = Material.objects.get_or_create(sigla="SA-516 GR 70", tipo="AÇO CARBONO")
        if not MaterialPrice.objects.filter(material=mat, forma="chapa").exists():
            MaterialPrice.objects.create(material=mat, forma="chapa",
                                         preco_brl_kg="20.00", valid_from=date(2020, 1, 1))
        casco = ComponentTemplate.objects.create(
            tema_part="shell", tema_letter="E", name=f"Casco E{sufixo}")
        ComponentOperation.objects.create(
            template=casco, codigo_op="OP-CORTE", descricao="Corte de chapa",
            operacao="CORTE_CHAPA", metodo="manual", driver="massa", setup_fixo=Decimal("2"))
        if not ProcessParameter.objects.filter(operacao="CORTE_CHAPA", metodo="manual").exists():
            ProcessParameter.objects.create(
                operacao="CORTE_CHAPA", metodo="manual", valor=Decimal("0.01"),
                unidade="fator", valid_from=date(2020, 1, 1))
        if not Rate.objects.filter(operacao="CORTE_CHAPA").exists():
            Rate.objects.create(operacao="CORTE_CHAPA", rate_hh=Decimal("100.00"),
                                valid_from=date(2020, 1, 1))

        q = Quotation.objects.create(number=f"COT-P9-HTTP{sufixo}", customer=self.customer,
                                     title=f"Casco reposição P9{sufixo}", scope="parts")
        QuotationPart.objects.create(quotation=q, template=casco, tema_letter="E",
                                     material_sigla="SA-516 GR 70",
                                     params={"massa": 500}, incluso=True)
        recompute(q)
        q.refresh_from_db()
        return q


class RevisaoDePartesCopiaQuotationPartTests(TenantTestCase):
    def setUp(self):
        from datetime import date
        from apps.tema_templates.models import ComponentTemplate, ComponentOperation
        from apps.engineering_params.models import ProcessParameter, Rate
        from apps.materials.models import Material, MaterialPrice
        from apps.quotations.models import QuotationPart

        self.customer = Customer.objects.create(company_name="Cliente Reposição P9")
        mat = Material.objects.create(sigla="SA-516 GR 70", tipo="AÇO CARBONO")
        MaterialPrice.objects.create(material=mat, forma="chapa",
                                     preco_brl_kg="20.00", valid_from=date(2020, 1, 1))
        self.casco = ComponentTemplate.objects.create(
            tema_part="shell", tema_letter="E", name="Casco E P9")
        ComponentOperation.objects.create(
            template=self.casco, codigo_op="OP-CORTE", descricao="Corte de chapa",
            operacao="CORTE_CHAPA", metodo="manual", driver="massa", setup_fixo=Decimal("2"))
        ProcessParameter.objects.create(
            operacao="CORTE_CHAPA", metodo="manual", valor=Decimal("0.01"),
            unidade="fator", valid_from=date(2020, 1, 1))
        Rate.objects.create(operacao="CORTE_CHAPA", rate_hh=Decimal("100.00"),
                            valid_from=date(2020, 1, 1))

        self.q = Quotation.objects.create(number="COT-P9-1", customer=self.customer,
                                          title="Casco reposição P9", scope="parts")
        QuotationPart.objects.create(quotation=self.q, template=self.casco, tema_letter="E",
                                     material_sigla="SA-516 GR 70",
                                     params={"massa": 500}, incluso=True)
        recompute(self.q)
        self.q.refresh_from_db()

    def test_revisar_parts_copia_as_partes_e_preserva_o_custo(self):
        from apps.quotations.adapter import revise_feixe
        from apps.quotations.models import QuotationPart

        self.assertGreater(self.q.custo_total, 0)   # sanity: a original custeia

        revisada = revise_feixe(self.q, created_by=None)

        self.assertEqual(revisada.number, self.q.number)
        self.assertEqual(revisada.revision, 1)
        self.assertEqual(QuotationPart.objects.filter(quotation=revisada).count(), 1)
        self.assertEqual(revisada.custo_total, self.q.custo_total)
        self.assertGreater(revisada.custo_total, 0)


class RevisaoDePartesViaHttpTests(_PartsQuotationMixin, TenantTestCase):
    """BLOQUEANTE (revisão do Diretor): o botão "Nova Revisão" de uma cotação scope='parts'
    ia para `quotations:edit` — o form do FEIXE (tubo/espelho/chicana obrigatórios). Parts
    precisa postar direto para `quotations:revise` (mesma rota do 'complete'), e
    `quotation_edit` precisa recusar/redirecionar scope='parts' em vez de tentar processar
    o form errado."""

    def setUp(self):
        self.client.defaults["HTTP_HOST"] = self.get_test_tenant_domain()
        from django.contrib.auth.models import User
        self.user = User.objects.create_user(username="orc-p9-http", password="123")
        from apps.accounts.models import UserProfile
        UserProfile.objects.create(user=self.user, full_name="Orc P9", role=UserProfile.ROLE_ORCAMENTISTA)
        self.client.force_login(self.user)
        self.customer = Customer.objects.create(company_name="Cliente Reposição P9 HTTP")
        self.q = self._monta_cotacao_parts()

    def test_revisar_via_view_mantem_numero_sobe_revisao_e_copia_partes(self):
        from apps.quotations.models import QuotationPart

        n_before = Quotation.objects.count()
        resp = self.client.post(f"/cotacoes/{self.q.pk}/revisar/")
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(Quotation.objects.count(), n_before + 1)

        nova = Quotation.objects.exclude(pk=self.q.pk).order_by("-id").first()
        self.assertEqual(nova.number, self.q.number)     # mantém o número
        self.assertEqual(nova.revision, 1)                # sobe a revisão
        self.assertEqual(nova.scope, "parts")
        self.assertEqual(QuotationPart.objects.filter(quotation=nova).count(), 1)
        self.assertGreater(nova.custo_total, 0)            # não custeia zero
        # nunca grava inputs de FEIXE (o form de edit não deveria ter rodado)
        self.assertEqual(nova.inputs, self.q.inputs)

    def test_quotation_edit_recusa_scope_parts(self):
        """`quotation_edit` é o Tier A do FEIXE (form com tubo/espelho/chicana
        obrigatórios) — uma cotação 'parts' não deve nem tentar renderizar/processar
        esse form; a rota certa é `quotations:revise`."""
        resp = self.client.get(f"/cotacoes/{self.q.pk}/editar/")
        self.assertEqual(resp.status_code, 302)
        n_before = Quotation.objects.count()

        resp = self.client.post(f"/cotacoes/{self.q.pk}/editar/", {})
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(Quotation.objects.count(), n_before)   # nada foi criado
