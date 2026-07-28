"""
O admin não é porta de fuga do selo de custo (M1.2).

`QuotationAdmin` não declarava `fields` nem `exclude`, então o formulário do admin
expunha `custo_material`, `custo_mo`, `custo_total`, `fator_preco` e `impostos_pct` como
editáveis — e gravar por ali **não emite CalculationSnapshot**. Esses campos alimentam
direto o cabeçalho da Ordem de Fabricação.

Não é escalada de papel: exige `is_staff`, flag do Django que nenhum papel de tenant
concede. Mas é o último bypass conhecido do selo que o M1 construiu, e um operador de
plataforma mexendo ali quebraria a garantia sem perceber — não há nada na tela que diga
que aquele campo é derivado.

Custo é DERIVADO: sai do motor ou do roll-up da EAP, nunca da digitação. No admin ele
vira leitura.
"""
from django_tenants.test.cases import TenantTestCase

from apps.quotations.admin import QuotationAdmin
from apps.quotations.models import Quotation

CAMPOS_DERIVADOS = ("custo_material", "custo_mo", "custo_total",
                    "preco_sem_impostos", "preco_com_impostos",
                    "peso_bruto_kg", "peso_liquido_kg",
                    "fator_preco", "impostos_pct")


class AdminNaoEditaCustoTests(TenantTestCase):
    def test_campos_derivados_sao_somente_leitura(self):
        readonly = set(QuotationAdmin.readonly_fields)
        for campo in CAMPOS_DERIVADOS:
            self.assertIn(campo, readonly,
                          f"{campo} é derivado do motor/roll-up — editar aqui burlaria o selo")

    def test_proveniencia_continua_protegida(self):
        """`pricing_basis` já era readonly (SQ-COST-1) e não pode regredir."""
        self.assertIn("pricing_basis", QuotationAdmin.readonly_fields)

    def test_formulario_do_admin_nao_expoe_custo_como_editavel(self):
        """Vale o formulário renderizado, não só a declaração da classe."""
        from django.contrib.admin.sites import AdminSite

        admin_obj = QuotationAdmin(Quotation, AdminSite())
        editaveis = set(admin_obj.get_form(request=None)().fields)

        for campo in CAMPOS_DERIVADOS:
            self.assertNotIn(campo, editaveis,
                             f"{campo} chegou editável no form do admin")

    def test_campos_de_entrada_continuam_editaveis(self):
        """A trava é sobre o que é DERIVADO — o resto do admin segue servindo."""
        from django.contrib.admin.sites import AdminSite

        admin_obj = QuotationAdmin(Quotation, AdminSite())
        editaveis = set(admin_obj.get_form(request=None)().fields)

        self.assertIn("title", editaveis)
        self.assertIn("status", editaveis)
