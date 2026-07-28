# PROJECT_MAP — SmartQuotation (índice central anti-desperdício de token)

> Propósito: referenciar este mapa leve em vez de varrer arquivos pesados.
> NUNCA reparsear os .xlsx (788K–1.4M) — toda informação já foi extraída para seeds JSON.

## ⛔ NÃO LER (pesados, já extraídos)
- `~/dev/uploads/Planilha Padrão - Feixe Tubular - Rev.0.xlsx` (788K) → extraída
- `~/dev/uploads/Planilha Padrão - Permutador 'BEU'/'BEM' - Rev.0.xlsx` (1.4M cada) → blocos confirmados
- Parser (se precisar re-extrair): venv `/tmp/xlsxenv/bin/python3` + openpyxl; nomes têm acento → achar via glob.

## ✅ FONTE DE VERDADE (ler estes — leves)
| Arquivo | O quê |
|---|---|
| `pricing_engine/seeds/materials_pe.json` (84K) | 423 materiais + densidade |
| `pricing_engine/seeds/dim_standards.json` (4K) | OD polegada→mm, BWG→mm |
| `pricing_engine/seeds/feixe_operacoes_formulas.json` (20K) | 67 operações + fórmulas verbatim |
| `pricing_engine/seeds/feixe_referencial.json` (8K) | custo calculado por operação (referencial) |
| `~/.gstack/projects/tropeks-SmartQuotation/rcosta00-main-costing-engine-spec.md` | SPEC do motor (entidades, fórmulas, ProcessParameters) |
| `~/.gstack/projects/.../rcosta00-main-domain-feixe-planilha-analise.md` | análise bruta da planilha |
| `~/.gstack/projects/.../rcosta00-main-design-*.md` | design doc aprovado (Approach C) |
| `~/.gstack/projects/.../rcosta00-main-eng-review-plan-*.md` | plano de arquitetura M1 |

## 🔧 GRAFO DE MÓDULOS (pricing_engine/ — Python puro)
```
dimensions.py ──┐                         (OD/BWG → mm, geometria → peso)
materials.py ───┤                         (catálogo 423, densidade + fallback)
process_params.py ┤                       (avanços/taxas editáveis; regra radial≤600<CNC)
rates.py ───────┤                         (TenantCostChain: HH/HM, R$/kgf×forma, fatores)
                ▼
components.py ──► (CompSpec → peso por geometria; feixe + BEU/BEM)
operations.py ──► (64 operações no registry; gates de regressão)
                ▼
wbs.py ─────────► Cotacao→Item→{MateriaPrima,Operacao,Ensaio}  (EAP + roll-up + render)
                ▼
tests/validate_feixe_completo.py ───────► feixe 136 tubos: gate ±10%
tests/validate_permutador_completo.py ──► BEU+BEM: gate ±10% + geometria
```

## 📊 ESTADO DO MOTOR (validação contra caso real Petrobras RPBC)
- Referencial: custo R$ 35.353 · venda c/imposto R$ 44.192 (gate 10%/5min)
- ✅ Feixe tubular: custo calculado R$ 34.344,93 vs referencial R$ 35.353,00 (delta -2,9%)
- ✅ Operações: 64 no registry, 0 erros no gate atual
- ✅ Permutador completo: BEU R$ 128.162,69 vs R$ 128.160,00; BEM R$ 119.297,24 vs R$ 119.295,00 (delta 0,00%)
- ✅ Geometria BEU/BEM: 18 itens grandes, 0 divergências >15%
- ✅ CNC confirmado: furar espelho 97,56 mm/min; furar chicanas 83,34 mm/min; alargar espelho não existe como etapa CNC

## 🏭 ESTADO DO PRODUTO DJANGO
- ✅ H1 técnico: cotação feixe + BEU/BEM, EAP persistida, proposta PDF/DOCX, histórico e API DRF.
- ✅ H1 auditável: aprovação técnica CREA, `CalculationSnapshot` com hash e `AccessLog`.
- ✅ H2.1: cotação aprovada → Ordem de Fabricação com BOM/roteiro em deep-copy.
- ✅ H2.2: apontamento de produção e fechamento gerando `ActualRate` por operação.
- ✅ H2.3: `RateSuggestion` a partir de `ActualRate` elegível; aplicar/descartar com RBAC.
- ✅ H2.4: ITP básico gerado da OF/roteiro, aceite por item com responsável/data e `AccessLog`.
- ✅ H2.5 foundation: app tenant-scoped `apps.integrations.protheus` mergeado (`#52`) com config por tenant, bindings/runs/attempts de sync, snapshots remotos, fake client e testes de OF/BOM/materiais/fornecedores.
- ✅ H2.5.2: scheduler global/beat único, healthcheck operacional admin-only, retry tipado transitório/permanente, reenfileiramento seguro no admin e testes verdes em `apps.integrations.protheus` + `apps.production`.
- ✅ H2.6: app tenant-scoped `apps.integrations.omie` com emissão assistida de NF-e via Omie a partir da OF concluída, config por tenant, documento fiscal mínimo, tasks assíncronas, admin operacional e healthcheck.
- ✅ H2.7a: app tenant-scoped `apps.integrations.sap_b1` registrado em settings, healthcheck admin-only e action manual de export da OF no admin de produção.
- ✅ H2.7b: `_schedule_sap_b1_export` wired em `production.services.transition()` em STATUS_LIBERADA; enfileira sales_order + BOM via `maybe_enqueue_*` com dispatch `on_commit`.
- ✅ H2.x audit (Spock+Ewoks, 2026-06-26, PR #58 commits 1dd1972+15efa48): 8 bugs corrigidos — SAP B1 idempotency PROCESSING guard, Protheus remote_code `or`-fallback (CRITICAL), RBAC appoint view, entry_date str→date parse, hours_hh/hm >24 validation, delta clamp, reset_sync_run select_for_update.
- 🧭 H2.x Cost & Pricing Intelligence (discovery Wellington, 2026-07-16): próximo corte deve preservar CPQ atual e adicionar provenance `referencial` vs `validado por custo`, auditar back-solve como benchmark-contaminável, decompor horas orçadas vs reais, e tratar custo fixo/overhead como linha separada (`overhead_*`/`custo_estrutura_*`; NÃO reutilizar `wbs.OperacaoExecutada.custo_fixo`, que significa serviço de valor fixo).
- ✅ Testes locais: gates do motor OK; 334 testes Django OK (apps.*).

## 🧭 DECISÕES TRAVADAS (não re-litigar)
Approach C (plataforma completa) · clone fundação Vitali (django-tenants) · HTMX+session auth ·
design system G·Refined Bauhaus + Command Center · cálculo=modo importado mas PESO computado ·
Rate dia-1 só camada tenant · ProcessParameter separado de Rate · EAP/WBS como espinha dorsal.

## ⚙️ DIRETRIZ DE TRABALHO (Romulo)
gstack em todas etapas · autonomia (perguntas só essenciais) · /cso a cada milestone · Boil the Ocean.

## ▶️ PRÓXIMO PASSO
SQ-COST-1 — spec + auditoria de contaminação do back-solve antes de implementar modelos. H2.x integrações Protheus/Omie/SAP B1 seguem completos/auditados; o novo corte é Cost & Pricing Intelligence.
