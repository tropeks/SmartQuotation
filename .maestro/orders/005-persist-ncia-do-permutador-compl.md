<!-- maestro-order v1
id: 005
ts: 2026-09-27T19:08:32-03:00
epoch: 1790546912
head: 828e66ab3ab205647d6056658a6c7c4520c2256b
branch: order/005-adapter-permutador
intent_version: 3
intent_hash: be9e1bc4
author_session: d125f612-fe58-44f9-9789-3bae25d86d02
-->
# Ordem 005 — persistência do permutador completo passa para o adapter

## Direção

INTENT v3 §Limites: "pricing_engine é Python puro, sem Django, e o único caminho que
**persiste** resultado do motor é `apps/quotations/adapter.py` (outros módulos podem chamar
o motor para simular ou exibir, nunca gravar o resultado), travado por import-linter no CI."

Decisão A do Diretor (aprovação do plano 01M3JEJ9SGZS8FFJA4G9MV6JHW): mover
`apps.quotations.services.create_permutador_quotation` — que hoje persiste a EAP do
permutador completo por fora do adapter, achado registrado no relato da ordem 004 e mantido
como `ignore_imports` explícito no `.importlinter` até esta ordem — para
`apps.quotations.adapter`, fechando o único ponto de acoplamento que a Direção exige.

## Plano aprovado (4 commits)

- **C1** — caracterização: `tests_characterization_005.py` + golden `golden/char_005.json`,
  VERDE sobre o código ATUAL (antes da mudança), cobrindo BEU/BEM de referência, BEU com
  geometria/liga alterada e pressão de projeto, `quotation_revise` (caminho normal e
  fallback com inputs inválidos) e `adapter.recompute()`.
- **C2** — a mudança: `adapter.persist_complete()` e `adapter.revise_complete()` (corpo
  idêntico ao de `create_permutador_quotation`/ao ramo `scope == "complete"` de
  `quotation_revise`, movidos com `@transaction.atomic`); `create_permutador_quotation` sai
  de `services.py` sem wrapper de compat; chamadores (views + ~12 testes) atualizados;
  `.importlinter` ganha `apps.quotations.adapter -> pricing_engine.permutador_quote` e perde
  `apps.quotations.views -> pricing_engine.permutador_quote`. O golden do C1 não pode mudar.
- **C3** — teste estrutural (`tests_persistence_boundary.py`, AST puro, sem Django/banco):
  prova que só o adapter (+ allowlist nomeada e justificada) escreve resultado na EAP
  (Quotation/QuotationItem/ItemMaterial/ItemOperation/CalculationSnapshot).
- **C4** — docs: `docs/ARCHITECTURE.md` (linha do adapter, ACHADO 004 resolvido, §Flags) e
  `CLAUDE.md` (parágrafo do achado).

## Divergências PRESERVADAS de propósito (não corrigidas nesta ordem)

- `fator_preco`/`impostos_pct` são copiados do resultado do motor com truncamento em 2
  casas (o model comporta 5/3 casas) — vira ordem 006.
- A revisão de uma cotação `scope="complete"` ganha **número novo** a cada `revisar`, em vez
  de manter o número e só subir `revision`. Regra de negócio: decidida pelo Capitão (decisão
  01M3JEK53Y43C5A55X0ANSA4B5) que o comportamento CORRETO é manter o número — a correção
  fica para a ordem 006, junto com a de `fator_preco`/`impostos_pct`. Esta ordem preserva o
  comportamento atual (número novo) no golden e no código; não corrige.

## Contrato de execução
- Trabalhe APENAS no branch `order/005-adapter-permutador`; NUNCA no main/master.
- Prove com o ledger: `maestro evidence --record --label order-5 -- <suíte>` no tip do branch.
- Direção vigente na criação: INTENT v3 (`.maestro/INTENT.md`) — o plano cita a seção da direção que autoriza esta ordem.
- Estourou Ask-First ou orçamento? PARE e reporte ao humano — não improvise.
- O aceite é do diretor: `maestro order --accept 005` (você não fecha a própria ordem).
