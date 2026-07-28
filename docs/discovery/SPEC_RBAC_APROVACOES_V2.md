# SPEC — RBAC & Aprovações V2 (roles como dado + workflow builder + inbox)

> **Autor:** Fable 5 (CEO/produto) · **Data:** 2026-07-17
> **Insumos:** `FABLE_BRIEFING_RBAC_V2_2026-07-17.md`, `F10_RBAC_CONFIG_PLAN.md`,
> `WELLINGTON_DECISOES_2026-07-17.md`, código real de `apps/access`, `apps/audit`, `apps/accounts`,
> pesquisa web (fontes ao longo do doc).
> **Status:** proposta de produto para validação com Rom + Wellington. **Sem código.**
> **Premissa de negócio:** o F10 já atende a ENGEMATEX. A V2 existe para **vender a mais empresas** —
> cada fábrica de caldeiraria tem organograma diferente (tem a de 4 pessoas onde o dono é engenheiro,
> orçamentista e comercial ao mesmo tempo; tem a de 80 com PCP, qualidade e diretoria). Roles fixos
> não sobrevivem ao segundo cliente.

---

## 0. Sumário executivo

**O que a V2 entrega** (visão do Rom, refinada):

1. **Papéis como DADO por tenant** — criar role do zero marcando capabilities (estilo Zabbix),
   partindo de **templates de boas práticas** que o sistema já traz (os 5 papéis atuais viram os 5
   templates iniciais).
2. **Builder de fluxos de aprovação** — por tipo de ação (hoje: conversão em OF), definir estágios
   ordenados e **qual role aprova cada um**, com templates prontos + criação do zero. Estágio técnico
   CREA permanece built-in e intravável (compliance).
3. **Inbox de aprovações com badge** — item de menu **"Aprovações"** com contador numérico; página
   com duas abas: **"A aprovar"** (o que espera POR MIM) e **"Minhas solicitações"** (o que EU pedi
   e em que pé está). *(Naming: evitar "minhas aprovações pendentes" — é ambíguo entre os dois
   sentidos; a ambiguidade é exatamente o motivo das duas abas.)*

**Os 5 maiores achados desta spec** (detalhe nas seções 4 e 6):

- **G1 — O CREA está acoplado ao NOME do papel, não à qualificação.** `UserProfile.clean()`,
  a `CheckConstraint engenheiro_requires_crea` e `TechnicalApproval.clean()` comparam
  `role == "engenheiro"` (string literal). Com roles custom, "engenheiro" pode nem existir no
  tenant. A V2 precisa mover compliance de *nome de role* para **traits de role**
  (ex.: `requires_crea`) + capability de assinatura (`approval.technical_sign`). Sem isso, a V2
  quebra o pilar de compliance do produto.
- **G2 — Não existe estado "rejeitado".** `ApprovalRequest.STATUS_CHOICES` só tem
  pending/approved/cancelled. O aprovador hoje não consegue dizer **"não, e eis o porquê"** — que é
  metade do valor de um fluxo de aprovação. Reprovação com motivo obrigatório é V2.0.
- **G3 — Não há segregação de funções (SoD).** Um engenheiro pode solicitar aprovação da própria
  cotação e aprová-la ele mesmo (`approve_quotation` não compara solicitante×aprovador). Config
  por tenant "solicitante não aprova a própria solicitação", default **ligado** — mas com escape
  explícito para a fábrica de 1 engenheiro (ver G3 na seção 4).
- **G4 — E-mail de aprovação com roles hard-coded.** `audit/services.py:79` filtra destinatários
  por `role__in=[ROLE_ENGENHEIRO, ROLE_GESTOR_COMERCIAL]` — segundo ponto (além do enum) que
  explode com roles custom. Na V2, os destinatários derivam do **estágio corrente do workflow**
  (quem tem a capability aprovadora), nunca de nomes de role.
- **G5 — Aprovação condicional por valor é o killer feature do segmento** (não estava na visão).
  SAP release strategy vive disso: "PO > $100k → diretor aprova". Num SaaS de **cotação**, a regra
  "cotação acima de R$ X exige estágio extra do gestor/diretoria" é o argumento de venda mais forte
  do módulo — e é barato de adicionar depois que o builder existir (V2.1).

**Perguntas do Wellington respondidas com fonte** (seção 6): Q4 (baffle cut % — sim, % do diâmetro
interno do casco é o padrão; faixa recomendada 20–35%, típico 20–25%) e Q7 (designações TEMA mais
comuns e o que muda) — **fechadas**. Q3 (ângulos 30/45/60/90 — geometria e efeito no nº de tubos
confirmados; falta só o passo que a ENGEMATEX pratica) e Q5 (raio 1,5×OD confirmado TEMA;
comprimentos padrão de mercado = 20 ft/6,10 m, **6,95 m NÃO encontrado como padrão** — provável
prática de fornecedor local) — **parcialmente fechadas**.

---

## 1. O que já existe (F10) — base sobre a qual a V2 é construída

| Peça | Onde | Papel na V2 |
|---|---|---|
| Catálogo de 20 capabilities em código | `backend/apps/access/capabilities.py` (`CAPABILITIES`, fail-closed) | **REUSA como está.** Continua sendo a fonte da verdade "o que existe para permitir". Ganha ~4 capabilities novas de estágio (ver §3.2). |
| `RolePermission` (role × capability × allowed) | `backend/apps/access/models.py:20` | **REUSA.** Só muda o tipo da coluna `role`: de choice do enum para referência ao novo model `Role` (mesmos valores de chave → migração barata). |
| Enforcement + cache per-schema | `backend/apps/access/enforcement.py` (`role_can`/`user_can`/`require_capability`, cache `access:matrix:{schema}`) | **REUSA 100%.** O contrato `role_can(role_key, cap)` não muda; roles custom são só mais chaves na matriz. |
| `DEFAULT_MATRIX` + seeds idempotentes | `backend/apps/access/matrix.py` | **VIRA os templates.** `DEFAULT_MATRIX` é literalmente o conteúdo dos 5 templates iniciais (§3.1). |
| UI grade papel×capability + anti-lockout + audit | `backend/apps/access/views.py` (`access_config`, `toggle_permission`, `_last_access_manage`) | **REUSA a grade**; colunas passam a ser dinâmicas (roles do tenant). Anti-lockout generaliza (§4-G8). |
| `ApprovalStage` (key/label/order/required/approver_capability/is_builtin) | `backend/apps/access/models.py:47` | **EVOLUI.** Já tem quase tudo do builder; falta agrupar por tipo de ação (workflow) e instanciar por cotação (§3.2). |
| `TechnicalApproval` (CREA, snapshot_hash, revogação lógica) | `backend/apps/audit/models.py:8` | **REUSA como registro de compliance** do estágio técnico. Não vira genérico — continua sendo a "assinatura" com CREA. |
| `ApprovalRequest` (pending/approved/cancelled) | `backend/apps/audit/models.py:55` | **EVOLUI ou é substituído** pelo `ApprovalTask` por estágio (§3.3). Ganha estado `rejected` + motivo. |
| E-mail de solicitação | `backend/apps/audit/services.py:64-100` (`request_remote_approval`) | **REUSA o canal**, troca o critério de destinatário (hard-coded → capability do estágio corrente). |
| Gate de conversão | `production.services.is_convertible` → `_assert_convertible` | **REUSA o padrão** (front e back na mesma função); passa a consultar o estado do workflow, não só a aprovação técnica. |
| Poller de convertibilidade (HTMX 5 s) | `quotations detail.html` → `audit:convertibility_panel` | **REUSA o padrão de poller** para o badge do inbox (com cache por role — §3.3). |

**Princípio de continuidade:** a V2 **não reescreve** o F10 — promove enum→tabela, estágio→workflow,
request→task. Todo tenant existente migra por data migration sem mudança de comportamento observável
(mesmos 5 papéis, mesma matriz, mesmo gate técnico).

---

## 2. Modelo conceitual V2

```
CATÁLOGO (código, fail-closed — já existe)
  Capability ─ code, label, category, is_dangerous

ROLES COMO DADO (novo)
  RoleTemplate (código, versionado)          Role (tabela, por tenant)
    key, label, caps sugeridas, traits  ──►    key (slug), name, description
    "Orçamentista", "Engenheiro",              traits: requires_crea, is_admin_like
    "Gestor Comercial", "Somente leitura",     source_template + template_version (para diff)
    "Administrador"                            is_seeded (veio do provisionamento)
                                               └── RolePermission (já existe; role vira FK/key da tabela)
  UserProfile.role: enum ──► FK Role (mesmas keys nos 5 seeds → migração transparente)

FLUXO DE APROVAÇÃO (evolução do ApprovalStage)
  ApprovalWorkflow (por tenant)                ApprovalStage (já existe, ganha workflow FK)
    action_type: "of.convert" (V2.0)   ──►      key, label, order, required
    (V2.1+: "rate.change", limiares…)           approver_capability  ◄── continua! (ver nota A)
    is_active                                   is_builtin (CREA travado)

  WorkflowTemplate (código): "Só técnica (CREA)" [default=comportamento atual],
    "Técnica + Comercial", "Técnica + Comercial + Qualidade", "Do zero"

EXECUÇÃO (novo — o que alimenta o inbox)
  ApprovalCase (1 por cotação × workflow disparado)
    target (cotação), workflow_snapshot (JSON congelado — ver nota B), status, snapshot_hash
    └── ApprovalTask (1 por estágio do case)
          stage_key, status: pending|approved|REJECTED|skipped|invalidated
          decided_by, decided_at, reason (obrigatório em rejeição)
          link p/ TechnicalApproval quando stage=technical (registro CREA continua o mesmo)

INBOX
  Badge = count(ApprovalTask pending do estágio CORRENTE cujo approver_capability ∈ caps do MEU role)
  → o count é idêntico para todos os usuários do mesmo role → cache access:inbox:{schema}:{role}
```

**Nota A — por que o aprovador do estágio é uma CAPABILITY, e não um role direto.** O Rom pediu
"escolher qual role aprova". Na UI é exatamente isso que o admin vê ("Comercial aprova este passo").
Mas por baixo, o estágio guarda `approver_capability` (que **já existe** no model) e a UI, ao
selecionar a role, liga essa capability na matriz da role. Motivos: (1) reusa 100% do enforcement e
cache do F10, um único modelo mental — a matriz continua sendo a fonte da verdade de "quem pode o
quê"; (2) duas roles podem aprovar o mesmo estágio sem M2M novo; (3) deletar uma role não deixa
estágio órfão (fail-closed: ninguém com a capability → estágio insatisfazível → aviso na UI, ver
G8). A "tradução role↔capability" é responsabilidade da UI do builder, não do usuário.

**Nota B — workflow congelado por case (filosofia snapshot do produto).** "Cotação = snapshot, não
referência viva" já é decisão de domínio do SmartQuotation. O mesmo vale aqui: quando a primeira
aprovação de uma cotação é solicitada, o `ApprovalCase` congela a definição do workflow. Admin
mudar o fluxo no meio não muda casos em andamento (evita o caso de auditoria indefensável: "esta
cotação foi aprovada sob QUAL regra?"). Config nova vale para casos novos.

### Capabilities novas na V2.0 (registry estático, mantém o fail-closed)

O registry em código é um trunfo (deploy-time safety) — **não** o trocamos por capabilities
dinâmicas na V2.0 (ver G6). Adicionamos um conjunto FIXO de capabilities de aprovação:

| Code | Uso |
|---|---|
| `approval.technical_sign` | assinar o estágio técnico (exige trait `requires_crea` na role — dupla condição) |
| `approval.commercial_sign` | estágio comercial (gestor/diretoria) |
| `approval.quality_sign` | estágio de qualidade (comum em caldeiraria com ITP/ISO) |
| `approval.custom_sign_1..3` | estágios "do zero" (o admin renomeia o label do estágio; a capability é só o slot) |
| `role.manage` | criar/editar/excluir roles (separado de `access.manage` = editar matriz; admin pequeno pode querer delegar um sem o outro) |

3 slots custom cobrem o P95 dos fluxos reais (SAP limita a 8 níveis TOTAIS e a própria comunidade
SAP recomenda "keep it simple"; ServiceNow recomenda evitar cadeias longas — fontes na §5).
Registry dinâmico fica para V2.1 se algum cliente estourar os slots.

---

## 3. Especificação funcional

### 3.1 Roles como dado + templates

**Página "Papéis" (nova, sob Config, gate `role.manage`):**

- Lista de roles do tenant: nome, nº de usuários, origem (template X vN / do zero), traits.
- **"Novo papel"** → passo 1: escolher ponto de partida — um dos 5 templates **ou** "em branco";
  passo 2: nome + descrição; passo 3: a MESMA grade de capabilities do F10, pré-marcada pelo
  template, editável checkbox a checkbox (padrão Zabbix: parte do perfil-base e revoga/concede).
- **Template = CÓPIA no momento da criação, nunca link vivo** (lição AWS IAM: customer-managed
  policy copiada, não policy gerenciada compartilhada — mudança de template não altera roles de
  tenants silenciosamente). Guardamos `source_template + template_version`; quando lançarmos
  template v(N+1), a UI mostra aviso passivo "template atualizado — ver diff" (adotar/ignorar).
  Nunca aplicar automático.
- **Editar role**: mesma grade (a página `/config/` atual vira a visão "matriz completa", com
  colunas dinâmicas = roles do tenant).
- **Excluir role**: bloqueado se houver usuário ativo com a role → exige reatribuição em massa
  ("mover os 3 usuários para: [dropdown]"). Auditar (`role_change` já existe no `AccessLog`).
- **Traits (compliance — resolve o G1):**
  - `requires_crea` (bool): usuários desta role precisam de CREA (validação que hoje está presa em
    `role == "engenheiro"` passa a ler o trait). Seeds: True só no template "Engenheiro".
  - O estágio técnico exige `approval.technical_sign` **E** trait `requires_crea` na role do
    aprovador **E** CREA preenchido no perfil — a tripla que hoje é `role=="engenheiro" and
    crea_number`. O trait é editável, mas **remover `requires_crea` de uma role que tem
    `approval.technical_sign` ligado é bloqueado** (invariante de compliance, mesmo espírito do
    built-in CREA do F10).
- **Guard-rails**: limite de roles por tenant (sugestão: 15 — anti-sprawl, lição Jira §5);
  anti-lockout generalizado (G8); `is_dangerous` continua marcando capabilities sensíveis na grade.
- **Sem hierarquia/herança de roles** (decisão explícita — ver G9): roles são planas, templates dão
  o ponto de partida. GitHub mostra o custo da permissão aditiva multi-fonte ("mixed roles"
  warning); Zabbix é plano e todo mundo entende.

**Migração dos 5 papéis fixos** (invisível para o usuário):

1. Data migration cria as 5 `Role` com `key` idêntica ao enum (`viewer`, `orcamentista`,
   `engenheiro`, `gestor_comercial`, `admin`), marcadas `is_seeded`, traits corretos.
2. `UserProfile.role` (CharField) → FK por key. `rbac.user_role()` continua devolvendo a key
   (string) → `role_can(key, cap)` e o cache **não mudam**.
3. Pontos que comparam string de role a migrar para capability/trait (inventário do que achamos —
   check completo é tarefa de eng):
   - `accounts/models.py:44` CheckConstraint `engenheiro_requires_crea` → trait (a constraint de
     banco vira validação de aplicação + constraint no Role, já que o requisito agora é da role).
   - `audit/models.py:42` `TechnicalApproval.clean` → trait + capability.
   - `audit/services.py:79` destinatários do e-mail → quem tem a capability do estágio corrente.
   - Qualquer `ROLE_*` residual em views/templates (grep por `ROLE_ENGENHEIRO|ROLE_GESTOR|
     user_role(` na migração).
4. Os ~235 testes de RBAC continuam válidos (mesmas keys); ganhamos testes novos de role custom.

### 3.2 Builder de fluxos de aprovação

**Página "Fluxo de aprovações" (evolui a seção de estágios do `/config/` atual):**

- V2.0 tem **um** workflow: `action_type = of.convert` (conversão cotação→OF) — é o único gate real
  do produto hoje (`is_convertible`). A UI já nasce com o conceito de "tipo de ação" para não
  precisar redesenhar quando vierem outros (rate.change, material.write…).
- **Templates de fluxo**: "Somente técnica (CREA)" *(default — comportamento atual)*, "Técnica +
  Comercial", "Técnica + Comercial + Qualidade", "Montar do zero".
- **Editor**: lista ordenada de estágios (drag p/ reordenar `order`); por estágio: label, role(s)
  aprovadora(s) (dropdown de roles do tenant → liga a capability por baixo, Nota A), obrigatório
  sim/não. Estágio técnico: **travado** (is_builtin, não remove, não desliga — igual F10).
  Adicionar estágio custom consome um slot `approval.custom_sign_N`.
- **Semântica de execução (V2.0 — deliberadamente simples, modelo SAP "níveis sequenciais"):**
  - Estágios são **sequenciais** na ordem definida; o estágio corrente é o primeiro `required` não
    aprovado. Só tarefas do estágio corrente aparecem como acionáveis no inbox (evita aprovar
    comercial antes da técnica — e evita spam de badge).
  - Um estágio é satisfeito por **UMA** aprovação de qualquer usuário qualificado (quorum N-de-M,
    paralelo e condicional ficam para V2.1 — §7).
  - **Rejeição** (novo): qualquer estágio pode ser rejeitado com **motivo obrigatório** → o case
    inteiro vai para `rejected`; a cotação volta a editável; nova solicitação abre um case novo
    (histórico preservado). Resolve o G2.
  - **Invalidação por edição**: o case guarda o `snapshot_hash` da cotação (mesmo mecanismo do
    `TechnicalApproval.calculation_snapshot_hash`). Recalcular/editar a cotação com case em
    andamento → case `invalidated` (estágios já aprovados NÃO migram — recomeça; auditoria mantém
    tudo). Default conservador; "reaproveitar estágios não-técnicos" é refinamento V2.1 se doer.
  - **SoD** (resolve o G3): flag por tenant `solicitante não aprova a própria solicitação`,
    default **ligado**. Exceção operacional: se NENHUM outro usuário do tenant é qualificado para o
    estágio (fábrica de 1 engenheiro), a UI permite a auto-aprovação com aviso explícito e log
    destacado (`metadata.self_approved=true`) — melhor um escape auditado do que o cliente pequeno
    abandonar o fluxo.
- `production.is_convertible` passa a perguntar "o case ativo desta cotação está `completed`?" —
  mantendo o padrão fonte-única front/back (anti-flicker do F10 preservado).

### 3.3 Inbox "Aprovações" + badge

- **Menu**: item "Aprovações" com badge numérico (padrão de qualquer inbox). Zero pendências = sem
  badge (não "0").
- **Página** (evolui o `approval.panel_read` atual), duas abas:
  1. **"A aprovar"** — tarefas do estágio corrente que o MEU role está qualificado a decidir.
     Card: cotação (nº, título, cliente, valor), estágio, solicitante, quando, snapshot ok/desatualizado.
     Ações inline: **Aprovar** (estágio técnico → fluxo CREA/senha atual, `approve_presencial`/ART;
     demais estágios → confirmação simples) e **Rejeitar** (motivo obrigatório).
  2. **"Minhas solicitações"** — cases que EU abri, com stepper do progresso (técnica ✓ → comercial
     pendente…), quem falta, e motivo quando rejeitado.
- **Badge — performance**: enquanto não houver escopo por objeto (G10), a fila "a aprovar" é
  idêntica para todos os usuários do mesmo role → **1 count por (schema, role)**, cacheado
  (`access:inbox:{schema}:{role}`), invalidado nos eventos do case (criar/aprovar/rejeitar/
  invalidar). Poller HTMX reusa o padrão do painel de convertibilidade (5 s), custo ≈ 1 hit de
  cache por poll. (Se um dia houver escopo por objeto, o cache muda para por-usuário — decisão
  registrada para não ser surpresa.)
- **Notificações**: V2.0 = badge in-app + o e-mail que já existe (`request_remote_approval`),
  corrigido para mirar quem tem a capability do estágio corrente (G4). V2.1+ = lembrete/digest,
  escalonamento por SLA, Telegram/webhook (§7).

---

## 4. Análise de gaps — o que não estávamos enxergando

*(G1–G5 estão no sumário executivo; detalhes e demais gaps aqui.)*

| # | Gap | Impacto | Tratamento |
|---|---|---|---|
| **G1** | **CREA acoplado ao nome "engenheiro"** em `accounts/models.py:44` (CheckConstraint), `accounts/models.py:51` (clean) e `audit/models.py:42-45` (TechnicalApproval.clean). Roles custom quebram compliance silenciosamente. | ALTO — pilar de compliance | Traits de role (`requires_crea`) + capability `approval.technical_sign`; invariante: quem assina técnico tem trait+CREA. **V2.0, pré-requisito.** |
| **G2** | **Sem estado "rejeitado"** em `ApprovalRequest` (pending/approved/cancelled). Aprovador não consegue negar com motivo — o pedido apodrece pendente. | ALTO — metade do valor do fluxo | `ApprovalTask.rejected` + motivo obrigatório + case rejeitado reabre edição. **V2.0.** |
| **G3** | **Sem SoD**: solicitante pode se auto-aprovar (`approve_quotation` não compara requester×approver). Auditoria externa (ISO/cliente final da caldeiraria) reprova isso. | ALTO p/ venda a empresas maiores | Flag por tenant, default ON, com escape auditado p/ tenant de 1 engenheiro. **V2.0.** |
| **G4** | **Destinatários de e-mail hard-coded** (`audit/services.py:79`, `role__in=[engenheiro, gestor_comercial]`). Segundo acoplamento ao enum, fora do RBAC. | MÉDIO (bug latente na V2) | Derivar do estágio corrente (capability). **V2.0, junto da migração.** |
| **G5** | **Aprovação condicional por valor ausente da visão** ("cotação > R$ X → estágio extra"). É o padrão SAP release strategy e o argumento de venda nº 1 do módulo num produto de COTAÇÃO. | ALTO (oportunidade) | V2.1 — o builder ganha condição de disparo por faixa de valor. Modelar `ApprovalWorkflow` já com campo de condição vazio para não migrar depois. |
| **G6** | **Capabilities dinâmicas × registry fail-closed.** Estágios "do zero" pedem capability nova, mas o catálogo em código é uma proteção de deploy que não queremos perder. | MÉDIO | Slots estáticos `approval.custom_sign_1..3` (V2.0). Registry híbrido (estático + tabela de stage-caps) só V2.1+ se demanda real. |
| **G7** | **Config viva × caso em andamento**: admin edita o fluxo com 10 cotações no meio do pipeline — elas seguem a regra velha ou nova? Auditoria exige resposta determinística. | ALTO (auditoria) | `workflow_snapshot` congelado por `ApprovalCase` (filosofia snapshot já é DNA do produto). **V2.0.** |
| **G8** | **Anti-lockout precisa generalizar**: hoje protege "última célula access.manage" (`views.py:150`). Com roles custom: excluir role, desligar caps, ou desativar o último USUÁRIO de uma role admin-like também tranca o tenant. | MÉDIO | Invariante nova: sempre ≥1 role com `access.manage`+`role.manage` **que tenha ≥1 usuário ativo**. Checar em: toggle, exclusão de role, troca de role de usuário, desativação de membro. |
| **G9** | **Hierarquia/herança de roles** — tentação natural ("Engenheiro Sênior herda de Engenheiro"). | — | **Decisão: NÃO fazer.** Roles planas + templates. Herança cria o problema "mixed roles/aditivo" do GitHub e o efeito-cascata de grupo do Jira; Zabbix (plano) é o benchmark de simplicidade que o público-alvo entende. Reavaliar só com dor real. |
| **G10** | **Escopo por objeto** ("só as cotações que EU criei", "só clientes da minha carteira") — RBAC puro não expressa; é ABAC. | MÉDIO (vai aparecer no 3º-4º cliente) | Fora da V2.0/V2.1. Preparação barata AGORA: assinatura `user_can(user, cap, obj=None)` aceita objeto opcional (ignora por enquanto) — não quebra call-sites quando chegar. |
| **G11** | **Delegação/férias**: numa fábrica com UM engenheiro, ele viajar = pipeline parado. ServiceNow trata como first-class (fallback approver). | MÉDIO-ALTO no segmento | V2.1: "delegar minhas aprovações a [user qualificado] até [data]", com trilha (aprovado POR delegação DE). Estágio técnico: delegado também precisa trait+CREA (compliance não delega). |
| **G12** | **Permissão temporária / break-glass** (acesso elevado por tempo limitado). | BAIXO agora | V2.2+. Registrar apenas. |
| **G13** | **Multi-tenant / template drift**: template v2 sai depois de 30 tenants customizarem. Atualização automática = quebra silenciosa (anti-padrão AWS managed policy). | MÉDIO | Cópia-no-uso + `template_version` + diff opcional (§3.1). Seeds continuam `get_or_create` (nunca sobrescrevem custom — padrão já correto do `seed_access_matrix`). |
| **G14** | **Auditoria de config**: `AccessLog` já cobre `permission_change`/`approval_config_change`, mas mudanças de ROLE (criar/excluir/renomear/trait) e de WORKFLOW precisam de diff legível no metadata (antes/depois), senão a resposta a "quem deixou o estagiário converter OF?" é arqueologia. | MÉDIO | Ações novas no `AccessLog` + metadata com diff. **V2.0** (barato agora, caro depois). |
| **G15** | **Performance do enforcement**: inalterada (matriz cacheada por schema; roles custom só adicionam linhas). Pontos novos: badge (resolvido com cache por role, §3.3) e invalidação do cache de matriz também nos saves de `Role`. LocMem per-process continua ok single-node; multi-node → Redis (já anotado no T8 do F10). | BAIXO | Já endereçado no design. |
| **G16** | **Onboarding/empty-state**: tenant novo não pode cair numa página de builder vazia. | MÉDIO (é o momento "uau" da venda) | Provisionamento semeia os 5 roles-template + workflow "Somente técnica". Primeiro acesso ao builder mostra os templates como cards, não um formulário em branco. |

---

## 5. Benchmark de mercado — o que adotar / evitar

| Sistema | O que fazem | Adotar | Evitar |
|---|---|---|---|
| **Zabbix** (user roles 5.2+) | Role criada na UI marcando permissões de UI/API/ações, partindo de um "user type" base que é TETO de privilégio. | O fluxo de criação (partir de base + marcar/desmarcar checkboxes) — é exatamente a UX da nossa grade. | O conceito de "user type teto" (3 castas fixas) — nossa matriz plana + traits cobre sem a rigidez. |
| **GitHub** (custom org/repo roles) | Role custom = base role herdada + permissões finas adicionais; acesso é ADITIVO entre fontes (aviso "mixed roles"). | Base-role como ponto de partida (= nossos templates); rótulo de permissões perigosas. | Aditividade multi-fonte (usuário∈2 grupos+base+role custom = soma) — fonte única (1 usuário = 1 role) é mais auditável para o nosso porte. |
| **Jira** (permission schemes) | Schemes compartilhados entre projetos; roles contextuais vs groups globais; mudar um scheme compartilhado afeta N projetos sem aviso. | Separação "definição de permissões" × "quem ocupa" (nossa matriz × membros). | Compartilhamento implícito de config e efeito-cascata; sprawl de schemes → nosso limite de roles/tenant e diff no audit. |
| **AWS IAM** | Managed vs customer-managed vs inline policies; versionamento com rollback; least-privilege via análise de uso. | Template=cópia (customer-managed), versionamento de template, princípio least-privilege nos defaults (fail-closed já é assim). | A linguagem de policy genérica (JSON condicional) — poder infinito, UX hostil; nosso público é fábrica, não DevOps. |
| **ServiceNow** (approval flows) | Sequencial e paralelo, escalonamento, lembretes, DELEGAÇÃO/fallback approver nativos; recomendação: cadeias curtas, fallback para evitar gargalo. | Rejeição com motivo, delegação (V2.1), lembrete/SLA (V2.1), "evitar cadeias longas" como guard-rail de UX. | O motor genérico de workflow (Flow Designer) — over-engineering para 1 tipo de ação; nosso builder é lista ordenada, não grafo. |
| **SAP MM** (release strategy) | Release codes/groups; até 8 níveis; roteamento por VALOR do documento ("> $100k → diretor"); comunidade recomenda MINIMIZAR variantes de estratégia. | Sequencial-por-níveis como semântica default; **condição por valor** (G5, V2.1); "keep it simple" como limite de produto. | A combinatória de release groups/classes/características (CL02/CT04…) — notoriamente hostil; templates prontos existem para o cliente nunca ver essa complexidade. |

**Síntese em uma frase:** UX da Zabbix, templates-como-cópia do IAM, semântica sequencial-por-valor
do SAP, rejeição/delegação/SLA do ServiceNow — e a disciplina de NÃO construir o motor genérico de
workflow do ServiceNow nem a linguagem de policy do IAM.

Fontes: [Zabbix user roles](https://www.zabbix.com/documentation/current/en/manual/web_interface/frontend_sections/users/user_roles) · [Zabbix blog — user roles for the enterprise](https://blog.zabbix.com/user-roles-for-the-enterprise/12887/) · [GitHub custom org roles](https://docs.github.com/en/enterprise-cloud@latest/organizations/managing-peoples-access-to-your-organization-with-roles/permissions-of-custom-organization-roles) · [GitHub roles in an organization](https://docs.github.com/en/organizations/managing-peoples-access-to-your-organization-with-roles/roles-in-an-organization) · [Jira groups vs roles vs schemes](https://unitlane.net/articles/groups-vs-roles-vs-permission-schemes-in-jira/) · [AWS IAM managed vs inline](https://docs.aws.amazon.com/IAM/latest/UserGuide/access_policies_managed-vs-inline.html) · [ServiceNow Flow Designer approvals](https://www.servicenow.com/community/workflow-automation-articles/flow-designer-approvals-overview-workflow-automation-center-of/ta-p/2528202) · [SAP PO release strategy](https://www.michaelmanagement.com/blogs/sap/how-to-configure-sap-purchase-order-release-strategy) · [SAP release strategy best practices](http://www.saptechsupport.com/2021/05/setting-up-release-strategy-for-po-part.html)

---

## 6. Perguntas do Wellington — o que a pesquisa fechou

### Q3 — Ângulo de furação (30/45/60/90) — **PARCIALMENTE FECHADA (fonte)**

**Pesquisado com fonte:**
- Os 4 layouts padrão são: triangular **30°**, triangular rotacionado **60°**, quadrado **90°**,
  quadrado rotacionado **45°**. 30/45/60 são escalonados (staggered), 90 é alinhado.
- Passo mínimo TEMA: **1,25 × OD do tubo** (regra geral; passo maior quando precisa de limpeza
  mecânica ou solda tubo-espelho).
- **Efeito no custo é REAL, não só documental**: 30° dá a maior densidade de tubos (mais furos por
  área de espelho / menos casco para a mesma área térmica); 45°/90° são obrigatórios quando o lado
  do casco exige limpeza mecânica (deixam "faixas de limpeza"). Para mesmo passo e vazão, coeficiente
  e perda de carga caem na ordem 30° > 45° > 60° > 90°.
- Tradução para o motor: ângulo + passo determinam o Nº DE FUROS possível num dado espelho → furação
  (radial/CNC), tempo de mandrilagem e área perfurada. Ou seja: dá para o ângulo dirigir custo via
  contagem de furos com regra de norma, sem inventar número.

**Ainda precisa do Wellington:** o PASSO que a ENGEMATEX pratica por situação (usa 1,25×OD sempre?
quando abre para limpeza?), e se ele valida ligar o ângulo ao custo já ou manter documental na fase
atual (default proposto pelo Claude continua razoável até essa confirmação).

Fontes: [Thermopedia — Shell and Tube Heat Exchangers](https://www.thermopedia.com/content/1121/) · [WeBBusterZ — tube pitch Q&A](https://www.webbusterz.org/tube-pitch-in-heat-exchangers-questions-answers/) · [Altex — S&T design guide](https://www.altexinc.com/company-news/an-expert-guide-to-shell-tube-heat-exchanger-design/)

### Q4 — Baffle cut: % é o padrão? — **FECHADA (fonte)**

- **Sim**: a convenção da indústria expressa o corte da chicana segmental como **% do diâmetro
  interno do casco**.
- Faixas: segmental simples 15–45%; **boa prática: 20–35%**; **típico/ótimo: 20–25%** (melhor
  conversão de perda de carga em troca térmica). Abaixo de 20% ou acima de 35% = projeto pobre.
- **Recomendação de produto:** o form aceita **% (default 25%)** E mm ("altura restante", que é o que
  o motor usa — TEMA RCB-4, hc = OD − corte), com conversão bidirecional exibida. Armazenar mm
  (fonte da verdade do motor), mostrar os dois. Isso responde o "preciso saber" do Q4: **oferecer os
  dois, % como entrada primária** — é o vocabulário do data sheet TEMA que o cliente da ENGEMATEX manda.

Fontes: [ScienceDirect — Baffle Cut overview](https://www.sciencedirect.com/topics/engineering/baffle-cut) · [WeBBusterZ — baffles in heat exchangers](https://www.webbusterz.org/baffles-in-heat-exchangers/)

### Q5 — Comprimentos padrão + raio de curvatura U — **PARCIALMENTE FECHADA (fonte)**

**Pesquisado com fonte:**
- **Comprimentos preferenciais TEMA** (retos e U): **8, 10, 12, 16, 20 ft = 2,44 / 3,05 / 3,66 /
  4,88 / 6,10 m**. Na prática de mercado, tubo de trocador (ex.: ASTM A179) é vendido em **6 m /
  20 ft (6,096 m)** ou comprimento sob encomenda. 20 ft é o máximo "normal" para feixe removível;
  24 ft para espelho fixo.
- **O valor 6,95 m NÃO apareceu em nenhuma fonte como padrão de mercado.** Pode ser prática de
  fornecedor local/brasileiro — **não usar como default sem o Wellington confirmar.** Default mais
  defensável: **6,10 m (20 ft)** e **12 m**, ambos configuráveis por tenant (a V2 de RBAC não muda
  isso; é config de catálogo).
- **Raio de curvatura**: regra geral da indústria/TEMA: **R ≥ 1,5 × OD** para tubo de parede fina;
  TEMA RCB-2.3 dá a fórmula de espessura mínima antes da curva: **t₀ = t₁ × (1 + dₒ/4R)** (afinamento
  no extradorso); parede muito fina (t/D < 0,10) pede raio maior que 1,5×OD. Ou seja: o default
  proposto (1,5×OD) **tem base em norma** — falta só o Wellington dizer se a ENGEMATEX usa outro
  valor de casa.
- Fórmula do desenvolvido proposta (2×perna + π×R da curva, por fileira) é geometria pura — sem
  objeção; sinalizar emenda quando desenvolvido > comprimento padrão continua correto.

**Ainda precisa do Wellington:** confirmar/negar 6,95 m (e de onde vem); raio praticado na fábrica.

Fontes: [TEMA Standards (10ª ed., índice)](https://dl.gasplus.ir/standard-ha/Standard-CORROSION/TEMA_Standards_of_the_Tubular_Exchanger.pdf) · [Cheresources — standard tube lengths](https://www.cheresources.com/invision/topic/2041-standard-tube-lengths/) · [heat-exchanger-world — thermal design](https://heat-exchanger-world.com/shell-tube-heat-exchangers-thermal-design-and-optimization/) · [Solitaire — U-bend tubes](https://www.solitaire-overseas.com/blog/u-bend-tubes-in-heat-exchangers-design-fabrication-tolerances-failure-modes/) · [Eng-Tips — min radius U tubes](https://www.eng-tips.com/viewthread.cfm?qid=279948) · [Derbo — A179 6 m stock](https://www.derbosteelpipe.com/astm-a179-seamless-heat-exchanger-tube-19-05-x-2-11mm-length-6-meters.html)

### Q7 — Designações TEMA mais comuns — **FECHADA na parte de norma; job de calibração continua com o Wellington**

Designação = 3 letras: cabeçote dianteiro · casco · cabeçote traseiro. As mais relevantes para
caldeiraria pesada:

| Designação | O que é | Quando/por quê |
|---|---|---|
| **BEU** | Bonnet + casco E + feixe U removível | A MAIS comum; feixe removível mais econômico; U absorve dilatação diferencial. *(já calibrada a 0,0%)* |
| **BEM** | Bonnet + casco E + espelho fixo | A construção mais BARATA; serviço limpo, sem grande tensão térmica. *(já calibrada)* |
| **AES** | Canal removível A + casco E + cabeçote flutuante S (split-ring) | Padrão de REFINARIA para serviço sujo/fouling — limpeza mecânica dos dois lados; construção mais cara. |
| **AEU** | Canal A + casco E + feixe U | Variante do BEU com canal removível (acesso aos tubos sem desmontar tubulação). |
| **NEN** | Espelhos soldados ao casco e aos canais | Alta pressão (minimiza flanges e espessura de espelho). |

O que muda entre elas para o CUSTEIO: cabeçote dianteiro (A tem canal+tampa removível = mais peças
usinadas que o bonnet B), traseiro (M fixo = simples; S flutuante = anel bipartido, contra-flange,
mais usinagem; U = curvamento + referencial), e a consequência em feixe removível vs fixo (horas de
montagem/teste). Ordem típica de custo: BEM < BEU < AES.

**Ainda precisa do Wellington (inalterado):** QUAIS designações a ENGEMATEX quer custear a seguir e
**um orçamento real fechado de cada uma** para o seed de calibração — a norma diz o que muda
fisicamente, mas os pesos/horas do motor vêm de referencial (decisão de arquitetura correta; a
pesquisa não substitui).

Fontes: [Wermac — TEMA designations](https://www.wermac.org/equipment/heatexchanger_part5.html) · [Kasko — TEMA types BEM/AES/BEU](https://www.kaskomakine.com/blogs/shell-and-tube-heat-exchanger-tema-types) · [Mihir's Handbook — AEL/BEM/AES/AEU/AKU](https://chemicalprocessengineering.com/shell-and-tube-heat-exchangers-tema-types-ael-bem-aes-aeu-aku/) · [Enerquip — TEMA types](https://www.enerquip.com/tema-types-explained/) · [XLG — BEU/BKU/NEN/DEU](https://xlg-heattransfer.com/tema-designation-heat-exchangers-guide/)

### O que continua 100% com o Wellington (sem resposta de norma possível)

- **Q1** (taxas de hora-máquina da ENGEMATEX), **Q2** (nomes/ordem do roteiro do espelho na fábrica),
  **Q6** (aval do faseamento completo×partes), **Q8** (orçamentista converte OF no fluxo real),
  **Q9** (gestor_comercial edita config — nota: na V2 isso vira trivial, é dar `access.manage`/
  `role.manage` à role dele), **Q10** (estágios reais além do técnico — nota: na V2 a resposta dele
  vira apenas a escolha do TEMPLATE de fluxo; a mecânica não bloqueia mais).

---

## 7. Faseamento

### V2.0 — o mínimo que destrava venda multi-empresa

1. **Roles como dado** (model Role + traits + migração enum→FK + G1 resolvido) — pré-requisito de tudo.
2. **5 templates de role** (conteúdo = `DEFAULT_MATRIX` atual) + página "Papéis" (criar de template/
   do zero, editar na grade, excluir com reatribuição, anti-lockout G8, limite de roles).
3. **Capabilities de estágio estáticas** (`technical_sign`/`commercial_sign`/`quality_sign`/
   `custom_1..3` + `role.manage`).
4. **Builder sequencial para `of.convert`** (templates de fluxo + do zero; técnico built-in travado;
   case/task com snapshot congelado G7; **rejeição com motivo G2**; **SoD default-on G3**;
   invalidação por edição).
5. **Inbox "Aprovações"** (2 abas + badge com cache por role) + e-mail corrigido para capability (G4).
6. **Auditoria com diff** para role/workflow (G14) + empty-states de onboarding (G16).

*Critério de pronto V2.0: um tenant novo, sem tocar em nada, se comporta EXATAMENTE como o F10 hoje
(5 papéis, gate técnico único); e um tenant que queira "Diretor Comercial aprova depois do
engenheiro" monta isso sozinho em < 5 minutos, sem suporte.*

### V2.1 — diferenciação comercial

- **Condição por valor no workflow (G5)** — "cotação > R$ X adiciona estágio Y". Prioridade máxima da V2.1.
- **Delegação/férias (G11)** + lembretes + SLA/escalonamento ("pendente > N dias → notificar role Z").
- Quorum N-de-M e estágios paralelos (só se cliente real pedir — ServiceNow/SAP ensinam a resistir).
- Canais extra: Telegram/webhook (o público de chão de fábrica vive no WhatsApp/Telegram — avaliar
  na pesquisa de cliente), digest diário.
- Workflows para outras ações (`rate.change`, `material.write` — aprovação de mudança de preço).
- Diff de template ("template Engenheiro v3 disponível — comparar").

### V2.2+ — quando o produto crescer

- Registry híbrido de capabilities (estágios ilimitados) (G6).
- Escopo por objeto/ABAC (G10) — carteira de clientes, "minhas cotações".
- Permissões temporárias/break-glass (G12).
- Relatório de aprovações (lead time por estágio — vira métrica de venda: "seu gargalo é a
  aprovação comercial, 4,2 dias em média").

---

## 8. Decisões abertas para Rom (produto) — nenhuma bloqueia o início da V2.0

1. **Nome do menu**: "Aprovações" (recomendado) vs "Pendências" vs "Minha fila".
2. **Limite de roles por tenant**: 15 é um bom teto? (anti-sprawl; sobe por plano se precisar —
   pode inclusive virar alavanca de pricing por plano).
3. **SoD escape** (auto-aprovação auditada quando não há outro qualificado): confortável para
   compliance, ou preferimos bloquear e forçar 2º usuário?
4. **`role.manage` separado de `access.manage`** (recomendado) ou uma capability só?
5. Monetização: roles custom + builder são feature de plano superior? (Zabbix/GitHub cobram
   fine-grained em tiers altos — precedente de mercado a favor.)
