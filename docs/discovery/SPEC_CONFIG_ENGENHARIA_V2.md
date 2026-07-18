# Spec (rascunho) — Config de Engenharia V2: parâmetros configuráveis + aprovação + export de template

> Origem: conversa com o Rom (2026-07-18). Ideia: os valores de engenharia que hoje "dependem
> do Wellington" devem ser **configuráveis num painel**, com **dupla validação** (um engenheiro
> lança, outro aprova — reusando o motor de aprovação da RBAC V2) e um **export/import de template**
> pra o domínio-expert configurar e exportar, em vez de nos pedir pra hard-codar.
>
> **Status: RASCUNHO pra revisão.** Nada implementado. Escopo = V2.1.
>
> **Rev. 2 (2026-07-18):** incorporado review técnico (fable) conferido contra o código real.
> Principais correções: §5 (o contrato do motor MUDA — não é "injeta como hoje"), §3 (CALIB e
> FOLGA rebaixados), Bloco B (é generalização + model de proposta + aplicação on-approve, não
> "reuso"), Bloco C (confidencialidade comercial + schema_version), faseamento (F2↔F3 invertidos).

## 1. Princípio

Hoje, quando um valor de custeio não tem default validado, ele fica hard-coded no `pricing_engine`
e "espera o Wellington". Isso acopla o roadmap a uma pessoa. O mesmo padrão que resolvemos no RBAC
(a dúvida "orçamentista converte OF?" virou *capability configurável*, não um palpite nosso) se
aplica aqui: **tornar o valor um dado configurável por tenant + dar ao domínio-expert as ferramentas
pra configurar, validar e versionar** (aprovação + export). O "default" deixa de ser um número nosso
e passa a ser *"comece do template do Wellington"*.

## 2. O que JÁ existe (não reinventar)

| Peça | Onde | Papel |
|---|---|---|
| `Rate` (R$/HH, R$/HM, temporal) | `engineering_params.models` | custo→R$ editável por operação×máquina |
| `ProcessParameter` (física→horas) | `engineering_params.models` | editável; `valor=None` = pendente |
| `TenantParamConfig` (singleton) | `engineering_params.models` | knobs da Config Eng. v1: `fator_correcao_mo`, `drill_method_threshold_holes`, `tema_compat_mode`, `baffle_cut_default_pct`, `tube_standard_lengths_mm`, `u_bend_min_radius_factor` |
| `RateSuggestion` (status `pending/accepted/dismissed`, delta, confiança) | `engineering_params.models:200` | fluxo sugestão→**aceite de 1 ator** (não dupla validação — não há SoD). Meio caminho do padrão, não pronto. |
| `LigaMetalurgica` (seed_ligas) | `materials` + fatores em `tema_templates.services:20` | fatores de liga ainda vivem **hard-coded** em `LIGA_FATOR`/`CLASSE_DENSIDADE`/`PRECO_FATOR`; a tabela do tenant é consultada com **fallback silencioso nas constantes** (`services.py:42`). Padrão a NÃO repetir. |
| `ApprovalWorkflow.action_type` | `access.models` | motor de aprovação genérico (RBAC V2 M3/M4) — hoje só `of.convert`, **feito pra extensão** |

## 3. O que ainda está HARD-CODED no motor (candidatos a knob)

Do `pricing_engine` (lib pura). São **calibrações/proxies**, não normas físicas. ⚠️ Nenhum deles é
injetável hoje — são **constantes de módulo** lidas internamente (ver §5). Candidatos, por prioridade:

- **BONS** — `PERDA_POR_FAMILIA` — scrap por família (`beu_geometry.py:24`). ⚠️ Efeito **não-uniforme**:
  em `permutador_quote.py:255` só espelho/perfurado/disco usam `perda_familia()`; as demais famílias
  usam perda **auto-calibrada** (`bruto_seed/liq_seed`). O knob tem de ser um *override* que **não
  substitui** a auto-calibração na referência — senão quebra o gate 0,0%.
- **BONS** — frações de **setup** por operação (`_SETUP_FRAC`, `permutador_quote.py:72`) — defaults fixos.
  ⚠️ Coexiste com `ComponentOperation.setup_fixo` no banco (scope `parts`, `adapter.py:251`): **dois
  conceitos de setup**. Nomear distinto na UI, senão o tenant edita um achando ser o outro.
- **MÉDIOS** — defaults de **pressão→espessura** (ASME) — os *defaults*, não as fórmulas.
- **REBAIXADO** — `FOLGA_POR_CABECOTE` (`permutador_layout.py:23`): hoje só gera **aviso**, não custeia
  nem bloqueia (`permutador_layout.py:45`). Mispricing zero → valor de knob baixo. Despriorizar.
- **FORA** — ~~`CALIB` (tampo 2:1 = 4/π)~~: é constante de **fit** nossa, calibrada a 1 ponto do
  gabarito (`beu_geometry.py:41`), não decisão de engenharia do Wellington. Expor = quebrar a
  reconciliação 0,0% sem ganho, e vira dívida de migração no Bloco C quando o tampo for modelado direito.
- **FORA (não expor)** — `_param_da_op` (`permutador_quote.py:85`): casa por **keyword no label do seed**
  ("RAIO X", "HIDROST"…). Renomear uma operação re-classifica o driver silenciosamente. Estrutural demais.

**NÃO viram knob** (são norma/fórmula): ASME VIII (UG-27/32, Ap.2), geometria TEMA, densidades de
norma. Só os *inputs/defaults* deles são configuráveis.

## 4. Design proposto (3 blocos)

### Bloco A — Parâmetros como dado configurável
Levar os itens da §3 pro `TenantParamConfig` (ou tabelas dedicadas quando houver dimensão, ex.:
folga por cabeçote, scrap por família). Cada knob com: **default validado**, **unidade**, **faixa
segura (min/max)** e **texto de ajuda**. UI: estende a página de Config de Engenharia.

### Bloco B — Dupla validação via o motor de aprovação (⚠️ generalização, não "reuso")
Conceitualmente casa com a RBAC V2, mas no código o motor de aprovação é **todo acoplado a
`Quotation`** — isto é uma refatoração média, não plug-and-play. O que falta de fato:

1. **Schema:** `ApprovalCase.quotation` é FK **NOT NULL** para `quotations.Quotation`
   (`backend/apps/audit/models.py:116`). `param.change` não tem cotação. → model novo
   **`ParamChangeProposal`** (payload: model/campo, `valor_antigo`, `valor_novo`, `valid_from`
   proposto), com o case apontando pra ele (target genérico).
2. **Runtime assume cotação:** `open_case/approve_task/reject_task/active_case` recebem `quotation`;
   staleness = `snapshot_hash` vs `latest_snapshot_for(quotation)`; inbox faz `select_related("quotation")`;
   e-mail usa `case.quotation.number/title` (`backend/apps/audit/approvals.py:55,101,273,361`). Tudo
   quebra sem cotação. Pra param, staleness = "o valor vigente mudou desde a proposta" — semântica nova.
3. **Seletor de workflow é singleton implícito:** `_workflow_and_stages()`/`seed_workflow()` retornam
   O workflow (`approvals.py:29`); `action_type` é `unique` com choice única (`access/models.py:57`).
   Multi-action exige refatorar o seletor e o builder do M3.
4. **Falta o principal — aplicação on-approve:** hoje completar um case só muda status; a conversão
   acontece noutro lugar checando o gate. Pra `param.change`, alguém precisa **aplicar a mudança
   atomicamente** (service + trilha) quando o case completa. **Isso não existe em lugar nenhum.**
5. **Estágio builtin CREA** é satisfeito via `TechnicalApproval` da cotação (`approvals.py:143`) —
   workflow de param nasce sem builtin.
6. **SoD degenera com 1 engenheiro:** o escape auditado (`approvals.py:209`) faz a dupla validação
   virar auto-aprovação num tenant com um único qualificado. Aceitável, mas declarar na spec.

**Ponto forte a explorar:** `Rate`/`ProcessParameter` já são versionados por vigência → a "proposta"
pode ser uma linha futura que só ganha `valid_from` na aprovação. Já `TenantParamConfig` é **singleton
pk=1 SEM versionamento** (`engineering_params/models.py:185`) — precisa de staging (ou virar
versionado) **antes** de receber knobs sensíveis.

- **Granularidade (decisão de produto):** não gatear *toda* edição. Recomendação: **por lote** (1
  proposta de mudança = 1 case; qualquer item sensível no lote → lote inteiro gateado) — ver §7.
- Generaliza o padrão `pending→applied` do `RateSuggestion`, mas **acrescentando SoD** (que ele não tem).

### Bloco C — Export / Import de template
- Botão **"Exportar template"** na página de config: serializa a config de engenharia do tenant
  (knobs + process params) num **JSON versionado** com `schema_version` + versão do motor + registry
  de knobs conhecidos. Import **rejeita/avisa** chave desconhecida — nunca aplica silenciosamente.
- **"Importar template"**: aplica um template a um tenant (ou semeia um tenant novo), **sempre** pela
  aprovação (Bloco B) e com **diff-preview** (reusa o padrão de diff do M6). Import cria **novas
  vigências** (nunca muta linhas).
- ⚠️ **Confidencialidade comercial (não estava na spec):** `MaterialPrice` é cifrado no banco por
  decisão de produto. Exportar rates/preços tira-os da fronteira de cripto e vira arquivo que circula;
  e "template compartilhável entre tenants" = **estrutura de custo da ENGEMATEX semeando concorrentes**.
  → template em **duas camadas**: *física/knobs* (compartilhável) vs *comercial* (rates/preços — **nunca
  sai por default**; cross-tenant só com acordo formal com o design partner).
- ⚠️ **Migração de schema:** quando o motor **remove** um knob (ex.: CALIB modelado direito) ou muda a
  **semântica** (caso real do projeto: baffle cut % de corte vs % restante — mesmo número, sentido
  diferente entre versões), o import de template antigo precisa de regra explícita (ignorar+avisar).
- ⚠️ **Invalidação de calibração:** o `fator_correcao_mo` foi back-solved contra os knobs **antigos**;
  importar template que os altera invalida a calibração → exigir re-back-solve ou aviso forte.
- Fecha o loop: **Wellington configura → valida rodando cotações reais → exporta o template** que
  vira a base ("golden config"), em vez de nos pedir números. Casa com a filosofia de *snapshot/
  template* do produto (cotação=snapshot, proposta=template, TEMA=data sheet).

## 5. Guard-rails / riscos

- **O contrato do motor MUDA (correção da rev.1):** ~~"o adapter injeta como hoje — mesmo contrato
  `TenantCostChain`"~~ está **errado**. `TenantCostChain` (`pricing_engine/rates.py:24`) só carrega
  `rate_hh/hm`, `material_price`, `process_params`, `fator_correcao_mo`, `fator_preco`, `impostos_pct`.
  Os knobs da §3 são **constantes de módulo** sem kwarg de injeção. Bloco A exige **estender o contrato
  público do motor** (campos novos na chain ou kwargs em `quote_completo`/`check_layout`/geometria) —
  mantém a lib pura, mas é trabalho de motor + gates, não só UI+model.
- **Default ainda é necessário** pra tenant novo — mas com import, o default vira "template do
  Wellington", não um número nosso.
- **Mispricing silencioso já existe estruturalmente:** `build_cost_chain` tem `except Exception: pass`
  (`adapter.py:78,100,127`) — se a leitura de um knob falhar, a cotação sai com defaults **sem avisar**.
  Knobs novos herdam o risco. Falha de leitura de knob sensível deveria ser **visível**, não engolida.
  Além disso: faixa min/max + aviso fora da faixa + marcar `is_dangerous` (→ exige aprovação).
- **Fórmulas não viram knob** — só inputs/defaults.
- **Auditoria**: toda mudança de parâmetro logada com diff (já temos o padrão de diff do M6;
  `param_change`/`rate_change` já existem como action em `audit/models.py:202` e `engineering_params/services.py:90`).
- **Motor puro**: `pricing_engine` continua lib pura; o adapter injeta os valores configuráveis via
  o contrato **estendido** (ver primeiro item).

## 6. Escopo & faseamento (⚠️ F2↔F3 invertidos vs rascunho — aprovação ANTES de import)

- **F1 — Parâmetros como dado (Bloco A)**: estende o contrato do motor + lift das constantes + UI, já
  com guard-rails mínimos (min/max em modo *warn* + `AccessLog`). Entrega valor sozinho (destrava o
  Wellington na maioria dos casos: ele configura). ⚠️ Pré-condição: corrigir `_recompute_complete`
  (§7 riscos) antes de expor knobs de scope `complete`.
- **F2 — Aprovação de parâmetros (Bloco B lite)**: aprovação **por lote** dos knobs sensíveis
  generalizando o padrão `RateSuggestion` (proposal `pending→applied` + SoD simples), **sem** ainda
  generalizar o `ApprovalCase`. A generalização plena do motor (multi-action, inbox) fica pra quando
  houver demanda de multi-estágio.
- **F3 — Export/Import template (Bloco C)**: golden config versionável, **já nascendo gateada pela
  aprovação (F2)** e com `schema_version` + camada comercial separada.

**Racional da inversão:** import sem aprovação é a forma mais eficiente de **errar preço em massa**
(dezenas de valores de uma vez, sem segundo olhar); e o valor do C ("golden config") só existe
*depois* que o Wellington configurou com F1 — não há corrida. Se mantiverem C antes de B: no mínimo
diff-preview + confirmação forte no import.

## 7. Decisões abertas (pra Rom/Wellington) — com recomendação

1. **Granularidade da aprovação** → **por LOTE.** 1 proposta de mudança = 1 case (é como o engenheiro
   recalibra: vários valores juntos; evita spam de inbox). Qualquer item sensível no lote → lote inteiro gateado.
2. **Quais são "sensíveis"** → **regra, não lista:** knob que entra no **cálculo** = sensível
   (`fator_correcao_mo`, rates, preços, scrap, setup, fatores de liga, markup, impostos — e
   `drill_method_threshold_holes`, que muda horas!). Knob que só pré-preenche formulário ou gera aviso
   = livre (`baffle_cut_default_pct`, `tube_standard_lengths_mm`, `tema_compat_mode`,
   `u_bend_min_radius_factor`, folgas de layout).
3. **Template por-tenant ou compartilhável** → **por-tenant primeiro.** Artefato cross-tenant só numa
   v2, **sem a camada comercial** (rates/preços de fora por default) e com acordo formal com a ENGEMATEX.
4. **Faixas min/max** → **não esperar o Wellington.** Lançar com faixa provisória (±50% do default
   validado) em modo *warn* (não block); apertar depois com ele e com o `delta_pct` empírico do
   `RateSuggestion`. O gargalo dele são os *valores*, não os limites.

## 8. Riscos vistos no código (fora do escopo da spec original)

- **Bug latente — `_recompute_complete` sem params** (`adapter.py:289`): chama `estimate_complete(desig)`
  **sem** `dims_override`/`params`/metalurgia, enquanto `tema_templates/views.py:69` passa tudo.
  Recompute de cotação `scope=complete` **reverte pra geometria de referência**. Pré-condição do Bloco A.
- **`except Exception: pass` no adapter** (`adapter.py:78,100,127`) — ver §5 (mispricing silencioso já existe).
- **`_param_da_op` casa por keyword no label do seed** (`permutador_quote.py:85`) — renomear operação
  re-classifica o driver silenciosamente. Não expor; se um dia expor, versionar junto do seed.
- **Dois conceitos de setup** coexistem (`_SETUP_FRAC` scope complete vs `ComponentOperation.setup_fixo`
  scope parts) — unificar ou nomear distinto na UI.
- **`TenantParamConfig.get_solo()` singleton sem histórico** — cada edição perde o valor anterior (fora
  do AccessLog). Considerar vigência (igual a `Rate`) antes de inflar com knobs sensíveis — de quebra
  resolve o staging do Bloco B.
- **CI não cobre configs de tenant:** os gates (`tests.validate_permutador_completo`) rodam a lib pura
  com defaults de módulo. Um template que altera knob calibrado nunca é exercitado → adicionar gate que
  rode o **golden template pelo caminho completo do adapter**.
