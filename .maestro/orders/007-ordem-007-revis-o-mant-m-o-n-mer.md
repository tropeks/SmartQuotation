<!-- maestro-order v1
id: 007
ts: 2026-09-28T00:59:23-03:00
epoch: 1790567963
head: 314ef78e3e1d3d2ae84d19770abcc9d4722e5485
branch: order/007-revisao-mantem-numero
intent_version: 3
intent_hash: be9e1bc4
author_session: d125f612-fe58-44f9-9789-3bae25d86d02
-->
# Ordem 007 — revisão de cotação mantém o número e sobe a revisão (P1 a P7)

Direção: INTENT v3 §Limites (adapter único que persiste resultado do motor; preservar proveniência). Decisão do Capitão 01M3JEK53Y43C5A55X0ANSA4B5: revisão MANTÉM o número e sobe `revision`. P1–P7 decididos pelo Diretor dentro dessa direção.

## Escopo
- Migração `quotations/0010`: `number` deixa de ser unique (fica com índice); `UniqueConstraint(number, revision)` `uniq_quotation_number_revision`; reverse com guarda (recusa desfazer se já existe número repetido). Migra antes do código; irreversível depois do primeiro uso.
- Alocador único `allocate_revision` (select_for_update) usado nas 3 rotas: feixe (`quotation_revise`), completo (`adapter.revise_complete`) e `quotation_edit`. Persistência da revisão do feixe passa ao adapter (`revise_feixe`), atômica. IntegrityError vira mensagem de conflito.
- Proposta: storage do arquivo por pk (Rev.1 não pode apagar o PDF da Rev.0). P5: número `PROP-AAAA-NNN-A` na Rev.0 e `PROP-AAAA-NNN-R{n}-A` na Rev.N.
- P1: listagem mostra só a revisão vigente (max revision do número); histórico no detalhe.
- P2: revisão não vigente não envia proposta nem vira OF (guarda na OF e na proposta).
- P3: revisar a partir de revisão antiga é permitido; a nova sai com max+1.
- P4: nova revisão marca `superseded` as propostas draft/ready das anteriores; enviadas ficam.
- P6: revisão não troca o cliente (bloqueado).
- P7: não se revisa cotação que já tem OF (bloqueado, por ora).
- Revisão de escopo `parts` copia as QuotationPart (hoje sai com custo zero).
- Ajustar test_feature.py:85/104; emendar DATA_MODEL.md:255 e ARCHITECTURE.md:496 no mesmo changeset.

## Fora de escopo
Markup/impostos do tenant no motor do permutador (008); `next_number` lexicográfico (backlog).

## Aceite
Teste vermelho antes de cada regra; migração testada ida e volta (guarda); gates do motor intactos; suíte e CI verdes; `docs/ship/ORDEM_007_DIFERENCA.md` com o passo a passo de deploy (migrar antes, irreversível) para o ship do Capitão.



## Contrato de execução
- Trabalhe APENAS no branch `order/007-ordem-007-revis-o-mant-m-o-n-mer`; NUNCA no main/master.
- Prove com o ledger: `maestro evidence --record --label order-7 -- <suíte>` no tip do branch.
- Direção vigente na criação: INTENT v3 (`.maestro/INTENT.md`) — o plano cita a seção da direção que autoriza esta ordem.
- Estourou Ask-First ou orçamento? PARE e reporte ao humano — não improvise.
- O aceite é do diretor: `maestro order --accept 007` (você não fecha a própria ordem).
