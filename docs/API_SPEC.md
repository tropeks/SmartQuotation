# API_SPEC.md — SmartQuotation

> **Status:** Contrato alvo aprovado; contrato H1 atual documentado no topo | **Versão:** 1.0 | **Referência:** ARCHITECTURE.md, DATA_MODEL.md

---

## 1. Convenções Gerais

### Base URL
```
https://{tenant_slug}.smartquotation.com.br/api/v1/
```

### Autenticação
Para o contrato alvo pós-H1/H1.5 documentado nesta seção, todos os endpoints (exceto os marcados `Auth: none`) exigem:
```
Authorization: Bearer {access_token}
```
Token JWT emitido no login com expiração de 15 minutos. Refresh token com expiração de 7 dias via cookie httpOnly.

### Contrato H1 atual
O H1 real usa autenticação por sessão do Django, com cookie de sessão e proteção CSRF. O contrato JWT/v1 abaixo
fica como alvo pós-H1/H1.5.

Endereços em uso no H1:
- `GET /login/` e `POST /login/` para autenticação por sessão
- `POST /logout/` para encerramento de sessão
- `GET /api/cotacoes/` para listagem de cotações do H1
- `POST /api/permutador/estimate/` para recálculo/estimativa de permutador

Regras do H1:
- `SessionAuthentication` no Django REST Framework
- cookie `sessionid` + `X-CSRFToken` nas mutações
- sem JWT, refresh token ou MFA no H1

### Versionamento
- H1 atual: endpoints legados sob `/api/` conforme lista acima.
- Contrato alvo: path-based `/api/v1/`, `/api/v2/` — versões antigas suportadas por 12 meses após deprecação
- Deprecação anunciada via header `Sunset: {ISO8601_date}` e `Deprecation: true`

### Rate Limiting (alvo pós-H1/H1.5)
Headers de resposta:
```
X-RateLimit-Limit: 100
X-RateLimit-Remaining: 95
X-RateLimit-Reset: 1735689600
```
Rate limit excedido → HTTP 429 com body `{ "error": "RATE_LIMIT_EXCEEDED", "retry_after": 30 }`

### Formato de Erro Padrão (alvo pós-H1/H1.5)
```json
{
  "error": "ERROR_CODE",
  "message": "Mensagem legível em português",
  "field_errors": {
    "field_name": ["Erro específico do campo"]
  },
  "request_id": "uuid-do-request-para-suporte"
}
```

### Paginação (alvo pós-H1/H1.5)
```
GET /api/v1/quotations/?page=1&page_size=25&ordering=-created_at
Response:
{
  "count": 142,
  "next": "https://acme.smartquotation.com.br/api/v1/quotations/?page=2&page_size=25",
  "previous": null,
  "results": [...]
}
```

---

## 2. Autenticação e Usuários (alvo pós-H1/H1.5)

### POST /api/v1/auth/login
**Auth:** none | **Rate limit:** 5 req/min por IP
```
Request:
  { "email": "string", "password": "string", "totp_code": "string|null" }

Response 200:
  {
    "access_token": "string (JWT, 15min)",
    "token_type": "Bearer",
    "expires_in": 900,
    "user": {
      "id": "uuid",
      "full_name": "string",
      "role": "string",
      "requires_mfa": "boolean"
    }
  }

Response 400: { "error": "MFA_REQUIRED" }           -- TOTP não fornecido mas obrigatório
Response 401: { "error": "INVALID_CREDENTIALS" }
Response 423: { "error": "ACCOUNT_LOCKED", "unlock_at": "ISO8601" }
```

### POST /api/v1/auth/refresh
**Auth:** refresh_token (cookie httpOnly) | **Rate limit:** 10 req/min por user
```
Response 200: { "access_token": "string", "expires_in": 900 }
Response 401: { "error": "REFRESH_TOKEN_EXPIRED" }
```

### POST /api/v1/auth/logout
**Auth:** Bearer | **Rate limit:** 10 req/min
```
Response 204: (no body — invalida refresh token)
```

### GET /api/v1/users/me
**Auth:** Bearer | **Rate limit:** 60 req/min
```
Response 200:
  {
    "id": "uuid",
    "email": "string",
    "full_name": "string",
    "role": "orçamentista|engenheiro|gestor_comercial|pcp|admin",
    "crea_number": "string|null",
    "crea_state": "string|null",
    "mfa_enabled": "boolean",
    "last_login_at": "ISO8601"
  }
```

### GET /api/v1/users/
**Auth:** Bearer (admin) | **Rate limit:** 30 req/min
```
Query params: ?role=&is_active=&search=
Response 200: { paginação padrão com lista de UserDTO }
```

### POST /api/v1/users/
**Auth:** Bearer (admin) | **Rate limit:** 10 req/min
```
Request:
  {
    "email": "string (unique, max 255)",
    "full_name": "string (max 255)",
    "role": "enum",
    "crea_number": "string|null (obrigatório se role=engenheiro)",
    "crea_state": "string|null",
    "phone": "string|null",
    "send_welcome_email": "boolean (default true)"
  }

Response 201: UserDTO
Response 400: field_errors com validação
Response 409: { "error": "EMAIL_ALREADY_EXISTS" }
```

---

## 3. Materiais

### GET /api/v1/materials/
**Auth:** Bearer (any) | **Rate limit:** 60 req/min
```
Query params: ?category=&norm=&search=&is_active=true
Response 200: paginação com lista de MaterialDTO:
  {
    "id": "uuid",
    "code": "SA-516-70",
    "name": "Aço Carbono SA-516-70",
    "norm": "ASME",
    "density_kg_m3": 7850.000,
    "tensile_strength_mpa": 485.00,
    "yield_strength_mpa": 260.00,
    "allowable_stress_mpa": 138.00,
    "current_price_brl_kg": {
      "chapa": 8.50,
      "tubo": 12.30
    }
  }
```

### GET /api/v1/materials/{id}/
**Auth:** Bearer (any)
```
Response 200: MaterialDTO completo com allowable_stress_table e price_history
```

### GET /api/v1/materials/{id}/allowable-stress/
**Auth:** Bearer (any)
```
Query params: ?temp_c=250&edition=2021
Response 200:
  {
    "material_id": "uuid",
    "temp_c": 250.0,
    "allowable_stress_mpa": 118.60,
    "standard_edition": "2021",
    "interpolated": true
  }
```

### POST /api/v1/materials/
**Auth:** Bearer (engenheiro, admin)
### PATCH /api/v1/materials/{id}/
**Auth:** Bearer (engenheiro, admin)

---

## 4. Clientes

### GET /api/v1/customers/
**Auth:** Bearer (any) | **Rate limit:** 60 req/min
```
Query params: ?search=&state=
Response 200: paginação com CustomerDTO
```

### POST /api/v1/customers/
**Auth:** Bearer (orçamentista, gestor, admin)
```
Request:
  {
    "company_name": "string",
    "cnpj": "string|null (formato XX.XXX.XXX/XXXX-XX)",
    "contact_name": "string|null",
    "email": "string|null",
    "phone": "string|null",
    "city": "string|null",
    "state": "string|null (UF 2 chars)"
  }
Response 201: CustomerDTO
Response 409: { "error": "CNPJ_ALREADY_EXISTS" }
```

---

## 5. Cotações

### GET /api/v1/quotations/
**Auth:** Bearer (any) | **Rate limit:** 60 req/min
```
Query params: ?status=&customer=&search=&from_date=&to_date=&ordering=-created_at
Response 200: paginação com QuotationSummaryDTO:
  {
    "id": "uuid",
    "number": "COT-2025-001",
    "revision": 0,
    "customer": { "id": "uuid", "company_name": "string" },
    "title": "string",
    "status": "draft",
    "total_price_brl": 125000.00,
    "created_by": "string",
    "created_at": "ISO8601",
    "updated_at": "ISO8601"
  }
```

### POST /api/v1/quotations/
**Auth:** Bearer (orçamentista, engenheiro, admin)
```
Request:
  {
    "customer_id": "uuid",
    "title": "string (max 500)",
    "description": "string|null",
    "valid_until": "date|null",
    "currency": "BRL",
    "delivery_weeks": "integer|null",
    "payment_terms": "string|null"
  }
Response 201: QuotationDTO com número gerado automaticamente
```

### GET /api/v1/quotations/{id}/
**Auth:** Bearer (any)
```
Response 200: QuotationDTO completo com equipamentos, custo e proposta mais recente
Response 404: { "error": "NOT_FOUND" }
```

### PATCH /api/v1/quotations/{id}/
**Auth:** Bearer (orçamentista, engenheiro, admin) | Cotação deve estar em status editável
```
Request: campos parciais (qualquer campo não-calculado)
Response 200: QuotationDTO atualizado
Response 409: { "error": "QUOTATION_NOT_EDITABLE", "current_status": "approved" }
```

### POST /api/v1/quotations/{id}/revise/
**Auth:** Bearer (orçamentista, engenheiro, admin)
```
Response 201: nova QuotationDTO com revision+1, status='draft', parent_quotation_id apontando para original
```

### POST /api/v1/quotations/{id}/submit-for-review/
**Auth:** Bearer (orçamentista)
```
Response 200: { "status": "in_review" }
Response 422: { "error": "MISSING_TECHNICAL_APPROVAL", "components": ["uuid1", "uuid2"] }
```

### POST /api/v1/quotations/{id}/approve/
**Auth:** Bearer (gestor_comercial, admin)
```
Response 200: { "status": "approved", "approved_at": "ISO8601" }
```

### POST /api/v1/quotations/{id}/mark-won/
**Auth:** Bearer (gestor_comercial, admin)
```
Request: { "notes": "string|null" }
Response 200: { "status": "won" }
```

### POST /api/v1/quotations/{id}/mark-lost/
**Auth:** Bearer (gestor_comercial, admin)
```
Request: { "reason": "string" }
Response 200: { "status": "lost" }
```

---

## 6. Equipamentos e Componentes

### GET /api/v1/quotations/{quotation_id}/equipment/
**Auth:** Bearer (any)
```
Response 200: lista de EquipmentDTO com seus componentes
```

> Esta família de rotas é contrato-alvo pós-H1/H1.5. O H1 atual trabalha com EAP persistida
> por cotação e não expõe o modelo Equipment/Component formal.

### POST /api/v1/quotations/{quotation_id}/equipment/
**Auth:** Bearer (orçamentista, engenheiro, admin)
```
Request:
  {
    "equipment_type": "pressure_vessel|heat_exchanger",
    "tag": "string|null",
    "description": "string|null",
    "design_standard": "ASME VIII Div.1",
    "corrosion_allowance_mm": 3.0,
    "heat_treatment": "none|pwht|...",
    -- Campos específicos do tipo:
    "pressure_vessel": {
      "orientation": "vertical|horizontal",
      "design_pressure_bar": 10.0,
      "design_temp_c": 150.0,
      "shell_material_id": "uuid",
      "shell_od_mm": 1000.0,
      "shell_length_mm": 3000.0,
      "joint_efficiency": 1.0,
      "head_type": "elliptical",
      "head_material_id": "uuid"
    }
    -- OU
    "heat_exchanger": { ... }
  }
Response 201: EquipmentDTO
```

### POST /api/v1/quotations/{quotation_id}/equipment/{equipment_id}/calculate/
**Auth:** Bearer (orçamentista, engenheiro, admin)
**Descrição:** Dispara o motor de cálculo para todos os componentes do equipamento.
```
Response 202:
  {
    "task_id": "uuid",
    "status": "calculating",
    "poll_url": "/api/v1/tasks/{task_id}/"
  }
```

### GET /api/v1/quotations/{quotation_id}/equipment/{equipment_id}/components/
**Auth:** Bearer (any)
```
Response 200: lista de ComponentDTO com calculation_snapshot mais recente
```

### POST /api/v1/quotations/{quotation_id}/equipment/{equipment_id}/components/{component_id}/import-calculation/
**Auth:** Bearer (engenheiro, admin)
**Descrição:** Importa cálculo de terceiro (modo 'imported'). Aceita upload de arquivo.
```
Request: multipart/form-data
  - document: File (PDF/DOCX/DWG, max 20MB)
  - import_source: string (ex: "PVElite calculado por Eng. João - CREA-SP 123456")
  - notes: string|null

Response 200: ComponentDTO atualizado com imported_document_hash e calculation_mode='imported'
```

---

## 7. Cálculo Normativo

### GET /api/v1/tasks/{task_id}/
**Auth:** Bearer (any)
**Descrição:** Polling de tarefa assíncrona (cálculo, geração de proposta).
```
Response 200:
  {
    "task_id": "uuid",
    "status": "pending|calculating|done|error",
    "progress_pct": 65,
    "result": { ... } | null,
    "error": "string" | null,
    "created_at": "ISO8601",
    "completed_at": "ISO8601|null"
  }
```

### GET /api/v1/quotations/{quotation_id}/equipment/{equipment_id}/snapshots/
**Auth:** Bearer (engenheiro, admin)
**Descrição:** Histórico de execuções do motor de cálculo para auditoria.
```
Response 200: lista de CalculationSnapshotDTO:
  {
    "id": "uuid",
    "component_id": "uuid",
    "function_name": "engineering.asme.viii_div1.shell.calc_thickness",
    "function_version": "1.0.0",
    "standard_reference": "ASME BPVC Sec. VIII Div.1 UG-27 (2021)",
    "inputs": { ... },
    "outputs": { "required_thickness_mm": 12.3, "mawp_bar": 11.5, ... },
    "pvélite_validated": false,
    "created_by": "string",
    "created_at": "ISO8601"
  }
```

### POST /api/v1/quotations/{quotation_id}/equipment/{equipment_id}/snapshots/{snapshot_id}/validate-pvélite/
**Auth:** Bearer (engenheiro, admin)
**Descrição:** Registra validação manual contra PVElite.
```
Request:
  {
    "pvélite_result": {
      "required_thickness_mm": 12.4,
      "mawp_bar": 11.3
    },
    "delta_pct": 0.8,
    "notes": "string|null"
  }
Response 200: SnapshotDTO atualizado com pvélite_validated=true
```

---

## 8. Aprovação Técnica

### POST /api/v1/quotations/{quotation_id}/technical-approvals/
**Auth:** Bearer (engenheiro) — obrigatório ter crea_number no perfil
```
Request:
  {
    "component_id": "uuid|null",
    "art_number": "string|null",
    "notes": "string|null"
  }

Response 201:
  {
    "id": "uuid",
    "approved_by": { "full_name": "string", "crea_number": "string" },
    "art_number": "string|null",
    "calculation_snapshot_hash": "string (SHA-256)",
    "approved_at": "ISO8601"
  }

Response 403: { "error": "CREA_NUMBER_REQUIRED" }
Response 422: { "error": "NO_CALCULATION_TO_APPROVE" }   -- componente sem snapshot calculado
```

### DELETE /api/v1/technical-approvals/{id}/
**Auth:** Bearer (engenheiro que aprovou, admin)
**Descrição:** Revogação lógica (não deleta, grava revoked_at e revoked_by).
```
Request: { "reason": "string" }
Response 200: TechnicalApprovalDTO com revoked_at preenchido
```

---

## 9. Custo e Preço

### GET /api/v1/quotations/{quotation_id}/cost-breakdown/
**Auth:** Bearer (orçamentista, engenheiro, gestor, admin)
```
Response 200:
  {
    "quotation_id": "uuid",
    "by_cost_type": {
      "material": 45000.00,
      "labor": 18000.00,
      "overhead": 7200.00,
      "external_service": 3500.00
    },
    "by_equipment": [
      {
        "equipment_id": "uuid",
        "tag": "V-101",
        "total_cost_brl": 52000.00,
        "items": [...]
      }
    ],
    "total_cost_brl": 73700.00,
    "calculated_at": "ISO8601"
  }
```

### POST /api/v1/quotations/{quotation_id}/price-formation/
**Auth:** Bearer (gestor_comercial, admin)
```
Request:
  {
    "overhead_pct": 15.0,
    "margin_pct": 22.0,
    "tax_config": {
      "icms_pct": 12.0,
      "pis_cofins_pct": 9.25,
      "iss_pct": 0.0
    }
  }
Response 200: PriceFormationDTO completo
```

### GET /api/v1/rates/
**Auth:** Bearer (engenheiro, admin)
```
Query params: ?operation=&material=&layer=industry_standard|tenant|actual
Response 200: lista de RateDTO com hierarquia e confiança
```

---

## 10. Propostas

### POST /api/v1/quotations/{quotation_id}/proposals/
**Auth:** Bearer (orçamentista, gestor, admin)
```
Request:
  {
    "template_id": "uuid",
    "format": "docx|pdf|both"
  }
Response 202:
  {
    "proposal_id": "uuid",
    "task_id": "uuid",
    "status": "generating",
    "poll_url": "/api/v1/tasks/{task_id}/"
  }
```

### GET /api/v1/quotations/{quotation_id}/proposals/{proposal_id}/download/
**Auth:** Bearer (any)
```
Query params: ?format=docx|pdf
Response 200: arquivo (Content-Disposition: attachment)
Response 404: { "error": "PROPOSAL_NOT_READY" }
```

---

## 11. Webhooks (H2 — ERP Integration)

Webhooks permitem que ERPs externos recebam notificações de eventos em tempo real.

### Configuração (admin)
```
POST /api/v1/webhooks/
  {
    "url": "https://erp.cliente.com.br/smartquotation/webhook",
    "events": ["quotation.won", "quotation.converted_to_order"],
    "secret": "string (gerado pelo cliente, usado para HMAC-SHA256)"
  }
```

### Payload de evento
```
Headers:
  X-SmartQuotation-Event: quotation.won
  X-SmartQuotation-Signature: sha256={HMAC-SHA256 do body}
  X-SmartQuotation-Delivery: uuid

Body:
  {
    "event": "quotation.won",
    "tenant_id": "uuid",
    "occurred_at": "ISO8601",
    "data": {
      "quotation_id": "uuid",
      "number": "COT-2025-001",
      "customer_cnpj": "string",
      "total_price_brl": 125000.00,
      "bom_url": "/api/v1/quotations/{id}/bom/",
      "route_url": "/api/v1/quotations/{id}/route/"
    }
  }
```

### Eventos disponíveis
| Evento | Quando dispara |
|---|---|
| `quotation.created` | Nova cotação criada |
| `quotation.approved` | Cotação aprovada internamente |
| `quotation.won` | Cotação marcada como ganha |
| `quotation.lost` | Cotação marcada como perdida |
| `quotation.converted_to_order` | Cotação convertida em OF (H2) |
| `proposal.generated` | Proposta PDF/DOCX pronta |
| `technical.approved` | Cálculo assinado pelo engenheiro |

---

## 12. OpenAPI / Swagger

O schema OpenAPI 3.1 é gerado automaticamente pelo DRF Spectacular:
```
GET /api/v1/schema/          → openapi.yaml
GET /api/v1/docs/            → Swagger UI
GET /api/v1/redoc/           → ReDoc
```
