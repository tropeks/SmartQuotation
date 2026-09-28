# Ordem 006 — precisão de fator_preco/impostos_pct

## O problema, em uma frase

Ao salvar um permutador completo, o `fator_preco` (markup) e o `impostos_pct` (ICMS/PIS/
COFINS...) gravados na cotação eram **arredondados para 2 casas decimais antes de ir para o
banco**, mesmo os campos aceitando mais casas (5 e 3 respectivamente). Um markup calibrado
como 1,01377 virava 1,01 — perdido para sempre, não só na tela.

## O que muda

| Cenário | Campo | Antes (truncava em 2 casas) | Depois (casa do próprio campo) |
|---|---|---|---|
| Markup calibrado fino | `fator_preco` | 1,01377 → **1,01** (perde 0,37%) | 1,01377 → **1,01377** |
| Imposto fracionário | `impostos_pct` | 23,303 → **23,30** | 23,303 → **23,303** |
| BEU/BEM de referência | `fator_preco` | 1,25 → 1,25 (sem perda; já é redondo) | 1,25 → 1,25 (idêntico) |
| BEU/BEM de referência | `impostos_pct` | 9,0 → 9,0 (sem perda) | 9,0 → 9,0 (idêntico) |

**O preço da cotação (`preco_com_impostos`, `preco_sem_impostos`) NÃO muda em nenhum
cenário.** Hoje o motor do permutador completo (`quote_completo`) sempre calcula com
1,25/9,0 fixos — nenhum tenant tem markup próprio entrando nesse cálculo ainda (isso é a
ordem 008, fora deste escopo). Então, na prática, nenhuma cotação existente ou nova muda de
preço por causa desta ordem. A correção protege o dia em que um markup calibrado e não
redondo (como o próprio default do campo, 1,01377) passar a ser usado de verdade.

## Efeito no hash de assinatura técnica (`CalculationSnapshot.snapshot_hash`)

O `snapshot_hash` é calculado a partir da string do `fator_preco`/`impostos_pct` no momento
em que a cotação é salva. Como a REPRESENTAÇÃO em texto muda de formato (ex.: `"1.25"` vira
`"1.25000"`, `"9.0"` vira `"9.000"`), **toda cotação NOVA ou REVISADA a partir de agora tem
um hash diferente do que teria antes** — mesmo quando o valor numérico e o preço são
idênticos. Isso é o comportamento correto e esperado do hash: ele é uma assinatura textual
exata do que foi gravado, não uma comparação numérica "aproximadamente igual".

## Efeito sobre cotações existentes

**Nenhuma cotação já salva é regravada ou tem seu snapshot recalculado por esta ordem.**
O conserto está em `apps/quotations/adapter.py:persist_complete` (o único caminho que
persiste resultado do motor — INTENT v3 §Limites), que só roda quando:

- uma cotação de permutador completo é **criada** pela primeira vez (data sheet → "salvar");
- uma cotação existente é **revisada** (`revise_complete` chama `persist_complete` por
  baixo, sempre com um número/registro NOVO — a revisão nunca sobrescreve o original).

Cotações já emitidas, aprovadas ou enviadas ao cliente continuam com o `fator_preco`/
`impostos_pct`/`snapshot_hash` que tinham no momento em que foram salvas. Não há migração
de dados nesta ordem.

## Rollback

Reverter é reverter o commit `fix(quotations): fator_preco/impostos_pct quantizam pela
casa do campo` (troca `_q(...)` de volta para `_money2(...)` nas duas linhas de
`persist_complete`) e o commit que regenerou `backend/apps/quotations/golden/char_005.json`
junto. Não há coluna nova, migração de schema nem dado gravado que precise ser desfeito —
o golden é o único artefato "de estado" tocado, e ele só espelha o comportamento do código.

## Onde ver a prova

- `backend/apps/quotations/tests_precision_006.py` — caso sintético (1,01377/23,303,
  vermelho antes do fix) e caso BEU de referência (1,25/9,0 — preço idêntico, só a string
  do hash muda).
- `backend/apps/quotations/tests_characterization_005.py` + golden `char_005.json` —
  fotografia de ponta a ponta (HTTP → persistência → snapshot) dos 6 cenários (a–f);
  diff campo a campo do golden antes/depois desta ordem no anexo abaixo (18 caminhos, todos em `snapshot.inputs.pricing.{fator_preco,impostos_pct}`
  ou `snapshot_hash` — nenhum total, item, peso ou proposta mudou).

## Anexo — diff do golden `char_005.json` (antes -> depois)

```
$.a.snapshot.snapshot.inputs.pricing.fator_preco: '1.25' -> '1.25000'
$.a.snapshot.snapshot.inputs.pricing.impostos_pct: '9.0' -> '9.000'
$.a.snapshot.snapshot.snapshot_hash: '03643f50d7a8f2d9c0300272280fa1368df5eb66d583cfcf82c295a7ab9a5ace' -> '349003d3215653c3e14b343ee46c91bf077f00916a18d06aa302dd89e91b50e9'
$.b.snapshot.snapshot.inputs.pricing.fator_preco: '1.25' -> '1.25000'
$.b.snapshot.snapshot.inputs.pricing.impostos_pct: '9.0' -> '9.000'
$.b.snapshot.snapshot.snapshot_hash: '9dccc1b2a09a09560dd1598ae01c6a7e5231b9451baa81444429782fde3c5207' -> '78722b938c2d53a3655afe425829316720869a889ca8c490cb32e9d932937e24'
$.c.snapshot.snapshot.inputs.pricing.fator_preco: '1.25' -> '1.25000'
$.c.snapshot.snapshot.inputs.pricing.impostos_pct: '9.0' -> '9.000'
$.c.snapshot.snapshot.snapshot_hash: '308d5fa6b1c5a55f268b2f7efe36c7b09d20f4260ed79c592d569ae7ae079905' -> 'b047122b8a86c60cd470dc6cec3b94a902a51dcb46ff00007ed6ccdcee9d2b8a'
$.d.snapshot.snapshot.inputs.pricing.fator_preco: '1.25' -> '1.25000'
$.d.snapshot.snapshot.inputs.pricing.impostos_pct: '9.0' -> '9.000'
$.d.snapshot.snapshot.snapshot_hash: 'd067a51199486ac71d662849874e5b52de7cbb7c3996fb4bf7efee16a4456063' -> '7ce2164083bcb449ac087d65b5943f6c88ddf977f5d37cfcbe3fd32655590bc0'
$.e.snapshot.snapshot.inputs.pricing.fator_preco: '1.25' -> '1.25000'
$.e.snapshot.snapshot.inputs.pricing.impostos_pct: '9.0' -> '9.000'
$.e.snapshot.snapshot.snapshot_hash: '0833e09f8c38756e815160f5a685bdc71638f2c0d494f031da1261d8e2e0d2bf' -> 'e066c4c969b940182df5b22e4991b6455c1030eb30b9553125077fb4fd6331a3'
$.f.snapshot.snapshot.inputs.pricing.fator_preco: '1.25' -> '1.25000'
$.f.snapshot.snapshot.inputs.pricing.impostos_pct: '9.0' -> '9.000'
$.f.snapshot.snapshot.snapshot_hash: '03643f50d7a8f2d9c0300272280fa1368df5eb66d583cfcf82c295a7ab9a5ace' -> '349003d3215653c3e14b343ee46c91bf077f00916a18d06aa302dd89e91b50e9'
```
