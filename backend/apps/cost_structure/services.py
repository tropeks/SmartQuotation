"""
Diagnóstico do custo/hora e importação das respostas do formulário externo.

O formulário público (form.qtec.me) coleta os números com o cliente; aqui eles viram
vigência dentro do tenant. A conta é a mesma dos dois lados — mas quem manda é este,
porque o outro roda no navegador do cliente.
"""
from datetime import date
from decimal import Decimal, InvalidOperation

from django.db import transaction

from apps.cost_structure.models import CostStructure

# Abaixo disso a hora vendida não paga nem o custo; acima, ainda não sobra para
# imprevisto, retrabalho e lucro. Não é norma — é o limiar que separa "no limite" de
# "tem margem", e existe para o diagnóstico dizer algo acionável em vez de um número solto.
FOLGA_MINIMA_PCT = Decimal("15")


def parse_num(value):
    """Lê número digitado em português. Vazio/lixo -> 0.

    '1.234,56' -> 1234.56 · '8.000' -> 8000 (milhar) · '1234.56' -> 1234.56 (decimal).

    A regra do ponto com exatamente 3 dígitos é a que importa: sem ela, quem digita o
    salário como '8.000' teria o custo lido como R$ 8,00 — erro de mil vezes, silencioso.
    Espelha `parse_num` do formulário externo; se mudar aqui, mudar lá.
    """
    if value is None:
        return Decimal("0")
    s = "".join(ch for ch in str(value).strip() if ch.isdigit() or ch in ",.-")
    if not s:
        return Decimal("0")
    if "," in s:
        s = s.replace(".", "").replace(",", ".")
    elif s.count(".") > 1:
        s = s.replace(".", "")
    elif "." in s and len(s.partition(".")[2]) == 3:
        s = s.replace(".", "")
    try:
        return Decimal(s)
    except (InvalidOperation, ValueError):
        return Decimal("0")


def diagnosticar(estrutura):
    """Veredito sobre o rate praticado. Chaves: nivel, titulo, texto, delta, pct."""
    custo_hora = estrutura.custo_hora
    if custo_hora is None or custo_hora <= 0:
        return {"nivel": "sem_dados", "titulo": "Capacidade não informada",
                "texto": "Sem as horas vendáveis não há custo/hora a comparar."}

    rate = estrutura.rate_praticado
    if not rate or rate <= 0:
        return {"nivel": "sem_rate", "titulo": "Falta o rate praticado",
                "texto": f"Manter a fábrica aberta custa R$ {custo_hora} por hora vendável."}

    delta = rate - custo_hora
    pct = (delta / custo_hora * Decimal("100")).quantize(Decimal("0.1"))
    if delta < 0:
        return {"nivel": "prejuizo", "titulo": "Cada hora vendida perde dinheiro",
                "texto": "Vender mais volume aumenta o prejuízo.",
                "delta": delta, "pct": pct}
    if pct < FOLGA_MINIMA_PCT:
        return {"nivel": "limite", "titulo": "No limite",
                "texto": "Cobre o custo, mas não sobra para imprevisto, retrabalho nem "
                         "lucro. Um atraso na obra já vira prejuízo.",
                "delta": delta, "pct": pct}
    return {"nivel": "saudavel", "titulo": "Margem de contribuição positiva",
            "texto": "Sobra por hora vendida, antes de impostos e lucro.",
            "delta": delta, "pct": pct}


def _somar_linhas(linhas, chave):
    return sum((parse_num(l.get(chave)) for l in (linhas or [])), Decimal("0"))


def _somar_pessoas(linhas):
    return sum((parse_num(l.get("qtd")) * parse_num(l.get("custo"))
                for l in (linhas or [])), Decimal("0"))


def _contar_cabecas(linhas):
    return sum((parse_num(l.get("qtd")) for l in (linhas or [])), Decimal("0"))


def da_resposta_do_formulario(dados, valid_from=None):
    """Traduz o JSON do form.qtec.me numa CostStructure (ainda NÃO salva).

    O formulário externo manda listas paralelas por bloco, porque o usuário acrescenta
    linhas sob demanda — não há índice fixo em que confiar.
    """
    linhas = dados.get("linhas") or {}
    escalares = dados.get("escalares") or {}

    rateio = parse_num(escalares.get("rateio_pct"))
    if rateio <= 0:
        rateio = Decimal("100")

    diretos = _somar_pessoas(linhas.get("diretos"))
    cabecas = _contar_cabecas(linhas.get("diretos"))
    pessoas = parse_num(escalares.get("pessoas")) or cabecas

    rate = parse_num(escalares.get("rate_atual"))

    return CostStructure(
        origem="formulario",
        empresa=(dados.get("empresa") or "")[:255],
        respondente=(dados.get("respondente") or "")[:255],
        mes_referencia=(dados.get("mes_referencia") or "")[:7],
        custo_pessoal_direto=diretos,
        custo_pessoal_indireto=_somar_pessoas(linhas.get("indiretos")),
        custo_galpao=_somar_linhas(linhas.get("galpao"), "valor"),
        custo_maquinas=_somar_linhas(linhas.get("maquinas"), "valor"),
        custo_estrutura=(_somar_linhas(linhas.get("estrutura"), "valor")
                         * rateio / Decimal("100")),
        pessoas_produtivas=pessoas,
        jornada_semanal_h=parse_num(escalares.get("jornada_semanal")) or Decimal("44"),
        semanas_mes=parse_num(escalares.get("semanas_mes")) or Decimal("4.33"),
        fator_pratico_pct=parse_num(escalares.get("fator_pratico_pct")) or Decimal("82"),
        horas_extras_mes=parse_num(escalares.get("horas_extras")),
        rate_praticado=rate if rate > 0 else None,
        valid_from=valid_from or date.today(),
        payload=dados,
        notes=(escalares.get("observacoes") or ""),
    )


@transaction.atomic
def abrir_vigencia(estrutura, created_by=None):
    """Grava a estrutura como vigência corrente, fechando a anterior na véspera.

    Nunca sobrescreve: a cotação feita sob a régua antiga tem de continuar
    reproduzindo aquela régua.
    """
    anterior = CostStructure.objects.vigente(estrutura.valid_from)
    if anterior is not None and anterior.pk != estrutura.pk:
        if anterior.valid_from == estrutura.valid_from:
            raise ValueError(
                f"Já existe estrutura de custo vigente a partir de "
                f"{estrutura.valid_from:%d/%m/%Y}. Use outra data de início."
            )
        anterior.encerrar_em(estrutura.valid_from)

    estrutura.created_by = created_by
    estrutura.full_clean()
    estrutura.save()
    return estrutura
