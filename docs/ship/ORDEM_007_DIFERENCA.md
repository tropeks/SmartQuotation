# Ordem 007 — a revisão de cotação MANTÉM o número

## O que muda para o usuário

Até aqui, "Revisar" (ou "Nova Revisão") uma cotação criava uma cotação **com número
novo** (ex.: `COT-2026-004` virava `COT-2026-011`), e a revisão (`Rev. 1`, `Rev. 2`...) só
existia como um contador dentro de uma cotação que, na prática, tinha um número diferente
da anterior. Isso quebrava a rastreabilidade que a numeração deveria dar: o cliente recebia
propostas com números sem relação aparente, e "revisão" virava, na prática, "cotação nova".

A partir desta ordem, revisar **mantém o número** (`Quotation.number`) e sobe apenas a
`revision`: `COT-2026-004` Rev.0 → `COT-2026-004` Rev.1 → `COT-2026-004` Rev.2, sempre o
mesmo número, decisão do Capitão (01M3JEK53Y43C5A55X0ANSA4B5).

### Regras novas (P1–P7)

- **P1 — a listagem só mostra a revisão vigente.** A tela "Cotações" não lista mais uma
  linha por revisão: mostra uma linha por `number`, sempre a de maior `revision`. O
  histórico completo (todas as revisões do mesmo número) aparece no **detalhe** da
  cotação vigente, com um link para cada revisão anterior.
- **P2 — só a revisão vigente pode enviar proposta ou virar Ordem de Fabricação.** Se
  existe uma `Rev.2` mais nova, a `Rev.1` não pode mais enviar e-mail de proposta nem ser
  convertida em OF — a tentativa falha com uma mensagem explicando por quê, não com erro
  genérico.
- **P3 — revisar uma revisão antiga também avança a partir da mais recente.** Se você abrir
  a `Rev.0` e clicar em "Revisar" mesmo depois de já existir uma `Rev.2`, o sistema cria a
  `Rev.3` (nunca recria uma `Rev.1` que já existe).
- **P4 — revisar supera as propostas em aberto.** Ao criar uma revisão nova, as propostas
  em rascunho (`draft`) ou prontas mas não enviadas (`ready`) das revisões anteriores viram
  `superseded` (substituída) automaticamente. Uma proposta já **enviada** (`sent`) ao
  cliente não é alterada — ela já saiu, e revogar um envio real não é desta ordem.
- **P5 — número da proposta ganha o sufixo da revisão.** `PROP-2026-004-A` continua sendo
  o formato da proposta da Rev.0 (sem mudança); a partir da Rev.1, o número passa a ser
  `PROP-2026-004-R1-A`, `PROP-2026-004-R2-A`, etc. — sem isso, a proposta da Rev.1 teria o
  MESMO número da proposta da Rev.0 (já que as duas revisões agora compartilham
  `Quotation.number`). O arquivo (PDF/DOCX) de cada proposta passou a ser guardado no
  storage pela chave interna (`pk`), não mais pelo número — assim a Rev.1 nunca apaga o
  PDF já gerado/enviado da Rev.0.
- **P6 — revisão não troca o cliente.** A tela de edição (Tier A, feixe) bloqueia a
  tentativa de trocar o cliente durante uma revisão, com uma mensagem clara. Para outro
  cliente, é preciso criar uma cotação nova.
- **P7 — não se revisa uma cotação com Ordem de Fabricação.** Se qualquer revisão de um
  número já foi convertida em OF (não cancelada), o botão de revisar passa a falhar com
  mensagem — a intenção é impedir que o número mude de projeto depois que a fábrica já
  recebeu a lista de material e o roteiro.
- **Revisão por partes (scope "parts") volta a custear.** Havia um defeito onde revisar
  uma cotação de peças avulsas (casco/cabeçote isolados) não copiava as peças escolhidas
  — a revisão nascia com custo zero. Corrigido: a revisão copia as peças da cotação
  original.

## Deploy

**Ordem obrigatória: migrar ANTES de subir o código.** A migração
`quotations/0010_quotation_revision_keeps_number` só muda o schema (não migra dado — os
dados existentes continuam válidos, cada `number` hoje é único, então o par
`(number, revision)` também é). O código novo é o que passa a GRAVAR `number` repetido
(entre revisões); se o código novo subir antes da migração, a primeira tentativa de
revisar vai falhar (`IntegrityError`/`RevisionConflictError`), sem corromper dado — mas
para não gerar esse atrito, migre primeiro.

```bash
python manage.py migrate_schemas --schema=<schema_do_tenant>
# ou, para todos os tenants:
python manage.py migrate_schemas
```

### A migração é IRREVERSÍVEL na prática assim que a primeira revisão repetir um número

A migração 0010 tem reverse code (`python manage.py migrate quotations 0009
--schema=<tenant>` desfaria o schema), mas o reverse **recusa rodar** — com uma mensagem
clara, não um erro de banco cru — se já existir alguma cotação com `number` repetido entre
revisões (ou seja, se a feature já foi usada de verdade). Reverter o SCHEMA depois desse
ponto exigiria primeiro consolidar/renumerar manualmente as cotações duplicadas — a
migração não faz isso por você, de propósito (é uma decisão de negócio, não de schema).

Reverter o CÓDIGO (voltar ao binário anterior) continua seguro a qualquer momento — o
schema novo (`number` não-único + `UniqueConstraint(number, revision)`) é compatível com o
código antigo, que sempre gerava número novo e nunca repetia `number` mesmo assim.

### Checagem prévia — confirme que não há `number` duplicado ANTES de migrar

Não é uma pré-condição da migração (o schema aceita rodar de qualquer estado — os dados
atuais são, por construção, todos com `number` único), mas é uma boa prática confirmar o
estado esperado antes de uma migração de constraint:

```sql
-- Espera-se ZERO linhas: hoje `number` é UNIQUE, então nenhum duplicado deveria existir.
SELECT number, COUNT(*) AS n
FROM <schema_do_tenant>.quotations_quotation
GROUP BY number
HAVING COUNT(*) > 1;
```

Se essa consulta devolver alguma linha (não deveria, dado o schema atual), pare e
investigue antes de migrar — indicaria um estado já inconsistente, não algo que a
migração 0010 causa.

## Rollback

- **Código:** reverter o binário/deploy para a versão anterior a esta ordem. É seguro a
  qualquer momento (ver acima) — o schema novo aceita o comportamento antigo (número novo
  a cada revisão) sem conflito, já que `(number, revision)` continua único quando `number`
  nunca se repete.
- **Migração:** só reverter (`migrate quotations 0009`) enquanto NENHUMA cotação tiver
  `number` repetido entre revisões. Depois do primeiro uso real da feature, reverter a
  migração exige antes consolidar/renumerar as cotações duplicadas (decisão de negócio,
  fora do escopo desta migração) — o reverse code vai recusar com uma mensagem explicando
  exatamente isso, listando os números repetidos encontrados.

## Onde ver a prova

- `backend/apps/quotations/tests.py` — `RevisionKeepsNumberMigrationTests` (migração 0010,
  ida e volta, com e sem `number` repetido) e `RefuseDowngradeGuardUnitTests` (a guarda do
  reverse, chamada direto); `AllocateRevisionTests` (P3, alocador, corrida →
  `RevisionConflictError`); `IsCurrentRevisionTests`, `ListagemMostraApenasVigenteTests`
  (P1); `SupersedePropostasAnterioresTests` (P4); `RevisaoNaoTrocaClienteTests` (P6);
  `RevisaoBloqueiaComOfAtivaTests` (P7); `RevisaoDePartesCopiaQuotationPartTests` (cópia de
  `QuotationPart` na revisão).
- `backend/apps/production/tests.py` — `test_convert_bloqueia_revisao_nao_vigente` (P2, OF).
- `backend/apps/proposals/tests.py` — `ProposalOrdem007Tests` (P5, storage por `pk`, P2 no
  envio de e-mail).
- `backend/apps/quotations/test_feature.py` — `test_quotation_revise_feixe` /
  `test_quotation_revise_permutador` atualizados para o novo comportamento (número mantido).

## Anexo — diff do golden `char_005.json` (antes → depois da ordem 007)

`tests_characterization_005.py` é a fotografia de ponta a ponta da persistência do
permutador completo (ordem 005). A ordem 007 muda o comportamento de propósito — a
revisão (cena `d`) passa a manter o número da cotação original, e a proposta superada
(cena `a`) passa a `superseded` — então o golden foi regenerado (`SQ_RECORD_CHAR=1`).
Diff completo (10 caminhos, todos explicados pelas duas regras acima; nenhum total, item,
peso ou preço mudou):

```
$.a.propostas[0].status: 'draft' -> 'superseded'
$.d.quotation.number: 'COT-2026-004' -> 'COT-2026-001'
$.d.snapshot.snapshot.inputs.quotation.number: 'COT-2026-004' -> 'COT-2026-001'
$.d.snapshot.snapshot.outputs.number: 'COT-2026-004' -> 'COT-2026-001'
$.d.snapshot.snapshot.snapshot_hash: '7ce2164083bcb449ac087d65b5943f6c88ddf977f5d37cfcbe3fd32655590bc0' -> 'db04b24f3bd48697988dd58441ea8bdc98ab17ade294d5668cd3056cfe4a3409'
$.e.quotation.number: 'COT-2026-901' -> 'COT-2026-900'
$.e.snapshot.snapshot.inputs.quotation.number: 'COT-2026-901' -> 'COT-2026-900'
$.e.snapshot.snapshot.outputs.number: 'COT-2026-901' -> 'COT-2026-900'
$.e.snapshot.snapshot.snapshot_hash: 'e066c4c969b940182df5b22e4991b6455c1030eb30b9553125077fb4fd6331a3' -> 'c0c96230a2669b3bd1b24d25cddff6c0dbb4b16e25c0eb6bbf895af482a7b306'
$.f.propostas[0].status: 'draft' -> 'superseded'
```

- `$.d.*.number` (cena d = `revisar()` da cena a): antes ganhava um número NOVO
  (`COT-2026-004`, sequencial); agora mantém `COT-2026-001` (o número da cena `a`) — é
  exatamente a mudança de comportamento desta ordem. `snapshot_hash` muda porque o número
  entra no payload assinado.
- `$.e.*.number` (cena e = `revisar()` de uma cotação seed com `number="COT-2026-900"`):
  mesma razão — mantém `COT-2026-900` em vez de pular para `COT-2026-901`.
- `$.a.propostas[0].status` e `$.f.propostas[0].status` (a proposta da cena `a`, capturada
  de novo em `f` após um `recompute()`): P4 — revisar a cena `a` (na cena `d`) marca a
  proposta draft da cena `a` como `superseded`.

