"""
Ordem 006 — `adapter.persist_complete` gravava `fator_preco` (DecimalField 8,5) e
`impostos_pct` (6,3) via `_money2`, que quantiza a 2 casas SEMPRE — pensado para os campos
monetários (custo_*/preco_*), não para esses dois, que são política comercial, não dinheiro.
Markup fracionário (ex.: 1,01377 — o próprio default do campo) virava 1,01; impostos
23,303 viravam 23,30. O `CalculationSnapshot` (inputs.pricing) e o `snapshot_hash` herdam
a string truncada porque `build_snapshot_payload` lê `str(quotation.fator_preco)` do banco.

Este arquivo prova o caso sintético do relato (1,01377 / 23,303): preserva as casas do
CAMPO, não 2, na Quotation persistida E no snapshot.inputs.pricing (vermelho antes do fix:
TRUNCA — 1,01377 vira 1,01000; 23,303 vira 23,300... na verdade 23,30, ver traceback).
"""
from decimal import Decimal

from django.contrib.auth import get_user_model
from django_tenants.test.cases import TenantTestCase

from apps.accounts.models import UserProfile
from apps.quotations.adapter import persist_complete
from apps.quotations.models import Customer


def _resultado_sintetico(**overrides) -> dict:
    base = {
        "custo_material": 1000.0,
        "custo_mao_obra": 500.0,
        "custo_servicos": 100.0,
        "custo_total": 1600.0,
        "por_secao": {"material_feixe": 1000.0, "fabricacao_mo": 500.0, "servicos": 100.0},
        "fator_preco": 1.01377,
        "impostos_pct": 23.303,
        "preco_com_impostos": 1622.03,
        "preco_sem_impostos": 1319.87,
    }
    base.update(overrides)
    return base


class PrecisaoFatorPrecoImpostosPctTests(TenantTestCase):
    """Ordem 006 — casas de fator_preco/impostos_pct sobrevivem ao adapter."""

    def setUp(self):
        self.client.defaults["HTTP_HOST"] = self.get_test_tenant_domain()
        User = get_user_model()
        self.user = User.objects.create_user(username="orc-006", password="x")
        UserProfile.objects.create(
            user=self.user, full_name="Orçamentista 006", role=UserProfile.ROLE_ORCAMENTISTA)
        self.customer = Customer.objects.create(company_name="ACME Precisão 006")

    def test_persist_complete_preserva_casas_do_campo_fator_e_impostos(self):
        """Caso sintético do relato: 1,01377 (fator, campo 8,5) e 23,303 (impostos, campo
        6,3) — nenhum dos dois é redondo em 2 casas. `_money2` truncaria para 1,01/23,30."""
        resultado = _resultado_sintetico()
        q = persist_complete(
            customer=self.customer, designacao="BEU", cleaned={"designacao": "BEU"},
            resultado=resultado, created_by=self.user, title="Precisão 006",
        )
        q.refresh_from_db()

        self.assertEqual(q.fator_preco, Decimal("1.01377"))
        self.assertEqual(q.impostos_pct, Decimal("23.303"))

        snap = q.snapshots.first()
        self.assertIsNotNone(snap, "persist_complete deveria ter criado o CalculationSnapshot")
        self.assertEqual(snap.inputs["pricing"]["fator_preco"], "1.01377")
        self.assertEqual(snap.inputs["pricing"]["impostos_pct"], "23.303")
