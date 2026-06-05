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
| `pricing_engine/seeds/feixe_ground_truth.json` (8K) | custo calculado por operação (gabarito) |
| `~/.gstack/projects/tropeks-SmartQuotation/rcosta00-main-costing-engine-spec.md` | SPEC do motor (entidades, fórmulas, ProcessParameters) |
| `~/.gstack/projects/.../rcosta00-main-domain-feixe-planilha-analise.md` | análise bruta da planilha |
| `~/.gstack/projects/.../rcosta00-main-design-*.md` | design doc aprovado (Approach C) |
| `~/.gstack/projects/.../rcosta00-main-eng-review-plan-*.md` | plano de arquitetura M1 |

## 🔧 GRAFO DE MÓDULOS (pricing_engine/ — Python puro, 706 linhas)
```
dimensions.py ──┐                         (OD/BWG → mm, geometria → peso)
materials.py ───┤                         (catálogo 423, densidade + fallback)
process_params.py ┤                       (avanços/taxas editáveis; regra radial≤600<CNC)
rates.py ───────┤                         (TenantCostChain: HH/HM, R$/kgf×forma, fatores)
                ▼
components.py ──► (CompSpec → peso por geometria; 11/17 ok, 2 PENDENTES)
operations.py ──► (fórmulas de horas; drivers validados 4/4)
                ▼
wbs.py ─────────► Cotacao→Item→{MateriaPrima,Operacao,Ensaio}  (EAP + roll-up + render)
                ▼
tests/validate_feixe.py ──► harness: feixe 136 tubos vs gabarito
```

## 📊 ESTADO DO MOTOR (validação contra caso real Petrobras RPBC)
- Gabarito: custo R$ 35.353 · venda c/imposto R$ 44.192 (gate 10%/5min)
- ✅ Operações-driver: 4/4 exatas (furar 660, mandrilar 720, furar chicana 1650, soldar 630)
- ✅ Material: 11/17 componentes, subtotal R$ 13.266 (~87% de ~15.319)
- 🔨 FALTA: ~60 ops restantes + 6 itens menores + impostos/eng/ferramentas p/ fechar total
- ⏳ PENDENTE DOMÍNIO (Wellington): fração de corte da chicana; comprimento do espaçador BWG; convenção de códigos (item/MP/op); valores CNC

## 🧭 DECISÕES TRAVADAS (não re-litigar)
Approach C (plataforma completa) · clone fundação Vitali (django-tenants) · HTMX+session auth ·
design system G·Refined Bauhaus + Command Center · cálculo=modo importado mas PESO computado ·
Rate dia-1 só camada tenant · ProcessParameter separado de Rate · EAP/WBS como espinha dorsal.

## ⚙️ DIRETRIZ DE TRABALHO (Romulo)
gstack em todas etapas · autonomia (perguntas só essenciais) · /cso a cada milestone · Boil the Ocean.

## ▶️ PRÓXIMO PASSO
Completar as ~60 operações restantes (mesmo padrão dos 4 validados, dados em feixe_operacoes_formulas.json)
+ itens menores + impostos → fechar R$ 35.353 → rodar /cso → milestone do pricing_engine.
