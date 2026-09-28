# Ordem 008 — markup e impostos do tenant no permutador completo

## O problema, em uma frase

O `fator_preco` (markup comercial) e o `impostos_pct` (ICMS, por dentro) que o motor usa
para transformar o CUSTO de um permutador completo (BEU, BEM...) em PREÇO DE VENDA eram
**valores fixos no código** (`pricing_engine.permutador_quote.quote_completo(...,
fator_preco=1.25, impostos_pct=9.0)`), vindos direto da planilha ENGEMATEX
(`scripts/extract_permutador.py`). Nenhum tenant conseguia mudar esse número sem editar
código e reimplantar — a única forma de negociar outra margem era... não existia.

## O que muda

`TenantParamConfig` (singleton, `apps/engineering_params/models.py`) ganha dois campos
novos:

| Campo | Tipo | Default | Equivale a |
|---|---|---|---|
| `fator_preco_completo` | `DecimalField(8,5)` | `1.25000` | o `fc=1.25` hardcoded hoje |
| `impostos_pct_completo` | `DecimalField(6,3)` | `9.000` | o `icms=9.0` hardcoded hoje |

**O default é idêntico ao valor hardcoded de hoje — no dia 1, nenhum preço muda.** Só muda
quem, depois do deploy, editar esses dois campos (admin) para uma margem diferente.

### Escopo: só o PERMUTADOR COMPLETO, não o feixe

O FEIXE (cotação de feixe tubular isolado) continua exatamente como está: markup/imposto
**por cotação**, em `Quotation.fator_preco`/`.impostos_pct` (default `1,01377`/`23,303`,
imposto **por fora**) — não é tocado por esta ordem. São dois markups genuinamente
diferentes, calibrados para escopos diferentes:

- Feixe: `1,01377 × (1 + 23,303%)` ≈ 1,25 no preço final — calibração por back-solve contra
  um job real, imposto **por fora**.
- Permutador completo: `custo × 1,25`, depois ICMS **por dentro** (`preco_sem =
  preco_com / (1 − 9%)`) — fiel à planilha ENGEMATEX, que documenta `icms_pct` como campo
  próprio.

As duas semânticas continuam como estão — unificá-las é decisão fiscal do Capitão, fora
do escopo desta ordem (ver `.maestro/orders/008-*.md`, decisão (b) do Diretor).

### O motor (`pricing_engine`) não muda

`quote_completo` já aceitava `fator_preco`/`impostos_pct` como parâmetros — só que **nada**
em `apps/tema_templates/services.py` passava outro valor além do default da função. A
correção é inteira do lado Django: `estimate_complete`/`estimate_from_inputs`
(`apps/tema_templates/services.py`) leem `TenantParamConfig.fator_preco_completo`/
`.impostos_pct_completo` e passam os dois EXPLICITAMENTE como kwargs de `quote_completo`.

**Por que não usar `TenantCostChain.fator_preco`/`.impostos_pct` (que já existem no
dataclass)?** Porque esses campos têm default NEUTRO (`1.0`/`0.0`) — se o motor passasse a
ler a cadeia de custos para esses dois campos, qualquer chamador que monte uma
`TenantCostChain()` "vazia" (sem setar os dois campos) zeraria o markup em silêncio, sem
erro nenhum. Passar os valores como kwargs explícitos, calculados a partir do
`TenantParamConfig` no ponto de chamada, evita essa armadilha por construção.

### Exemplo de efeito (custo 100.000)

| | Antes / default (1,25 / 9,0) | Tenant configurado p/ 1,30 / 12,0 |
|---|---|---|
| `preco_com_impostos` | 100.000 × 1,25 = **125.000,00** | 100.000 × 1,30 = **130.000,00** |
| `preco_sem_impostos` | 125.000 / (1 − 0,09) = **113.750,00**¹ | 130.000 / (1 − 0,12) = **114.400,00** |

¹ Contas: `gross_up_icms(pct) = 1 / (1 - pct/100)`; `preco_sem = preco_com / gross_up_icms(pct)`
⇒ `preco_com × (1 - pct/100)`. 125.000 × 0,91 = 113.750,00.

### Revisão (`revise_complete`) CONGELA o markup da cotação original

Decisão (c) do Diretor: revisar uma cotação de permutador completo recomputa com o
`fator_preco`/`impostos_pct` **da cotação original**, não com o vigente do tenant — por
paridade com `revise_feixe`, que já faz exatamente isso para o feixe. Se o tenant mudar de
`1,25/9,0` para `1,40/15,0` DEPOIS de uma cotação ter sido criada (e possivelmente enviada
ao cliente), revisar essa cotação continua usando `1,25/9,0` — a revisão não reprecifica
silenciosamente por baixo do pano.

Isso vale inclusive no caminho de fallback (`estimate_from_inputs` devolve `None` quando os
inputs salvos não validam mais o form) — `revise_complete` passa `fator_preco`/
`impostos_pct` da original também para o `quote_completo(desig)` de emergência, não só para
o caminho feliz.

#### Regra de PROVENIÊNCIA (rodada de conserto, a partir da revisão do Diretor)

**"O `fator_preco`/`impostos_pct` da cotação original" não é o mesmo que "o que está
gravado em `Quotation.fator_preco`/`.impostos_pct`."** Esses dois campos do MODEL têm
default `1,01377`/`23,303` — os valores do markup/imposto do FEIXE, não do permutador. Uma
`Quotation(scope="complete")` criada **fora** de `persist_complete` (admin "add", carga de
dados, migração — o mesmo caminho real exercitado por
`backend/apps/quotations/tests_memorial_robusto.py:113-166`) nasce com esse default sem
nunca ter passado pelo motor do permutador. Congelar esse valor numa revisão gravaria um
markup/ICMS ~19% errado no preço de venda, sem aviso nenhum — bloqueante encontrado na
revisão desta ordem.

**A fonte de verdade não é `orig.fator_preco`/`.impostos_pct` — é o `CalculationSnapshot`
mais recente da original** (`inputs.pricing.fator_preco`/`.impostos_pct`), porque é o que o
motor de fato **rodou** para chegar no preço que está na tela/proposta. `adapter.
_pricing_da_original(orig)` resolve nessa ordem:

1. Existe um `CalculationSnapshot`? Usa `snapshot.inputs["pricing"]` — congela o par que
   realmente precificou a original (o caso comum: toda cotação criada por
   `persist_complete`, ou seja, todo o fluxo normal do data sheet, tem snapshot).
2. Não existe snapshot (a original nunca passou pelo motor)? Usa o markup **vigente do
   tenant** (`tenant_pricing_completo()`) e registra `logger.warning` com o número/revisão
   da cotação — silenciosamente inventar uma proveniência que não existe seria pior do que
   assumir o vigente e deixar rastro no log.

Efeito prático: `orig.fator_preco`/`.impostos_pct` sozinhos deixaram de ser lidos por
`revise_complete` — quem quiser saber "com que markup uma cotação foi feita" deve olhar o
snapshot, não o campo solto na `Quotation` (o campo continua existindo e sendo gravado por
`persist_complete`, só não é mais a fonte de leitura da revisão).

### Preview/simulador (tela "Compor Trocador")

O preview HTMX de `/tema/compor/check/` e o data sheet (`/tema/permutador/`) chamam
`estimate_complete` sem passar `fator_preco`/`impostos_pct` — herdam automaticamente o
valor vigente do tenant, sem mudança de código na view/template (o template já exibia
`custo.fator_preco`, só o número mudou de fonte).

## Onde configurar

**Hoje só existe o admin do Django** (`/admin/engineering_params/tenantparamconfig/`) — não
existe, e esta ordem não cria, uma tela própria de "configuração comercial" (o mesmo é
verdade para `fator_correcao_mo`, `drill_method_threshold_holes` e os outros knobs
escalares de `TenantParamConfig`; só os knobs SENSÍVEIS `perda_por_familia`/`setup_frac`
têm tela dedicada com fluxo de aprovação em dois passos — Config de Engenharia V2/F1-F2 —
e este par de campos não entrou nesse fluxo porque é comercial, não físico/de engenharia).

Procedimento para o Capitão:

1. Acessar `https://<subdomínio-do-tenant>/admin/engineering_params/tenantparamconfig/`
   (usuário com acesso ao admin do Django).
2. Abrir a única linha (singleton — sempre `id=1`).
3. Editar `Fator preco completo` (ex.: `1.30` para markup de 30%) e/ou `Impostos pct
   completo` (ex.: `12` para 12% de ICMS por dentro).
4. Salvar. **Validação:** `fator_preco_completo` precisa ser `> 0`; `impostos_pct_completo`
   precisa estar em `[0, 100)` — o admin recusa a gravação com esses limites violados
   (`TenantParamConfig.clean()`, chamado pelo form do admin).
5. O efeito é IMEDIATO em qualquer estimativa/preview/nova cotação de permutador completo a
   partir da próxima requisição — não precisa reiniciar nada. Cotações JÁ SALVAS não mudam
   de preço; só a próxima criação/preview usa o valor novo. Revisões de cotações antigas
   continuam usando o markup que a cotação original tinha (ver seção acima).

## Golden `char_005.json` — sem diff

O golden (`backend/apps/quotations/golden/char_005.json`) fica **byte a byte idêntico**
depois desta ordem — confirmado rodando `tests_characterization_005` antes e depois. Isso é
esperado: o default de `TenantParamConfig.fator_preco_completo`/`.impostos_pct_completo`
(`1,25`/`9,0`) é literalmente o valor que já estava hardcoded na assinatura de
`quote_completo`, então nenhum cenário do golden (que roda contra um tenant novo, sem
reconfigurar o markup) muda de resultado.

Um ajuste colateral foi necessário no PRÓPRIO teste de caracterização
(`tests_characterization_005.py`): a fixture da cena (e) (`_fallback_seed_quotation`) cria
uma `Quotation` `scope='complete'` via ORM cru, sem passar por `persist_complete` — sem
setar `fator_preco`/`impostos_pct` explicitamente, ela caía no default do MODEL Django
(`1,01377`/`23,303`, os valores do FEIXE, não do permutador — um artefato da fixture, nunca
o que uma cotação `complete` real tem, porque `persist_complete` SEMPRE grava o par que o
motor devolveu). Antes desta ordem isso não importava: o fallback de `revise_complete`
(`quote_completo(desig)` sem argumentos) sempre usava os defaults da FUNÇÃO (1,25/9,0),
ignorando o que a original tinha. Depois desta ordem, `revise_complete` CONGELA o par da
original por decisão (c) — e se a fixture não representa um par realista, o congelamento
propaga o artefato. A correção foi dar à fixture o par realista que `persist_complete`
teria gravado (`fator_preco=1.25`, `impostos_pct=9.0`), não mudar o comportamento de
produção — o golden continua exatamente o mesmo depois do ajuste.

## Rollback

- **Código:** reverter os commits desta ordem é seguro a qualquer momento — a migração
  (`engineering_params/0008_tenantparamconfig_fator_preco_completo_and_more`) só ADICIONA
  dois campos com default; nenhum dado existente é reescrito, nenhuma FK, nenhuma
  constraint que outra migração dependa.
- **Migração:** reverter (`python manage.py migrate engineering_params 0007
  --schema=<tenant>`) é seguro sempre — os dois campos novos não são lidos por nenhum
  código fora desta ordem; removê-los não deixa nada pendurado.
- Se algum tenant já tiver reconfigurado `fator_preco_completo`/`.impostos_pct_completo`
  para um valor diferente do default antes de um rollback de código, a próxima estimativa
  volta a usar o hardcoded `1,25`/`9,0` da função — sem erro, mas silenciosamente diferente
  do que o tenant tinha configurado. Avise o tenant antes de reverter em produção se ele já
  tiver usado a configuração de verdade.

## Onde ver a prova

- `backend/apps/tema_templates/tests_ordem_008.py`:
  - `TenantParamConfigCamposOrdem008Tests` — default `1,25000`/`9,000`; `fator_preco_completo`
    tem que ser `> 0`; `impostos_pct_completo` tem que estar em `[0, 100)`.
  - `EstimateCompleteUsaMarkupDoTenantTests` — sem configuração, o preço da cadeia de custos
    do tenant é idêntico ao de antes desta ordem; tenant em `1,30/12` muda
    `preco_com_impostos`/`preco_sem_impostos` pela fórmula correta (ICMS por dentro); o
    preview HTMX (`/tema/compor/check/`) reflete o markup do tenant.
  - `ReviseCompleteCongelaMarkupTests` — o snapshot (`CalculationSnapshot.inputs.pricing`)
    grava o par do tenant no momento da criação (`"1.30000"`/`"12.000"`); revisar depois de
    o tenant mudar para `1,40/15` sai com o par ORIGINAL (`1,30/12`), não o vigente.
- `backend/apps/quotations/tests_ordem_008_provenance.py` (rodada de conserto):
  - `RevisaoSemProvenienciaUsaMarkupDoTenantTests` — uma `Quotation(scope='complete')` criada
    fora de `persist_complete` (sem `CalculationSnapshot`, mesmo caminho de
    `tests_memorial_robusto.py`) tem o default do MODEL (`1,01377`/`23,303`, os valores do
    FEIXE); revisá-la usa o markup VIGENTE do tenant (não esse default), com
    `logger.warning` registrando o número/revisão.
  - `RevisaoComProvenienciaCongelaOSnapshotTests` — cotação criada de verdade por
    `persist_complete` (com snapshot) continua congelando o par DO SNAPSHOT mesmo com o
    tenant mudando de política comercial depois — prova que a regra de proveniência não
    regride o comportamento já coberto por `ReviseCompleteCongelaMarkupTests`.
- `backend/apps/tema_templates/tests_ordem_008_savepoint.py` (rodada de conserto):
  `TenantCostChainSavepointTests`/`TenantPricingCompletoSavepointTests` — erro de banco REAL
  (`SELECT 1/0`, mesmo padrão de `tests_ordem_007_revise_feixe_savepoint.py`) dentro de
  `tenant_cost_chain()`/`tenant_pricing_completo()` não aborta a transação de quem chamou
  (savepoint) e dispara `logger.warning` (antes: nem savepoint, nem log).
- `backend/apps/quotations/tests_characterization_005.py` + golden `char_005.json` — sem
  diff (rodado antes e depois desta ordem, e de novo depois da rodada de conserto).
- Gates do motor intactos: `python -m tests.validate_feixe_completo`,
  `python -m tests.validate_permutador_completo` (`scripts/prova_motor.sh`).
