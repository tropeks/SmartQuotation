# SECURITY.md — SmartQuotation

> **Status:** Aprovado | **Versão:** 1.0 | **Referência:** ARCHITECTURE.md, API_SPEC.md

---

## 1. Contexto e Criticidade

SmartQuotation é classificado como **software de engenharia regulado**, pois:
- Gera cálculos normativos (ASME/TEMA) que fundamentam projetos sob responsabilidade técnica
- Armazena dados que constituem evidência de auditoria NR-13 e ISO 9001
- Processa dados pessoais de usuários e contatos de clientes (LGPD)
- Opera no modelo SaaS multi-tenant — falha de isolamento expõe dados de múltiplas empresas

**Classificação de risco:** Alto (engenharia regulada + SaaS multi-tenant + dados comercialmente sensíveis)

---

## 2. Modelo de Ameaças (STRIDE simplificado)

| Asset protegido | Ameaça | Controle |
|---|---|---|
| Dados de cotação de concorrentes (preço, margem, cliente) | Acesso indevido entre tenants | Schema-per-tenant + RLS + testes de isolamento no CI |
| Cálculos normativos (integridade) | Adulteração de resultado após aprovação | CalculationSnapshot append-only + hash SHA-256 + TechnicalApproval imutável |
| Credenciais de usuário | Credential stuffing, brute force | Argon2 + rate limiting login (5/min) + account lockout + MFA obrigatório para admin |
| Propostas com preço de venda | Exfiltração de dados comerciais | RBAC (apenas roles autorizados geram/baixam proposta) + AccessLog + download via token temporário |
| Assinatura técnica (ART/CREA) | Falsificação ou uso indevido | Snapshot hash vinculado à aprovação + trigger append-only + log imutável |
| Dados pessoais (LGPD) | Exposição de PII, requisição de exclusão | Campos PII mapeados + base legal documentada + processo de exclusão |
| Infraestrutura (VPS) | Acesso não autorizado ao servidor | SSH key-only + fail2ban + firewall UFW + Docker não expõe portas desnecessárias |
| Supply chain | Dependência comprometida (ex: pip package) | pip-audit no CI + Dependabot + hash de imagens Docker |
| Sessões | Session hijacking | Cookie httpOnly + Secure + SameSite=Lax + expiração 15min (access) / 7d (refresh) |
| API endpoints | Injection (SQL, SSTI, path traversal) | ORM parametrizado (Django nunca string-format SQL) + Pydantic valida inputs + Bandit no CI |
| Arquivos de upload | Malware, SSRF via arquivo | Validação de MIME type + extensão + tamanho + armazenamento fora do webroot |

---

## 3. Controles de Segurança

### 3.1 Autenticação

| Controle | Implementação |
|---|---|
| Hash de senha | Argon2id (custo: time=2, memory=65536, parallelism=2) via Django `argon2-cffi` |
| MFA | TOTP (RFC 6238) via `django-otp` + `qrcode` para QR de setup |
| MFA obrigatório | Roles `admin` e `gestor_comercial` — forçado no middleware de request |
| Rate limit login | 5 tentativas / minuto por IP + 10 tentativas / hora por email |
| Account lockout | Após 10 falhas em 1h → conta bloqueada por 30 minutos; admin pode desbloquear |
| Tokens JWT | Access: RS256, 15min; Refresh: httpOnly cookie, SameSite=Strict, 7 dias |
| Rotação de refresh | Refresh token é invalidado e um novo é emitido a cada uso (rotation) |
| Logout | Refresh token adicionado a blocklist Redis com TTL = remaining expiry |

### 3.2 Autorização

```
Modelo: RBAC com 5 roles fixas (ver ARCHITECTURE.md §6)
Implementação: Django Groups + django-guardian para permissões por objeto quando necessário
Princípio: least privilege — nenhum role tem mais permissão do que o necessário
Elevação de privilégio: apenas admin pode promover usuário a role superior
API: todas as views DRF decoradas com permission_class explícita (sem default permissivo)
Auditoria: toda mudança de role gera entrada no django-simple-history de UserProfile
```

### 3.3 Proteção de Dados em Trânsito

| Controle | Implementação |
|---|---|
| TLS | TLS 1.3 obrigatório; TLS 1.2 tolerado para compatibilidade; SSL 3.0/TLS 1.0/1.1 bloqueados |
| Certificados | Let's Encrypt via Caddy (renovação automática) |
| HSTS | `Strict-Transport-Security: max-age=31536000; includeSubDomains; preload` |
| Certificados de ERP | mTLS para webhooks de saída para ERPs que suportem |

### 3.4 Proteção de Dados em Repouso

| Controle | Implementação |
|---|---|
| Filesystem | Volume Docker em filesystem cifrado (LUKS no VPS) |
| Backup | `pg_dump` cifrado com `age` (chave pública/privada); chave privada em cofre offline |
| Campos sensíveis | Preços de venda e margens cifrados em nível de campo com `pgcrypto` (AES-256) |
| Segredos | `.env` fora do repositório no MVP; migração para Vault/AWS Secrets em H2 |

### 3.5 HTTP Security Headers

```
Content-Security-Policy: default-src 'self'; script-src 'self' 'nonce-{random}'; style-src 'self' 'nonce-{random}'; img-src 'self' data:; frame-ancestors 'none'
X-Frame-Options: DENY
X-Content-Type-Options: nosniff
Referrer-Policy: strict-origin-when-cross-origin
Permissions-Policy: geolocation=(), camera=(), microphone=()
Cache-Control: no-store (para páginas autenticadas)
```
Implementado via `django-csp` + middleware customizado.

### 3.6 Proteção contra Injeção

| Vetor | Controle |
|---|---|
| SQL injection | Django ORM parametrizado; `raw()` e `extra()` proibidos sem code review |
| SSTI (template injection) | Templates Jinja/Django com autoescape ativo; docxtpl usa `escape_xml` |
| Path traversal (upload) | Nomes de arquivo sanitizados com `uuid4` no armazenamento; path original gravado separado |
| XSS | Django templates escapam HTML por padrão; HTMX não executa JS injetado |
| CSRF | Django `CsrfViewMiddleware` ativo; HTMX inclui header `X-CSRFToken` automaticamente |

### 3.7 Rate Limiting e DDoS

```
Caddy: limite de conexões por IP (rate_limit)
Django: django-ratelimit por endpoint crítico
  - /api/v1/auth/login: 5/min por IP
  - /api/v1/auth/refresh: 10/min por usuário
  - /api/v1/quotations/{id}/proposals/: 5/hora por usuário (geração de PDF é cara)
  - /api/v1/quotations/{id}/calculate/: 20/hora por usuário
CloudFlare (opcional H2): proteção DDoS Layer 3/4 sem custo adicional
```

### 3.8 Upload de Arquivos

```
Tipos aceitos: PDF, DOCX, DWG, DXF, XLSX
Tamanho máximo: 20MB por arquivo
Validação: MIME type verificado via python-magic (não apenas extensão)
Armazenamento: /data/uploads/{tenant_slug}/{quotation_id}/{uuid4}.{ext}
              fora do webroot — servido via view Django com verificação de permissão
Scan de malware: ClamAV (opcional H2 — integrado via Celery task pós-upload)
```

### 3.9 Secrets Management

| Ambiente | Implementação |
|---|---|
| MVP | `.env` file no servidor, fora do repositório, permissões 600, owner=app |
| H2 | HashiCorp Vault OSS ou AWS Secrets Manager |
| CI/CD | GitHub Actions Secrets (nunca em variáveis de ambiente de workflow expostas) |
| Rotação | DATABASE_URL, SECRET_KEY: rotação semestral documentada; tokens de API ERP: rotação anual |

### 3.10 Dependency Security

```
pip-audit: roda no CI a cada commit (bloqueia se CVSS >= 7.0)
Dependabot: PRs automáticos para atualizações de segurança (GitHub)
Trivy: scan de imagem Docker antes de push para registry
pre-commit hooks: bandit (SAST Python), safety, black, ruff
Pinning: requirements.txt com versões exatas; `pip-compile` para atualizar
```

---

## 4. Audit Trail — Especificação

### 4.1 O que é registrado

| Entidade | django-simple-history | AccessLog |
|---|---|---|
| Quotation | ✅ (todo campo) | ✅ (view, export, print) |
| Equipment / Component | ✅ | — |
| CalculationSnapshot | append-only (sem history — imutável por design) | ✅ (view) |
| TechnicalApproval | append-only | ✅ (create, revoke) |
| Material / Price | ✅ | — |
| Rate | ✅ | — |
| UserProfile | ✅ | ✅ (role change) |
| Proposal (download) | — | ✅ (download) |

### 4.2 Integridade do log

- `AccessLog` usa `BIGSERIAL` incremental — gaps no sequence indicam possível adulteração
- Trigger PostgreSQL rejeita `UPDATE` e `DELETE` em `AccessLog` enquanto registro tiver menos de 15 anos
- Hash acumulado opcional (H2): cada linha guarda `SHA256(previous_hash || row_data)` — cadeia verificável

### 4.3 Retenção

| Tipo de dado | Retenção | Base |
|---|---|---|
| Cotações e cálculos | 15 anos | NR-13 (vasos de pressão) |
| Propostas (DOCX/PDF) | 15 anos | NR-13 |
| AccessLog | 5 anos | ISO 27001 A.12.4 / LGPD |
| Histórico de usuários | 5 anos após desativação da conta | LGPD |
| Backups | 30d diários / 90d semanais / 365d mensais | RPO/RTO |

---

## 5. LGPD — Compliance Operacional

### 5.1 Dados pessoais mapeados

| Campo | Entidade | Base legal | Finalidade |
|---|---|---|---|
| email | auth.User | Execução de contrato | Autenticação e comunicação |
| full_name | UserProfile | Execução de contrato | Identificação do usuário |
| phone | UserProfile | Legítimo interesse | Suporte |
| crea_number | UserProfile | Obrigação legal | Responsabilidade técnica NR-13 |
| contact_name, email, phone | Customer | Execução de contrato | Elaboração de proposta |
| ip_address | AccessLog | Legítimo interesse / Segurança | Segurança e auditoria |

### 5.2 Direitos do titular

| Direito LGPD | Implementação |
|---|---|
| Acesso | Export JSON de todos os dados do usuário via endpoint `GET /api/v1/users/me/export/` |
| Correção | Usuário edita próprio perfil; admin edita qualquer usuário |
| Exclusão | Soft-delete do UserProfile + anonimização de campos PII em AccessLog (nome → hash); cotações e cálculos são retidos por obrigação legal (NR-13) com dissociação do titular |
| Portabilidade | Export JSON / CSV de cotações do tenant via `GET /api/v1/export/` |
| Informação | Política de privacidade acessível em `/privacidade/` antes do login |

### 5.3 Incidentes

Processo documentado:
1. Detecção → alerta Sentry / AccessLog anomalia
2. Contenção em até 1h (desativar tenant afetado se necessário)
3. Investigação: AccessLog + django-simple-history
4. Notificação ANPD em até 72h se houver risco a titulares
5. Notificação aos titulares afetados
6. Relatório pós-incidente e ação corretiva

---

## 6. Controles ISO 27001 (mapeamento para H2/H3)

| Controle ISO 27001:2022 | Status MVP | Plano H2 |
|---|---|---|
| A.5.1 Políticas de segurança | Documentado neste arquivo | Política formal aprovada |
| A.8.2 Gestão de acesso privilegiado | RBAC + MFA para admin | PAM básico |
| A.8.3 Restrição de acesso | RBAC implementado | Revisão semestral de acessos |
| A.8.5 Autenticação segura | Argon2 + MFA + rate limit | SSO/SAML |
| A.8.12 Prevenção de vazamento | RBAC + download controlado | DLP básico |
| A.8.15 Log de auditoria | AccessLog + django-simple-history | SIEM básico (H3) |
| A.8.24 Criptografia | TLS 1.3 + cifragem em repouso + bcrypt | Vault para secrets |
| A.8.31 Separação de ambientes | dev/staging/prod isolados | Formalmente documentado |
| A.5.30 Continuidade de TI | Backup off-site diário | RTO/RPO formalmente testado |

---

## 7. Checklist de Segurança — Gate de Release

Antes de cada deploy em produção, o CI verifica:

```
[ ] pip-audit: 0 vulnerabilidades CVSS >= 7.0
[ ] bandit: 0 issues severity HIGH
[ ] trivy: imagem Docker sem CVEs críticos
[ ] pytest: 100% dos testes de isolamento multi-tenant passando
[ ] pytest: 100% dos testes de regressão PVElite passando
[ ] migrations: nenhuma migration destrutiva sem período de deprecação
[ ] secrets: nenhum secret em código (detect-secrets pre-commit hook)
[ ] TLS: certificado válido e configurado (testado via staging)
```
