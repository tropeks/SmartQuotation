"""
Ordem 006 — `adapter.persist_complete` gravava `fator_preco` (DecimalField 8,5) e
`impostos_pct` (6,3) via `_money2`, que quantiza a 2 casas SEMPRE — pensado para os campos
monetários (custo_*/preco_*), não para esses dois, que são política comercial, não dinheiro.
Markup fracionário (ex.: 1,01377 — o próprio default do campo) virava 1,01; impostos
23,303 viravam 23,30. O `CalculationSnapshot` (inputs.pricing) e o `snapshot_hash` herdam
a string truncada porque `build_snapshot_payload` lê `str(quotation.fator_preco)` do objeto em
memória recém-criado (sem round-trip pelo Postgres).

Este arquivo prova:
  1) o caso sintético do relato (1,01377 / 23,303) preserva as casas do CAMPO, não 2, na
     Quotation persistida E no snapshot.inputs.pricing (vermelho antes do fix: TRUNCA).
  2) BEU de referência (motor usa 1,25/9,0 fixos — `tenant_cost_chain()` não injeta markup
     do tenant no permutador completo, ordem 008 fora de escopo): preco_com_impostos e
     preco_sem_impostos são EXATAMENTE os mesmos antes/depois do fix — só a STRING gravada
     (e portanto o snapshot_hash) muda de "1.25"/"9.0" para "1.25000"/"9.000".
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

    def test_beu_referencia_preco_identico_so_string_do_hash_muda(self):
        """BEU de referência: o motor sempre usa 1,25/9,0 fixos (nenhum knob de tenant
        entra em quote_completo hoje — ordem 008). O PREÇO não muda; a STRING gravada
        (e o snapshot_hash, por depender dela) sim: "1.25"/"9.0" -> "1.25000"/"9.000"."""
        resultado = _resultado_sintetico(
            fator_preco=1.25, impostos_pct=9.0,
            preco_com_impostos=2000.0, preco_sem_impostos=1830.28,
        )
        q = persist_complete(
            customer=self.customer, designacao="BEU", cleaned={"designacao": "BEU"},
            resultado=resultado, created_by=self.user, title="BEU Referência 006",
        )

        # Preço: idêntico antes/depois do fix — 1,25/9,0 não truncam em 2 casas, então o
        # VALOR nunca esteve em risco aqui (a prova de valor real está no teste acima).
        self.assertEqual(q.preco_com_impostos, Decimal("2000.00"))
        self.assertEqual(q.preco_sem_impostos, Decimal("1830.28"))

        # O snapshot é montado a partir do objeto em memória, ANTES de qualquer refresh —
        # é aqui que a STRING muda de formato: "1.25"/"9.0" (2 casas, `_money2`) para
        # "1.25000"/"9.000" (casa do campo, `_q`). Isso é o que move o snapshot_hash.
        snap = q.snapshots.first()
        self.assertEqual(snap.inputs["pricing"]["fator_preco"], "1.25000")
        self.assertEqual(snap.inputs["pricing"]["impostos_pct"], "9.000")

    def test_persist_complete_recusa_fator_ou_impostos_none(self):
        """Chave presente com valor None (dict.get não aplica o default) não pode virar 0
        em silêncio — `_money2` gravava fator 0; `_q` falha alto com a causa."""
        for campo in ("fator_preco", "impostos_pct"):
            with self.subTest(campo=campo):
                with self.assertRaisesMessage(ValueError, campo):
                    persist_complete(
                        customer=self.customer, designacao="BEU",
                        cleaned={"designacao": "BEU"},
                        resultado=_resultado_sintetico(**{campo: None}),
                        created_by=self.user, title="None 006",
                    )
