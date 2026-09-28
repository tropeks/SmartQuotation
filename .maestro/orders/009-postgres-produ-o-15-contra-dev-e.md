<!-- maestro-order v1
id: 009
ts: 2026-09-28T13:08:28-03:00
epoch: 1790611708
head: 3283af4dd096f6c9c8437ba8e58ccef3cc7e9be2
branch: order/009-postgres-produ-o-15-contra-dev-e
intent_version: 3
intent_hash: be9e1bc4
author_session: desconhecido
-->
# Ordem 009 — Postgres: produção 15 contra dev e CI 16


## Escopo
Achado do Conformador (INFRA, 27/09): produção roda Postgres 15, dev e CI rodam 16.
1. Provar pelo repositório (INFRASTRUCTURE, compose de produção, runbooks) qual versão a produção
   roda de fato, sem acessar o host.
2. A suíte passa a rodar também contra a versão da produção: patch de workflow em `docs/patches/`
   para o Capitão aplicar; até lá, um teste local documentado.
3. Plano de upgrade da produção para 16 em `docs/ship/`: backup (a 002 e a 003 já existem),
   pg_upgrade ou dump/restore, tempo de parada estimado e volta.

## Fora desta ordem
Nada no host de produção. Nenhum dado real da ENGEMATEX.

## Contrato de execução
- Trabalhe APENAS no branch `order/009-postgres-produ-o-15-contra-dev-e`; NUNCA no main/master.
- Prove com o ledger: `maestro evidence --record --label order-9 -- <suíte>` no tip do branch.
- Direção vigente na criação: INTENT v3 (`.maestro/INTENT.md`) — o plano cita a seção da direção que autoriza esta ordem.
- Estourou Ask-First ou orçamento? PARE e reporte ao humano — não improvise.
- O aceite é do diretor: `maestro order --accept 009` (você não fecha a própria ordem).
accepted_at: 2026-09-28T17:24:04-03:00
accepted_session: desconhecido
accepted_tree: 71c68485c7c7b3720ea9edcce486c9032c705eb5
accepted_intent: 3
