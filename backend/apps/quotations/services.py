"""Serviços de cotação: numeração sequencial por tenant, criação e snapshots."""
from datetime import date, datetime
from decimal import Decimal
import hashlib
import json
from django.db import IntegrityError, models, transaction
from apps.quotations.models import CalculationSnapshot, Quotation
from apps.quotations.adapter import default_inputs, recompute


class RevisionConflictError(Exception):
    """Corrida entre duas revisões concorrentes do MESMO `number` — a UniqueConstraint
    `uniq_quotation_number_revision` rejeitou o INSERT (IntegrityError). `allocate_revision`
    (select_for_update) já serializa o caso normal; isto é o backstop para quando o INSERT
    corre fora do lock (ou o nível de isolamento do banco permite a corrida). Vira mensagem
    de conflito ao usuário — nunca um 500."""


class NotCurrentRevisionError(Exception):
    """P2: ação bloqueada porque a cotação não é a revisão VIGENTE (a de maior `revision`)
    do seu `number` — só a vigente pode enviar proposta ou virar Ordem de Fabricação."""


class CustomerChangeNotAllowedError(Exception):
    """P6: uma revisão não pode trocar o cliente da cotação original."""


class QuotationHasProductionOrderError(Exception):
    """P7: não se revisa uma cotação cujo `number` já tem Ordem de Fabricação ativa
    (não cancelada) — em qualquer revisão desse número."""


# v2 (M1): `outputs.items.operacoes` passou a carregar horas, taxas, custo_direto e
# origem. Sem o bump, snapshots de formatos diferentes se identificavam igual e quem
# comparasse épocas distintas não teria como saber que o schema mudou. A versão é
# metadado — não entra no hash de identidade, então bumpar não invalida nada.
ENGINE_VERSION = "calc-snapshot-v2"


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
    """Permutador completo COM pressão de projeto real exige memorial ASME.

    A coerção para float não é preciosismo: `memorial_asme` decide se há pressão fazendo
    `float(...)`, e este guard decidia por truthiness do JSON cru. Os dois discordavam
    para qualquer valor truthy mas não coercível — `"50,0"`, `"50 bar"`, ou `"0"` como
    string — e o guard passava a EXIGIR um memorial que o construtor não tinha como
    montar. Resultado: RuntimeError, e desde que a edição da EAP emite snapshot, 500 ao
    editar uma cotação legada.

    Valor não coercível ou ≤ 0 significa que não há pressão de projeto utilizável, e sem
    ela não existe memória de pressão a escrever. O compliance continua de pé onde ele
    faz sentido: pressão numérica positiva segue exigindo o memorial.
    """
    inputs = quotation.inputs or {}
    if quotation.scope != "complete":
        return False
    try:
        return float(inputs.get("pressao_projeto_bar") or 0) > 0
    except (TypeError, ValueError):
        return False


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
            # HORAS E TAXAS ENTRAM NO HASH (M1). Guardar só o `custo` deixava o
            # snapshot cego a `custo = horas × taxa`: dava para partir as horas pela
            # metade e dobrar a taxa que o custo — e portanto o hash — não mudava, e a
            # assinatura técnica continuava casando. A Ordem de Fabricação copia as
            # HORAS para o chão de fábrica (production/services.py), então o que o
            # engenheiro assinou e o que a fábrica executa divergiam em silêncio.
            "operacoes": [
                {
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


def allocate_revision(orig: Quotation) -> int:
    """Ordem 007 — aloca a PRÓXIMA revisão de `orig.number`: max(revision)+1 entre TODAS
    as linhas do mesmo número (P3: revisar a partir de uma revisão antiga também sai com
    max+1, nunca `orig.revision+1` — senão duas revisões concorrentes a partir de revisões
    antigas diferentes colidiriam).

    `select_for_update()` TRAVA essas linhas — precisa ser chamada DENTRO da MESMA
    `transaction.atomic()` que faz o INSERT da revisão nova: é a trava seguindo até o
    commit que serializa dois pedidos de revisão concorrentes do mesmo número (o segundo
    espera o primeiro commitar, e então enxerga o `max(revision)` já atualizado).
    """
    maior = (Quotation.objects.select_for_update()
             .filter(number=orig.number)
             .aggregate(models.Max("revision"))["revision__max"])
    base = maior if maior is not None else orig.revision
    return base + 1


def is_current_revision(quotation: Quotation) -> bool:
    """P1/P2: True sse `quotation` é a revisão VIGENTE (maior `revision`) do seu `number`.
    A listagem só mostra a vigente (P1); só ela pode virar proposta enviada/OF (P2)."""
    maior = Quotation.objects.filter(number=quotation.number).aggregate(
        models.Max("revision"))["revision__max"]
    return quotation.revision == maior


def has_active_production_order(number: str) -> bool:
    """P7: True sse alguma revisão deste `number` já tem Ordem de Fabricação NÃO cancelada.
    Import tardio: evita ciclo quotations<->production (production já importa quotations
    no nível de módulo; aqui o sentido é o inverso, só em runtime)."""
    from apps.production.models import OrdemFabricacao, STATUS_CANCELADA

    return (OrdemFabricacao.objects.filter(quotation__number=number)
            .exclude(status=STATUS_CANCELADA).exists())


def assert_revisable(orig: Quotation) -> None:
    """P7: recusa revisar uma cotação cujo número já tem Ordem de Fabricação ativa."""
    if has_active_production_order(orig.number):
        raise QuotationHasProductionOrderError(
            f"A cotação {orig.number} já possui Ordem de Fabricação e não pode ser "
            "revisada."
        )


def supersede_previous_proposals(number: str) -> None:
    """P4: ao criar uma revisão nova, marca como 'superseded' as propostas 'draft'/'ready'
    de QUALQUER revisão anterior do mesmo número — o texto/preço delas não corresponde
    mais à revisão vigente. As já 'sent' ficam como estão (já saíram para o cliente; a
    ordem não pede revogar um envio já feito). Import tardio: proposals não é dependência
    de módulo de quotations.services (só desta função, em runtime)."""
    from apps.proposals.models import Proposal

    Proposal.objects.filter(
        quotation__number=number, status__in=["draft", "ready"],
    ).update(status="superseded")


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


# A persistência do permutador completo (create_permutador_quotation) mudou para
# apps.quotations.adapter.persist_complete / .revise_complete na ordem 005 (INTENT v3
# §Limites: só o adapter persiste resultado do motor). Sem wrapper de compat aqui de
# propósito — os dois chamadores (tema_templates/views.py, quotations/views.py) e os
# testes foram atualizados para importar do adapter.
