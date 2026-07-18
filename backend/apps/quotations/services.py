"""Serviços de cotação: numeração sequencial por tenant, criação e snapshots."""
from datetime import date, datetime
from decimal import Decimal
import hashlib
import json
from django.db import transaction
from django.utils import timezone
from apps.quotations.models import CalculationSnapshot, Quotation
from apps.quotations.adapter import default_inputs, recompute


def _d(x) -> Decimal:
    """float/str → Decimal com 2 casas (campos monetários da Quotation)."""
    return Decimal(str(round(float(x or 0), 2)))


ENGINE_VERSION = "calc-snapshot-v1"


def _normalize_snapshot_value(value):
    if isinstance(value, dict):
        return {str(k): _normalize_snapshot_value(value[k]) for k in sorted(value)}
    if isinstance(value, (list, tuple)):
        return [_normalize_snapshot_value(v) for v in value]
    if isinstance(value, set):
        return [_normalize_snapshot_value(v) for v in sorted(value, key=repr)]
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat()
    if hasattr(value, "isoformat") and not isinstance(value, str):
        try:
            return value.isoformat()
        except Exception:
            pass
    return value


def _canonical_json(value) -> str:
    return json.dumps(_normalize_snapshot_value(value), sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _quotation_memorial(quotation) -> list:
    if getattr(quotation, "scope", None) != "complete":
        return []
    inp = quotation.inputs or {}
    from apps.tema_templates.services import memorial_asme
    return memorial_asme(inp.get("designacao", ""), inp)


def _snapshot_standard_refs(memorial: list) -> list:
    refs = []
    seen = set()
    for entry in memorial or []:
        if not isinstance(entry, dict):
            continue
        ref = {
            k: entry.get(k)
            for k in ("item", "norma", "fonte")
            if entry.get(k)
        }
        key = tuple(ref.get(k) for k in ("item", "norma", "fonte"))
        if not any(ref.values()) or key in seen:
            continue
        seen.add(key)
        refs.append(ref)
    return refs


def _requires_memorial(quotation) -> bool:
    inputs = quotation.inputs or {}
    return quotation.scope == "complete" and bool(inputs.get("pressao_projeto_bar"))


def build_snapshot_payload(quotation, memorial=None) -> dict:
    memorial = _quotation_memorial(quotation) if memorial is None else memorial
    if _requires_memorial(quotation) and not memorial:
        raise RuntimeError("CalculationSnapshot de permutador pressurizado exige memorial ASME.")
    items = []
    for item in quotation.itens.prefetch_related("materiais", "operacoes").all():
        items.append({
            "codigo_item": item.codigo_item,
            "descricao": item.descricao,
            "custo_material": str(item.custo_material),
            "custo_mo": str(item.custo_mo),
            "sort_order": item.sort_order,
            "materiais": [
                {
                    "codigo_mp": mp.codigo_mp,
                    "descricao": mp.descricao,
                    "material": mp.material,
                    "forma": mp.forma,
                    "peso_bruto_kg": str(mp.peso_bruto_kg),
                    "peso_liquido_kg": str(mp.peso_liquido_kg),
                    "preco_kgf": str(mp.preco_kgf),
                    "custo": str(mp.custo),
                }
                for mp in item.materiais.order_by("codigo_mp", "id")
            ],
            "operacoes": [
                {
                    "codigo_op": op.codigo_op,
                    "descricao": op.descricao,
                    "metodo": op.metodo,
                    "custo": str(op.custo),
                    "aplicavel": op.aplicavel,
                }
                for op in item.operacoes.order_by("codigo_op", "id")
            ],
        })
    totals = {
        "custo_material": str(quotation.custo_material),
        "custo_mo": str(quotation.custo_mo),
        "custo_total": str(quotation.custo_total),
        "preco_sem_impostos": str(quotation.preco_sem_impostos),
        "preco_com_impostos": str(quotation.preco_com_impostos),
        "peso_bruto_kg": str(quotation.peso_bruto_kg),
        "peso_liquido_kg": str(quotation.peso_liquido_kg),
    }
    outputs = {
        "scope": quotation.scope,
        "number": quotation.number,
        "revision": quotation.revision,
        "totals": totals,
        "items": items,
    }
    if memorial:
        outputs["memorial"] = memorial
    inputs = {
        "quotation": {
            "number": quotation.number,
            "revision": quotation.revision,
            "scope": quotation.scope,
            "title": quotation.title,
        },
        "inputs": _normalize_snapshot_value(quotation.inputs or {}),
        "pricing": {
            "fator_preco": str(quotation.fator_preco),
            "impostos_pct": str(quotation.impostos_pct),
        },
    }
    standard_refs = _snapshot_standard_refs(memorial)
    payload = {
        "engine_version": ENGINE_VERSION,
        "inputs": inputs,
        "outputs": outputs,
        "standard_refs": standard_refs,
    }
    payload["snapshot_hash"] = hashlib.sha256(_canonical_json(payload).encode("utf-8")).hexdigest()
    return payload


def create_calculation_snapshot(quotation, memorial=None) -> CalculationSnapshot:
    payload = build_snapshot_payload(quotation, memorial=memorial)
    snapshot = CalculationSnapshot.objects.create(
        quotation=quotation,
        snapshot_hash=payload["snapshot_hash"],
        inputs=payload["inputs"],
        outputs=payload["outputs"],
        engine_version=payload["engine_version"],
        standard_refs=payload["standard_refs"],
    )
    # RBAC V2 M4: recalcular a cotação invalida cases de aprovação OPEN cujo snapshot
    # divergiu (mesma filosofia do TechnicalApproval). Import tardio: evita ciclo audit↔quotations.
    if payload["snapshot_hash"]:
        from apps.audit.approvals import invalidate_stale_cases

        invalidate_stale_cases(quotation)
    return snapshot


def next_number() -> str:
    """Gera COT-{ANO}-{SEQ:03d} sequencial no schema do tenant."""
    ano = date.today().year
    prefixo = f"COT-{ano}-"
    ultimo = (Quotation.objects.filter(number__startswith=prefixo)
              .order_by("-number").values_list("number", flat=True).first())
    seq = int(ultimo.split("-")[-1]) + 1 if ultimo else 1
    return f"{prefixo}{seq:03d}"


@transaction.atomic
def create_feixe_quotation(customer, title, created_by=None, inputs=None) -> Quotation:
    """Cria uma cotação de feixe com inputs (default = caso 136) e computa."""
    q = Quotation.objects.create(
        number=next_number(), customer=customer, title=title,
        scope="tube_bundle", created_by=created_by,
        inputs=inputs or default_inputs(),
    )
    recompute(q)
    create_calculation_snapshot(q)
    return q


def _inputs_serializaveis(cleaned: dict) -> dict:
    """Subconjunto JSON-serializável do data sheet (descarta objetos não serializáveis)."""
    import json
    out = {}
    for k, v in (cleaned or {}).items():
        try:
            json.dumps(v)
            out[k] = v
        except (TypeError, ValueError):
            out[k] = str(v)
    return out


@transaction.atomic
def create_permutador_quotation(customer, designacao, cleaned, resultado,
                                created_by=None, title=None, number=None, revision=0) -> Quotation:
    """Persiste uma cotação de PERMUTADOR COMPLETO a partir do resultado do motor
    (tema_templates.estimate_complete / pricing_engine.quote_completo). Fecha o elo
    motor → Quotation, de onde a proposta é gerada. Cria itens a partir de por_secao."""
    from apps.quotations.models import QuotationItem
    desig = (designacao or "").upper()
    custo_mo = float(resultado.get("custo_mao_obra", 0)) + float(resultado.get("custo_servicos", 0))
    q = Quotation.objects.create(
        number=number or next_number(), revision=revision, customer=customer, scope="complete",
        title=title or f"Permutador {desig}", created_by=created_by,
        inputs={**_inputs_serializaveis(cleaned), "designacao": desig},
        custo_material=_d(resultado.get("custo_material")),
        custo_mo=_d(custo_mo),
        custo_total=_d(resultado.get("custo_total")),
        preco_sem_impostos=_d(resultado.get("preco_sem_impostos")),
        preco_com_impostos=_d(resultado.get("preco_com_impostos")),
        fator_preco=_d(resultado.get("fator_preco", 1)),
        impostos_pct=_d(resultado.get("impostos_pct", 0)),
        computed_at=timezone.now(),
    )
    # itens da EAP a partir das seções do motor (material vs fabricação/finalização = MO)
    for i, (secao, valor) in enumerate(sorted((resultado.get("por_secao") or {}).items())):
        is_material = "material" in secao
        QuotationItem.objects.create(
            quotation=q, codigo_item=secao[:30], descricao=secao.replace("_", " ").title(),
            custo_material=_d(valor) if is_material else Decimal("0"),
            custo_mo=Decimal("0") if is_material else _d(valor),
            sort_order=i,
        )
    create_calculation_snapshot(q)
    return q
