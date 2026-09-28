<!-- maestro-order v1
id: 008
ts: 2026-09-28T04:22:15-03:00
epoch: 1790580135
head: c1945effdac627836f0e1db66db58919c99baa43
branch: order/008-markup-impostos-permutador
intent_version: 3
intent_hash: be9e1bc4
author_session: d125f612-fe58-44f9-9789-3bae25d86d02
-->
# Ordem 008 — markup e impostos do tenant no motor do permutador completo

Direção: INTENT v3 §Limites. Plano: scratchpad/plan008.md, aprovado pelo Diretor em 28/09 (decisão 01M3KET7KPPPVBD4031BMAW0FP).

## Decisões do Diretor
- (a) Só o par do permutador: `TenantParamConfig.fator_preco_completo`/`impostos_pct_completo`. O feixe continua por cotação.
- (b) Mantêm-se as duas semânticas de imposto: por fora no feixe e ICMS por dentro no permutador. Unificar é decisão fiscal do Capitão.
- (c) `revise_complete` congela o markup da cotação original.
- (d) Default 1,25/9,0: o preço não muda no dia 1. O ship leva só o procedimento de configurar o tenant.

## Escopo
1. Campos novos em TenantParamConfig, com migração, default 1,25/9,0 e as mesmas casas de Quotation (8,5 e 6,3). Admin e tela, se já houver edição de TenantParamConfig.
2. `tema_templates` passa esses valores EXPLICITAMENTE a `quote_completo(fator_preco=..., impostos_pct=...)`. O motor (pricing_engine) NÃO muda.
3. `revise_complete` recalcula com o fator e os impostos da cotação original.
4. TDD: teste vermelho primeiro. Um tenant com 1,30/12 muda o preço e o snapshot; o default dá o mesmo preço de hoje; a revisão congela.
5. Golden char_005 sem diff (o default é igual). `docs/ship/ORDEM_008_DIFERENCA.md` com o procedimento de configuração.

## Aceite
Gates do motor intactos; suíte e CI verdes; import-linter 2/2; makemigrations limpo; recibos motor/suite/order-8.



## Contrato de execução
- Trabalhe APENAS no branch `order/008-markup-e-impostos-do-tenant-no-m`; NUNCA no main/master.
- Prove com o ledger: `maestro evidence --record --label order-8 -- <suíte>` no tip do branch.
- Direção vigente na criação: INTENT v3 (`.maestro/INTENT.md`) — o plano cita a seção da direção que autoriza esta ordem.
- Estourou Ask-First ou orçamento? PARE e reporte ao humano — não improvise.
- O aceite é do diretor: `maestro order --accept 008` (você não fecha a própria ordem).
