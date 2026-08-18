#!/usr/bin/env python3
"""Varredura de sensibilidade do motor de custeio (pricing_engine) — READ-ONLY.

Responde a pergunta de negócio: quais campos do formulário/entradas do motor merecem a
paciência do Wellington, e quais são ruído? Ver docs/HANDOFF_MIGRACAO.md §4 e
docs/SENSIBILIDADE_MOTOR.md (relatório gerado a partir deste harness).

Este script NUNCA importa Django/backend — só `pricing_engine` (lib pura). Ele também NUNCA
edita o motor: perturba entradas, chama `quote_completo`/`quote_feixe`, lê a saída.

── O que o harness mede, por entrada, por caso (BEU, BEM, OF3683, feixe) ──

  E_bruta  = elasticidade do CUSTO_TOTAL (ou do PREÇO, p/ knobs downstream como markup/
             imposto) a uma perturbação ±δ da entrada, SEM recalibrar nada. "Se eu errar
             este campo, quanto o número final anda?"

  E_calib  = elasticidade que SOBRA depois do back-solve. ⚠️ O back-solve É MECANISMO REAL DO
             PRODUTO só para o FEIXE — `apps.cost_discovery.services.back_solve()` ajusta
             `fator_correcao_mo` contra um preço conhecido, mas importa e opera SÓ sobre
             `FeixeInputs`/`quote_feixe`; não existe (grep confirmado, 2026-08-18) equivalente
             para `quote_completo`/permutador em `apps.cost_discovery`, `apps.quotations.adapter`
             nem `apps.tema_templates.services` — BEU/BEM/OF3683 hoje NÃO têm nenhum mecanismo
             de produto que calibre fc contra referencial. Para esses 3 casos, o que este
             harness faz é SIMULAR um back-solve HIPOTÉTICO — a mesma equação que o produto
             resolveria SE o back-solve fosse estendido ao permutador (extensão trivial:
             `custo_total` já é afim em fc para os dois motores, provado abaixo). Trate
             `E_calib` do permutador como "o que aconteceria se isso existisse", não como
             comportamento hoje em produção — é uma recomendação de produto com o número do
             impacto ao lado, não uma medição do que já roda. Mecânica (idêntica nos dois
             casos, real ou hipotética):
               1. perturba a entrada X por δ;
               2. resolve fc* tal que custo_total(X_perturbado, fc*) == referencial
                  (a mesma equação que o back_solve() do feixe resolve de verdade hoje, e que
                  o permutador resolveria SE ganhasse o mesmo mecanismo);
               3. mede o que SOBRA de erro no CUSTO_MÃO_DE_OBRA (não no total — o total
                  bate por construção, é isso que "reabsorver" significa) relativo ao
                  custo_mão_de_obra "verdadeiro" (X=1,0, fc=1,0).
             Por que custo_mão_de_obra e não o total: o total SEMPRE reconcilia (é a
             própria definição do back-solve — 1 grau de liberdade, 1 equação). O que o
             back-solve NÃO enxerga é a composição interna: ele empurra o erro de X para
             dentro de fc, e fc multiplica cega e uniformemente TODA a mão-de-obra. Se X
             não afeta a MO do jeito que fc afeta (ex.: X é preço de material, ou X só
             afeta um subconjunto de operações, não todas), o fc recalibrado fica ERRADO
             para qualquer coisa que dependa da mão-de-obra "real" — em especial o
             diagnóstico de capacidade (`cost_structure.diagnosticar`: cada hora vendida
             ganha ou perde dinheiro?), que precisa do custo/hora real, não do custo/hora
             que só "parece certo" porque o total bateu.
             Prova de que o back-solve é bem definido (2 pontos bastam, não é chute):
             cada operação de mão-de-obra do motor é `custo = base·eff·liga·fc + ajuste`
             (permutador_quote._escala_op) ou `horas_ceil · fc · rate` (feixe_quote.FC) —
             em AMBOS os casos fc entra depois de qualquer arredondamento/degrau, então
             custo_total(fc) É AFIM em fc para X fixo. Resolvo com 2 avaliações e
             interpolação linear EXATA — não é otimização numérica, é álgebra.

             fator_correcao_mo, fator_preco e impostos_pct NÃO seguem esse fluxo de
             "recalibração" (faria pouco sentido recalibrar fc perturbando o próprio fc,
             ou recalibrar algo que nem entra em custo_total — ver abaixo); para eles o
             harness reporta só E_bruta e documenta explicitamente por quê.

  Assimetria: +δ e −δ são reportados separados sempre. Onde o motor tem clamps (ex.:
  `max(perda_eff, 1.0)`, `faixa()` em degraus, `math.ceil()`) a resposta NÃO é simétrica.

  Fora do ponto calibrado: repete params em bloco (1,5× e 0,7×) e mede lá a elasticidade de
  knobs que são estruturalmente ~0 NO ponto de referência (setup_frac, sobretudo — a
  fração de setup se cancela algebricamente quando toda razão de driver é 1,0; ver
  permutador_quote._escala_op). É o "onde o produto vive de verdade": cotação nova não é o
  referencial.

Uso:
  python3 scripts/sensibilidade_motor.py [--json out.json] [--md out.md] [--delta 0.10]
"""
from __future__ import annotations

import argparse
import json
import math
import os
import sys
from dataclasses import dataclass, field, replace
from typing import Any, Callable

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from pricing_engine.permutador_quote import (  # noqa: E402
    quote_completo,
    _FAMILIA_FORMA,   # mapeamento família→forma p/ montar preço/kg — leitura, não edição
    _SETUP_FRAC,      # chaves dos parâmetros físicos com fração de setup — leitura
)
from pricing_engine.rates import TenantCostChain  # noqa: E402
from pricing_engine.permutador_layout import check_layout  # noqa: E402
from pricing_engine.feixe_quote import quote_feixe  # noqa: E402
from pricing_engine.feixe_inputs import caso_136_tubos, FeixeInputs  # noqa: E402
from pricing_engine.components import componentes_from_inputs, peso_componente  # noqa: E402

SEEDS = os.path.join(ROOT, "pricing_engine", "seeds")
DELTA_PRIMARIO = 0.10    # δ primário da varredura — sobrescrito por --delta na CLI
DELTA_NAO_LINEAR = 0.25  # rodada extra p/ checar não-linearidade (clamps/degraus), FIXA


# ═══════════════════════════════════════════════════════════════════════════════════
# Utilidades numéricas
# ═══════════════════════════════════════════════════════════════════════════════════

def _pct(a: float, b: float) -> float | None:
    """Δ% de a em relação a b. None se b == 0 (não dividir por zero, não mentir)."""
    if b == 0:
        return None
    return (a - b) / b * 100.0


def elasticidade(base: float, pert: float, delta: float) -> float | None:
    """E = (Δ%saída) / (Δ%entrada). None se base==0 ou delta==0 (indefinido, não 0)."""
    if base == 0 or delta == 0:
        return None
    return ((pert - base) / base) / delta


def solve_fc_affine(eval_fn: Callable[[float], float], target: float,
                    fc_lo: float = 1.0, fc_hi: float = 2.0) -> float | None:
    """Resolve fc* tal que eval_fn(fc*) == target, assumindo eval_fn AFIM em fc (provado no
    docstring do módulo: fc multiplica cada operação de MO depois de qualquer ceil/degrau).
    2 pontos bastam — é interpolação linear exata, não busca numérica. None se a inclinação
    for ~0 (não há massa de MO para calibrar contra — back-solve não converge)."""
    y_lo = eval_fn(fc_lo)
    y_hi = eval_fn(fc_hi)
    slope = (y_hi - y_lo) / (fc_hi - fc_lo)
    if abs(slope) < 1e-6:
        return None
    return fc_lo + (target - y_lo) / slope


# ═══════════════════════════════════════════════════════════════════════════════════
# Ponte "linguagem do formulário" — porta PURA (sem Django) da lógica de
# backend/apps/tema_templates/{services.py,forms.py}. Só os campos que o data sheet do
# permutador completo realmente expõe ao orçamentista (PermutadorDataSheetForm). Servem
# só p/ leitura/simulação — não substituem o app, e não importam Django.
# ═══════════════════════════════════════════════════════════════════════════════════

LABEL_TUBOS = "TUBOS DE TROCA TÉRMICA"
LABEL_VIROLA = "VIROLA"
RT_FATOR = {"Total": 1.0, "Parcial": 0.33, "Isento": 0.1}


def _load_seed(designacao: str, nome: str) -> list[dict]:
    path = os.path.join(SEEDS, f"{designacao.lower()}_{nome}.json")
    with open(path, encoding="utf-8") as f:
        return json.load(f)[nome]


def reference_inputs(designacao: str) -> dict:
    """Valores de referência (do seed) p/ pré-preencher o data sheet — espelha
    tema_templates.services.reference_inputs (porta pura, sem Django)."""
    mats = _load_seed(designacao, "materiais")
    by_label = {m["label"]: m.get("dims", {}) for m in mats if m.get("label")}
    tub = by_label.get(LABEL_TUBOS, {})
    vir = by_label.get(LABEL_VIROLA, {})
    chic = next((m.get("dims", {}) for m in mats
                if "CHICANA" in (m.get("label") or "").upper()), {})
    larguras = [m.get("dims", {}).get("LARGURA") for m in mats
               if "VIROLA" in (m.get("label") or "")]
    larg = max([x for x in larguras if x], default=None)
    d_casco = round(larg / math.pi, 1) if larg else None
    return {
        "n_tubos": tub.get("QUANTIDADE"), "comprimento_tubo_mm": tub.get("COMPR."),
        "od_tubo_mm": tub.get("OD"), "esp_tubo_mm": tub.get("ESP."),
        "comprimento_casco_mm": vir.get("COMPR."), "n_chicanas": chic.get("QUANTIDADE") or 1,
        "diametro_casco_mm": d_casco, "esp_casco_mm": vir.get("ESP."),
        "n_passes_tubos": 2, "fator_correcao_mo": 1.0,
    }


def tem_data_sheet(designacao: str) -> bool:
    """True se a designação tem os labels canônicos (TUBOS/VIROLA) que o data sheet do
    permutador completo sabe editar. OF3683 (job avulso, seed com nomenclatura do
    manuscrito) NÃO tem — só é custeável por replay direto do seed. Achado do harness."""
    ref = reference_inputs(designacao)
    return bool(ref.get("n_tubos") and ref.get("comprimento_casco_mm"))


def physical_params(designacao: str, cleaned: dict) -> dict:
    """Razões físicas proj/ref — porta pura de tema_templates.services._physical_params."""
    ref = reference_inputs(designacao)
    if not ref.get("n_tubos"):
        return {}

    def r(campo):
        rv, v = ref.get(campo), cleaned.get(campo)
        return (float(v) / float(rv)) if (v and rv) else 1.0

    tubos = r("n_tubos")
    chicanas = r("n_chicanas")
    np_ref = float(ref.get("n_passes_tubos") or 2)
    np_proj = float(cleaned.get("n_passes_tubos") or np_ref)
    rasgos = max(np_proj - 1.0, 0.0) / max(np_ref - 1.0, 1.0)
    comprimento = r("comprimento_tubo_mm")
    diametro = r("diametro_casco_mm")
    esp_casco_ratio = r("esp_casco_mm")
    esp2 = esp_casco_ratio ** 2
    return {
        "tubos": tubos, "chicanas": chicanas, "comprimento": comprimento, "diametro": diametro,
        "rasgos": rasgos, "furacao_chicana": tubos * chicanas,
        "massa": diametro * diametro * comprimento,
        "solda_long": comprimento * esp2, "solda_circ": diametro * esp2,
        "solda": (0.5 * comprimento + 0.5 * diametro) * esp_casco_ratio,
        "rt": (0.5 * comprimento + 0.5 * diametro) * esp_casco_ratio
              * RT_FATOR.get(cleaned.get("rt_escopo", "Total"), 1.0),
        "area": diametro * comprimento, "volume": diametro * diametro * comprimento,
    }


def to_dims_override(designacao: str, cleaned: dict) -> dict:
    """Porta pura de PermutadorDataSheetForm.to_dims_override (sem fator_correcao_mo,
    que este harness trata como entrada própria)."""
    ref = reference_inputs(designacao)
    ref_d = ref.get("diametro_casco_mm") or cleaned["diametro_casco_mm"]
    largura_ratio = float(cleaned["diametro_casco_mm"]) / float(ref_d)
    return {
        LABEL_TUBOS: {
            "QUANTIDADE": cleaned["n_tubos"], "COMPR.": cleaned["comprimento_tubo_mm"],
            "OD": cleaned["od_tubo_mm"], "ESP.": cleaned["esp_tubo_mm"],
        },
        LABEL_VIROLA: {
            "COMPR.": cleaned["comprimento_casco_mm"], "ESP.": cleaned["esp_casco_mm"],
            "_LARGURA_RATIO": largura_ratio,
        },
    }


def rear_letter(designacao: str) -> str:
    """3ª letra TEMA = cabeçote traseiro (BEU→U, BEM→M) — mesma convenção do adapter."""
    return (designacao or "")[2:3]


# ═══════════════════════════════════════════════════════════════════════════════════
# Cadeia de custos auxiliar: escala TODOS os preços/kg de uma designação (ou do feixe)
# por um multiplicador uniforme, reproduzindo exatamente os defaults do seed em mult=1,0.
# ═══════════════════════════════════════════════════════════════════════════════════

def colisoes_preco_kgf(designacao: str) -> list[dict]:
    """ACHADO (não é bug do harness): `TenantCostChain.material_price` é chaveada por
    (material, forma) — cada FAMÍLIA mapeia p/ uma forma via `_FAMILIA_FORMA` (ex.: 'disco',
    'chapa_retangular' e 'anel' todos caem em 'chapa'/'forjado'). O SEED, porém, tem
    price_kgf DISTINTO por ITEM (mesmo material+forma, preços bem diferentes — ex. hardware
    pequeno com R$/kgf inflado vs. chapa estrutural). Se um tenant seta UM preço para
    (material, forma), ele sobrescreve TODOS os itens que caem nessa chave — inclusive os
    que nada têm a ver com o item que o Wellington tinha em mente. Achado do harness,
    reportado — não é corrigido aqui (pricing_engine é read-only)."""
    por_chave: dict[tuple[str, str], list[dict]] = {}
    for m in _load_seed(designacao, "materiais"):
        if m.get("familia") == "catalogo" or not m.get("peso_bruto") or not m.get("price_kgf"):
            continue
        forma = _FAMILIA_FORMA.get(m["familia"], "chapa")
        key = ((m.get("material") or "").strip().upper(), forma)
        por_chave.setdefault(key, []).append(m)
    colisoes = []
    for (material, forma), itens in por_chave.items():
        precos = {round(m["price_kgf"], 3) for m in itens}
        if len(precos) > 1:
            colisoes.append({
                "material": material, "forma": forma,
                "itens": [{"label": m["label"], "price_kgf": m["price_kgf"],
                          "peso_bruto_kg": m["peso_bruto"]} for m in itens],
                "razao_max_min": round(max(precos) / min(precos), 2),
            })
    return colisoes


def material_chain_permutador(designacao: str, mult: float = 1.0, **kw) -> TenantCostChain:
    """Escala o preço/kg de TODOS os materiais não-catálogo por `mult`. Onde o mesmo
    (material, forma) tem price_kgf DISTINTO em itens diferentes do seed (ver
    `colisoes_preco_kgf` — limitação real da chave (material,forma) do motor, não deste
    harness), usa o preço do item de MAIOR peso_bruto — é o que um tenant racional
    calibraria contra (o item que domina o R$ daquela chave), e é o único jeito de manter
    a reprodução exata do baseline em mult=1,0 para a MAIOR PARTE da massa de material."""
    chain = TenantCostChain(**kw)
    dominante: dict[tuple[str, str], tuple[float, float]] = {}   # key -> (peso, price_kgf)
    for m in _load_seed(designacao, "materiais"):
        if m.get("familia") == "catalogo" or not m.get("peso_bruto") or not m.get("price_kgf"):
            continue
        forma = _FAMILIA_FORMA.get(m["familia"], "chapa")
        key = ((m.get("material") or "").strip().upper(), forma)
        peso = m["peso_bruto"]
        if key not in dominante or peso > dominante[key][0]:
            dominante[key] = (peso, m["price_kgf"])
    for key, (_, price) in dominante.items():
        chain.material_price[key] = price * mult
    return chain


def material_chain_feixe(inp: FeixeInputs, mult: float = 1.0, **kw) -> TenantCostChain:
    """Mesma ressalva de `material_chain_permutador`: `feixe_quote._preco_material` também
    resolve por (material, forma) — e o feixe TEM colisão real (ver `colisoes_preco_kgf_feixe`):
    SA-36/barra_chata cobre barras de selagem (R$4,5/kg), chapa de impacto (R$6,5/kg) E a
    alça de içamento (R$10/kg) com o MESMO (material,forma). Usa o item de maior peso p/
    não inflar o baseline em mult=1,0."""
    chain = TenantCostChain(**kw)
    dominante: dict[tuple[str, str], tuple[float, float]] = {}
    for c in componentes_from_inputs(inp):
        peso, _ = peso_componente(c)
        key = (c.material.strip().upper(), c.forma.strip().lower())
        if key not in dominante or peso > dominante[key][0]:
            dominante[key] = (peso, c.rkg)
    for key, (_, rkg) in dominante.items():
        chain.material_price[key] = rkg * mult
    return chain


def colisoes_preco_kgf_feixe(inp: FeixeInputs) -> list[dict]:
    """Mesmo achado de `colisoes_preco_kgf`, para os componentes do feixe."""
    por_chave: dict[tuple[str, str], list[dict]] = {}
    for c in componentes_from_inputs(inp):
        peso, _ = peso_componente(c)
        key = (c.material.strip().upper(), c.forma.strip().lower())
        por_chave.setdefault(key, []).append({"codigo": c.codigo, "descricao": c.descricao,
                                              "rkg": c.rkg, "peso_kg": peso})
    colisoes = []
    for (material, forma), itens in por_chave.items():
        precos = {round(i["rkg"], 3) for i in itens}
        if len(precos) > 1:
            colisoes.append({"material": material, "forma": forma, "itens": itens,
                            "razao_max_min": round(max(precos) / min(precos), 2)})
    return colisoes


# ═══════════════════════════════════════════════════════════════════════════════════
# Resultado de uma entrada varrida
# ═══════════════════════════════════════════════════════════════════════════════════

@dataclass
class Ponto:
    """Resultado de UMA perturbação (uma direção, um δ)."""
    delta: float
    custo_total_bruto: float | None = None
    e_bruta: float | None = None
    fc_calibrado: float | None = None
    custo_mo_calib: float | None = None
    e_calib: float | None = None
    avisos: list[str] = field(default_factory=list)


@dataclass
class Entrada:
    nome: str
    grupo: str            # driver_fisico | dims_form | metalurgia | knob_tenant | markup_imposto
    unidade: str
    alvo: str              # métrica primária afetada: 'custo_total' ou 'preco_com_impostos'
    reabsorvivel: str      # explicação curta de por que É/NÃO É absorvível pelo back-solve
    pontos: dict[str, Ponto] = field(default_factory=dict)   # chave: '+10%', '-10%', '+25%', '-25%'
    nota: str = ""

    def to_json(self):
        return {
            "nome": self.nome, "grupo": self.grupo, "unidade": self.unidade, "alvo": self.alvo,
            "reabsorvivel": self.reabsorvivel, "nota": self.nota,
            "pontos": {k: vars(v) for k, v in self.pontos.items()},
        }


# ═══════════════════════════════════════════════════════════════════════════════════
# Caso PERMUTADOR (BEU, BEM, OF3683) — quote_completo
# ═══════════════════════════════════════════════════════════════════════════════════

@dataclass
class CasoPermutador:
    nome: str
    designacao: str
    referencial: float                    # custo_total "verdade" (job fechado/planilha)
    fator_preco: float
    impostos_pct: float
    tem_form: bool
    baseline: dict = field(default_factory=dict)             # preenchido em __post_init__
    fc_referencia: float = 1.0                               # fc* calibrado SEM perturbação
    mo_referencia: float = 0.0                                # custo_mao_obra NESSE fc*

    def __post_init__(self):
        # Baseline com uma TenantCostChain NEUTRA (fator_correcao_mo=1,0, tudo mais vazio),
        # não cost_chain=None. ACHADO (documentado em docs/SENSIBILIDADE_MOTOR.md): as duas
        # rotas NÃO são idênticas — com cost_chain presente, operações que têm horas+rate no
        # seed usam `horas × cost_chain.hh(...)`; sem cost_chain, usam `preco_referencial −
        # ajuste` direto. Para MANDRILAR (BEU/BEM) esses dois caminhos DIVERGEM: o seed tem
        # "rate": 80 mas "preco_referencial": horas×120 — inconsistência de transcrição (rates.py
        # usa 120 p/ MANDRILAR). custo_total(cost_chain=None) ≠ custo_total(cost_chain=<vazia>)
        # por R$120 (BEU) / R$240 (BEM). O produto REAL sempre passa uma TenantCostChain (nunca
        # None — ver tema_templates.services.tenant_cost_chain()), então uso a mesma rota aqui:
        # é o número que o Wellington realmente vê, MANDRILAR errado incluído.
        self.baseline = self.quote(cost_chain=TenantCostChain(fator_correcao_mo=1.0))
        # Ponto de calibração de REFERÊNCIA: fc* que reconcilia o baseline (SEM nenhuma
        # perturbação) com self.referencial. Não é 1,0 exato — há um resíduo residual do
        # próprio gate (~0,002%–0,15%, ver validate_permutador_completo) mais o gap do
        # MANDRILAR acima. TODA medição de E_calib compara contra ESTE ponto (não contra
        # fc=1,0 "cru") — senão o resíduo pré-existente vaza pro cálculo como um artefato de
        # sinal (Δ constante dividido por +δ/−δ troca de sinal sem ser um efeito real da
        # entrada perturbada). Ver docstring do módulo + docs/SENSIBILIDADE_MOTOR.md.
        self.fc_referencia, self.mo_referencia = self.calibrar_e_medir(
            lambda fc: TenantCostChain(fator_correcao_mo=fc), {})

    def quote(self, cost_chain=None, dims_override=None, params=None,
             liga_por_lado=None, dens_por_lado=None, preco_por_lado=None,
             fator_preco=None, impostos_pct=None) -> dict:
        return quote_completo(
            self.designacao, cost_chain=cost_chain, dims_override=dims_override,
            params=params, liga_por_lado=liga_por_lado, dens_por_lado=dens_por_lado,
            preco_por_lado=preco_por_lado,
            fator_preco=self.fator_preco if fator_preco is None else fator_preco,
            impostos_pct=self.impostos_pct if impostos_pct is None else impostos_pct,
        )

    def custo_total(self, **kw) -> float:
        return self.quote(**kw)["custo_total"]

    def custo_mo(self, **kw) -> float:
        return self.quote(**kw)["custo_mao_obra"]

    def preco(self, **kw) -> float:
        return self.quote(**kw)["preco_com_impostos"]

    def calibrar_e_medir(self, make_chain: Callable[[float], TenantCostChain],
                         quote_kw: dict) -> tuple[float | None, float | None]:
        """Resolve fc* que faz custo_total bater com self.referencial — a mesma equação do
        `back_solve()` real do feixe (`apps.cost_discovery.services`), aqui SIMULADA para o
        permutador (que não tem esse mecanismo em produção — ver docstring do módulo).
        `make_chain(fc)` monta a cadeia de custos com QUALQUER perturbação já embutida, MAIS o
        fc sob teste; devolve (fc*, custo_mao_obra resultante). None se não convergir (sem
        massa de MO p/ calibrar)."""
        fc_star = solve_fc_affine(
            lambda fc: self.custo_total(cost_chain=make_chain(fc), **quote_kw), self.referencial)
        if fc_star is None:
            return None, None
        mo = self.custo_mo(cost_chain=make_chain(fc_star), **quote_kw)
        return fc_star, mo


# perturbar(delta) -> (make_chain, quote_kw, avisos):
#   make_chain(fc) -> TenantCostChain PRONTA (com a perturbação já embutida + o fc sob teste)
#   quote_kw        -> kwargs de CasoPermutador.quote() (dims_override/params/liga.../fator_preco...)
#   avisos          -> avisos de viabilidade geométrica (permutador_layout.check_layout), [] se ok
Perturbador = Callable[[float], tuple[Callable[[float], TenantCostChain], dict, list[str]]]


def _sweep_permutador_entrada(
    caso: CasoPermutador, entrada: Entrada, perturbar: Perturbador,
    deltas=(DELTA_PRIMARIO, -DELTA_PRIMARIO, DELTA_NAO_LINEAR, -DELTA_NAO_LINEAR),
) -> None:
    """Aplica `perturbar(delta)` p/ cada δ; mede E_bruta (fc=1,0 fixo — sem recalibrar) e,
    quando o grupo da entrada afeta custo_total, o back-solve (E_calib), sempre relativo ao
    PONTO DE CALIBRAÇÃO DE REFERÊNCIA (caso.mo_referencia — fc* já calibrado sem perturbação),
    não ao custo_mao_obra cru em fc=1,0 (ver comentário em CasoPermutador.__post_init__)."""
    mo_base = caso.mo_referencia
    calc_calib = entrada.grupo != "markup_imposto"   # markup/imposto não tocam custo_total
    for delta in deltas:
        make_chain, q_kw, avisos = perturbar(delta)
        alvo_base = caso.baseline[entrada.alvo]
        alvo_pert = caso.quote(cost_chain=make_chain(1.0), **q_kw)[entrada.alvo]
        ponto = Ponto(
            delta=delta,
            custo_total_bruto=alvo_pert,
            e_bruta=elasticidade(alvo_base, alvo_pert, delta),
            avisos=avisos,
        )
        if calc_calib:
            fc_star, mo_calib = caso.calibrar_e_medir(make_chain, q_kw)
            ponto.fc_calibrado = fc_star
            ponto.custo_mo_calib = mo_calib
            if mo_calib is not None:
                ponto.e_calib = elasticidade(mo_base, mo_calib, delta)
        entrada.pontos[f"{delta:+.0%}"] = ponto


# ═══════════════════════════════════════════════════════════════════════════════════
# Montagem das entradas varridas — PERMUTADOR (BEU, BEM, OF3683)
# ═══════════════════════════════════════════════════════════════════════════════════

def _espelho_label(designacao: str) -> str | None:
    for m in _load_seed(designacao, "materiais"):
        if m.get("familia") == "espelho":
            return m["label"]
    return None


def _sem_chain(fc: float) -> TenantCostChain:
    return TenantCostChain(fator_correcao_mo=fc)


def montar_entradas_permutador(caso: CasoPermutador) -> list[Entrada]:
    entradas: list[Entrada] = []

    def add(nome, grupo, unidade, alvo, reabsorvivel, perturbar, nota="", deltas=None):
        e = Entrada(nome=nome, grupo=grupo, unidade=unidade, alvo=alvo,
                    reabsorvivel=reabsorvivel, nota=nota)
        _sweep_permutador_entrada(caso, e, perturbar,
                                  deltas=deltas or (DELTA_PRIMARIO, -DELTA_PRIMARIO, DELTA_NAO_LINEAR, -DELTA_NAO_LINEAR))
        entradas.append(e)

    # ── 1. fator_correcao_mo — o próprio knob de calibração ──
    add("fator_correcao_mo", "knob_calibracao", "multiplicador", "custo_total",
       reabsorvivel="N/A — é o PRÓPRIO knob de calibração; recalibrar fc perturbando fc é "
                     "tautológico (o back-solve sempre converge de volta ao ponto de partida). "
                     "Fica como demonstração do mecanismo, não como achado.",
       perturbar=lambda d: (lambda fc: TenantCostChain(fator_correcao_mo=1 + d), {}, []))

    # ── 2/3. markup e imposto — downstream de custo_total, não tocam o back-solve ──
    add("fator_preco (markup)", "markup_imposto", "multiplicador", "preco_com_impostos",
       reabsorvivel="NÃO — fator_preco multiplica custo_total DEPOIS de calculado; back-solve "
                     "de fc não o vê e não o corrige. Erro aqui é 1:1 no preço, sempre.",
       perturbar=lambda d: (_sem_chain, {"fator_preco": caso.fator_preco * (1 + d)}, []))
    # ACHADO: em quote_completo, `preco_com_impostos = custo_total × fator_preco` é calculado
    # PRIMEIRO (é o preço de TABELA, política comercial — não depende de impostos_pct); só
    # `preco_sem_impostos` é DERIVADO dele por gross-up ("por dentro", ver gross_up_icms —
    # coerente com ICMS por dentro no Brasil: a empresa fixa o preço de venda e calcula quanto
    # sobra líquido de imposto). Logo impostos_pct tem elasticidade EXATAMENTE ZERO sobre
    # preco_com_impostos (o nº que o cliente vê) — só move preco_sem_impostos (receita líquida
    # que a empresa embolsa). Meço aqui o que ele REALMENTE move.
    add("impostos_pct", "markup_imposto", "multiplicador", "preco_sem_impostos",
       reabsorvivel="NÃO — mesmo motivo do fator_preco: é gross-up aplicado sobre o preço já "
                     "calculado (gross_up_icms), fora do alcance de fc. E não move o preço "
                     "que o cliente vê (preco_com_impostos) — só a receita líquida da empresa.",
       perturbar=lambda d: (_sem_chain, {"impostos_pct": caso.impostos_pct * (1 + d)}, []))

    # ── 4. preço/kg de material (uniforme em toda a designação) ──
    # ACHADO: TenantCostChain.material_price é chaveada por (material, forma) — quando a
    # designação tem MUITOS itens colidindo nessa chave com price_kgf bem diferente (típico
    # de job avulso transcrito item a item, como OF3683 — 54 itens manuscritos, cada um com
    # seu próprio R$/kgf), a resolução por "item de maior peso" (ver material_chain_permutador)
    # já introduz um desvio GRANDE no baseline (mult=1,0) antes de qualquer perturbação
    # intencional — testar "preço uniforme" nesse caso mediria o artefato do mecanismo, não
    # o campo. Guarda: só roda a entrada se o desvio em mult=1,0 for pequeno (<2%).
    _mat_base = caso.quote(cost_chain=material_chain_permutador(caso.designacao, mult=1.0))
    _drift = _pct(_mat_base["custo_material"], caso.baseline["custo_material"])
    if _drift is not None and abs(_drift) < 2.0:
        add("preço/kg de material (uniforme)", "material", "multiplicador", "custo_total",
           reabsorvivel="SIM no TOTAL, por construção — mas o fc recalibrado fica ERRADO: ele "
                         "absorve um erro de MATERIAL dentro do multiplicador de MÃO-DE-OBRA. O "
                         "preço de venda sai certo; o diagnóstico de custo/hora sai FALSO.",
           perturbar=lambda d: (
               lambda fc: material_chain_permutador(caso.designacao, mult=1 + d, fator_correcao_mo=fc),
               {}, []))
    else:
        e = Entrada(nome="preço/kg de material (uniforme)", grupo="material",
                    unidade="multiplicador", alvo="custo_total",
                    reabsorvivel="N/A — NÃO testável via cost_chain nesta designação",
                    nota=f"PULADO: a chave (material,forma) do cost_chain colide entre itens "
                         f"com preços muito diferentes nesta designação (ver "
                         f"colisoes_preco_kgf); a resolução por item dominante já desvia o "
                         f"material em {_drift:+.1f}% em mult=1,0, antes de qualquer "
                         f"perturbação. Job avulso (transcrição item a item) não cabe na "
                         f"granularidade (material×forma) do override de tenant.")
        entradas.append(e)

    # ── 5/6. liga metalúrgica por lado (multiplicador de horas de MO) ──
    for lado in ("feixe", "casco"):
        add(f"liga_por_lado[{lado}] (fator de horas)", "metalurgia", "multiplicador", "custo_total",
           reabsorvivel="PARCIAL — liga escala só as ops daquele LADO (feixe OU casco), fc "
                         "escala TODAS. O back-solve absorve o erro médio, mas distorce a "
                         "proporção feixe/casco do custo/hora — diagnóstico por componente sai "
                         "torto mesmo com o total batendo.",
           perturbar=(lambda d, lado=lado: (
               lambda fc: TenantCostChain(fator_correcao_mo=fc),
               {"liga_por_lado": {lado: 1 + d}}, [])))

    # ── 7/8. densidade por lado (peso, não afeta MO) ──
    for lado in ("feixe", "casco"):
        add(f"dens_por_lado[{lado}] (peso material)", "metalurgia", "multiplicador", "custo_total",
           reabsorvivel="SIM no total (tautológico), mas é 100% material — igual ao preço/kg, "
                         "corromper fc para compensar erro de densidade é sempre a coisa errada.",
           perturbar=(lambda d, lado=lado: (
               lambda fc: TenantCostChain(fator_correcao_mo=fc),
               {"dens_por_lado": {lado: 1 + d}}, [])))

    # ── 9/10. preço/kg por lado (fator de liga nobre no preço da MP) ──
    for lado in ("feixe", "casco"):
        add(f"preco_por_lado[{lado}] (R$/kg da liga)", "metalurgia", "multiplicador", "custo_total",
           reabsorvivel="SIM no total (tautológico); 100% material, mesma ressalva do preço/kg "
                         "uniforme — e o de MAIOR massa possível (inox/duplex/inconel chegam a "
                         "13× o preço do CS; ver PRECO_FATOR em tema_templates.services).",
           perturbar=(lambda d, lado=lado: (
               lambda fc: TenantCostChain(fator_correcao_mo=fc),
               {"preco_por_lado": {lado: 1 + d}}, [])))

    # ── 11. setup_frac (TODOS os parâmetros de uma vez) NO PONTO DE REFERÊNCIA ──
    # No ponto de referência (params=None → toda razão=1,0), _escala_op = setup + (1-setup)*1,0
    # = 1,0 PARA QUALQUER setup — é cancelamento ALGÉBRICO, não coincidência numérica (ver
    # permutador_quote._escala_op). Resultado esperado: E_bruta e E_calib EXATAMENTE zero,
    # para QUALQUER valor de setup_frac. A prova de verdade (não-trivial) está na seção "fora
    # do ponto calibrado", onde params ≠ 1,0.
    add("setup_frac (todos os parâmetros, no ponto de referência)", "knob_tenant", "multiplicador",
       "custo_total",
       reabsorvivel="N/A no ponto de referência — a fração de setup se cancela algebricamente "
                     "quando a razão do driver é 1,0. Só importa em cotações DESLOCADAS do "
                     "referencial (ver seção própria abaixo). Errar este knob no ponto exato "
                     "que o Wellington validou é, por construção, inofensivo.",
       perturbar=lambda d: (
           lambda fc: TenantCostChain(fator_correcao_mo=fc,
                                      setup_frac={k: max(0.0, min(1.0, v * (1 + d)))
                                                 for k, v in _SETUP_FRAC.items()}),
           {}, []))

    # ── 12. perda_por_familia['espelho'] — REALISTA (form atual não alcança) ──
    espelho_label = _espelho_label(caso.designacao)
    if caso.tem_form and espelho_label:
        cleaned0 = reference_inputs(caso.designacao)
        dims_form_realista = to_dims_override(caso.designacao, cleaned0)
        add("perda_por_familia['espelho'] (data sheet ATUAL)", "knob_tenant", "multiplicador",
           "custo_total",
           reabsorvivel="N/A — o data sheet do permutador completo só sobrescreve dims de "
                         "TUBOS e VIROLA (PermutadorDataSheetForm.to_dims_override); o espelho "
                         "nunca entra no caminho `dims_override`, então esta knob (V2/F1 Bloco "
                         "A) fica INERTE hoje, mesmo que o tenant a configure. ACHADO, não é "
                         "fix — reportado, não consertado.",
           perturbar=lambda d: (
               lambda fc: TenantCostChain(fator_correcao_mo=fc, perda_por_familia={"espelho": 1.40 * (1 + d)}),
               {"dims_override": dims_form_realista}, []))

        # ── 12b. mesma knob, mas com o form HIPOTETICAMENTE editando o espelho também ──
        dims_form_com_espelho = dict(dims_form_realista)
        espelho_dims = next(m["dims"] for m in _load_seed(caso.designacao, "materiais")
                            if m["label"] == espelho_label)
        dims_form_com_espelho[espelho_label] = {"OD": espelho_dims["OD"], "ESP.": espelho_dims["ESP."]}
        add("perda_por_familia['espelho'] (SE o form editasse o espelho)", "knob_tenant",
           "multiplicador", "custo_total",
           reabsorvivel="SIM no total (tautológico) — demonstra que a knob FUNCIONA quando "
                         "alcançável; o problema em (12) é de FIAÇÃO (wiring) do form, não do "
                         "motor.",
           perturbar=lambda d: (
               lambda fc: TenantCostChain(fator_correcao_mo=fc, perda_por_familia={"espelho": 1.40 * (1 + d)}),
               {"dims_override": dims_form_com_espelho}, []))

    # ── 13+. campos do data sheet (dims_override + params físicos) — só designações com form ──
    if caso.tem_form:
        cleaned0 = reference_inputs(caso.designacao)
        campos_form = [
            ("n_tubos", "nº de tubos"), ("comprimento_tubo_mm", "comprimento do tubo (mm)"),
            ("od_tubo_mm", "OD do tubo (mm)"), ("esp_tubo_mm", "parede do tubo (mm)"),
            ("n_chicanas", "nº de chicanas"), ("n_passes_tubos", "nº de passes"),
            ("comprimento_casco_mm", "comprimento do casco/virola (mm)"),
            ("diametro_casco_mm", "diâmetro do casco (mm)"), ("esp_casco_mm", "espessura da virola (mm)"),
        ]
        for campo, label in campos_form:
            def perturbar(d, campo=campo):
                cleaned = dict(cleaned0)
                cleaned[campo] = float(cleaned0[campo]) * (1 + d)
                dims_override = to_dims_override(caso.designacao, cleaned)
                params = physical_params(caso.designacao, cleaned)
                avisos = check_layout(int(cleaned["n_tubos"]), float(cleaned["od_tubo_mm"]),
                                      float(cleaned["diametro_casco_mm"]),
                                      cabecote=rear_letter(caso.designacao))
                return (_sem_chain, {"dims_override": dims_override, "params": params}, avisos)
            add(f"data sheet: {label}", "dims_form", "razão proj/ref", "custo_total",
               reabsorvivel="PARCIAL — o back-solve reconcilia o TOTAL, mas se o campo move "
                             "material E mão-de-obra em proporções diferentes (a maioria move), "
                             "o custo/hora resultante fica sistematicamente errado.",
               perturbar=perturbar)

    return entradas


def fora_do_ponto_calibrado(caso: CasoPermutador, block_factors=(1.5, 0.7),
                            delta_knob: float = 0.10) -> list[dict]:
    """"Fora do ponto calibrado": aplica o fc já fixado pelo ÚNICO job histórico (fc=1,0,
    gate 0,0%) a uma cotação NOVA, deslocada do referencial (todos os drivers físicos em
    bloco, ×1,5 ou ×0,7 — "job 50% maior/menor"). Ao contrário da seção anterior, aqui NÃO
    há recalibração possível: esta cotação não tem um referencial próprio contra o qual
    calibrar fc de novo. O que a calibração escondia EXATAMENTE no ponto de referência
    (setup_frac com elasticidade zero) deixa de ser zero aqui — é onde o produto vive."""
    resultados = []
    for bf in block_factors:
        params_block = {k: bf for k in _SETUP_FRAC}
        base = caso.quote(cost_chain=_sem_chain(1.0), params=params_block)
        pert = caso.quote(
            cost_chain=TenantCostChain(
                fator_correcao_mo=1.0,
                setup_frac={k: max(0.0, min(1.0, v * (1 + delta_knob)))
                           for k, v in _SETUP_FRAC.items()}),
            params=params_block)
        e_setup = elasticidade(base["custo_total"], pert["custo_total"], delta_knob)
        fator_escala_mo = (base["custo_mao_obra"] / caso.baseline["custo_mao_obra"]) / bf
        fator_escala_total = (base["custo_total"] / caso.baseline["custo_total"]) / bf
        resultados.append({
            "bloco": bf,
            "custo_total_no_bloco": round(base["custo_total"], 2),
            "custo_mao_obra_no_bloco": round(base["custo_mao_obra"], 2),
            "fator_escala_efetivo_mo": round(fator_escala_mo, 3),
            "fator_escala_efetivo_total": round(fator_escala_total, 3),
            "e_setup_frac_no_bloco": e_setup,
        })
    return resultados


def rt_escopo_discreto(caso: CasoPermutador) -> dict:
    """Escopo de radiografia é ESCOLHA categórica (Total/Parcial/Isento), não campo
    contínuo — reportado como tabela discreta, fora do framework de elasticidade ±δ."""
    if not caso.tem_form:
        return {}
    cleaned0 = reference_inputs(caso.designacao)
    out = {}
    for esc in ("Total", "Parcial", "Isento"):
        cleaned = dict(cleaned0)
        cleaned["rt_escopo"] = esc
        params = physical_params(caso.designacao, cleaned)
        dims_override = to_dims_override(caso.designacao, cleaned)
        q = caso.quote(cost_chain=_sem_chain(1.0), dims_override=dims_override, params=params)
        out[esc] = round(q["custo_total"], 2)
    return out


def montar_caso_permutador(nome: str, designacao: str) -> CasoPermutador:
    with open(os.path.join(SEEDS, f"{designacao.lower()}_referencial.json"), encoding="utf-8") as f:
        ref = json.load(f)
    referencial = ref["custo_total_com_impostos"]
    fator_preco = ref.get("fator_comercial")
    impostos_pct = ref.get("icms_pct")
    if fator_preco is None or impostos_pct is None:
        # OF3683 (job avulso): seed não traz fator_comercial/icms_pct explícitos — deriva
        # do gross-up conhecido (preco_venda_com_impostos, icms_pct_reduzido).
        impostos_pct = ref.get("icms_pct_reduzido", 9.0)
        preco_sem = ref["preco_venda_com_impostos"] * (1 - impostos_pct / 100.0)
        fator_preco = preco_sem / referencial
    return CasoPermutador(nome=nome, designacao=designacao, referencial=referencial,
                          fator_preco=fator_preco, impostos_pct=impostos_pct,
                          tem_form=tem_data_sheet(designacao))


# ═══════════════════════════════════════════════════════════════════════════════════
# Caso FEIXE — quote_feixe(FeixeInputs)
# ═══════════════════════════════════════════════════════════════════════════════════

REFERENCIAL_FEIXE = 35353.0   # validate_feixe_completo.py — custo total (ops + material)


@dataclass
class CasoFeixe:
    nome: str
    referencial: float
    fator_preco: float
    impostos_pct: float
    inp_base: FeixeInputs = field(default_factory=caso_136_tubos)
    baseline: dict = field(default_factory=dict)
    fc_referencia: float = 1.0
    mo_referencia: float = 0.0

    def __post_init__(self):
        self.baseline = self.metrics(self.quote(self.inp_base))
        # Mesmo cuidado do CasoPermutador: E_calib compara contra o fc* já calibrado no ponto
        # de referência (sem perturbação), não contra custo_mao_obra cru em fc=1,0 — senão o
        # resíduo do próprio gate (aqui maior: −2,9%, ver validate_feixe_completo) vaza como
        # artefato de sinal na divisão por ±δ.
        self.fc_referencia, self.mo_referencia = self.calibrar_e_medir(
            self.inp_base, lambda fc: TenantCostChain(fator_correcao_mo=fc), {})

    def quote(self, inp: FeixeInputs, cost_chain=None, fator_preco=None, impostos_pct=None):
        return quote_feixe(
            inp, cost_chain=cost_chain,
            fator_preco=self.fator_preco if fator_preco is None else fator_preco,
            impostos_pct=self.impostos_pct if impostos_pct is None else impostos_pct)

    @staticmethod
    def metrics(cot) -> dict:
        return {
            "custo_total": cot.custo_total,
            "custo_mao_obra": sum(it.custo_mo for it in cot.itens),
            "preco_com_impostos": cot.preco_com_impostos,
        }

    def calibrar_e_medir(self, inp: FeixeInputs, make_chain, extra_kw: dict):
        fc_star = solve_fc_affine(
            lambda fc: self.metrics(self.quote(inp, cost_chain=make_chain(fc), **extra_kw))["custo_total"],
            self.referencial)
        if fc_star is None:
            return None, None
        mo = self.metrics(self.quote(inp, cost_chain=make_chain(fc_star), **extra_kw))["custo_mao_obra"]
        return fc_star, mo


# perturbar(delta) -> (inp, make_chain, extra_kw, avisos)
PerturbadorFeixe = Callable[[float], tuple[FeixeInputs, Callable[[float], Any], dict, list[str]]]


def _sweep_feixe_entrada(caso: CasoFeixe, entrada: Entrada, perturbar: PerturbadorFeixe,
                         deltas=(DELTA_PRIMARIO, -DELTA_PRIMARIO, DELTA_NAO_LINEAR, -DELTA_NAO_LINEAR)) -> None:
    mo_base = caso.mo_referencia
    calc_calib = entrada.grupo != "markup_imposto"
    for delta in deltas:
        inp, make_chain, extra_kw, avisos = perturbar(delta)
        alvo_base = caso.baseline[entrada.alvo]
        m = caso.metrics(caso.quote(inp, cost_chain=make_chain(1.0), **extra_kw))
        alvo_pert = m[entrada.alvo]
        ponto = Ponto(delta=delta, custo_total_bruto=alvo_pert,
                      e_bruta=elasticidade(alvo_base, alvo_pert, delta), avisos=avisos)
        if calc_calib:
            fc_star, mo_calib = caso.calibrar_e_medir(inp, make_chain, extra_kw)
            ponto.fc_calibrado = fc_star
            ponto.custo_mo_calib = mo_calib
            if mo_calib is not None:
                ponto.e_calib = elasticidade(mo_base, mo_calib, delta)
        entrada.pontos[f"{delta:+.0%}"] = ponto


def _sem_chain_feixe(fc: float):
    return None if fc == 1.0 else TenantCostChain(fator_correcao_mo=fc)


def montar_entradas_feixe(caso: CasoFeixe) -> list[Entrada]:
    entradas: list[Entrada] = []
    inp0 = caso.inp_base

    def add(nome, grupo, unidade, alvo, reabsorvivel, perturbar, deltas=None):
        e = Entrada(nome=nome, grupo=grupo, unidade=unidade, alvo=alvo, reabsorvivel=reabsorvivel)
        _sweep_feixe_entrada(caso, e, perturbar,
                             deltas=deltas or (DELTA_PRIMARIO, -DELTA_PRIMARIO, DELTA_NAO_LINEAR, -DELTA_NAO_LINEAR))
        entradas.append(e)

    def campo(nome_campo, label, arredonda=False):
        def perturbar(d):
            valor = getattr(inp0, nome_campo) * (1 + d)
            if arredonda:
                valor = max(1, round(valor))
            inp = replace(inp0, **{nome_campo: valor})
            return inp, lambda fc: TenantCostChain(fator_correcao_mo=fc), {}, []
        add(f"data sheet: {label}", "dims_form", "razão proj/ref", "custo_total",
           reabsorvivel="PARCIAL — mesma ressalva do permutador: o campo move material e MO "
                         "em proporções diferentes; o back-solve reconcilia o total, não a "
                         "composição.",
           perturbar=perturbar)

    campo("n_tubos", "nº de tubos", arredonda=True)
    campo("tubo_comp_mm", "comprimento do tubo (mm)")
    campo("chicana_qty", "nº de chicanas", arredonda=True)
    campo("chicana_esp_mm", "espessura da chicana (mm)")
    campo("espelho_esp_bruta_mm", "espessura bruta do espelho (mm)")
    campo("tirante_qty", "nº de tirantes", arredonda=True)

    add("fator_correcao_mo", "knob_calibracao", "multiplicador", "custo_total",
       reabsorvivel="N/A — é o próprio knob de calibração (mesma ressalva do permutador).",
       perturbar=lambda d: (
           inp0, lambda fc: TenantCostChain(fator_correcao_mo=1 + d), {}, []))

    add("custo_transporte", "knob_tenant", "R$ (input direto)", "custo_total",
       reabsorvivel="SIM no total (tautológico) — é custo FIXO por job (OP-TRANSP-ENT), não "
                     "escala com fc; a mesma distorção do preço/kg de material se aplica: o "
                     "back-solve empurraria um erro de logística para dentro do fator de MO.",
       perturbar=lambda d: (
           replace(inp0, custo_transporte=inp0.custo_transporte * (1 + d)),
           lambda fc: TenantCostChain(fator_correcao_mo=fc), {}, []))

    add("preço/kg de material (uniforme)", "material", "multiplicador", "custo_total",
       reabsorvivel="SIM no total (tautológico), mas 100% material — mesma ressalva do "
                     "permutador: corrompe o custo/hora diagnóstico.",
       perturbar=lambda d: (
           inp0, lambda fc: material_chain_feixe(inp0, mult=1 + d, fator_correcao_mo=fc), {}, []))

    add("fator_preco (markup)", "markup_imposto", "multiplicador", "preco_com_impostos",
       reabsorvivel="NÃO — downstream de custo_total (mesma ressalva do permutador).",
       perturbar=lambda d: (
           inp0, _sem_chain_feixe, {"fator_preco": caso.fator_preco * (1 + d)}, []))
    add("impostos_pct", "markup_imposto", "multiplicador", "preco_com_impostos",
       reabsorvivel="NÃO — downstream de custo_total (mesma ressalva do permutador).",
       perturbar=lambda d: (
           inp0, _sem_chain_feixe, {"impostos_pct": caso.impostos_pct * (1 + d)}, []))

    return entradas


# ═══════════════════════════════════════════════════════════════════════════════════
# Orquestração — monta todos os casos, roda a varredura completa, serializa
# ═══════════════════════════════════════════════════════════════════════════════════

FATOR_PRECO_FEIXE_136 = 1.01377    # validate_feixe_completo.py / feixe_quote.quote_feixe defaults
IMPOSTOS_FEIXE_136 = 23.303


def montar_tudo() -> dict:
    resultado = {"casos": [], "colisoes_preco_kgf": {}}

    permutadores = [("BEU", "BEU"), ("BEM", "BEM"), ("OF3683", "OF3683")]
    for nome, desig in permutadores:
        caso = montar_caso_permutador(nome, desig)
        entradas = montar_entradas_permutador(caso)
        resultado["colisoes_preco_kgf"][nome] = colisoes_preco_kgf(desig)
        resultado["casos"].append({
            "nome": nome, "tipo": "permutador", "designacao": desig,
            "baseline_custo_total": round(caso.baseline["custo_total"], 2),
            "baseline_custo_mao_obra": round(caso.baseline["custo_mao_obra"], 2),
            "baseline_custo_material": round(caso.baseline["custo_material"], 2),
            "baseline_custo_servicos": round(caso.baseline["custo_servicos"], 2),
            "fracao_mo_pct": round(caso.baseline["custo_mao_obra"] / caso.baseline["custo_total"] * 100, 1),
            "fracao_material_pct": round(caso.baseline["custo_material"] / caso.baseline["custo_total"] * 100, 1),
            "referencial": caso.referencial,
            "delta_gate_pct": round((caso.baseline["custo_total"] / caso.referencial - 1) * 100, 3),
            "fc_referencia": round(caso.fc_referencia, 5),
            "tem_data_sheet": caso.tem_form,
            "entradas": [e.to_json() for e in entradas],
            "fora_do_ponto_calibrado": fora_do_ponto_calibrado(caso),
            "rt_escopo_discreto": rt_escopo_discreto(caso),
        })

    caso_feixe = CasoFeixe(nome="FEIXE-136", referencial=REFERENCIAL_FEIXE,
                           fator_preco=FATOR_PRECO_FEIXE_136, impostos_pct=IMPOSTOS_FEIXE_136)
    entradas_feixe = montar_entradas_feixe(caso_feixe)
    resultado["casos"].append({
        "nome": "FEIXE-136", "tipo": "feixe", "designacao": "FEIXE-136",
        "baseline_custo_total": round(caso_feixe.baseline["custo_total"], 2),
        "baseline_custo_mao_obra": round(caso_feixe.baseline["custo_mao_obra"], 2),
        "fracao_mo_pct": round(caso_feixe.baseline["custo_mao_obra"] / caso_feixe.baseline["custo_total"] * 100, 1),
        "referencial": caso_feixe.referencial,
        "delta_gate_pct": round((caso_feixe.baseline["custo_total"] / caso_feixe.referencial - 1) * 100, 3),
        "fc_referencia": round(caso_feixe.fc_referencia, 5),
        "tem_data_sheet": True,
        "entradas": [e.to_json() for e in entradas_feixe],
    })
    return resultado


def ranking_movimenta_dinheiro(dados: dict) -> list[dict]:
    """Ordena TODAS as (entrada, caso) por |E_bruta| médio (±10%) — "quanto move o número
    final por 10% de erro no campo". ATENÇÃO — NÃO é um invariante que todo alvo seja
    custo_total OU preco_com_impostos: `impostos_pct` no permutador tem
    alvo=preco_sem_impostos (receita líquida da empresa, não o preço que o cliente vê — ver
    achado #5 do relatório). O `alvo` de cada linha vai explícito no dict devolvido —
    NÃO pressuponha que a coluna é homogênea antes de comparar duas linhas."""
    linhas = []
    for caso in dados["casos"]:
        for ent in caso["entradas"]:
            p10 = ent["pontos"].get("+10%", {})
            m10 = ent["pontos"].get("-10%", {})
            ebs = [abs(x["e_bruta"]) for x in (p10, m10) if x.get("e_bruta") is not None]
            ecs = [abs(x["e_calib"]) for x in (p10, m10) if x.get("e_calib") is not None]
            if not ebs:
                continue
            linhas.append({
                "caso": caso["nome"], "entrada": ent["nome"], "grupo": ent["grupo"],
                "alvo": ent["alvo"],
                "e_bruta_medio": sum(ebs) / len(ebs),
                "e_calib_medio": (sum(ecs) / len(ecs)) if ecs else None,
                "reabsorvivel": ent["reabsorvivel"],
            })
    return sorted(linhas, key=lambda r: -r["e_bruta_medio"])


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--json", help="grava o resultado completo em JSON neste caminho")
    ap.add_argument("--md", help="grava um resumo em markdown neste caminho")
    ap.add_argument("--delta", type=float, default=0.10,
                    help="δ primário da varredura (default 0,10 = ±10%%); "
                         "±25%% roda sempre em paralelo p/ checar não-linearidade")
    args = ap.parse_args()

    global DELTA_PRIMARIO   # noqa: PLW0603 — CLI override do δ primário do módulo
    DELTA_PRIMARIO = args.delta
    dados = montar_tudo()
    ranking = ranking_movimenta_dinheiro(dados)

    print("=" * 78)
    print("VARREDURA DE SENSIBILIDADE — pricing_engine (read-only)")
    print("=" * 78)
    for caso in dados["casos"]:
        print(f"\n[{caso['nome']}] baseline R$ {caso['baseline_custo_total']:,.2f} "
             f"(referencial R$ {caso['referencial']:,.2f}, Δ {caso['delta_gate_pct']:+.3f}%) "
             f"— MO {caso['fracao_mo_pct']:.1f}%")
    print(f"\n{'-'*78}\nTOP 10 — entradas que MAIS movem dinheiro (|E_bruta| médio @±10%):")
    for r in ranking[:10]:
        ec = f"{r['e_calib_medio']:.3f}" if r["e_calib_medio"] is not None else "  N/A"
        print(f"  {r['e_bruta_medio']:6.3f}  (E_calib {ec})  [{r['caso']:8}] {r['entrada']}"
             f"  (alvo={r['alvo']})")
    print("\nBOTTOM 10 — praticamente ruído:")
    for r in ranking[-10:]:
        ec = f"{r['e_calib_medio']:.3f}" if r["e_calib_medio"] is not None else "  N/A"
        print(f"  {r['e_bruta_medio']:6.3f}  (E_calib {ec})  [{r['caso']:8}] {r['entrada']}"
             f"  (alvo={r['alvo']})")
    total_avisos = sum(
        len(ponto.get("avisos") or [])
        for caso in dados["casos"] for ent in caso["entradas"]
        for ponto in ent["pontos"].values()
    )
    print(f"\nAvisos de viabilidade geométrica (check_layout) nesta rodada: {total_avisos}"
         f"{' — nenhuma combinação testada ficou geometricamente inviável' if not total_avisos else ''}")

    if args.json:
        with open(args.json, "w", encoding="utf-8") as f:
            json.dump({"casos": dados["casos"], "colisoes_preco_kgf": dados["colisoes_preco_kgf"],
                      "ranking": ranking}, f, ensure_ascii=False, indent=2)
        print(f"\nJSON escrito em {args.json}")

    if args.md:
        with open(args.md, "w", encoding="utf-8") as f:
            f.write(_render_markdown(dados, ranking))
        print(f"Markdown escrito em {args.md}")


def _render_markdown(dados: dict, ranking: list[dict]) -> str:
    linhas = ["# Varredura de sensibilidade — pricing_engine\n",
             "Gerado por `scripts/sensibilidade_motor.py`. Ver docs/SENSIBILIDADE_MOTOR.md "
             "para a leitura narrativa. ⚠️ `E_calib` do PERMUTADOR (BEU/BEM/OF3683) é "
             "HIPOTÉTICO — o back-solve só existe em produção para o feixe "
             "(`apps.cost_discovery.services.back_solve`); ver docstring do módulo.\n"]
    linhas.append("## Ranking — quem move dinheiro (|E_bruta| médio @±10%)\n")
    linhas.append("Coluna `Alvo` NÃO é homogênea: a maioria mede custo_total/preco_com_impostos, "
                  "mas `impostos_pct` no permutador mede preco_sem_impostos (receita líquida, "
                  "não o preço cobrado do cliente) — não compare `E_bruta` entre alvos "
                  "diferentes como se fossem a mesma régua.\n")
    linhas.append("| Entrada | Caso | Alvo | E_bruta | E_calib |")
    linhas.append("|---|---|---|---:|---:|")
    for r in ranking:
        ec = f"{r['e_calib_medio']:.3f}" if r["e_calib_medio"] is not None else "N/A"
        linhas.append(f"| {r['entrada']} | {r['caso']} | {r['alvo']} | {r['e_bruta_medio']:.3f} | {ec} |")
    linhas.append("")
    for caso in dados["casos"]:
        avisos_caso = sum(len(p.get("avisos") or []) for ent in caso["entradas"]
                          for p in ent["pontos"].values())
        linhas.append(f"## {caso['nome']}\n")
        linhas.append(f"Baseline: R$ {caso['baseline_custo_total']:,.2f} · "
                      f"referencial R$ {caso['referencial']:,.2f} · "
                      f"Δ {caso['delta_gate_pct']:+.3f}% · MO {caso['fracao_mo_pct']:.1f}%\n")
        linhas.append(f"Avisos de viabilidade geométrica (`check_layout`) nas "
                      f"{sum(len(ent['pontos']) for ent in caso['entradas'])} combinações "
                      f"testadas: **{avisos_caso}**"
                      f"{' — nenhum, silêncio confirmado, não presumido' if not avisos_caso else ''}.\n")
        linhas.append("| Entrada | Grupo | Alvo | +10% Eb | -10% Eb | +10% Ec | -10% Ec |")
        linhas.append("|---|---|---|---:|---:|---:|---:|")
        for ent in caso["entradas"]:
            p, m = ent["pontos"].get("+10%", {}), ent["pontos"].get("-10%", {})
            def fmt(v):
                return f"{v:.3f}" if v is not None else "—"
            linhas.append(f"| {ent['nome']} | {ent['grupo']} | {ent['alvo']} | {fmt(p.get('e_bruta'))} | "
                          f"{fmt(m.get('e_bruta'))} | {fmt(p.get('e_calib'))} | {fmt(m.get('e_calib'))} |")
        linhas.append("")
    return "\n".join(linhas)


if __name__ == "__main__":
    main()
