# Briefing para Fable 5 (CEO/spec) — RBAC & Aprovações V2

> **De:** Claude (dev/arquiteto) · **Para:** Fable 5 · **Data:** 2026-07-17
> **Seu papel (metodologia):** CEO/spec — você DOCUMENTA a visão de produto e valida com Rom/Wellington, **sem codar**. Produza uma spec de produto + análise de gaps + pesquisa de mercado. Não implemente.

## Produto
SmartQuotation — SaaS **multi-tenant** de cotação técnico-comercial para caldeiraria média/pesada (trocadores de calor casco-tubo, norma TEMA). Design partner: ENGEMATEX. Django 5.2 + django-tenants (schema-per-tenant), session auth, HTMX/Alpine, Design System G.

## O que JÁ existe (sprint F10, mergeada na main hoje — `origin/main`)
Ver `docs/discovery/F10_RBAC_CONFIG_PLAN.md` para detalhe. Resumo:
- **Catálogo de capabilities** (`apps/access/capabilities.py`): 21 capabilities em código (ex.: `quotation.create/write/read`, `of.convert`, `of.transition`, `itp.manage`, `approval.*`, `rate.change/edit`, `material.read/write`, `proposal.write`, `members.manage`, `access.manage`).
- **Matriz papel×capability por tenant** (`RolePermission`, model): editável, fail-closed. Enforcement via `require_capability("cap")` (substituiu `require_role`), com cache per-tenant.
- **5 papéis FIXOS** (enum `UserProfile.ROLE`): viewer, orcamentista, engenheiro, gestor_comercial, admin. **← LIMITAÇÃO: papéis são hard-coded, não dá pra criar do zero.**
- **Página "Acessos"** (`/config/`, só admin): grade papel×capability com toggles HTMX, anti-lockout, auditoria.
- **Fluxo de aprovações (parcial)**: model `ApprovalStage` (key/label/order/required/approver_capability/is_builtin). `is_convertible` já consulta os estágios `required=True`. Só o estágio built-in **technical (CREA)** está semeado + com resolver; **estágios custom + "quem aprova cada um" estão como STUB** (esperando definição de domínio).
- **Aprovações já existentes** (app `audit`): `TechnicalApproval` (CREA), `ApprovalRequest` (pending/approved/cancelled), `request_remote_approval`, `approve_presencial`. Há maquinário de aprovação, mas não um inbox por usuário.

## Visão V2 do Rom (o que ele quer que você especifique)
1. **Permissões 100% configuráveis + templates de boas práticas.** Estilo **Zabbix**: criar uma role **do zero** selecionando o que ela permite (capability a capability), MAS o sistema já vem com **templates pré-configurados por boas práticas da indústria** (ex.: "Orçamentista", "Engenheiro", "Gestor", "Somente leitura", "Admin") que o tenant usa como ponto de partida e ajusta. Papéis viram DADO por tenant, não enum fixo.
2. **Fluxos de aprovação configuráveis + templates + criação do zero** (paralelo às roles): o usuário escolhe, para **cada tipo de acesso/ação**, **qual role precisa aprovar**. Vir com fluxos pré-configurados de boas práticas + builder do zero.
3. **"Minhas aprovações pendentes"** no perfil de cada usuário — uma caixa/inbox com **notificação numérica** de quantas aprovações estão pendentes para aquele usuário (badge). Nome pode ser melhor que "minhas aprovações pendentes" — sugira.

## O que o Rom pediu explicitamente de VOCÊ (Fable)
- Pegue essas ideias + o que já existe e **veja o que a gente NÃO está enxergando** — gaps, riscos, casos de uso, no domínio de permissões E de aprovações.
- **Pesquise boas práticas de mercado** (RBAC/ABAC, role templates, approval workflow engines) — referências úteis: Zabbix (user roles), Jira/Confluence (permission schemes + approval workflows), GitHub (org roles/rulesets), AWS IAM (policies), SAP/ERP de manufatura (release strategies/approval em ordens), ServiceNow (approval rules). Traga o que se aplica a um SaaS ETO de caldeiraria.
- **Talvez, pesquisando, você responda algumas das perguntas que fizemos ao Wellington** (ver `docs/discovery/WELLINGTON_DECISOES_2026-07-17.md`) — especialmente onde há resposta padrão de indústria/norma:
  - Q3 ângulo de layout de furação de trocador (30/45/60/90) e efeito no passo/nº de furos (TEMA/norma).
  - Q4 baffle cut convenção (% do diâmetro é o padrão TEMA? faixas típicas 20–35%?).
  - Q5 tubo em U desenvolvido: comprimentos padrão de tubo de mercado (6,10 m? 6,95 m? 12 m?) e raio mínimo de curvatura (regra TEMA RCB ~ 1,5×OD? por bitola?).
  - Q7 designações TEMA (BEU, BEM, AES, …) — quais são mais comuns em caldeiraria pesada e o que muda entre elas.
  Marque claramente o que é **resposta pesquisada com fonte** vs **ainda precisa do Wellington** (nunca invente número de engenharia sem fonte).

## Entregável esperado (documento, sem código)
1. **Spec de produto RBAC & Aprovações V2**: modelo conceitual (roles-como-dado, templates, capability sets, approval workflow builder, inbox de aprovações + badge), fluxos de UX, e como evolui a partir do F10 que já existe (o que reusa: capabilities/RolePermission/ApprovalStage; o que muda: papéis viram dado, novos models de role/template/approval-instance).
2. **Análise de gaps** — o que não estamos vendo: ex. papéis customizados vs os 5 fixos e migração; herança/hierarquia de roles; permissões temporárias/delegação; escopo por objeto (ex.: só cotações que eu criei); aprovação multi-nível/paralela vs sequencial; SLA/escalonamento; notificação (in-app/email/telegram); como o inbox de aprovações se liga ao `ApprovalRequest`/`TechnicalApproval` que já existem; impacto multi-tenant; auditoria; performance do enforcement.
3. **Benchmark de mercado** com o que adotar/evitar.
4. **Respostas pesquisadas às perguntas do Wellington** que couberem, com fontes; e a lista do que ainda precisa dele.
5. **Recomendação de faseamento** (o que é V2.0 mínimo vs V2.1+), lembrando que o F10 (toggle por capability + estágio técnico) JÁ atende a ENGEMATEX hoje — a V2 é generalização para vender a mais empresas.

Seja concreto e cite os arquivos/models reais do F10. Priorize profundidade de produto sobre extensão. Use pesquisa web onde ajudar.
