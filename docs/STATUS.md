# SmartQuotation — Status do Projeto

> Documento vivo. Última revisão: 2026-06-19 — **aval do PE (Wellington) nos 7 itens normativos**.
> (colaboração com @WellToMcAt). **41 PRs mergeados · gates feixe −2,9% / permutador BEU+BEM 0,0% ·
> 150 testes na suíte Django · CI verde em todos os PRs.**

---

## 1. Visão geral

Motor de custeio **paramétrico** para permutadores de calor casco-tubo (caldeiraria média/pesada),
design partner **ENGEMATEX**. Reproduz os gabaritos reais e responde às dimensões/materiais do projeto.

| Equipamento | Motor | Gabarito | Erro |
|---|---:|---:|:--:|
| Feixe tubular (136 tubos) | — | venda R$ 44.192 | −2,9% |
| **BEU** (bonnet + casco 1 passe + feixe-U) | R$ 128.160 | R$ 128.160 | **0,0%** |
| **BEM** (espelho fixo, tubos retos) | R$ 119.295 | R$ 119.295 | **0,0%** |

---

## 2. O que o motor calcula hoje

- **Matéria-prima** — peso pela geometria de cada peça: tubo, virola, espelho, chicana, tampo 2:1,
  anel, pescoço de bocal e flange WN (tabela ASME B16.5).
- **Mão de obra** — horas escalam pelo driver físico de cada operação, com setup fixo: furação ∝ nº
  tubos; furação de chicana ∝ tubos × chicanas; soldas ∝ comprimento/diâmetro × espessura²; rasgos ∝
  (passes − 1); bocais ∝ peso do flange.
- **Ensaios/serviços** — raio-X ∝ escopo de RT; UT/LP ∝ metros de solda; TT/consumíveis ∝ massa;
  hidrostático ∝ volume.
- **Metalurgia por lado** (feixe|casco, bimetálico) — liga (MO), densidade (peso), preço/kg.
- **Verificações ASME VIII Div.1** (alertas, não bloqueiam):
  - **UG-27/UG-32** — espessura mínima de casco e tampo 2:1, com corrosão (CA); alerta crítico se a
    espessura informada for menor que a norma.
  - **Apêndice 2** — espessura mínima do flange de corpo (girth flange); alerta se a referência não
    cobrir a pressão de projeto.
  - **UG-21** — a pressão de projeto inclui a coluna estática do fluido (ρ·g·h).
  - **Estimativa de RT** — nº de exposições (chapas de filme) do equipamento (Seção V Art.2).

---

## 3. Tier de design mecânico — CONCLUÍDO (PRs #5–34)

| Item | Status |
|---|:--:|
| A1 espessura ASME (UG-27 casco + UG-32 tampo + corrosão) | ✅ |
| A2 fluido corrosivo (Tubos/Casco/Ambos → metalurgia do cabeçote/espelho) | ✅ |
| A3 flanges WN (peso real por Ø×rating×schedule) | ✅ |
| Calibrações (scrap 40%/20%/10%, ICMS por dentro, RT escopo) | ✅ |
| **RT do gabarito = Total (100%)** | ✅ (#27) |
| **Tabelas S → ASME II-D MÉTRICA 2025 (edição licenciada)** + rastreabilidade | ✅ (#28–29) |
| **Inconel 625 e Monel 400 como classes separadas** | ✅ (#30) |
| **Cadastro de ligas editável por tenant** (sem deploy) | ✅ (#31) |
| **Flange de corpo — Apêndice 2** | ✅ (#32) |
| **Pressão estática de coluna — UG-21** | ✅ (#33) |
| **RT por nº de exposições — Seção V Art.2** | ✅ (#34) |

### Rastreabilidade ASME (certificação)
Cada valor de tensão admissível S carrega **norma + edição + tabela + linha** (`S_PROCEDENCIA` em
`pricing_engine/asme.py`) e é citado na memória de cálculo. Os 4 specs ativos rastreáveis à 2025:

| Classe | Spec | Tab/Linha (II-D 2025) | S @40°C |
|---|---|---|---:|
| CS | SA-516 GR 70 | 1A L43 | 138 MPa |
| INOX | SA-240 304 (conservadora) | 1A L3 | 138 MPa |
| DUPLEX | SA-240 S31803 (conservador) | 1A L12 | 177 MPa |
| INCONEL | SB-443 N06625 Grade 1 | 1B L22 | 217 MPa |
| MONEL | SB-127 N04400 | 1B L10 | 129 MPa |

> Correções que só a edição licenciada revelou: **Inconel −9%** (236,5→217) e **Duplex S32205 −10%**
> (206,9→187) — as fontes web superestimavam. CS não é platô até 343°C (cai a ~129).

---

## 3b. Camada de produto + normativo — CONCLUÍDA (PRs #35–41)

| Item | Status |
|---|:--:|
| Ciclo **cotação → proposta** do permutador (persiste Quotation + gera Proposal) | ✅ (#36) |
| **Memória de cálculo ASME** embutida no PDF e DOCX da proposta (c/ procedência S) | ✅ (#37–38) |
| **Tabela S data-driven** — `seeds/asme_materials_2025.json` (3213 regs II-D 2025) + flanges SO/BL | ✅ (#39) |
| Teste de guarda **anti-drift** 304L/316L (linha conservadora) | ✅ (#40) |
| **Histórico de cotações** — listar / reabrir / revisar (revision+1, recomputa c/ dims originais) | ✅ (#41) |
| **API REST (DRF)** — `GET /api/cotacoes/` + `POST /api/permutador/estimate/` (tenant-scoped) | ✅ (#41) |
| **Catálogo de ligas do DB ASME** — `seed_ligas_from_db` importa 3213 chapas como inativas | ✅ (#41) |

> Sprint #41 (multi-agente Hermes): refutação cross-engine pegou **2 bugs reais** de input cru
> (revise + API estimate passavam dimensões cruas → motor devolvia custo do gabarito; R$297k de
> diferença num caso). Fix: `tema_templates.services.estimate_from_inputs(designacao, inputs)`.

---

## 4. ✅ VALIDADO PELO PE — Wellington (@WellToMcAt), 2026-06-19

Os 7 itens foram **chancelados pelo engenheiro responsável**. Os defaults deixaram de ser provisórios.

| # | Item | Aval do PE (2026-06-19) |
|---|---|---|
| 1 | **Valores S 2025** | ✅ Avalizado — usar a extração da edição licenciada (BPVC.II.D.M-2025) para uso documental. |
| 2 | **UNS do duplex** | ✅ **S31803** confirmado (já era o default conservador). |
| 3 | **Inconel Grade** | ✅ **Grade 1 recozido** (217 MPa) confirmado. |
| 4 | **Flange de corpo (Apêndice 2)** | ✅ Gaxeta **espiralada m=3,0 / y=69 MPa** confere; furação proporcional ao flange. |
| 5 | **Pressão estática (UG-21)** | ✅ OK — casos da ENGEMATEX são **horizontais**, coluna ≈ Ø do casco, densidade água. |
| 6 | **RT por exposições** | ✅ Valores confirmados — filme útil **315 mm**, 2 costuras circunferenciais. |
| 7 | **Fatores MO/preço por liga** | ✅ Seguir com os **defaults** (Inconel 2,3×/13×, Monel 2,0×/9×); o orçamentista ajusta por caso no momento da cotação. |

---

## 5. Limitações honestas (declaradas na UI e no código)

1. Os defaults da seção 4 estão **validados pelo PE** (2026-06-19); fatores de **setup, preço e scrap** seguem editáveis por caso.
2. A escala é **calibrada a 1 job real** por designação (sem 2º gabarito p/ validar linearidade).
3. Verificações ASME são **alertas de apoio**, não substituem o memorial de cálculo do PE.

---

## 6. Como rodar / testar

```bash
python -m tests.validate_feixe_completo          # gate do feixe (±10%)
python -m tests.validate_permutador_completo     # gate BEU+BEM (±10% + geometria)
cd backend && python manage.py test apps         # suíte Django (django-tenants)
```

Arquitetura, decisões e seeds: ver `CLAUDE.md`, `pricing_engine/` e `docs/RT_CRITERIOS_ASME_V.md`.
