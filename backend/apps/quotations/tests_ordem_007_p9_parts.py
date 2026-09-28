"""
Ordem 007 — item 9 do escopo: a revisão de scope='parts' copia as QuotationPart da
cotação original; sem isso, a revisão sai com custo ZERO (achado da ordem 007).
"""
from decimal import Decimal
from django_tenants.test.cases import TenantTestCase

from apps.quotations.adapter import recompute
from apps.quotations.models import Customer, Quotation


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
