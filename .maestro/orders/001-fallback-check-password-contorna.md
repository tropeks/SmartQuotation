<!-- maestro-order v1
id: 001
ts: 2026-09-27T17:37:56-03:00
epoch: 1790541476
head: f2173a6d7c11cb809e20a8fd89deb51aec3fe10a
branch: order/001-axes-aprovacao
intent_version: 3
intent_hash: be9e1bc4
author_session: d125f612-fe58-44f9-9789-3bae25d86d02
-->
# Ordem 001 — fallback check_password contorna o lockout do axes na aprovação presencial com CREA

**Direção:** INTENT v3 §Limites ("papel privilegiado não opera efeito externo só com senha";
humano/engenheiro habilitado assina o que é dele). Achado ALTA do swarm do Conformador
(`backend/apps/audit/services.py:135`), ordem do Diretor em 27/09 (01M3J7GW1ZBBRDVMH4EFWPMK50).

**Problema:** `approve_presencial` caía em `user.check_password()` quando `authenticate()`
devolvia `None`. O axes (`AxesStandaloneBackend`) sinaliza lockout com `PermissionDenied`,
que o `authenticate()` engole: com a conta trancada, a senha certa aprovava por baixo do
lockout. O mesmo caminho aprovava approver com `is_active=False`.

**Plano (fix: investigate → implement → review):**
1. Teste vermelho (`ApprovePresencialAxesTests`, `AXES_ENABLED=True`): conta trancada, inativo,
   `request=None`, caminho feliz de controle. — b193696
2. Conserto: sem fallback; só aprova se `authenticate()` devolver o próprio approver;
   `request=None` negado; AccessLog `locked_out`/`invalid_credentials`/`missing_request`,
   mensagem genérica. — f2173a6
3. Review do diff pelo Diretor (lido e correto, 27/09); aceite condicionado ao recibo `suite`
   no tip, depois do item 0 (PR #116) na main.


## Contrato de execução
- Trabalhe APENAS no branch `order/001-axes-aprovacao`; NUNCA no main/master.
- Prove com o ledger: `maestro evidence --record --label order-1 -- <suíte>` no tip do branch.
- Direção vigente na criação: INTENT v3 (`.maestro/INTENT.md`) — o plano cita a seção da direção que autoriza esta ordem.
- Estourou Ask-First ou orçamento? PARE e reporte ao humano — não improvise.
- O aceite é do diretor: `maestro order --accept 001` (você não fecha a própria ordem).
