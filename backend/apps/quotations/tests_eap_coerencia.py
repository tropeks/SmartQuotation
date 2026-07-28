"""
Coerência do que sai da EAP para a Ordem de Fabricação (M1.4 e M1.7).

Mesma família de defeito do M1: o número que chega ao chão de fábrica diverge do
que foi aprovado, e ninguém percebe porque nada reclama.

M1.7 — a OF copia `quotation.peso_bruto_kg` no cabeçalho E `mp.peso_bruto_kg` em cada
linha de material (`apps/production/services.py:169,192`). Editar o peso de um material
no drawer gravava a linha e deixava o total da cotação parado: cabeçalho dizendo um peso,
linhas somando outro.

M1.4 — `eap_op_restore` repõe as HORAS sugeridas e grava `origem="seed"`, mas a taxa
manual sobrevive. O custo "restaurado" continua diferente do motor, agora rotulado como
se fosse do motor — o rótulo mente para quem for revisar.
"""
from decimal import Decimal

from django.contrib.auth.models import User
from django.urls import reverse
from django_tenants.test.cases import TenantTestCase

from apps.accounts.models import UserProfile
from apps.quotations.models import Customer, ItemMaterial, ItemOperation
from apps.quotations.services import create_feixe_quotation

SENHA = "x123456789"
MOTIVO = "Ajuste conferido com o desenho revisado."


class EapCoerenciaTests(TenantTestCase):
    def setUp(self):
        self.client.defaults["HTTP_HOST"] = self.get_test_tenant_domain()
        self.user = User.objects.create_user(username="orc_coer", password=SENHA)
        UserProfile.objects.create(user=self.user, full_name="Orçamentista",
                                   role=UserProfile.ROLE_ORCAMENTISTA)
        self.customer = Customer.objects.create(company_name="Cliente Coerência")
        self.quotation = create_feixe_quotation(self.customer, "Feixe Coerência",
                                                created_by=self.user)
        self.client.force_login(self.user)

    # ── M1.7 · peso ────────────────────────────────────────────────────────────
    def test_editar_peso_de_material_atualiza_o_peso_da_cotacao(self):
        """Sem o roll-up, a OF nasce com o cabeçalho de peso antigo e linhas novas."""
        mat = ItemMaterial.objects.filter(
            item__quotation=self.quotation, peso_bruto_kg__gt=0).select_related("item").first()
        self.assertIsNotNone(mat, "fixture precisa de material com peso")
        novo_peso = mat.peso_bruto_kg + Decimal("500.000")

        self.client.post(reverse("quotations:eap_item_save", args=[mat.item.pk]), {
            "motivo": MOTIVO,
            f"material_peso_{mat.pk}": str(novo_peso),
        })

        self.quotation.refresh_from_db()
        esperado = sum(
            (m.peso_bruto_kg for m in ItemMaterial.objects.filter(item__quotation=self.quotation)),
            Decimal("0"),
        )
        self.assertEqual(
            self.quotation.peso_bruto_kg.quantize(Decimal("0.01")),
            esperado.quantize(Decimal("0.01")),
            "o peso da cotação tem de acompanhar a soma das linhas",
        )

    def test_peso_liquido_tambem_acompanha(self):
        mat = ItemMaterial.objects.filter(
            item__quotation=self.quotation, peso_bruto_kg__gt=0).select_related("item").first()
        self.client.post(reverse("quotations:eap_item_save", args=[mat.item.pk]), {
            "motivo": MOTIVO,
            f"material_peso_{mat.pk}": str(mat.peso_bruto_kg + Decimal("100.000")),
        })

        self.quotation.refresh_from_db()
        esperado = sum(
            (m.peso_liquido_kg for m in ItemMaterial.objects.filter(item__quotation=self.quotation)),
            Decimal("0"),
        )
        self.assertEqual(self.quotation.peso_liquido_kg.quantize(Decimal("0.01")),
                         esperado.quantize(Decimal("0.01")))

    # ── M1.4 · restaurar de verdade ────────────────────────────────────────────
    def _operacao_horaria(self):
        op = ItemOperation.objects.filter(
            item__quotation=self.quotation, custo_direto=False, aplicavel=True
        ).select_related("item").first()
        self.assertIsNotNone(op, "fixture precisa de operação horária")
        return op

    def test_restaurar_repoe_tambem_a_taxa_do_motor(self):
        """Restaurar só as horas e manter a taxa manual devolve um custo que NÃO é o
        do motor, com o rótulo dizendo que é."""
        op = self._operacao_horaria()
        taxa_do_motor = op.taxa_hora
        horas_do_motor = op.horas_hh

        # Override manual: mexe nas horas E na taxa.
        self.client.post(reverse("quotations:eap_item_save", args=[op.item.pk]), {
            "motivo": MOTIVO,
            f"op_horas_hh_{op.pk}": "1.00",
            f"op_taxa_hh_{op.pk}": str(taxa_do_motor + Decimal("77.00")),
        })
        op.refresh_from_db()
        self.assertEqual(op.origem, "manual")

        self.client.post(reverse("quotations:eap_op_restore", args=[op.pk]),
                         {"motivo": MOTIVO})

        op.refresh_from_db()
        self.assertEqual(op.horas_hh, horas_do_motor, "horas voltaram")
        self.assertEqual(op.taxa_hora, taxa_do_motor,
                         "a taxa também tem de voltar — senão 'seed' é rótulo falso")
        self.assertEqual(op.origem, "seed")

    def test_custo_apos_restaurar_bate_com_o_do_motor(self):
        op = self._operacao_horaria()
        custo_do_motor = op.custo

        self.client.post(reverse("quotations:eap_item_save", args=[op.item.pk]), {
            "motivo": MOTIVO,
            f"op_horas_hh_{op.pk}": "3.00",
            f"op_taxa_hh_{op.pk}": str(op.taxa_hora + Decimal("50.00")),
        })
        self.client.post(reverse("quotations:eap_op_restore", args=[op.pk]),
                         {"motivo": MOTIVO})

        op.refresh_from_db()
        self.assertEqual(op.custo, custo_do_motor,
                         "restaurado tem de reproduzir o custo original do motor")
