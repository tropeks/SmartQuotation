# Critérios de Radiografia (RT) — ASME BPVC Seção V, Artigo 2 (ed. 2023)

> Extração da fonte primária licenciada (Seção V — Nondestructive Examination, Artigo 2,
> Radiographic Examination) para fundamentar a parametrização de custo de ensaio do motor.

## Conclusão-chave para a arquitetura do motor

**A EXTENSÃO do RT (Total / Parcial / Isento) NÃO se define na Seção V.** O parágrafo
**T-226** é explícito: *"The extent of radiographic examination shall be as specified by the
referencing Code Section."* — ou seja, a quantidade de solda radiografada e a eficiência de
junta vêm da **Seção VIII Div. 1** (UW-11 = extensão; **Tabela UW-12** = eficiência E).

→ O `E_POR_RT = {Total: 1.00, Parcial: 0.85, Isento: 0.70}` em `pricing_engine/asme.py` **já
reflete a Tabela UW-12** (junta tipo 1, topo duplo). Arquitetura confirmada, sem mudança.

A Seção V define **COMO** radiografar. O que ela agrega ao **custo** é o driver físico real:
**número de exposições** (não metragem linear pura).

## Critérios extraídos (Artigo 2)

| § | Critério | Relevância p/ custo |
|---|---|---|
| **T-210** | Escopo: método aplicável a materiais (incl. fundidos) e soldas, junto ao Artigo 1. | — |
| **T-226** | **Extensão = definida pelo código de referência** (Seção VIII). | Confirma que Total/Parcial vem da VIII, não da V. |
| **T-271** | Técnica: **parede simples sempre que prático**; senão **parede dupla** (tubos pequenos). *"An adequate number of exposures shall be made to demonstrate the required coverage."* | **Driver primário**: nº de exposições p/ cobrir a solda. |
| **T-274** | **Nitidez geométrica** `Ug = F·d/D` (F=tamanho da fonte, D=fonte→objeto, d=objeto→filme). Limites máx. por espessura. | Impõe distância fonte-filme mínima → limita cobertura/exposição. |
| **T-282** | **Densidade do filme**: mín. **1.8** (raio-X) / **2.0** (gama); composto 1.3/filme; máx. 4.0. | Critério de **retomada** (refilmagem → retrabalho). |
| **T-285** | Avaliação/aceitação é responsabilidade do **Fabricante** (interpreta os filmes). | Hora de interpretação/laudo. |

### T-274.2 — Nitidez geométrica máxima (Ug) por espessura
| Espessura do material | Ug máx. |
|---|---|
| < 50 mm | 0,51 mm |
| 50–75 mm | 0,76 mm |
| 75–100 mm | 1,02 mm |
| > 100 mm | 1,78 mm |

## Impacto no custeio (estado atual × refinamento possível)

**Hoje** (calibração): `custo_RT ≈ metragem_de_solda × RT_FATOR`, com
`RT_FATOR = {Total: 3.0, Parcial: 1.0, Isento: 0.3}`. É um multiplicador calibrado, não físico.

**Fisicamente (Seção V)**: `custo_RT ≈ nº_exposições × custo_por_exposição`, onde:
- **solda longitudinal**: `nº ≈ comprimento / (comprimento_útil_do_filme − sobreposição)`;
- **solda circunferencial**: depende do **Ø**, da **técnica** (parede simples vs dupla, T-271) e
  da **distância fonte-filme** (cobertura por exposição limitada pela geometria e pelo Ug, T-274).

**Refinamento opcional** (trocar metragem×fator por modelo de exposições): exige 2 parâmetros de
chão de fábrica da ENGEMATEX (a confirmar com @WellToMcAt):
1. comprimento útil de filme + sobreposição mínima (ex.: filme 350 mm, sobrepor ~10%);
2. regra parede-simples vs parede-dupla por diâmetro (T-271 favorece simples quando prático).

## O que isto resolve / não resolve

- ✅ **Resolve**: confirma que **extensão (UW-11) + eficiência E (UW-12) são da Seção VIII** — o
  motor está alinhado à norma nesse ponto.
- ⛔ **Não resolve**: o **escopo de RT do referencial** (Total vs Parcial) — é dado do *projeto*
  (desenho/contrato), não da norma. Continua pendente do @WellToMcAt.

---
*Fonte: ASME BPVC.V-2023, Artigo 2 (T-210 a T-292). Extração local do PDF licenciado.*
