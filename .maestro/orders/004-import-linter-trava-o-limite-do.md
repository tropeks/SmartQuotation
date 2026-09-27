<!-- maestro-order v1
id: 004
ts: 2026-09-27T18:24:28-03:00
epoch: 1790544268
head: de5c354136f283f2c48971144e66dee813f02173
branch: order/004-import-linter
intent_version: 3
intent_hash: be9e1bc4
author_session: d125f612-fe58-44f9-9789-3bae25d86d02
-->
# Ordem 004 — import-linter trava o limite do INTENT v3: só o adapter persiste resultado do motor

## Direção

`.maestro/INTENT.md` v3, §Limites: "`pricing_engine` é Python puro, sem Django, e o único
caminho que **persiste** resultado do motor é `apps/quotations/adapter.py` (outros módulos
podem chamar o motor para simular ou exibir, nunca gravar o resultado), travado por
import-linter no CI." A v3 trocou, nesta frase, "o adapter é o único acoplamento" (v2) por
"o único caminho que PERSISTE" (decisão 01M3J7RNGCM5Y22RHHZSFWJPGR do Capitão, 27/09/2026) —
liberando as chamadas de simulação/preview já existentes em `tema_templates/services.py`,
`engineering_params/simulation.py`, `cost_discovery/services.py` e `quotations/views.py`, e
prevendo a trava mecânica por import-linter como um passo à parte.

## Decisão do plano

Plano aprovado pelo Diretor em decisão **01M3JC1DSBDS2B4G70MMX4ZWMW**: tornar mecânico, via
import-linter no CI, o limite acima — hoje só documentado em prosa (INTENT + comentários).

## Plano

1. **import-linter**: declarar a dependência (ci.txt/ci.lock — o job `django-test` instala
   `ci.lock` —, `development.txt` e, se o job de ops for rodar o contrato, `ops.txt/ops.lock`).
   Regenerar os locks com hashes subindo só import-linter e suas dependências. Config em
   `.importlinter` na raiz (ou pyproject/setup.cfg se já existir), com `root_packages` que
   funcionem tanto para `pricing_engine` (raiz do repo) quanto para `apps` (`backend/`) —
   criar um wrapper que ajuste o `sys.path` se precisar.
2. **Contratos**: C1 "lib pura" — `pricing_engine` não importa django/rest_framework/celery/
   `apps.*`. C2 "só o adapter persiste" — os módulos do motor que COMPUTAM cotação
   (listados explicitamente) só podem ser importados, dentro de `apps`, por
   `apps.quotations.adapter` e por uma allowlist NOMEADA de módulos de simulação, cada
   entrada com comentário "simula, não persiste — <por quê>"; constantes/tipos/seeds
   continuam livres. Escolher o tipo de contrato do import-linter que expressa isso e
   explicar a escolha no `.importlinter`. Confirmar que os contratos passam hoje e provar
   que pegam uma violação (módulo novo em `apps` importando `quote_feixe` direto).
3. Como o import-linter não vê gravação: cada módulo da allowlist ganha um teste Django
   (TenantTestCase) confirmando que chamar a função de simulação com dados sintéticos não
   muda a contagem das tabelas da EAP (`apps/quotations/models.py`: Quotation, itens,
   matéria-prima, operações, snapshots). Se alguma entrada persistir de fato, parar e
   relatar ao Diretor — não corrigir dentro desta ordem.
4. **CI sem tocar `.github/`**: (a) `docs/patches/004-ci-import-linter.patch`, diff
   unificado aplicável com `git apply` a `ci.yml`, adicionando um step `lint-imports`;
   conferir com `git apply --check` e reverter antes de commitar (só o patch entra). (b) até
   o Capitão aplicar, o contrato roda como TESTE no job de ops, pendurado num módulo que o
   `ci.yml` já chama (padrão `python -m tests.X`), sem precisar de Django (import-linter é
   estático, via grimp).
5. **Docs**: `ARCHITECTURE.md` §0.3/§Flags e `CLAUDE.md` (Regra de ouro + Testes) apontam o
   contrato (arquivo e como rodar); atualizar `covers:` do ARCHITECTURE se necessário.

## Contrato de execução
- Trabalhe APENAS no branch `order/004-import-linter`; NUNCA no main/master.
- Prove com o ledger: `maestro evidence --record --label order-2 -- <suíte>` no tip do branch.
- Direção vigente na criação: INTENT v3 (`.maestro/INTENT.md`) — o plano cita a seção da direção que autoriza esta ordem.
- Estourou Ask-First ou orçamento? PARE e reporte ao humano — não improvise.
- O aceite é do diretor: `maestro order --accept 004` (você não fecha a própria ordem).
accepted_at: 2026-09-27T19:40:41-03:00
accepted_session: desconhecido
accepted_tree: c57d106858694f3ec551405f12ac205e940c065e
accepted_intent: 3
