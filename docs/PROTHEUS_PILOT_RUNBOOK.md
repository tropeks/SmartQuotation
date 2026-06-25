# PROTHEUS_PILOT_RUNBOOK.md — H2.5.2

> **Status:** Operacional para piloto assistido | **Última revisão:** 2026-06-25

---

## 1. Objetivo

Este documento amarra a operação real do conector TOTVS Protheus no piloto do SmartQuotation
após a entrega de H2.5.2.

Escopo coberto pelo código atual:

- export assíncrono de OF no `release`
- pull recorrente de catálogo via beat global único
- import assistido de materiais e fornecedores por staging
- snapshots remotos de OF/BOM
- healthcheck operacional por tenant no admin
- retry automático apenas para falhas transitórias

Fora do escopo atual:

- autoaplicação de staging no domínio
- monitoramento externo com alertas automáticos
- lock distribuído para impedir sobreposição de pulls
- contrato dinâmico de cadência via banco/admin

---

## 2. Pré-requisitos por tenant

Cada tenant piloto precisa ter exatamente uma `ProtheusIntegrationConfig` habilitada no próprio schema,
com os campos abaixo preenchidos conforme o ambiente do ERP:

- `enabled = True`
- `base_url`
- `company_code`
- `branch_code`
- `environment`
- `auth_type`
- `username` e `password`, ou `token`
- `timeout_seconds`

Feature flags operacionais por tenant:

- `export_on_release`
- `pull_materials_enabled`
- `pull_suppliers_enabled`
- `pull_work_orders_enabled`

Premissas do piloto:

- o endpoint Protheus é alcançável a partir do worker Celery
- as credenciais são exclusivas do tenant piloto
- a equipe do piloto aceita operação assistida no catálogo
- o Protheus tolera retry em chamadas transitórias sem efeito colateral indevido

---

## 3. Contrato operacional vigente

### 3.1 Push SmartQuotation → Protheus

Evento disponível hoje:

- liberação de `OrdemFabricacao` enfileira export assíncrono quando `export_on_release=True`

Entidade exportada:

- `work_order`

Comportamento:

- a OF gera `ProtheusSyncRun` com `idempotency_key` determinística por payload
- a task `integrations.protheus.process_sync_run` faz retry só em erro transitório
- sucesso/falha deixam trilha em `ProtheusSyncAttempt`

### 3.2 Pull Protheus → SmartQuotation

Entidades puxadas hoje:

- `materials`
- `suppliers`
- `work_orders`

Comportamento:

- materiais e fornecedores entram em `ProtheusCatalogStaging`
- OFs/BOMs remotas entram como snapshot
- staging não é aplicado automaticamente ao domínio

---

## 4. Scheduler e cadência

O pull recorrente usa um único beat global do app Celery.

- task dispatcher: `integrations.protheus.dispatch_recurring_pulls`
- cadência default: a cada 15 minutos
- configuração: `PROTHEUS_PULL_INTERVAL_MINUTES`
- critério de despacho: apenas tenants `is_active=True` com `ProtheusIntegrationConfig.enabled=True`

Implicação operacional:

- ajustar a cadência exige alterar a env do serviço e reiniciar o beat
- não existe cadência diferente por tenant no H2.5.2

Risco aceito no piloto:

- o sistema evita sobreposição de pull recorrente do mesmo tenant com advisory lock por schema
- ainda não existe fila inteligente por tenant além do lock simples do pull

---

## 5. Rotina de operação assistida

### 5.1 Healthcheck

Endpoint disponível apenas no admin do tenant:

- `GET /admin/protheus/health/`

Esse healthcheck resume:

- integração habilitada ou não
- `last_healthcheck_at`
- quantidade de runs pendentes e falhas
- quantidade de staging pendente
- último run, último sucesso e última falha
- status remoto do endpoint `/health` do Protheus

Também existem admin actions em `ProtheusIntegrationConfig` para:

- executar healthcheck operacional
- enfileirar pull de catálogo sob demanda

### 5.2 Staging de catálogo

Fluxo operacional esperado:

1. executar o pull recorrente ou manual
2. revisar `ProtheusCatalogStaging` no admin do tenant
3. aplicar apenas itens validados pelo responsável funcional
4. rejeitar itens inconsistentes com justificativa operacional

Responsabilidades humanas:

- time SmartQuotation: acompanhar sync, falhas e staging
- responsável do piloto: validar material/fornecedor antes da aplicação
- ninguém deve assumir autoaprovação no piloto

### 5.3 Reenfileiramento

`ProtheusSyncRun` no admin permite reenfileirar runs terminais.

Regra atual:

- runs já `pending` são ignorados
- ao reenfileirar, o run volta para `pending`, limpa erro e registra `requeued_at`

---

## 6. Diagnóstico rápido

### 6.1 Falha remota no healthcheck

Verificar:

- `base_url`
- credenciais
- conectividade do worker para o endpoint Protheus
- timeout configurado

### 6.2 Runs falhando

Verificar no admin:

- `ProtheusSyncRun.error_message`
- histórico de `ProtheusSyncAttempt`
- se a falha foi marcada como transitória em `result_payload.transient`

Tratamento:

- se transitória, aguardar retries automáticos
- se persistente, corrigir causa e reenfileirar manualmente

### 6.3 Catálogo inconsistente

Tratamento:

- não aplicar staging duvidoso
- rejeitar com razão operacional
- repetir o pull após correção no ERP, se necessário

---

## 7. Rollback operacional

O H2.5.2 não introduz rollback automático cross-system.

Procedimento conservador do piloto:

1. desabilitar `enabled` na `ProtheusIntegrationConfig` do tenant se a integração precisar parar
2. interromper ações manuais de aplicar staging
3. manter histórico de `SyncRun` e `SyncAttempt` para auditoria
4. corrigir configuração/endpoint/credencial
5. reativar a integração e reenfileirar apenas runs necessários

Se o problema for apenas de catálogo:

1. deixar staging pendente ou rejeitado
2. não alterar o catálogo local até validação humana

---

## 8. Riscos residuais aceitos no piloto

- cadência do pull fixa em código, não governada por banco/admin
- sem lock distribuído entre pulls sucessivos do mesmo tenant
- healthcheck retorna JSON operacional, mas não integra alerta externo
- retry depende de idempotência prática do lado Protheus para chamadas repetidas
- catálogo continua assistido; não há sincronização automática autoritativa

Esses riscos são aceitos para o tenant piloto porque preservam operação conservadora e reversível,
com humano no loop para catálogo e ação explícita para retomar sync.
