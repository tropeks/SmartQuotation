# Integração Nomus API

Status: pesquisa + design inicial para Epico 2.

## Objetivo

Definir o contrato minimo para exportar uma Ordem de Fabricacao do SmartQuotation para o Nomus, levando:

- lista de material da OF
- roteiro de fabricacao / operacoes
- horas por operacao

Esta versao nao faz wiring de producao. O foco e fixar a interface e o comportamento esperado para as proximas tasks.

## O que foi confirmado na documentacao publica

- A integracao Nomus e REST + JSON.
- O padrao de verbos informado e `POST`, `GET`, `PUT` e `DELETE`.
- As requisicoes seguem o formato `endereco_do_erp/nome_do_contexto/rest/nome_do_servico`.
- A autenticacao usa o header `Authorization`.
- O valor do header e `Basic <chave em Base64>`.
- O `Content-Type` precisa ser `application/json`.
- A chave de integracao fica na configuracao geral do ERP, no campo de chave de acesso para integracao via REST.
- A documentacao publica exposta na central ajuda confirma recursos de dominio como:
  - produtos
  - pedidos
  - rotas
  - grupos de produto
  - documentos de estoque
  - notas fiscais
- A documentacao de producao publica mostra que o Nomus trata roteiro de producao, centros de trabalho, recursos e ordens de producao como conceitos de dominio de primeira classe.

## O que ficou como suposicao

Nao encontrei, na documentacao publica acessivel, um artigo que detalhe o endpoint de criacao/alteracao de ordem de producao ou um contrato formal para BOM e roteiro de fabricacao.

Para nao bloquear a sprint, o contrato abaixo e uma proposta de integracao alinhada com as necessidades do SmartQuotation e com o padrao dos outros adapters internos.

## Credenciais necessarias

### Confirmado

- `base_url`
  - URL base do ERP, incluindo o contexto quando necessario.
- `access_key`
  - chave usada para montar `Authorization: Basic <base64>`.

### Ainda a validar com o cliente

- Se existe algum identificador adicional por empresa/filial.
- Se o contexto REST varia por ambiente, por exemplo `/erp`, `/cliente`, `/nomus`, etc.
- Se a chave REST e unica por instancia ou por empresa.
- Se ha expiracao, rotacao ou escopo por usuario.

## Interface proposta para o client

O pacote `apps.integrations.nomus` segue o mesmo formato dos adapters existentes:

- `BaseNomusClient`
- `HttpNomusClient`
- `MemoryNomusClient`

Metodos principais:

- `upsert_production_order(payload)`
- `upsert_bom(payload)`
- `upsert_routing(payload)`
- `get_order_status(remote_id)`
- `healthcheck()`

## Contrato assumido

### Ordem de fabricacao

Endpoint assumido:

- `POST /rest/ordens-producao`
- `GET /rest/ordens-producao/{remote_id}`

Payload assumido:

```json
{
  "external_id": "OF-2026-0001",
  "order_number": "OF-2026-0001",
  "product_code": "TX-100",
  "product_description": "Trocador de calor",
  "quantity": 1,
  "unit": "un",
  "status": "planejada",
  "bom": [
    {
      "component_code": "MAT-001",
      "description": "Chapa SA-516-70",
      "quantity": 2.5,
      "unit": "kg",
      "scrap_percent": 0
    }
  ],
  "routing": [
    {
      "sequence": 10,
      "operation_code": "OP-CORTE",
      "operation_description": "Corte",
      "work_center_code": "WC-CORTE",
      "hours": 1.5
    }
  ]
}
```

### Lista de material

Endpoint assumido:

- `POST /rest/listas-materiais`

Payload assumido:

```json
{
  "external_id": "BOM-OF-2026-0001",
  "order_number": "OF-2026-0001",
  "items": [
    {
      "component_code": "MAT-001",
      "quantity": 2.5,
      "unit": "kg"
    }
  ]
}
```

### Roteiro de fabricacao

Endpoint assumido:

- `POST /rest/roteiros`

Payload assumido:

```json
{
  "external_id": "RTE-OF-2026-0001",
  "order_number": "OF-2026-0001",
  "operations": [
    {
      "sequence": 10,
      "operation_code": "OP-CORTE",
      "work_center_code": "WC-CORTE",
      "hours": 1.5
    }
  ]
}
```

## Tratamento de erros e conflitos

### Classificacao

- `408`, `429` e `5xx` devem ser tratados como transientes.
- `4xx` fora de `429` devem ser tratados como permanentes.
- Timeout e falha de conexao sao transientes.

### Conflito

Quando o ERP indicar conflito de duplicidade ou recurso ja existente, o export deve ser tratado como conflito de negocio, nao como erro tecnico transitavel.

Assuncao pratica para a proxima task:

- `409 Conflict` ou mensagem equivalente = conflito
- a exportacao nao deve ser reenfileirada automaticamente
- o log precisa manter o `remote_id` ja conhecido

### Reexportacao

Se a OF ja tiver identificador remoto, a estrategia preferida sera `upsert`:

- atualizar se o registro existir
- criar se ainda nao existir

Se o endpoint real nao suportar upsert, a camada de servico vai precisar diferenciar create vs update depois da validacao com o cliente.

## O que precisa ser validado com o cliente Nomus

- Nome real dos endpoints de ordem, BOM e roteiro.
- Se o order payload aceita estrutura aninhada ou exige chamadas separadas.
- Nome real dos campos de horas da operacao.
- Se a operacao referencia recurso/centro de trabalho obrigatoriamente.
- Como o Nomus sinaliza conflito de ordem ja existente.
- Como consultar status real da ordem exportada.
- Se existe suporte a idempotencia por chave externa.

## Referencias publicas usadas

- https://www.nomus.com.br/erpindustrial/como-funciona/api/
- https://atendimento.nomus.com.br/hc/pt-br/articles/35195281009819-Introdu%C3%A7%C3%A3o-%C3%A0-integra%C3%A7%C3%A3o-com-API-REST
- https://atendimento.nomus.com.br/hc/pt-br/articles/35195290872219-Produtos
- https://atendimento.nomus.com.br/hc/pt-br/articles/35195296759579-Rotas
- https://atendimento.nomus.com.br/hc/pt-br/articles/49221239598491--Guia-R%C3%A1pido-Aplica%C3%A7%C3%B5es-do-produto-template
- https://atendimento.nomus.com.br/hc/pt-br/articles/35195251431579--Guia-R%C3%A1pido-Integra%C3%A7%C3%A3o-com-eCUBUS

