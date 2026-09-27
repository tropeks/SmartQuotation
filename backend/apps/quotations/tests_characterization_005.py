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
refactor inalterada). A única exceção é a fixture da cena (e), construída via ORM cru +
pricing_engine.permutador_quote.quote_completo direto (chamada de simulação, não de
persistência de produção — permitida em qualquer lado do refactor).

Cenários (cada um vira uma chave do golden):
  a) POST "salvar" no data sheet, BEU de referência (razão 1,0 nos drivers paramétricos).
  b) idem, BEM de referência.
  c) BEU com dimensões e liga alteradas + pressão de projeto > 0 (exige memorial ASME).
  d) quotation_revise() da cotação (a).
  e) quotation_revise() de uma cotação com inputs inválidos → cai no fallback
     `quote_completo(desig)` de estimate_from_inputs.
  f) adapter.recompute() sobre a cotação (a).

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


def _capture(q: Quotation) -> dict:
    q.refresh_from_db()
    itens = [_item_payload(it) for it in q.itens.order_by("sort_order", "id")]
    return {
        "quotation": _quotation_payload(q),
        "itens": itens,
        "snapshot": _snapshot_payload(q),
    }


def _fallback_seed_quotation(customer, created_by) -> Quotation:
    """Fixture da cena (e): cotação 'complete' com inputs incompletos (form fica inválido em
    estimate_from_inputs → revise cai no fallback quote_completo(desig)). Construída via ORM
    cru + motor direto: NÃO é o caminho de persistência de produção caracterizado aqui."""
    from pricing_engine.permutador_quote import quote_completo

    resultado_seed = quote_completo("BEU")
    custo_mo_seed = (float(resultado_seed.get("custo_mao_obra", 0))
                      + float(resultado_seed.get("custo_servicos", 0)))
    return Quotation.objects.create(
        number="COT-2026-900", revision=0, customer=customer, scope="complete",
        title="BEU inválido p/ fallback", created_by=created_by,
        inputs={"designacao": "BEU", "n_tubos": 68},  # incompleto: form fica inválido
        custo_material=Decimal(str(round(resultado_seed["custo_material"], 2))),
        custo_mo=Decimal(str(round(custo_mo_seed, 2))),
        custo_total=Decimal(str(round(resultado_seed["custo_total"], 2))),
        preco_sem_impostos=Decimal(str(round(resultado_seed["preco_sem_impostos"], 2))),
        preco_com_impostos=Decimal(str(round(resultado_seed["preco_com_impostos"], 2))),
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
        q_d = self._revise(q_a.pk)
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
