# Sprint S2 — Nível 0: o custo real da hora dentro do produto

**Contrato.** Gate Legatus: SEARCH → PLAN → RED → GREEN → VERIFY → REVIEW → EVIDENCE.

## Por quê

O motor hoje bate 0,0% contra o orçamento fechado da ENGEMATEX. Mas pelo próprio
Wellington (áudios de 2026-07-16), o preço dela é **benchmark não aferido** e *"a parte
de mão de obra não vai estar ok"*. Então 0,0% mede **fidelidade ao preço que o Mané
faria** — não prova que o preço cobre a operação.

São duas réguas. A de fidelidade já existe. Esta sprint constrói a **régua de verdade**:

```
custo da capacidade fornecida (R$/mês)  ÷  capacidade prática (h/mês)  =  custo/hora real
```

É a metade que falta do TDABC: o `ProcessParameter` já é a equação de tempo
(física → horas); falta a **taxa de custo da capacidade**.

## SEARCH — o que o mapa do código mostrou

**Greenfield confirmado.** Não existe nada de custo fixo, overhead, rateio, capacidade
ou horas disponíveis em `backend/apps` nem no `pricing_engine`. O único `custo_fixo` do
repo (`pricing_engine/wbs.py:47`) é custo fixo **por operação** (teste, transporte), não
overhead de empresa.

**O padrão de vigência a seguir já existe** e é consistente em `Rate` e
`ProcessParameter` (`apps/engineering_params/models.py`): `valid_from` + `valid_until`
nullable, resolvidos por um manager `.vigente(on_date=None)` que filtra
`valid_from <= data` e (`valid_until` nulo ou `>= data`), desempatando pelo `valid_from`
mais recente. **Sigo este padrão**, com manager — não invento outro.

**Dívida pré-existente anotada (não corrijo aqui):** `MaterialPrice` tem vigência
modelada mas **sem manager**; a mesma resolução está escrita 3 vezes
(`materials/views.py:33`, `quotations/adapter.py:88`, `cost_discovery/services.py:34`)
e com divergência — só a primeira desempata por `created_at`. Registrado como **S2.3**.

**Assimetria anotada:** `fator_correcao_mo` é global do tenant (`TenantParamConfig`),
mas `fator_preco` e `impostos_pct` vivem **por cotação** (`Quotation`). O custo/hora é
naturalmente global — fica coerente com o primeiro, não com os outros dois.

**Não há precedente de wizard multi-etapa no repo.** O `cost_discovery` se chama wizard
mas são dois formulários de página única. Portanto: **nada de wizard**. Uma tela só,
como o formulário que já está no ar em form.qtec.me e que o cliente já sabe preencher.

## PLAN — escopo desta fatia

| # | Entrega |
|---|---|
| 1 | `CostStructure` versionada por vigência, com manager `.vigente()` seguindo o padrão de `Rate` |
| 2 | `compute()` — custo da capacidade ÷ capacidade prática, no servidor, com diagnóstico |
| 3 | Comando que importa as respostas do `form.qtec.me` (JSON) como vigência nova |
| 4 | Testes cobrindo a conta, a vigência e a importação |

**Fora de escopo, explicitamente:**
- **S2.1** — a tela dentro do produto (o formulário público já coleta; a tela interna é
  outra fatia, e nasce com a pele do Vitali quando aquela sprint chegar).
- **S2.2** — ligar o custo/hora ao `TenantCostChain`. É a decisão mais delicada do
  produto: o custo/hora real **substitui** o `rate_hh` do catálogo ou vira um piso que
  alerta? Isso reprecifica tudo e precisa do Wellington. Não faço por conta.
- **S2.3** — extrair `MaterialPriceManager.vigente()` e matar as 3 duplicatas.

## A decisão que NÃO tomo sozinho

Ligar o custo/hora aferido no motor muda todos os preços do tenant. As opções são
substituir o rate, virar piso com alerta, ou ficar só como diagnóstico comparativo.
Isso é decisão de negócio do dono da margem — entra na fila do Wellington como
**w-014**, não em código.

---

## GREEN — o que ficou de pé

`apps/cost_structure`, com **29 testes verdes**:

- **`CostStructure`** — custo aberto por bloco (direto, indireto, galpão, máquinas,
  estrutura já rateada) e capacidade (pessoas produtivas, jornada, semanas, fator
  prático, extras). A abertura por bloco não é organização: um total único esconde
  justamente o custo indireto, que é onde a margem some sem deixar rastro.
- **`CostStructureManager.vigente(on_date)`** — cópia fiel do padrão de `RateManager`.
- **`abrir_vigencia()`** — grava a nova e fecha a anterior **na véspera**. Nunca
  sobrescreve. Recusa duas vigências no mesmo dia em vez de escolher uma calada.
- **`da_resposta_do_formulario()`** — traduz o JSON do form.qtec.me, somando as listas
  paralelas (o usuário acrescenta linhas pelo "+", então não há índice fixo).
- **`importar_estrutura_custo`** — comando com `--simular`, que imprime a conta e o
  diagnóstico antes de gravar.

### O diagnóstico

Três estados, e o limiar de 15% existe para a resposta ser acionável:

| Estado | Quando |
|---|---|
| **prejuízo** | cobra abaixo do custo — vender mais volume aumenta o prejuízo |
| **no limite** | folga < 15% — cobre o custo, mas um atraso na obra já vira prejuízo |
| **saudável** | folga ≥ 15% — sobra antes de impostos e lucro |

### O que o teste de importação mostra

Com os números do exemplo (10 pessoas produtivas, R$ 112.000/mês, 1.000 h vendáveis):
custo real **R$ 112/h** contra **R$ 80/h** praticados → **prejuízo em toda hora vendida**.
É exatamente o diagnóstico que a ENGEMATEX nunca teve.

## A decisão que virou pergunta, não código

Ligar o custo/hora no `TenantCostChain` reprecifica todas as cotações do tenant de uma
vez. Substituir o rate, virar piso com alerta, ou ficar só como comparação é decisão do
dono da margem. Entrou na fila do Wellington como **w-014** — o número fica calculado e
inerte até ele responder.

## VERIFY

- `apps.cost_structure`: **29 OK**
- Gates do motor: feixe −2,9% · permutador BEU/BEM 0,00% — OK
- `makemigrations --check`: sem pendência

## Backlog

- **S2.1** tela dentro do produto (nasce com a pele do Vitali)
- **S2.2** ligar o custo/hora ao motor — **bloqueado em w-014**
- **S2.3** extrair `MaterialPriceManager.vigente()` e matar as 3 duplicatas divergentes
