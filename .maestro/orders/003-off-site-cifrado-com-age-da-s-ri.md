<!-- maestro-order v1
id: 003
ts: 2026-09-27T18:24:27-03:00
epoch: 1790544267
head: 2b6c9b70421585afa0a0bfbeed2472adf096f2d9
branch: order/003-offsite-age
intent_version: 3
intent_hash: be9e1bc4
author_session: d125f612-fe58-44f9-9789-3bae25d86d02
-->
# Ordem 003 — off-site cifrado com age da série de backup, chave em custódia separada

**Direção:** INTENT v3 §Limites ("nenhum dado real de cliente sai [...] da instância dele";
"nada em produção real sem gate ship"): o que sai do host é só texto cifrado com `age`, que
o provedor não lê. Decisão do Capitão 01M3J7RNGCM5Y22RHHZSFWJPGR (off-site da série de
backup da 002). DP-29 do cognitive-core (backup cifrado em provedor estrangeiro, aprovada) e
DP-41 (raiz de recuperação da Quantum, offline no YubiKey). Plano aprovado pelo Diretor na
decisão 01M3JC174DFPRG8P17WJZBA0ZP.

**Decisões do Diretor:**
- (a) Destino ESTRANGEIRO é permitido já, pela DP-29 aprovada. Se o parecer J-29 apontar
  risco, troca-se o destino e a série é reenviada. O docs/SECURITY.md passa a dizer isso.
- (b) A FIELD_ENCRYPTION_KEY vai como objeto SEPARADO: cifrada só para a chave de
  recuperação da Quantum, num remote DISTINTO (`OFFSITE_KEY_REMOTE`, credencial própria),
  enviada só quando o fingerprint muda. A chave nunca passa por argv, env, log nem arquivo
  que não seja 0600.

**Plano:**
1. `scripts/offsite_push.sh`: cifra o dump e o tar de mídia mais recentes com `age` para dois
   destinatários (instância + recuperação), recusa chave privada e destinatário único, envia
   com `rclone copyto --immutable` para `OFFSITE_REMOTE` (o código não escolhe provedor).
   Objeto remoto já presente com o hash registrado: pula; com outro hash: falha, nunca
   sobrescreve.
2. Validação por conteúdo depois do envio: hash remoto = hash local do `.age`, e o cabeçalho
   tem exatamente 2 stanzas `X25519`. Só então grava `offsite_last_success` (atômico, 0600).
3. `scripts/offsite_key_push.sh`: a chave, lida do arquivo 0600 da 002 por stdin, cifrada
   só para a recuperação, no `OFFSITE_KEY_REMOTE` (recusado se igual ao, dentro do ou na
   mesma seção do `OFFSITE_REMOTE`), só quando o fingerprint muda.
4. A chave e o `.env.prod` nunca entram no pacote do dump (condição da 002, testada contra
   tudo que o remote de dump recebe). Sem poda remota enquanto a DP-27 estiver aberta.
5. Units: os dois scripts na sq-backup.service depois de db/media/key; `RCLONE_CACHE_DIR`
   em diretório permitido; backup.env.example com as variáveis novas e chaves fictícias.
6. `restore_check.sh` aceita `RESTORE_DUMP_FILE`/`RESTORE_MEDIA_FILE` para o drill
   trimestral a partir do off-site; runbook na §6 do INFRASTRUCTURE.
7. Testes com `age` e `rclone` falsos (tests/_ops_fakes.py), agregados em
   tests.test_backup_script, verdes no python com e sem cryptography.

## Contrato de execução
- Trabalhe APENAS no branch `order/003-offsite-age`; NUNCA no main/master.
- Prove com o ledger: `maestro evidence --record --label order-3 -- <suíte>` no tip do branch.
- Direção vigente na criação: INTENT v3 (`.maestro/INTENT.md`) — o plano cita a seção da direção que autoriza esta ordem.
- Estourou Ask-First ou orçamento? PARE e reporte ao humano — não improvise.
- O aceite é do diretor: `maestro order --accept 003` (você não fecha a própria ordem).
accepted_at: 2026-09-27T20:02:45-03:00
accepted_session: desconhecido
accepted_tree: 32f065cfccbcebd799ee3328e27b0341a4ea7440
accepted_intent: 3
