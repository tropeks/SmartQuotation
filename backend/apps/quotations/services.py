"""Serviços de cotação: numeração sequencial por tenant e criação."""
from datetime import date
from django.db import transaction
from apps.quotations.models import Quotation
from apps.quotations.adapter import default_inputs, recompute


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
