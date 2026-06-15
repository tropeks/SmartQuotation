"""Serviços de cotação: numeração sequencial por tenant e criação."""
from datetime import date
from decimal import Decimal
from django.db import transaction
from django.utils import timezone
from apps.quotations.models import Quotation
from apps.quotations.adapter import default_inputs, recompute


def _d(x) -> Decimal:
    """float/str → Decimal com 2 casas (campos monetários da Quotation)."""
    return Decimal(str(round(float(x or 0), 2)))


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
                                created_by=None, title=None) -> Quotation:
    """Persiste uma cotação de PERMUTADOR COMPLETO a partir do resultado do motor
    (tema_templates.estimate_complete / pricing_engine.quote_completo). Fecha o elo
    motor → Quotation, de onde a proposta é gerada. Cria itens a partir de por_secao."""
    from apps.quotations.models import QuotationItem
    desig = (designacao or "").upper()
    custo_mo = float(resultado.get("custo_mao_obra", 0)) + float(resultado.get("custo_servicos", 0))
    q = Quotation.objects.create(
        number=next_number(), customer=customer, scope="complete",
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
    return q
