<!-- maestro-order v1
id: 006
ts: 2026-09-27T20:22:28-03:00
epoch: 1790551348
head: ad1bf5943a2708ec9b6bc51aa288d339ee14559f
branch: order/006-precisao-e-revisao
intent_version: 3
intent_hash: be9e1bc4
author_session: d125f612-fe58-44f9-9789-3bae25d86d02
-->
# Ordem 006 — fator_preco/impostos_pct quantizados pela casa do campo (006a do Diretor)

Direção: INTENT v3 §Limites (o adapter é o único caminho que persiste resultado do motor; preservar cálculos de cotação e proveniência). Decisão do Diretor: 006 = precisão das casas (antiga 006a).

## Problema
`adapter.persist_complete` grava `fator_preco` (DecimalField 8,5) e `impostos_pct` (6,3) via `_money2`, que quantiza a 2 casas. Markup não redondo (ex.: 1,01377) vira 1,01; impostos 23,303 viram 23,30. O snapshot/hash carrega a string truncada.

## Escopo
1. Teste vermelho primeiro (commit próprio): cenário sintético fator 1,01377 / impostos 23,303 prova truncamento.
2. Conserto: helper que quantiza pela `decimal_places` do próprio campo (lida de `Quotation._meta`), aplicado a fator_preco e impostos_pct. Dinheiro segue em 2 casas.
3. `tests_precision_006.py`: BEU de referência — preço idêntico antes/depois; só a string do hash muda.
4. Golden `char_005.json`: diff restrito a `snapshot.inputs.pricing.{fator_preco, impostos_pct}` e aos 6 `snapshot_hash`, listado campo a campo no PR.
5. `docs/ship/ORDEM_006_DIFERENCA.md`: tabela antes/depois para o ship do Capitão.

## Fora de escopo
Revisão mantém o número (007); markup/impostos do tenant no motor do permutador (008).

## Aceite
Gates do motor 0,0% intactos; suíte Django verde; CI verde no tip; recibos motor/suite/order-6.


## Contrato de execução
- Trabalhe APENAS no branch `order/006-precisao-e-revisao`; NUNCA no main/master.
- Prove com o ledger: `maestro evidence --record --label order-6 -- <suíte>` no tip do branch.
- Direção vigente na criação: INTENT v3 (`.maestro/INTENT.md`) — o plano cita a seção da direção que autoriza esta ordem.
- Estourou Ask-First ou orçamento? PARE e reporte ao humano — não improvise.
- O aceite é do diretor: `maestro order --accept 006` (você não fecha a própria ordem).
accepted_at: 2026-09-28T00:59:00-03:00
accepted_session: desconhecido
accepted_tree: b6f660c7227da4203f8b9080dee413ce94bbc801
accepted_intent: 3
