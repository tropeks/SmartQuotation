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
