"""
Estrutura Analítica (EAP / WBS) — espinha dorsal do item (alinhamento @WellToMcAt 2026-06-04).

Nível 0: Cotação/Equipamento
  Nível 1: Item/Componente   (codigo_item, descricao)
    Nível 2: Matéria-Prima   (codigo_mp)  → custo_material
    Nível 2: Operações       (codigo_op)  → custo_mo
    Nível 2: Ensaios/END     (codigo_end) → custo_end
  roll-up: custo_item = MP + MO + END ; custo_equip = Σ itens + eng + ferramentas

Cada nó carrega código + descrição → quando a cotação vira pedido (H2), os códigos
JÁ são o BOM + roteiro de fabricação (zero retrabalho).
"""
from __future__ import annotations
from dataclasses import dataclass, field


@dataclass
class MateriaPrima:
    codigo_mp: str
    descricao: str
    material: str
    forma: str            # chapa|tubo|barra|forjado|fundido
    peso_kg: float = 0.0   # BRUTO (base de custo, Opção A — cobra perdas)
    preco_kgf: float = 0.0
    peso_liquido: float = 0.0   # instalado (informativo); refugo = peso_kg - peso_liquido

    @property
    def custo(self) -> float:
        return self.peso_kg * self.preco_kgf

    @property
    def perda_kg(self) -> float:
        return self.peso_kg - self.peso_liquido


@dataclass
class OperacaoExecutada:
    codigo_op: str
    descricao: str
    metodo: str = ""           # radial|cnc|manual
    quantidade: float = 0.0    # driver (nº furos, nº tubos...)
    horas_hh: float = 0.0
    horas_hm: float = 0.0
    rate_hh: float = 0.0
    rate_hm: float = 0.0
    custo_fixo: float = 0.0    # serviços de valor fixo (TT, transporte, LP...)
    aplicavel: bool = True

    @property
    def custo(self) -> float:
        if not self.aplicavel:
            return 0.0
        return self.horas_hh * self.rate_hh + self.horas_hm * self.rate_hm + self.custo_fixo


@dataclass
class Item:
    """Nível 1 — um componente do equipamento (espelho, tubos, chicanas...)."""
    codigo_item: str
    descricao: str
    materias_primas: list[MateriaPrima] = field(default_factory=list)
    operacoes: list[OperacaoExecutada] = field(default_factory=list)
    ensaios: list[OperacaoExecutada] = field(default_factory=list)

    @property
    def custo_material(self) -> float:
        return sum(mp.custo for mp in self.materias_primas)

    @property
    def custo_mo(self) -> float:
        return sum(op.custo for op in self.operacoes)

    @property
    def custo_end(self) -> float:
        return sum(e.custo for e in self.ensaios)

    @property
    def custo_total(self) -> float:
        return self.custo_material + self.custo_mo + self.custo_end


@dataclass
class Cotacao:
    """Nível 0 — equipamento ou parte (feixe avulso = subconjunto dos itens)."""
    codigo: str
    descricao: str
    itens: list[Item] = field(default_factory=list)
    custo_engenharia: float = 0.0
    custo_ferramentas: float = 0.0
    fator_preco: float = 1.0
    impostos_pct: float = 0.0
    # parcela que entra a custo, FORA da base de markup (ensaios/transporte por job,
    # quando o orçamentista desliga o markup sobre eles). Default 0 = baseline.
    custo_passthrough: float = 0.0

    @property
    def custo_itens(self) -> float:
        return sum(it.custo_total for it in self.itens)

    @property
    def custo_total(self) -> float:
        return self.custo_itens + self.custo_engenharia + self.custo_ferramentas

    @property
    def preco_sem_impostos(self) -> float:
        base_marcada = self.custo_total - self.custo_passthrough
        return base_marcada * self.fator_preco + self.custo_passthrough

    @property
    def preco_com_impostos(self) -> float:
        return self.preco_sem_impostos * (1 + self.impostos_pct / 100.0)

    def arvore(self) -> str:
        """Render ASCII da EAP com roll-up de custo."""
        out = [f"[0] {self.codigo} · {self.descricao}  → CUSTO R$ {self.custo_total:,.2f}"]
        for it in self.itens:
            out.append(f"  [1] {it.codigo_item} · {it.descricao}  "
                       f"(MP {it.custo_material:,.0f} + MO {it.custo_mo:,.0f} "
                       f"+ END {it.custo_end:,.0f} = {it.custo_total:,.0f})")
            for mp in it.materias_primas:
                out.append(f"      [2·MP] {mp.codigo_mp} {mp.descricao} "
                           f"{mp.peso_kg:,.1f}kg × R${mp.preco_kgf}/kg = R$ {mp.custo:,.0f}")
            for op in it.operacoes:
                if op.custo:
                    out.append(f"      [2·OP] {op.descricao} → R$ {op.custo:,.0f}")
        out.append(f"  + Engenharia R$ {self.custo_engenharia:,.0f} "
                   f"+ Ferramentas R$ {self.custo_ferramentas:,.0f}")
        out.append(f"  PREÇO s/imp R$ {self.preco_sem_impostos:,.2f} · "
                   f"c/imp R$ {self.preco_com_impostos:,.2f}")
        return "\n".join(out)
