<!-- maestro-order v1
id: 002
ts: 2026-09-27T17:55:41-03:00
epoch: 1790542541
head: c282b744a7a7b0a8ca380a489afe1c417acbc2a8
branch: order/002-backup-producao
intent_version: 3
intent_hash: be9e1bc4
author_session: d125f612-fe58-44f9-9789-3bae25d86d02
-->
# Ordem 002 — backup automatizado da produção validado pelo conteúdo, com a FIELD_ENCRYPTION_KEY coberta



**Direção:** INTENT v3 §Limites ("nenhum dado real sai da instância"; "nada em produção real
sem gate ship"). Achado CRÍTICO do swarm; ordem do Diretor em 27/09. Plano aprovado com
condições (decisão 01M3J8BZCMYA5M96G9ZP72T0RZ).

**Condições do Diretor:** a prova de decifra imprime só ok/falha/sem amostra, nunca o valor
nem a chave; nenhum log nem teste grava a FIELD_ENCRYPTION_KEY; a chave (e o `.env.prod`,
que a contém) NUNCA viaja junto com o dump no off-site da 003: custódia separada.
Instalar no host de produção é gate ship do Capitão.

**Entrega:** absorve o #114 (backup em container avulso + sensibilidade do motor, revisado),
corrige os achados da revisão dele (umask, rodapé, injeção em `sh -c`, trap, container
parado) e acrescenta backup_media em container avulso, backup_key.sh com prova de decifra,
restore_check.sh (drill em postgres:15 efêmero, `--network none`, `rm -fv`), units systemd
com env file dedicado (`/etc/smartquotation/backup.env`, sem `.env.prod`) e §6 do
INFRASTRUCTURE reescrita. Revisão opus: sem bloqueante; 4 importantes + 6 menores corrigidos.
Tudo provado com docker falso (77 testes de backup); off-site fica na 003.

## Contrato de execução
- Trabalhe APENAS no branch `order/002-backup-producao`; NUNCA no main/master.
- Prove com o ledger: `maestro evidence --record --label order-2 -- <suíte>` no tip do branch.
- Direção vigente na criação: INTENT v3 (`.maestro/INTENT.md`) — o plano cita a seção da direção que autoriza esta ordem.
- Estourou Ask-First ou orçamento? PARE e reporte ao humano — não improvise.
- O aceite é do diretor: `maestro order --accept 002` (você não fecha a própria ordem).
accepted_at: 2026-09-27T18:44:11-03:00
accepted_session: desconhecido
accepted_tree: 373874f2aa9e8cd07070592052f913f71b175ca5
accepted_intent: 3
