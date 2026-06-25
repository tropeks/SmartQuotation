# OMIE_NFE_RUNBOOK

Runbook curto para a operação inicial do conector Omie no SmartQuotation.

## Escopo atual

- emissão assistida de NF-e via Omie a partir de OF concluída
- config Omie por tenant
- documento fiscal mínimo por OF
- runs/attempts assíncronos
- admin operacional por tenant
- healthcheck admin-only em `/admin/omie/health/`

## Pré-requisitos por tenant

- `enabled=True`
- `app_key`
- `app_secret`
- `company_code`
- `environment`
- `emit_on_of_completed`
- `fiscal_defaults.base_url`

Dados mínimos de cliente para emitir:

- `cnpj`
- `city`
- `state`

## Operação diária

1. Faça login no admin do tenant com usuário staff/superuser.
2. Abra `Integracoes - Omie > Configuracoes Omie`.
3. Confirme se a integração está ativa e se `emit_on_of_completed=True`.
4. Use `Ver status` para inspecionar o healthcheck.
5. Monitore `OmieFiscalDocument` e `OmieInvoiceRun`.
6. Reenfileire apenas runs falhos após corrigir a causa.

## Leitura rápida do estado

- `200 OK` indica healthcheck operacional satisfatório.
- `503` indica integração habilitada com falha operacional/remota.
- `failed_runs > 0` pede triagem antes de reenfileirar.

## Rollback operacional

- desligar `enabled` na config do tenant
- interromper reenfileiramentos manuais
- corrigir defaults fiscais, credenciais ou dados do cliente
- reenfileirar apenas documentos necessários

## Limites aceitos

- slice Omie-only; Bling ficou fora
- sem motor fiscal completo
- sem cancelamento/carta de correção
- status remoto armazenado é o retornado pela Omie no envio
