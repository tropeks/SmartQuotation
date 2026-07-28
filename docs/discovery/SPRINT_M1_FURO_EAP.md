# Sprint M1 — tampar o vazamento de margem pela EAP

**Contrato.** Gate Legatus: SEARCH → PLAN → RED → GREEN → REFACTOR → VERIFY → REVIEW → EVIDENCE.
**Aval do domínio:** Wellington, 2026-07-24 — *"correção de vulnerabilidade de segurança
financeira, não feature. Entrega imediata, antes de qualquer outra."*

---

## SEARCH — o que a investigação achou (e corrigiu do plano original)

O plano do autoplan (`PLAN_TIPO_PROJETO_V2.md`) descrevia o furo em três views. A varredura
do código confirmou duas e **refutou uma**, e achou um agravante que ninguém tinha visto.

### ✅ Confirmado — `eap_item_save` e `eap_op_restore`

`backend/apps/quotations/views.py:496` e `:590` gravam direto em `ItemMaterial`/`ItemOperation`
e **não emitem `CalculationSnapshot`**. Como `_case_is_stale`
(`apps/audit/approvals.py:101`) e `_technical_approval_satisfied`
(`apps/production/services.py:38`) comparam contra `latest_snapshot_for(quotation)` — que
devolve o **último snapshot já gravado**, não um recálculo — o hash não muda e a assinatura
CREA continua "válida" sobre um custo que já não é o assinado.

### ❌ Refutado — `compose_parts_create`

Cotação `scope="parts"` nunca ganha snapshot na criação, mas `approve_quotation`
(`apps/audit/services.py:19`) **exige** snapshot e levanta `ValidationError` sem ele. Logo
essas cotações **nunca chegam a ser aprovadas** — é *fail-closed*, não *fail-open*. Não há
exploit aqui. **Sai do escopo do M1.**

### ⚠️ Agravante novo — a OF nasce com o número adulterado

`convert_quotation_to_of` (`apps/production/services.py:165,180,195,203-207`) copia os custos
dos objetos **vivos** do banco, **não** do JSON congelado do snapshot. Então mesmo que o gate
passasse por engano, o valor que entra na Ordem de Fabricação é o já adulterado — vestindo
uma assinatura que aprovou outro número.

### 🧭 Restrição de projeto que a correção precisa respeitar

`views.py:503-507` traz um **"GUARDRAIL ARQUITETURAL"** explícito: a EAP é derivada pelo motor,
e o override manual é deliberadamente gravado direto, sem chamar o motor. E `views.py:580`
documenta que **`computed_at` não é tocado de propósito** — sinaliza "o motor não rodou".
Existe teste consagrando isso
(`test_eap_item_save_persists_override_and_updates_rollup_without_engine`).

**Consequência de design:** `computed_at` ("o motor rodou") e `CalculationSnapshot`
("o estado mudou") são coisas diferentes. A correção emite snapshot e **preserva**
`computed_at` intocado. O guard-rail existente continua de pé.

---

## PLAN — escopo

| # | Entrega | Efeito |
|---|---|---|
| 1 | Override manual emite `CalculationSnapshot` (sem tocar `computed_at`) | hash muda → `invalidate_stale_cases` roda → aprovação deixa de casar → conversão bloqueada até re-assinar |
| 2 | `eap_item_save`/`eap_op_restore` em `transaction.atomic` + `select_for_update` na Quotation | roll-up por soma deixa de ser corrigível por corrida entre dois editores |
| 3 | Justificativa obrigatória no override | sem motivo, não salva (400) |
| 4 | Notificação ao gestor da margem quando o override atinge cotação já aprovada | ninguém baixa custo em silêncio |

**Fora de escopo, explicitamente:**
- `design_basis` imutável — estava no plano do M1 original, mas a regra de **origem do valor**
  que o Wellington deu em 2026-07-27 mudou a modelagem. Vai para o M2.
- `compose_parts_create` — refutado acima.
- Fazer a conversão ler do snapshot em vez do banco vivo — é correção real (agravante acima),
  mas mexe no contrato da OF e merece sprint própria. **Registrado como M1.1.**

**Desvio a validar com o Wellington (não bloqueia):** ele pediu justificativa obrigatória sem
ressalva. Implementado assim — obrigatória **sempre**. O risco é atrito no rascunho, onde o
orçamentista itera dezenas de vezes. Se incomodar, a troca para "obrigatória só quando há
aprovação vigente" é uma constante.

---

## RED — os testes que provam o furo

`backend/apps/quotations/tests_eap_guardrail.py`. Devem **falhar** antes da correção:

1. override na EAP invalida a aprovação técnica (`is_convertible` → False)
2. override emite novo `CalculationSnapshot`
3. `eap_op_restore` também invalida
4. override sem justificativa é recusado (400)
5. justificativa fica no `AccessLog`
6. override em cotação aprovada notifica o gestor da margem
7. `computed_at` continua intocado (protege o guard-rail existente — deve passar antes e depois)

---

## GREEN → REVIEW → o que a auditoria derrubou

O primeiro GREEN passou 10/10 e **estava errado**. O CSO adversarial achou dois
CRÍTICOS, ambos com exploit executado contra o código real:

### 🔴 O hash era cego a horas e taxas

`build_snapshot_payload` serializava só `custo` das operações. Como
`custo = horas × taxa`, dava para **partir as horas pela metade e dobrar a taxa**:
custo idêntico → hash idêntico → assinatura casando. E `convert_quotation_to_of`
copia as **horas** para a Ordem de Fabricação. Prova executada:

```
horas assinadas: 100.00 -> horas agora: 50.00
custo assinado : 5000.00 -> custo agora : 5000.00
is_convertible : True      <-- o M1 não pegou
```

O engenheiro assinava 100 h e a fábrica recebia 50, com a mesma ART. Era o mesmo
furo da sprint, um nível abaixo — não resíduo do M1.1: o snapshot também não tinha
as horas, então nem ler do snapshot resolveria.

**Correção:** `horas_hh`, `horas_hm`, `taxa_hora`, `taxa_hora_hm`, `custo_direto` e
`origem` entram no payload. ⚠️ Muda o hash de todas as cotações existentes e
invalida aprovações em voo — precisa de aviso no deploy.

### 🔴 A tela parou de salvar

O template do drawer não tinha campo `motivo`. Exigi o motivo na view e **não
ofereci onde digitar**: todo save real passou a devolver 400.

Pior que o bug: **os testes esconderam**. Eu editei os testes existentes para
injetar `motivo` no dict do POST e os novos montavam o POST à mão, sem nunca
renderizar o HTML. A suíte ficou verde exatamente em cima do defeito — consertei o
teste em vez de deixá-lo expor a quebra. Agora existe
`test_o_drawer_renderiza_o_campo_de_motivo`, que parte do HTML renderizado.

### Demais achados corrigidos

| Sev | Achado | Correção |
|---|---|---|
| ALTO | Notificação disparava mesmo sem mudança → e-mail e snapshot em laço | compara hash **antes × depois da requisição**; sem mudança, não grava nem avisa |
| ALTO | O engenheiro que assinou não era avisado da própria assinatura invalidada | entra na lista de destinatários |
| MÉDIO | E-mail dentro da transação segurando o lock no round-trip SMTP | `transaction.on_commit` |
| MÉDIO | Notificação sem destinatário falhava em silêncio | registra no `AccessLog` |
| BAIXO | `motivo` sem limite, copiado 1× por campo (~200× de amplificação) | truncado em 500 |

**Negativo explícito confirmado pela auditoria:** não há deadlock. As três views que
travam a cotação (`eap_item_save`, `eap_op_restore`, `convert_quotation_to_of`) pegam
o mesmo e único recurso como primeira operação.

## Fora de escopo — registrado, não corrigido

- **M1.1** — `convert_quotation_to_of` copia custos do banco vivo, não do snapshot.
- **M1.2** — `QuotationAdmin` deixa editar `custo_*` e `fator_preco` sem selo. Exige
  `is_staff` (staff de plataforma, não papel de tenant), mas é bypass vivo.
- **M1.3** — permutador pressurizado sem memorial ASME montável agora dá 500 na
  edição da EAP (`build_snapshot_payload` levanta `RuntimeError`). Fail-closed, não é
  bypass, mas inutiliza o drawer para essa classe.

## VERIFY

- `apps.quotations.tests_eap_guardrail` + `test_feature` + `apps.production`: **151 OK**
- Gates do motor: feixe (Δ −2,9%), permutador BEU/BEM (Δ 0,00%), knobs — **todos OK**

## Segunda passada — o que o codex achou depois do CSO

| Sev | Achado | Desfecho |
|---|---|---|
| P1 | Lock adquirido **depois** do `prefetch_related`: a segunda requisição espera na fila com um cache lido antes do lock e soma linhas que o primeiro editor já mudou | **corrigido** — o item passa a ser carregado dentro da transação, depois do lock |
| P1 | `suite.log` (10.150 linhas, rodada com falhas) foi commitado por `git add -A` | **corrigido** — removido do índice e no `.gitignore` |
| P1 | "Quatro testes em `tests.py` postam sem motivo e esperam 200" | **refutado** — não existe POST para `eap_item_save`/`eap_op_restore` em `tests.py`; as linhas citadas não correspondem |
| P2 | Aviso de deploy impreciso: incluir horas no payload **não** reescreve snapshots existentes; a invalidação só ocorre quando um snapshot novo é criado | **procede** — corrigido abaixo |
| P2 | `engine_version` continua `calc-snapshot-v1` com o schema de `operacoes` mudado | registrado (M1.5) |
| P2 | Override marca `origem="manual"` mesmo sem mudança numérica, porque o form envia todos os campos | registrado (M1.6) |

### Correção do aviso de deploy

O aviso anterior estava errado. Não há backfill nem migração: os snapshots já gravados
**permanecem intactos**, com o formato antigo. A divergência só aparece quando um snapshot
novo é criado para aquela cotação — aí o hash muda e a aprovação vigente deixa de casar.
Na prática: cotações paradas continuam válidas; cotações editadas passam a exigir
re-assinatura. (Irrelevante hoje — a base é toda de teste.)

## Backlog aberto pela sprint

- **M1.1** conversão lê custos do banco vivo, não do snapshot congelado
- **M1.2** `QuotationAdmin` edita `custo_*`/`fator_preco` sem selo (exige `is_staff`)
- **M1.3** permutador pressurizado sem memorial ASME montável → 500 na edição da EAP
- **M1.4** `eap_op_restore` repõe só as horas mas grava `origem="seed"` mesmo com taxa
  manual preservada — o custo "restaurado" pode continuar diferente do motor, agora
  rotulado como motor
- **M1.5** bumpar `engine_version` quando o schema do payload muda
- **M1.6** só marcar `origem="manual"` quando o valor realmente mudou
- **M1.7** `peso_bruto_kg` é editável e entra no snapshot, mas não há roll-up de peso na
  cotação — a OF pode receber peso total antigo com materiais de peso novo

## EVIDENCE

- RED: 7 falhas provando o exploit · 3 passando (guard-rails existentes protegidos)
- GREEN: 15/15 no `tests_eap_guardrail`
- VERIFY: `tests_eap_guardrail` + `test_feature` = **35 OK**; com `apps.production` = **151 OK**
- Gates do motor: feixe −2,9% · BEU/BEM 0,00% · knobs — todos OK
- REVIEW: CSO (2 críticos + 5) e codex (2 P1 válidos, 1 refutado, 4 P2)

---

# Sprint M1.4 + M1.7 — coerência do que chega à fábrica

Mesma família do M1: o número que vai para o chão de fábrica diverge do aprovado e
nada reclama. Fechados juntos porque são baratos e ficariam abertos enquanto eu
construísse feature nova.

## M1.7 — peso do cabeçalho × peso das linhas

A OF copia **duas** coisas: `quotation.peso_bruto_kg` no cabeçalho
(`production/services.py:169`) e `mp.peso_bruto_kg` em cada material (`:192`). Editar o
peso de um material no drawer gravava a linha e deixava o total parado.

RED mediu: cabeçalho **1.280,96 kg**, linhas somando **1.780,96 kg**. Meia tonelada de
diferença no mesmo equipamento.

Correção: `_rollup_peso()` ressoma bruto e líquido junto do roll-up de custo.

## M1.4 — "restaurado" que não restaura

`eap_op_restore` repunha as HORAS sugeridas e gravava `origem="seed"`, mas a taxa
manual sobrevivia. RED mediu: custo restaurado **R$ 1.600** contra **R$ 1.200** do
motor — 33% acima, carimbado como se fosse do motor.

Correção: `taxa_hora_sugerida` e `taxa_hora_hm_sugerida` entram no `ItemOperation`
(migration `0009`), o adapter as guarda nos 3 pontos onde já guardava as horas, e o
restore repõe as quatro. Agora `origem="seed"` é verdade.

## Um bug que só apareceu porque o teste de estabilidade existia

O roll-up de peso somava valores de **3 casas** (`ItemMaterial`) num campo de **2**
(`Quotation`). Em memória `1780.960`, no banco `1780.96` — e como o snapshot serializa
com `str()`, o hash mudava a **cada requisição**, mesmo sem edição: snapshot e e-mail
em laço, exatamente o ruído que o CSO tinha mandado eliminar.

A sondagem mostrou o hash convergindo enquanto a contagem de snapshots crescia — foi
essa contradição que denunciou. Sem `test_post_sem_alteracao_nao_vira_snapshot_nem_email`,
isso ia para produção silencioso. Correção: `.quantize(Decimal("0.01"))` no roll-up.

## VERIFY

- `tests_eap_coerencia` + `tests_eap_guardrail` + `test_feature`: **39 OK**
- Gates do motor: feixe −2,9% · permutador BEU/BEM 0,00% — OK
- `makemigrations --check`: sem pendência
