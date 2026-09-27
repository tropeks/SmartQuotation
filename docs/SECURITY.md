---
# Contrato de documentação (Maestro E16).
#
# Autenticação, RBAC por capability, isolamento por tenant, trilha de auditoria,
# credenciais de integração e o caminho de envio de proposta (efeito externo da F1).
# Mexeu num destes arquivos e mudou o contrato descrito aqui: o doc emenda no mesmo changeset.
covers:
  - backend/apps/accounts/**
  - backend/apps/access/**
  - backend/apps/audit/**
  - backend/apps/tenants/**
  - backend/apps/integrations/**
  - backend/apps/proposals/services.py
  - backend/apps/proposals/views.py
  - backend/smartquotation/settings/**
  - docker-compose.prod.yml
reviewed: 2026-09-27
---

# SECURITY.md — SmartQuotation

> **Versão:** 2.0 (27/09/2026) | **Direção:** `.maestro/INTENT.md` v2 (carimbado em 27/09/2026)
> **Consome:** `ARCHITECTURE.md`, `cognitive-core/docs/FASES.md` §4, `cognitive-core/docs/SEGURANCA.md`,
> `docs/discovery/CSO_ROUND3_2026-07-17.md` | **Perfil:** piloto (design partner) rumo a SaaS multi-tenant.
>
> A v1.0 descrevia controles-alvo como se existissem. A v2.0 separa **Atual** (está no código, com
> arquivo) de **Alvo** (ordem, fase ou horizonte que o entrega). O que não tem arquivo não é controle.

---

## 1. Contexto e Criticidade

SmartQuotation é **software de engenharia regulado**:
- Gera cálculos normativos (ASME/TEMA) que fundamentam projetos sob responsabilidade técnica (CREA).
- Guarda evidência de auditoria (NR-13, ISO 9001).
- Processa dados pessoais de usuários e contatos de clientes (LGPD).
- É SaaS multi-tenant: falha de isolamento expõe preço e margem de uma empresa a outra.
- Na F1 do Quantum Cognitive Core passa a produzir **efeito externo governado** (`proposal.send`).

**Classificação de risco:** Alto.

**Invariantes do INTENT v2 que este doc protege:**
1. **A assinatura vale o que assina.** Nenhum caminho (admin, API, Core) altera número assinado sem
   invalidar a assinatura.
2. **Envio uma vez.** Garantias de envio (idempotência, reserva, conciliação, destinatário e provedor em
   lista) são pré-condição do primeiro envio real.
3. **Passkey com step-up (F1-32) antes do primeiro envio real.** Papel privilegiado não opera efeito
   externo só com senha.
4. **Dado externo é dado, nunca instrução.**
5. **Nenhum dado real de cliente sai do repositório nem da instância**; fixtures são sintéticas.

---

## 2. Modelo de Ameaças do produto (STRIDE resumido)

| Asset | Ameaça | Controle atual | Alvo |
|---|---|---|---|
| Cotação de outro tenant (preço, margem, cliente) | Acesso entre tenants | Schema-per-tenant (`django-tenants`) + `TenantMembershipMiddleware` (`accounts/middleware.py`): usuário sem `UserProfile` ativo no schema é deslogado | Teste de isolamento por view no CI |
| Número assinado (cálculo) | Adulteração após aprovação | `CalculationSnapshot` com SHA-256 canônico (`quotations/services.py`); `TechnicalApproval` guarda o hash; recálculo invalida cases de aprovação divergentes (`audit/approvals.py` `invalidate_stale_cases`); campos derivados read-only no admin | Trigger append-only (H1.5); proposta e envio amarrados ao hash (F1-06, F1-30, F1-32) |
| Assinatura técnica | Assinar sem habilitação | `Role.requires_crea` + `UserProfile.clean/save` exigem CREA; `TechnicalApproval.clean` recusa papel sem CREA | Retrato imutável da habilitação no ato (F1-17) |
| Credenciais de usuário | Brute force, credential stuffing | Argon2; `django-axes` 5 falhas, bucket por **username** (e username+IP), cool-off 1 h; senha mínima 10 | Passkey + step-up para papel privilegiado (F1-32) |
| Proposta com preço | Exfiltração, envio indevido | `proposal.write` para gerar/enviar; `AccessLog` em download/preview | Leitura por capability; envio só via `proposal.send` do Core (F1-03, F1-07 a F1-10) |
| Credenciais de ERP | Vazamento em repouso | `EncryptedCharField` (Fernet, `FIELD_ENCRYPTION_KEY`) em Nomus, Omie, SAP B1, Bling, Protheus | Cofre de segredo (H2) |
| Origem HTTP | Acesso direto contornando o túnel | **Nenhum hoje**: `docker-compose.prod.yml:21-22` publica `0.0.0.0:8000` | Loopback (F1-04); túnel por instância (F1-14) |
| Trilha de auditoria | Repúdio, IP forjado | `AccessLog` por serviço | IP de proxy confiável após F1-04; trigger append-only (H1.5) |
| Supply chain | Dependência comprometida | Locks com `--require-hashes`; `pip-audit` no CI em `base.lock` e `ci.lock` | Bandit, Trivy, detect-secrets |
| Injeção | SQLi, SSTI, XSS | ORM parametrizado; autoescape Django; CSRF + `X-CSRFToken` no HTMX | CSP |

---

## 3. Controles de Segurança

### 3.1 Autenticação (atual)

| Controle | Implementação |
|---|---|
| Mecanismo | Sessão Django (`sessionid` em banco) + CSRF; DRF só com `SessionAuthentication`. **Sem JWT.** |
| Hash de senha | `Argon2PasswordHasher` (PBKDF2 só para migração de hash legado) |
| Política de senha | Validadores Django; mínimo 10 caracteres |
| Brute force | `django-axes`: `AXES_FAILURE_LIMIT=5`, `AXES_COOLOFF_TIME=1` h, `AXES_LOCKOUT_PARAMETERS=[["username","ip_address"],"username"]`, `AXES_RESET_ON_SUCCESS=False` (racional em `settings/base.py`) |
| Senha provisória | `MustChangePasswordMiddleware` bloqueia tudo até a troca |
| Cookies (prod) | `SESSION_COOKIE_SECURE`, `CSRF_COOKIE_SECURE`, HSTS 1 ano, `X_FRAME_OPTIONS=DENY`, `nosniff`, `SECURE_SSL_REDIRECT` |
| Expiração de sessão | Default do Django (2 semanas, `SESSION_COOKIE_AGE` não configurado) |
| Chaves | `production.py` recusa `DJANGO_SECRET_KEY` e `FIELD_ENCRYPTION_KEY` públicas (placeholders e chave dev commitados) |

**Alvo:** passkey (WebAuthn) com **step-up** na autorização de efeito externo, assinando o hash dos
parâmetros (F1-32; prova M11 = 0: replay, hash trocado e sessão velha recusados). **Pré-condição do
primeiro envio real.** Papel privilegiado (quem autoriza envio, aprova técnica, edita matriz de acesso,
e `is_staff`) não opera efeito externo só com senha. TOTP e SSO ficam fora da F1.

### 3.2 Autorização (atual)

- **RBAC configurável por capability** (`apps/access`, F10): catálogo em código (`capabilities.py`),
  matriz papel × capability por tenant em `RolePermission`, editável na UI (`access.manage`).
- **Fail-closed**: papel sem linha `allowed=True`, usuário sem perfil ou capability fora do catálogo → nega.
  `tests_registry_integrity.py` reprova no CI capability usada e não cadastrada.
- Views usam `@require_capability(code)`; flags de template usam `user_can` (mesma fonte).
- Papéis são dado (`Role`); CREA deriva do trait `requires_crea`, não do nome do papel.
- Aprovação multiestágio (`ApprovalWorkflow`/`ApprovalStage`/`ApprovalCase`) com capability aprovadora
  por estágio; conversão em OF exige todos os estágios obrigatórios satisfeitos **no snapshot atual**.
- Operador de plataforma (`is_staff`/`is_superuser`) passa na checagem de membership de qualquer tenant
  (`accounts/rbac.py` `has_tenant_membership`) e só passa em `require_capability` quando a view declara
  `allow_platform_staff=True`.
- Cache da matriz: `LocMemCache` por processo, TTL 300 s. Com vários workers, revogação leva até 300 s
  para valer nos outros processos (ver `apps/access/README.md`).

**Alvo F1:** token delegado curto por usuário e escopo de capability para o Core (F1-01); permissão
efetiva = interseção delegante ∩ delegação, **recalculada na execução** (F1-11). A latência de
revogação do cache precisa caber na prova do T-SEG-31.

### 3.3 Integridade do número assinado (atual)

- `build_snapshot_payload` gera JSON canônico (inputs, outputs, `engine_version`, referências de norma)
  e SHA-256; `create_calculation_snapshot` persiste e invalida cases de aprovação com hash divergente.
- `TechnicalApproval` guarda `calculation_snapshot_hash`, CREA e UF do aprovador; revogação é lógica.
- OF é montada a partir do snapshot assinado (`production/services.py`), com fallback ao banco vivo só
  para snapshots anteriores ao M1.
- Admin: custo, preço, peso e `pricing_basis` são read-only em `QuotationAdmin`.

**Regra:** qualquer caminho novo que grave número derivado (admin, API, `core_bridge`) passa pelo motor
e emite snapshot novo, o que invalida a assinatura anterior. Proposta e envio carregam o hash do snapshot
aprovado e são recusados se ele divergir (F1-06, F1-30).

### 3.4 Dados em trânsito e em repouso

| Controle | Estado |
|---|---|
| TLS | Termina no túnel (Cloudflare); Django confia em `X-Forwarded-Proto` (`SECURE_PROXY_SSL_HEADER`), o que **só é seguro com a origem em loopback** (F1-04) |
| Campos cifrados | `MaterialPrice.preco_brl_kg` e credenciais de ERP via `django-encrypted-model-fields` (Fernet). Preço de venda da cotação **não** é cifrado em campo |
| Backup | `pg_dump` cifrado com `age`; alvo: PITR + drill mensal, `age` com dois destinatários (F1-15) |
| Segredos | `.env` fora do repositório; nunca imprimir nem commitar. Alvo H2: cofre |

### 3.5 Headers e injeção

- Atual: HSTS, `X-Frame-Options: DENY`, `nosniff` (prod); CSRF ativo; ORM parametrizado; autoescape.
- Alvo: CSP com nonce e `Cache-Control: no-store` em páginas autenticadas (não há `django-csp` hoje).
- `raw()`/`extra()` só com revisão.

### 3.6 Upload, rate limit e dependências

- Upload: alvo continua o da v1.0 (MIME real, uuid4, fora do webroot, servido por view com permissão);
  `python-magic` está no requirements mas não é usado hoje.
- Rate limit: só o lockout do `axes` no login. Rate limit por endpoint (PDF, cálculo) é alvo.
- Dependências: locks com hash + `pip-audit` no CI (atual). Bandit, Trivy e detect-secrets são alvo.

---

## 4. Audit Trail

| Entidade | Atual | Alvo |
|---|---|---|
| Snapshot de cálculo | Hash por serviço | Trigger append-only (H1.5) |
| `TechnicalApproval` | Serviço + `AccessLog` approve/revoke | Trigger append-only |
| Aprovação multiestágio | `AccessLog` `case_open`, `task_approve/reject`, `case_invalidate` | — |
| Matriz de acesso e papéis | `AccessLog` `permission_change`, `role_change`, `member_deactivate`, `approval_config_change` | History detalhado |
| Proposta | `AccessLog` download/preview; `ProposalVersion.emailed_at/by/to` | Ledger de envio com reserva e recibo (F1-07, F1-08) e `trace_id` (F1-12) |
| Material, preço, taxa | Versionamento por vigência | History |

- `AccessLog` é append-only por convenção de serviço (sem trigger ainda). Alvo H1.5: trigger que rejeita
  `UPDATE`/`DELETE`; H2: hash encadeado.
- O IP gravado vem de `X-Forwarded-For` sem validação de proxy; só é confiável depois da F1-04.

**Retenção:** ver §9 (pendência jurídica DP-27). Até a decisão, nada é apagado por rotina.

---

## 5. LGPD — Compliance Operacional

### 5.1 Dados pessoais mapeados

| Campo | Entidade | Finalidade |
|---|---|---|
| email, nome | `auth.User` / `UserProfile` | Autenticação e identificação |
| crea_number, crea_state | `UserProfile`, `TechnicalApproval` | Responsabilidade técnica |
| contato (nome, e-mail, telefone) | Cliente | Proposta |
| ip_address, user_agent | `AccessLog` | Segurança e auditoria |

Base legal por campo e por capability **não é decidida neste doc**: depende de DP-22 e DP-23 (§9).

### 5.2 Direitos do titular

Alvo (não implementado): export dos dados do usuário, correção pelo perfil, exclusão por soft-delete com
anonimização em `AccessLog` e dissociação do titular nas cotações retidas, política em `/privacidade/`.
O prazo de retenção que limita a exclusão espera a DP-27.

### 5.3 Incidentes

Detecção (Sentry, anomalia no `AccessLog`) → contenção em até 1 h (desativar o tenant se preciso) →
investigação → notificação à ANPD e aos titulares quando houver risco → relatório. Encarregado, prazos e
papel da Quantum no incidente esperam DP-26 e DP-22.

---

## 6. Controles ISO 27001 (mapeamento H2/H3)

| Controle | Estado | Plano |
|---|---|---|
| A.8.2 Acesso privilegiado | RBAC por capability; `is_staff` com acesso a todo tenant | Passkey + step-up (F1-32); PAM básico |
| A.8.3 Restrição de acesso | Fail-closed por capability | Revisão semestral de acessos |
| A.8.5 Autenticação segura | Argon2 + sessão + `axes` | Passkey (F1-32); SSO |
| A.8.15 Log | `AccessLog` | Trigger append-only; SIEM (H3) |
| A.8.24 Criptografia | TLS no túnel + Fernet em campos | Cofre de segredo |
| A.5.30 Continuidade | Backup cifrado | PITR + drill (F1-15) |

---

## 7. Checklist — Gate de Release [VIBE-CODE-READY]

Hoje o CI verifica (bloqueia): gates do motor feixe e permutador; `pip-audit` nos locks; lockfiles com
hash; `manage.py check`; `makemigrations --check`; suíte Django multi-tenant.

Antes do **primeiro envio real** (F1), além disso:

1. `docker-compose.prod.yml` publica 8000 só em `127.0.0.1` (F1-04); varredura externa com 0 portas.
2. `proposal.send` recusa versão já `sent` e usa `idempotency_key` (F1-03); T-SEG-04 e T-SEG-05 no CI.
3. Guarda recalcula pelo motor e confere o hash do payload aprovado (F1-06); T-SEG-01 e T-SEG-02 verdes.
4. Destinatário fora do cadastro → 0 despachos (F1-09, T-SEG-03).
5. Provedor fora da allowlist e do DPA → 0 chamadas, inclusive com banco fora (F1-10, T-SEG-60).
6. Nenhuma chamada HTTP de conector fora do Tool Gateway (F1-05, T-SEG-07).
7. Autorização com passkey e step-up sobre o hash (F1-32).
8. Pendências jurídicas da §9 marcadas F1 resolvidas ou aceitas pelo Capitão.

Alvo (ainda não no CI): Bandit, Trivy, detect-secrets, teste comportamental do lockout do `axes`.

---

## 8. Threat model da fronteira SQ ↔ Core na F1

**Escopo.** O Core chama capabilities do SQ (`quotation.read`, `create_draft`, `recompute`,
`proposal.render`, `proposal.send`) pelo `core_bridge` e pelo Tool Gateway, em sombra e depois em
`act_with_approval`, nunca além. O SQ mantém a autoridade sobre o próprio negócio: o motor calcula, o
engenheiro assina, o humano autoriza o irreversível.

**Fronteiras de confiança:** (1) Core → `core_bridge` do SQ; (2) guarda do Core → despacho externo
(SMTP, LLM, conector); (3) dado externo (e-mail, PDF, planilha do cliente) → contexto do modelo;
(4) internet → origem do SQ.

| STRIDE | Ameaça na fronteira | Controle exigido | Ordem F1 | T-SEG |
|---|---|---|---|---|
| S | Agente usa token de um escopo para outra capability ou identidade de outro papel | Token delegado curto por usuário e escopo; Gateway confere delegação e capability | F1-01, F1-11 | T-SEG-30 |
| S | Requisição chega à origem sem passar pelo túnel e forja `X-Forwarded-*` | Porta 8000 só em loopback; túnel e Access por instância | F1-04, F1-14 | (prova por varredura externa, sem T-SEG) |
| T | Payload muda entre a aprovação e o envio (valor, destinatário, item) | Hash canônico do payload aprovado conferido na execução; item expira quando o hash do cálculo muda | F1-06, F1-30 | T-SEG-01 |
| T | Total vindo do modelo difere do número do motor | Recálculo pelo motor antes do envio; diferença ≥ R$ 0,01 bloqueia | F1-06 | T-SEG-02 |
| T | Autorização reaproveitada (replay, sessão velha, hash trocado) | Passkey com step-up assinando o hash dos parâmetros | F1-32 | (prova M11 = 0 da F1-32) |
| R | Envio sem trilha ou sem recibo | Ledger com reserva prévia; recibo obrigatório; `trace_id`, evidência e decisão por execução | F1-07, F1-08, F1-12 | T-SEG-05 |
| I | Proposta para destinatário fora do cadastro ou alterado há pouco | Cadastro com origem e data; alterado vira C4 | F1-09 | T-SEG-03 |
| I | Dado do cliente enviado a provedor (SMTP, LLM, conector) sem DPA | Allowlist da instância ∩ DPA, fail-closed mesmo com banco fora; todo HTTP pelo Gateway | F1-10, F1-05 | T-SEG-60, T-SEG-07 |
| D | Replays ou chamadas concorrentes geram vários envios | `idempotency_key` + chave única no ledger; queda vira `desconhecida` e conciliação, nunca retry cego | F1-03, F1-07, F1-08 | T-SEG-04, T-SEG-05 |
| E | Agente age acima de quem delegou, ou depois de perder a permissão | Interseção de permissões recalculada na execução; credencial por tarefa expira | F1-11 | T-SEG-31, T-SEG-32 |
| E | Dado externo vira instrução (prompt injection em e-mail, PDF, planilha) | Quarentena, parse tipado, template com campo delimitado, Supervisor sem `externo_texto` bruto, id de tool nunca vindo do modelo | F1-13 | T-SEG-45, T-SEG-46, T-SEG-47, T-SEG-48 |

**Estado atual do caminho de envio (antes da F1).** `proposal_send_email`
(`proposals/views.py`, `proposals/services.py` `send_email`) envia a qualquer e-mail válido digitado,
sem idempotência, sem conferir aprovação técnica nem hash, e o PDF é renderizado do estado vivo da
cotação, não do snapshot aprovado. É aceitável como envio manual humano; **não pode ser o caminho do
Core**. O `proposal.send` da F1 nasce separado, com os controles da tabela, e o envio manual converge
para ele antes do primeiro envio real.

---

## 9. Pendências jurídicas (não são limites)

Registradas como pendência, não como regra técnica. Este doc não decide nenhuma delas; o Capitão
encaminha ao jurídico (`cognitive-core/docs/DECISOES-CAPITAO.md`, parte II).

| DP / parte | Tema | Trava | Efeito aqui enquanto aberta |
|---|---|---|---|
| DP-27 (J-27) | Retenção; inclui os **15 anos NR-13** de cotações, cálculos e propostas citados no `PROJECT_BRIEF` | F1, F4 | Nada é apagado por rotina; prazo de `AccessLog` e histórico de usuário também esperam |
| DP-22 (J-22) | Papel da Quantum na LGPD (controladora ou operadora) | F1 | Define quem responde ao titular e à ANPD |
| DP-23 (J-23) | Bases legais por capability | F1 | §5.1 fica sem base legal por campo |
| DP-24 (J-24) | Modelo de DPA e lista de suboperadores | F1 | Allowlist de provedor (F1-10) não abre para ninguém sem DPA |
| DP-26 (J-26) | Incidente e encarregado | F1 | §5.3 sem nome do encarregado nem prazo contratual |
| J-19 (DP-19 aprovada) | Modelo de linguagem na nuvem: parte contratual | F1 | Nenhum dado de cliente a LLM em nuvem |
| J-20 (DP-20 aprovada) | Termo de uso de dado do piloto | F1 | Sem rotulagem nem golden set com dado real do piloto |
| J-28 (DP-28 aprovada) | Cloudflare no DPA | F1 | Túnel em uso técnico; contratação formal pendente |
| J-29 (DP-29 aprovada) | Backup cifrado em provedor estrangeiro | F1 | Backup off-site em provedor estrangeiro espera o parecer |
