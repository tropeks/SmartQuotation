# SAP B1 Pilot Runbook

## Escopo

Este runbook cobre o slice H2.7a manual/admin-only:

- `apps.integrations.sap_b1` registrado como app tenant-scoped
- healthcheck operacional exposto no admin
- export manual de OF a partir de `OrdemFabricacaoAdmin`

Não cobre automação por release/conclusão nem sincronização bidirecional.

## Operação

1. Verifique o healthcheck em `/admin/sap-b1/health/`.
2. No admin de produção, selecione uma ou mais OFs e execute `Exportar OF selecionadas para SAP B1`.
3. Confirme que a ação publicou a fila do conector e que o service do app retornou o run esperado.
4. Se a publicação falhar, reenfileire pela própria action do admin depois de corrigir credenciais, base URL ou indisponibilidade transitória.

## Contrato atual do app

- O app `apps.integrations.sap_b1` expõe:
  - `run_healthcheck()`
  - `maybe_enqueue_sales_order_sync()` / `enqueue_sales_order_sync()`
  - `maybe_enqueue_bom_sync()` / `enqueue_bom_sync()`
  - `enqueue_sync_run_async()`
- O service é tenant-aware e usa o schema corrente para publicar a tarefa assíncrona.

## Triage rápido

- Se o healthcheck retornar 503, valide o `base_url`, credenciais e disponibilidade do Service Layer.
- Se a action do admin não publicar nada, verifique se os enqueues de `sales_order` e `bom` retornaram `None` ou se o `enqueue_sync_run_async()` falhou.
- Se houver inconsistência após export manual, trate o SAP B1 como destino operacional, não como source of truth.
