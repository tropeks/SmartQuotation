# SmartQuotation — Status do Projeto

> Documento vivo. Última revisão: 2026-06-25 — H1 técnico estabilizado; H1 auditável fechado (#46);
> H2.1 (cotação → OF), H2.2 (apontamento), H2.3 (aprendizado), H2.4 (ITP básico), H2.5 foundation
> e H2.5.1 (primeira fatia operacional do conector Protheus) entregues.
> (colaboração com @WellToMcAt).
> **43 PRs mergeados · gates feixe −2,9% / permutador BEU+BEM 0,0% ·
> suítes relevantes locais verdes (`production` + `audit` = 49 testes) · CI verde nos PRs mergeados.**

---

## 1. Visão geral

Motor de custeio **paramétrico** para permutadores de calor casco-tubo (caldeiraria média/pesada),
design partner **ENGEMATEX**. Reproduz os gabaritos reais e responde às dimensões/materiais do projeto.

- **H1 técnico:** feixe tubular + BEU/BEM operando com EAP persistida por cotação.
- **H1 auditável:** aprovação técnica CREA, `CalculationSnapshot` com hash e trilha mínima (#46) ✅.
- **H2 (Gestão da Produção):** H2.1 converte cotação aprovada em Ordem de Fabricação (#47); H2.2 registra
  apontamento de horas por operação e, no fechamento, calcula R$/h observado → `ActualRate`; H2.3 lê
  esses agregados e sugere atualização de `Rate` quando há amostragem e confiança suficientes; H2.4
  gera ITP básico a partir do roteiro da OF e registra aceite por item com responsável/data; H2.5
  iniciou a trilha de ERP com a fundação do app `apps.integrations.protheus`.
- **Fora do H1:** vaso/PVElite completo, JWT/MFA, Equipment/Component formal e integrações ERP.

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

## 3c. H1 auditável + H2 (produção) — CONCLUÍDA até H2.5 foundation (PRs #46–47 + H2.2/H2.3/H2.4 + #52)

| Item | Status |
|---|:--:|
| **Aprovação técnica** — `TechnicalApproval` (CREA obrigatório do engenheiro, ART opcional, revogação lógica) vinculada ao hash do snapshot | ✅ (#46) |
| **`CalculationSnapshot`** — hash SHA-256 sobre inputs/outputs/memorial; criado em feixe, permutador e revise; recusa permutador pressurizado sem memorial ASME | ✅ (#46) |
| **`AccessLog`** append-only — view/download/generate/approve/revoke (+ convert/transition no H2) | ✅ (#46–47) |
| **H2.1 — Cotação → Ordem de Fabricação** — `apps/production`: deep-copy de BOM+roteiro, snapshot_hash pinado, exige aprovação técnica ativa, workflow de status com autoria por transição | ✅ (#47) |
| **H2.2 — Apontamento de produção** — `ProductionEntry` (horas por operação, somadas); no fechamento da OF grava `ProductionObservation` e agrega `ActualRate` em **R$/h observado = custo ÷ horas reais** (Welford online), usado pelo H2.3 | ✅ (PR) |
| **H2.3 — Motor de aprendizado de índices** — `RateSuggestion` gerada a partir de `ActualRate` elegível (`N ≥ 20`, confiança `≥ 70%`, delta material), com aplicar/descartar via serviço e UI protegida por RBAC | ✅ (`aa3127c`) |
| **H2.4 — ITP básico** — `InspectionPlan` gerado a partir das `OFOperation` aplicáveis; `InspectionItem` com snapshot da operação, tipo/critério, aceite por responsável/data e auditoria `itp_generate`/`itp_accept` | ✅ |
| **H2.5 foundation — Protheus** — app tenant-scoped `apps.integrations.protheus` com configuração por tenant, `SyncBinding`/`SyncRun`/`SyncAttempt`, snapshots remotos de OF/BOM, fake client, serialização determinística e testes de import/export para OF, BOM, materiais e fornecedores | ✅ (#52) |
| **H2.5.1 — Protheus operacional (fatia 1)** — export assíncrono da OF no `release`, tasks Celery tenant-aware, adapter HTTP por contrato, staging governado para import de materiais/fornecedores, admin actions de reenfileirar/aplicar/rejeitar e testes de `integrations.protheus` + `production` verdes | ✅ |

> H2.1 desenhado por agente Opus, codado por Sonnet, revisado por Opus (TOCTOU do guard fechado
> com `select_for_update` + `UniqueConstraint` parcial; desempate determinístico do snapshot).
> H2.1/H2.2 desenhados por Opus, codados por Sonnet (TDD), revisados por Opus. H2.2 fez pivot durante a
> review: o motor expõe custo (não horas) por operação → baseline = custo, aprendizado em R$/h observado.
> H2.3 foi codado com TDD e auditado em `aa3127c` (7 achados corrigidos): geração idempotente, bordas
> de confiança, proteção contra `Rate` inválido/zero, aplicação transacional e RBAC nas views.
> H2.4 seguiu TDD: ITP idempotente, snapshot do roteiro da OF, aceite protegido e eventos no `AccessLog`.
> H2.5 foundation (PR #52) entregou a espinha tenant-scoped do conector Protheus sem acoplar transporte
> HTTP especulativo ao domínio. O fechamento de H2.5.1 adicionou o primeiro slice operacional:
> export assíncrono por workflow de OF, tasks multi-tenant, adapter HTTP real mínimo e staging
> assistido para import de catálogo sem aplicar preço direto no domínio. Durante a trilha Protheus
> foi corrigido também um bug preexistente de data em `engineering_params` para estabilizar o gate global do CI.
> Próximo: **H2.5.2 — scheduler/beat, healthcheck operacional e observabilidade/retry mais fino**.

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
4. O H2.3 é um assistente de calibração: ele sugere novos índices, mas a aplicação continua exigindo ação humana autorizada.

---

## 6. Como rodar / testar

```bash
python -m tests.validate_feixe_completo          # gate do feixe (±10%)
python -m tests.validate_permutador_completo     # gate BEU+BEM (±10% + geometria)
cd backend && python manage.py test apps         # suíte Django (django-tenants)
```

Arquitetura, decisões e seeds: ver `CLAUDE.md`, `pricing_engine/` e `docs/RT_CRITERIOS_ASME_V.md`.
