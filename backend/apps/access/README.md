# apps.access — RBAC configurável (F10)

Permissões por perfil deixam de ser tuplas hardcoded (`_OF_CONVERT_ROLES` etc.) e
passam a ser uma matriz **papel × capability** editável por tenant, com fallback
fail-closed em toda ponta do sistema.

## Modelo

- **`capabilities.py`** — o *catálogo* (`CAPABILITIES`): o conjunto de ações
  protegíveis que EXISTEM no sistema (`quotation.create`, `of.convert`,
  `material.write`, ...). Vive em **código**, não em banco — é análogo a
  `accounts.rbac.ROLE_GROUPS`. Cada entrada tem `label`, `description`,
  `category` (agrupamento na UI) e `is_dangerous` (metadado de apresentação, não
  afeta enforcement).
- **`RolePermission`** (model, por tenant) — a *matriz*: quem PODE cada
  capability (`role`, `capability`, `allowed`). É o que a UI de configuração
  edita. Complementa os Django Groups (não os substitui; `ensure_groups()`
  continua rodando).
- **`enforcement.py`** — a leitura fail-closed da matriz:
  - `role_can(role, cap)` — papel pode a capability? Cache per-schema.
  - `user_can(user, cap)` — idem, resolvendo o papel do usuário; usado nas
    flags de contexto de template (`can_edit_prices`, `can_convert`, ...).
    **Mesma fonte no render inicial e nos pollers HTMX** — variar a fonte é o
    que causa o flicker do botão "Converter em OF" (ver `tests_flicker.py`).
  - `require_capability(cap, allow_platform_staff=False)` — decorator de view,
    mesma semântica de `accounts.rbac.require_role` (anônimo → login;
    autenticado sem a capability → 403).
- **Fail-closed em toda ponta**: papel sem linha `allowed=True` → nega. Papel
  `None`/usuário sem perfil → nega. **Capability desconhecida do catálogo →
  nega** (nunca é tratada como "permitido por omissão").

## Como adicionar uma capability nova

1. Cadastre o `code` em `CAPABILITIES` (`capabilities.py`) com `label`,
   `description`, `category` e `is_dangerous`.
2. Adicione o code (e o default por papel) em `DEFAULT_MATRIX`
   (`matrix.py`), refletindo o comportamento atual antes da mudança (ou o
   default conservador combinado com o time, se for capability nova de fato).
3. Rode `seed_access_matrix` (idempotente, tenant-aware) para semear a linha
   em cada schema — ou deixe a migration de dados fazer isso em
   `migrate_schemas`.
4. Use `@require_capability("seu.code")` na view e/ou `user_can(request.user,
   "seu.code")` na flag de contexto de template.
5. `manage.py test apps.access.tests_registry_integrity` cobre o passo 1: se
   você usar o code no decorator/flag mas esquecer de cadastrá-lo no
   catálogo, o teste falha listando o code órfão (fail-closed de DEPLOY, não
   só de runtime — pega no CI antes de virar "todo mundo perdeu acesso a X"
   silenciosamente em produção).

## Cache da matriz — LocMemCache per-process

Sem `CACHES` customizado no `settings`, o backend de cache é o
`LocMemCache` **por processo**. A matriz (`access:matrix:{schema}`) é
invalidada via signal `post_save`/`post_delete` de `RolePermission`
(`signals.py`), mas essa invalidação só alcança o processo que recebeu a
escrita.

**Em deploy single-node (1 processo/worker) isso é suficiente.** Em deploy
**multi-node/múltiplos workers** (vários processos Gunicorn/Uvicorn, várias
réplicas), uma alteração de permissão feita num processo NÃO invalida o
cache dos outros — usuários podem continuar vendo o comportamento antigo
(permitido/negado) até o TTL de 300s expirar nos demais processos.

**Antes de escalar para multi-node**, migrar `CACHES` (settings) para Redis
(já usado pelo Celery neste projeto) — o `cache.delete()` do signal passa a
invalidar todos os processos, não só o que fez a escrita.

## Testes desta app

- `tests.py` / `tests_enforcement.py` — `role_can`/`user_can`/
  `require_capability` (fail-closed em cada combinação).
- `tests_matrix.py` — `DEFAULT_MATRIX`/`seed_access_matrix` (idempotência,
  paridade com as tuplas legadas).
- `tests_flicker.py` — paridade render vs. poller de `can_convert` por papel.
- `tests_views.py` — UI de configuração (`access.manage`, anti-lockout).
- `tests_registry_integrity.py` (T8) — nenhum `require_capability(...)`/
  `user_can(..., ...)` em `views.py`/`api.py` de qualquer app referencia um
  code fora do catálogo.
