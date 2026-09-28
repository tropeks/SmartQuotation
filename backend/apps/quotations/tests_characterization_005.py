"""
Caracterização (ordem 005) — fotografia do comportamento ATUAL da persistência do
permutador completo, ANTES de mover apps.quotations.services.create_permutador_quotation
para apps.quotations.adapter (persist_complete/revise_complete).

Hoje, essa função é chamada por:
  - apps/tema_templates/views.py:data_sheet (POST "salvar")
  - apps/quotations/views.py:quotation_revise (scope == "complete")

Este teste NUNCA importa create_permutador_quotation nem persist_complete diretamente: o
nome muda de módulo entre C1 (código atual) e C2 (mudança), e este arquivo tem de continuar
IMPORTÁVEL e VERDE nos dois lados, comparando com o MESMO golden. Por isso ele dirige tudo
por HTTP (URLs não mudam) e por apps.quotations.adapter.recompute (função que sobrevive ao
refactor inalterada). A fixture da cena (e) é construída via ORM cru com PLACEHOLDERS fixos
(não chama o motor): o fallback de verdade (`quote_completo`) roda dentro de
`revise_complete`, por conta do próprio adapter — este arquivo não precisa importar
`pricing_engine.permutador_quote` (mantém a allowlist do `.importlinter` enxuta).

Cenários (cada um vira uma chave do golden):
  a) POST "salvar" no data sheet, BEU de referência (razão 1,0 nos drivers paramétricos).
  b) idem, BEM de referência.
  c) BEU com dimensões e liga alteradas + pressão de projeto > 0 (exige memorial ASME).
  d) quotation_revise() da cotação (a), depois de forçar (a) p/ status "sent" (prova por
     assertEqual, não só pelo golden: a revisão nasce em "draft" mesmo partindo de uma
     original que NÃO estava em draft).
  e) quotation_revise() de uma cotação com inputs inválidos → cai no fallback
     `quote_completo(desig)` de estimate_from_inputs.
  f) adapter.recompute() sobre a cotação (a) (já com status "sent" da cena (d)).

Cada cenário captura, além dos totais/itens/snapshot: created_by.username, customer.
company_name e, para a Quotation capturada, as Proposal ligadas a ela (number, status,
quotation_number de vínculo, docx_path/pdf_path, generated_at_is_null) — só (a)/(b)/(c)
geram Proposal (o data sheet chama create_proposal() só no "salvar"; quotation_revise não).

O golden é gravado (`json.dump`) SOMENTE com SQ_RECORD_CHAR=1 no ambiente — rode assim só
sobre o código ANTES da ordem 005. Sem a env var, o teste COMPARA contra o golden versionado
em backend/apps/quotations/golden/char_005.json.

Não-determinismo normalizado, fora do golden:
  - número da cotação: apps.quotations.services.date é mockado (next_number() usa
    date.today().year) para uma data fixa;
  - PKs de qualquer model: nunca aparecem no golden;
  - created_at/updated_at/CalculationSnapshot.created_at: nunca comparados; só
    `computed_at is None?` (bool) entra no golden.
"""
import json
import os
from datetime import date as real_date
from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.utils import timezone
from django_tenants.test.cases import TenantTestCase

from apps.accounts.models import UserProfile
from apps.audit.models import AccessLog, ApprovalCase
from apps.proposals.models import Proposal
from apps.quotations.adapter import recompute
from apps.quotations.models import Customer, Quotation

GOLDEN_PATH = os.path.join(os.path.dirname(__file__), "golden", "char_005.json")
RECORD = os.environ.get("SQ_RECORD_CHAR") == "1"

# "BEU de referência": os mesmos valores de reference_inputs('BEU') (KnobsConfigTests._REF,
# tema_templates/tests.py) — razão 1,0 nos drivers paramétricos, RT "Total" (baseline do
# referencial, Wellington 2026-06-13).
_REF_BEU = {
    "designacao": "BEU", "n_tubos": 68, "comprimento_tubo_mm": 13000,
    "od_tubo_mm": 19.05, "esp_tubo_mm": 2.108, "n_chicanas": 1,
    "comprimento_casco_mm": 1631, "diametro_casco_mm": 764,
    "esp_casco_mm": 9.5, "n_passes_tubos": 2, "rt_escopo": "Total",
    "classe_feixe": "CS", "classe_casco": "CS", "fluido_corrosivo": "Tubos",
    "fator_correcao_mo": 1.0,
}
# "BEM de referência": reference_inputs('BEM') — mesma forma, designação/tubos/comprimento
# do tubo diferentes (seed do BEM).
_REF_BEM = {**_REF_BEU, "designacao": "BEM", "n_tubos": 136, "comprimento_tubo_mm": 6096}
# BEU com geometria e liga fora da referência + pressão de projeto real (exige memorial ASME).
_ALT_BEU = {
    **_REF_BEU, "n_tubos": 100, "comprimento_tubo_mm": 9000, "diametro_casco_mm": 900,
    "esp_casco_mm": 12, "classe_feixe": "INOX", "classe_casco": "CS",
    "pressao_projeto_bar": 15, "temperatura_projeto_c": 150, "corrosao_mm": 3,
    "densidade_fluido_kg_m3": 1000,
}


def _quotation_payload(q: Quotation) -> dict:
    return {
        "number": q.number,
        "revision": q.revision,
        "scope": q.scope,
        "status": q.status,
        "title": q.title,
        "inputs": q.inputs,
        "avisos": q.avisos,
        "fator_preco": str(q.fator_preco),
        "impostos_pct": str(q.impostos_pct),
        "custo_material": str(q.custo_material),
        "custo_mo": str(q.custo_mo),
        "custo_total": str(q.custo_total),
        "preco_sem_impostos": str(q.preco_sem_impostos),
        "preco_com_impostos": str(q.preco_com_impostos),
        "peso_bruto_kg": str(q.peso_bruto_kg),
        "peso_liquido_kg": str(q.peso_liquido_kg),
        "pricing_basis": q.pricing_basis,
        "computed_at_is_null": q.computed_at is None,
        "created_by_username": q.created_by.username if q.created_by_id else None,
        "customer_company_name": q.customer.company_name,
    }


def _material_payload(mp) -> dict:
    return {
        "codigo_mp": mp.codigo_mp,
        "descricao": mp.descricao,
        "material": mp.material,
        "forma": mp.forma,
        "peso_bruto_kg": str(mp.peso_bruto_kg),
        "peso_liquido_kg": str(mp.peso_liquido_kg),
        "preco_kgf": str(mp.preco_kgf),
        "custo": str(mp.custo),
    }


def _operacao_payload(op) -> dict:
    return {
        "codigo_op": op.codigo_op,
        "descricao": op.descricao,
        "metodo": op.metodo,
        "custo": str(op.custo),
        "horas_hh": str(op.horas_hh),
        "horas_hm": str(op.horas_hm),
        "taxa_hora": str(op.taxa_hora),
        "taxa_hora_hm": str(op.taxa_hora_hm),
        "custo_direto": op.custo_direto,
        "origem": op.origem,
        "aplicavel": op.aplicavel,
    }


def _item_payload(item) -> dict:
    materiais = [_material_payload(mp) for mp in item.materiais.order_by("codigo_mp", "id")]
    operacoes = [_operacao_payload(op) for op in item.operacoes.order_by("codigo_op", "id")]
    return {
        "codigo_item": item.codigo_item,
        "descricao": item.descricao,
        "custo_material": str(item.custo_material),
        "custo_mo": str(item.custo_mo),
        "sort_order": item.sort_order,
        "materiais": materiais,
        "operacoes": operacoes,
    }


def _snapshot_payload(q: Quotation) -> dict:
    snap = q.snapshots.first()
    if snap is None:
        return {"count": 0, "snapshot": None}
    return {
        "count": q.snapshots.count(),
        "snapshot": {
            "snapshot_hash": snap.snapshot_hash,
            "engine_version": snap.engine_version,
            "inputs": snap.inputs,
            "outputs": snap.outputs,
            "standard_refs": snap.standard_refs,
        },
    }


def _proposal_payload(q: Quotation) -> list:
    """Campos principais das Proposal ligadas a q, + o número da PRÓPRIA cotação (prova
    de vínculo — apps.proposals.services.next_proposal_number deriva de quotation.number)."""
    return [
        {
            "number": p.number,
            "status": p.status,
            "quotation_number": p.quotation.number,
            "docx_path": p.docx_path,
            "pdf_path": p.pdf_path,
            "generated_at_is_null": p.generated_at is None,
        }
        for p in q.proposals.order_by("id")
    ]


def _capture(q: Quotation) -> dict:
    q.refresh_from_db()
    itens = [_item_payload(it) for it in q.itens.order_by("sort_order", "id")]
    return {
        "quotation": _quotation_payload(q),
        "itens": itens,
        "snapshot": _snapshot_payload(q),
        "propostas": _proposal_payload(q),
    }


def _fallback_seed_quotation(customer, created_by) -> Quotation:
    """Fixture da cena (e): cotação 'complete' com inputs incompletos — `estimate_from_inputs`
    devolve None (form inválido) e `revise_complete` cai no fallback `quote_completo(desig)`,
    chamado pelo PRÓPRIO adapter durante a revisão, não aqui. Os totais abaixo são
    PLACEHOLDERS arbitrários (a revisão os substitui integralmente pelo resultado real do
    fallback) — de propósito, para este arquivo não precisar importar
    `pricing_engine.permutador_quote` (mantém a allowlist do `.importlinter` enxuta).

    fator_preco/impostos_pct EXPLÍCITOS (ordem 008): sem isto, `Quotation.objects.create`
    cai no default do MODEL (1,01377/23,303 — o par do FEIXE, não do permutador), porque esta
    fixture nunca passou por `persist_complete` (que sempre grava o par do resultado do
    motor). Uma cotação `scope='complete'` real NUNCA tem esses defaults — `persist_complete`
    sempre grava o que `quote_completo` devolveu (1,25/9,0 ou o do tenant). Ordem 008 (c) faz
    `revise_complete` CONGELAR o fator_preco/impostos_pct da ORIGINAL — sem o valor explícito
    aqui, a revisão desta cena congelaria o artefato do fixture (1,01377/23,303) em vez do
    par real do permutador, e o golden mudaria por um motivo estranho ao escopo desta ordem."""
    return Quotation.objects.create(
        number="COT-2026-900", revision=0, customer=customer, scope="complete",
        title="BEU inválido p/ fallback", created_by=created_by,
        inputs={"designacao": "BEU", "n_tubos": 68},  # incompleto: form fica inválido
        custo_material=Decimal("1.00"), custo_mo=Decimal("1.00"), custo_total=Decimal("2.00"),
        preco_sem_impostos=Decimal("2.00"), preco_com_impostos=Decimal("2.00"),
        fator_preco=Decimal("1.25"), impostos_pct=Decimal("9.0"),
        computed_at=timezone.now(),
    )


class PersistenciaPermutadorCharacterizationTests(TenantTestCase):
    """Golden test da ordem 005 — ver docstring do módulo."""

    def setUp(self):
        self.client.defaults["HTTP_HOST"] = self.get_test_tenant_domain()
        User = get_user_model()
        self.admin = User.objects.create_user(username="admin-char-005", password="x")
        UserProfile.objects.create(
            user=self.admin, full_name="Admin Caracterização", role=UserProfile.ROLE_ADMIN)
        self.client.force_login(self.admin)

    def _post_data_sheet(self, payload: dict, cliente: str):
        data = {**payload, "salvar": "1", "cliente": cliente}
        resp = self.client.post("/tema/permutador/", data)
        self.assertEqual(resp.status_code, 200, resp.content[:2000])
        return resp

    def _revise(self, pk: int) -> Quotation:
        resp = self.client.post(f"/cotacoes/{pk}/revisar/")
        self.assertEqual(resp.status_code, 302)
        return Quotation.objects.get(pk=resp.url.split("/")[-2])

    def _cena_a(self) -> Quotation:
        self._post_data_sheet(_REF_BEU, "ACME Char A")
        q = Quotation.objects.filter(scope="complete").order_by("-id").first()
        self.assertIsNotNone(q, "data sheet deveria ter persistido a cotação BEU (a)")
        return q

    def _cena_b(self, excluir_pks) -> Quotation:
        self._post_data_sheet(_REF_BEM, "ACME Char B")
        q = (Quotation.objects.filter(scope="complete")
             .exclude(pk__in=excluir_pks).order_by("-id").first())
        self.assertIsNotNone(q, "data sheet deveria ter persistido a cotação BEM (b)")
        return q

    def _cena_c(self, excluir_pks) -> Quotation:
        self._post_data_sheet(_ALT_BEU, "ACME Char C")
        q = (Quotation.objects.filter(scope="complete")
             .exclude(pk__in=excluir_pks).order_by("-id").first())
        self.assertIsNotNone(q, "data sheet deveria ter persistido a cotação BEU alterada (c)")
        return q

    def _cena_e(self) -> Quotation:
        cust_e, _ = Customer.objects.get_or_create(company_name="ACME Char E")
        orig = _fallback_seed_quotation(cust_e, self.admin)
        return self._revise(orig.pk)

    @patch("apps.quotations.services.date")
    def test_caracterizacao_persistencia_permutador(self, mock_date):
        # Número determinístico: next_number() lê date.today().year.
        mock_date.today.return_value = real_date(2026, 1, 1)

        accesslog_antes = AccessLog.objects.count()
        approvalcase_antes = ApprovalCase.objects.count()

        q_a = self._cena_a()
        q_b = self._cena_b(excluir_pks=[q_a.pk])
        q_c = self._cena_c(excluir_pks=[q_a.pk, q_b.pk])

        # (d): a revisão sempre nasce em "draft" — inclusive quando a cotação ORIGINAL já
        # saiu do rascunho (ex.: enviada). Muda o status de (a) ANTES de revisar para provar
        # que "draft" na revisão não é um acidente de a original já estar em draft.
        q_a.status = "sent"
        q_a.save(update_fields=["status"])
        self.assertNotEqual(q_a.status, "draft")
        q_d = self._revise(q_a.pk)
        self.assertEqual(q_d.status, "draft")

        q_e = self._cena_e()

        golden = {
            "a": _capture(q_a),
            "b": _capture(q_b),
            "c": _capture(q_c),
            "d": _capture(q_d),
            "e": _capture(q_e),
        }

        recompute(q_a)  # (f) adapter.recompute() sobre (a) — não muda nesta ordem.
        golden["f"] = _capture(q_a)

        golden["counts"] = {
            "proposal_total": Proposal.objects.count(),
            "accesslog_delta": AccessLog.objects.count() - accesslog_antes,
            "approvalcase_delta": ApprovalCase.objects.count() - approvalcase_antes,
        }

        self._record_or_compare(golden)

    def _record_or_compare(self, golden: dict) -> None:
        if RECORD:
            os.makedirs(os.path.dirname(GOLDEN_PATH), exist_ok=True)
            with open(GOLDEN_PATH, "w", encoding="utf-8") as fh:
                json.dump(golden, fh, indent=2, sort_keys=True, ensure_ascii=False)
                fh.write("\n")
            return

        with open(GOLDEN_PATH, encoding="utf-8") as fh:
            expected = json.load(fh)
        # normaliza `golden` por um round-trip JSON (mesmos tipos que o golden carregado).
        actual = json.loads(json.dumps(golden, sort_keys=True))
        self.assertEqual(actual, expected)
