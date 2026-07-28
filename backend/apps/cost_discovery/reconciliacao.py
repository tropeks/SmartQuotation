"""
Calibração da mão de obra ancorada na FOLHA, não no preço da proposta.

O `back_solve` deste mesmo app calibra `fator_correcao_mo` até o motor reproduzir o
PREÇO de um job de referência. Mas o preço da ENGEMATEX vem de benchmark e, nas palavras
do Wellington, "a parte de mão de obra não vai estar ok" — então o fator encontrado
absorve o erro do preço. Calibrar assim ensina o motor a errar igual, com 0,1% de
precisão.

Aqui a âncora é outra: as horas que a fábrica **efetivamente pagou** no período, contra
as horas que o sistema **estimou** para as OFs entregues nesse período.

Sem bisseção, ao contrário do back_solve por preço: `fator_correcao_mo` é um
multiplicador escalar linear das horas (`pricing_engine/operations_registry.py:47`),
então `horas_reais = horas_estimadas × fator` inverte por divisão direta. Exato, não
convergente.
"""
from dataclasses import dataclass, field
from decimal import Decimal

from django.db.models import Sum

# Abaixo disso a diferença é ruído de arredondamento e de fronteira de período, não
# viés de estimativa: reagir a ela seria perseguir o próprio erro de medição.
TOLERANCIA_PCT = Decimal("5")


@dataclass
class Reconciliacao:
    horas_pagas: Decimal
    horas_estimadas: Decimal
    fator: Decimal | None = None
    desvio_pct: Decimal | None = None
    nivel: str = "sem_dados"
    titulo: str = ""
    texto: str = ""
    ofs: list = field(default_factory=list)

    @property
    def tem_resultado(self):
        return self.fator is not None


def horas_estimadas_de(quotations):
    """Soma HH + HM da EAP persistida das cotações dadas.

    Lê `ItemOperation`, que é onde o motor deixou o tempo previsto — o mesmo número que
    a Ordem de Fabricação copia para o chão de fábrica.
    """
    from apps.quotations.models import ItemOperation

    pks = [q.pk for q in quotations] if not hasattr(quotations, "values_list") else list(
        quotations.values_list("pk", flat=True))
    if not pks:
        return Decimal("0")
    agregado = ItemOperation.objects.filter(
        item__quotation_id__in=pks, aplicavel=True
    ).aggregate(hh=Sum("horas_hh"), hm=Sum("horas_hm"))
    return (agregado["hh"] or Decimal("0")) + (agregado["hm"] or Decimal("0"))


def reconciliar(horas_pagas, horas_estimadas, ofs=None):
    """Compara o pago com o estimado e devolve o fator de correção com diagnóstico."""
    horas_pagas = Decimal(str(horas_pagas or 0))
    horas_estimadas = Decimal(str(horas_estimadas or 0))
    r = Reconciliacao(horas_pagas=horas_pagas, horas_estimadas=horas_estimadas,
                      ofs=list(ofs or []))

    if horas_estimadas <= 0:
        r.nivel = "sem_estimativa"
        r.titulo = "Nenhuma hora estimada no período"
        r.texto = ("Sem OFs com EAP no período não há o que comparar. Confira o "
                   "intervalo e se as cotações têm operações com horas.")
        return r
    if horas_pagas <= 0:
        r.nivel = "sem_folha"
        r.titulo = "Horas pagas não informadas"
        r.texto = "Informe o total de horas pagas à produção no período (folha/ponto)."
        return r

    r.fator = (horas_pagas / horas_estimadas).quantize(Decimal("0.0001"))
    r.desvio_pct = ((r.fator - Decimal("1")) * Decimal("100")).quantize(Decimal("0.1"))

    if r.desvio_pct > TOLERANCIA_PCT:
        r.nivel = "subestima"
        r.titulo = "Os orçamentos subestimam a mão de obra"
        r.texto = ("A fábrica gastou mais horas do que o previsto. A diferença sai da "
                   "margem, porque o preço já foi fechado com o cliente.")
    elif r.desvio_pct < -TOLERANCIA_PCT:
        r.nivel = "superestima"
        r.titulo = "A fábrica gastou menos horas do que o previsto"
        r.texto = ("Ou os orçamentos estão folgados, ou nem todas as horas pagas foram "
                   "para essas OFs. Vale conferir o segundo antes de apertar o primeiro.")
    else:
        r.nivel = "calibrado"
        r.titulo = "Estimativa calibrada"
        r.texto = "As horas pagas batem com as orçadas dentro da tolerância."
    return r


def limites_conhecidos():
    """O que este número NÃO diz. Sai junto do resultado, sempre.

    Um fator de correção sem os limites vira verdade absoluta na cabeça de quem lê — e
    aí a próxima decisão é tomada sobre uma medida que não suporta o peso.
    """
    return [
        "Dá o viés AGREGADO: não diz qual operação estoura. Só apontamento resolve isso.",
        "Exige período fechado: OF iniciada antes ou entregue depois distorce a conta.",
        "Retrabalho, serviço avulso e ociosidade entram nas horas pagas e inflam o fator "
        "— a diferença entre horas pagas e horas produtivas é a capacidade ociosa, que a "
        "estrutura de custo (Nível 0) mede pelo outro lado.",
    ]
