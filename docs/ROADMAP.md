# ROADMAP.md — SmartQuotation

> **Status:** Aprovado | **Versão:** 1.0 | **Referência:** EPICS.md, PROJECT_BRIEF.md

---

## Visão Geral dos Horizontes

```
H1 técnico ─ Motor de Cotação           0 – 6 meses     ✅ fechado
H1 auditável ─ Aprovação + trilha       0 – 3 meses     ✅ fechado
H2 ─── Gestão da Produção              6 – 18 meses     ← estamos aqui (H2.5)
H3 ─── ERP Especializado Caldeiraria   18m+
```

### Leitura atual do escopo

| Faixa | Status real |
|---|---|
| H1 técnico | feixe tubular + BEU/BEM, sessão auth, EAP persistida, proposta, histórico e API |
| H1 auditável | CREA obrigatório, ART opcional, snapshot por cotação e trilha mínima |
| H2 | OF, apontamento, motor de aprendizado e ITP básico entregues; próximo foco é Protheus |
| H1.5/H2+ | Equipment/Component formal, JWT/MFA, PVElite completo e integrações ERP |

---

## H1 — MVP: Motor de Cotação (90 dias / 6 sprints)

### Critério de Conclusão do MVP

> O H1 técnico fica completo quando um usuário consegue criar, revisar e precificar cotações
> de feixe tubular e BEU/BEM com sessão auth e EAP persistida por cotação. O pacote auditável
> completo, a validação ampla contra PVElite e o contrato JWT/MFA ficam fora do H1.

---

### Sprint 0 — Fundação (semanas 1–2)

**Meta:** Infraestrutura base funcionando. Nenhum código de negócio ainda.

| Story | Descrição | SP |
|---|---|---|
| S-001 | Setup Django + PostgreSQL + django-tenants | 8 |
| S-002 | Health check, logging estruturado, Sentry | 3 |
| S-003 | Login / logout por sessão + CSRF | 5 |
| — | Docker Compose dev + staging provisionado | — |
| — | GitHub Actions: lint + test + bandit + pip-audit | — |
| — | Domínio + wildcard TLS via Caddy no staging | — |

**Total:** 16 SP
**Definition of Done do Sprint:**
- [ ] `https://acme.staging.smartquotation.com.br/health/` retorna 200
- [ ] Tenant A não vê dados do Tenant B (teste automatizado passando no CI)
- [ ] Login funciona com sessão; rate limiting ativo
- [ ] Pipeline CI/CD verde: lint → test → scan → deploy staging automático

---

### Sprint 1 — Auth completa + Cadastros Base (semanas 3–4)

**Meta:** H1 auditável começa a fechar: aprovação técnica mínima, CREA obrigatório e cadastros mestre estão disponíveis.

| Story | Descrição | SP |
|---|---|---|
| S-004 | Aprovação técnica com CREA obrigatório | 5 |
| S-005 | RBAC mínimo + auditoria de cotação | 8 |
| S-006 | Catálogo de materiais + preços + allowable stress | 8 |
| S-007 | Operações, máquinas, Rate 3-camadas + seeds | 8 |
| S-008 | Cadastro de clientes (CNPJ, contato) | 3 |
| S-009 | Estrutura do módulo `engineering/` + versionamento | 5 |

**Total:** 37 SP
**Definition of Done do Sprint:**
- [ ] Engenheiro sem CREA não consegue ser promovido ao role engenheiro
- [ ] Aprovação técnica exige CREA; ART segue opcional
- [ ] Seeds de materiais ASME carregados; allowable stress por temperatura consultável
- [ ] Rate `industry_standard` populado; resolução de hierarquia testada
- [ ] Módulo `engineering/` importável sem Django; decorator `@calculation` funcionando

---

### Sprint 2 — Motor de Cálculo ASME (semanas 5–6)

**Meta:** Sistema calcula espessura de vaso de pressão completo com validação PVElite.

| Story | Descrição | SP |
|---|---|---|
| S-010 | Cálculo de casco cilíndrico (UG-27) + regressão PVElite | 8 |
| S-011 | Cálculo de tampos — 5 tipos (UG-32 + UG-34) | 8 |
| S-012 | Cálculo de bocais e reforço (UG-37) | 8 |
| S-014 | Suite de regressão PVElite como gate de CI (≥ 25 casos) | 5 |

**Total:** 29 SP
**Definition of Done do Sprint:**
- [ ] CI bloqueia deploy se qualquer caso PVElite tiver delta > 1%
- [ ] Casco + tampos + bocais calculados para caso de referência (V-101 da documentação interna)
- [ ] Peso calculado com delta ≤ 2% em relação ao PVElite
- [ ] `CalculationSnapshot` gravado com hash, versão e referência à norma

---

### Sprint 3 — Cotação, Equipamentos e Trocadores (semanas 7–8)

**Meta:** Usuário cria cotação completa de vaso e trocador com componentes calculados.

| Story | Descrição | SP |
|---|---|---|
| S-013 | Cálculo de trocadores de calor (TEMA) | 13 |
| S-015 | CRUD de cotações + workflow de status | 8 |
| S-016 | Data sheet de vaso de pressão (formulário HTMX) | 8 |
| S-017 | Data sheet de trocador de calor (formulário HTMX) | 8 |
| S-018 | Disparo de cálculo + visualização de resultado | 8 |
| S-019 | Importação de cálculo de terceiro (modo Importado) | 5 |

**Total:** 50 SP ← sprint mais pesado; avaliar split se necessário
**Definition of Done do Sprint:**
- [ ] Cotação COT-2025-001 criada com V-101 (vaso) e E-101 (trocador) calculados
- [ ] Resultado exibido por componente com espessura e peso
- [ ] Modo importado funciona com PDF de laudo externo + hash gravado
- [ ] Revisão de cotação cria COT-2025-001-B apontando para original

> ⚠️ **Nota de planejamento:** Sprint 3 tem 50 SP — 70% acima da média.
> Opção A: splittar S-013 (TEMA) para Sprint 2b (semana extra entre sprint 2 e 3).
> Opção B: mover S-019 para Sprint 4. Decisão a ser tomada no planning do Sprint 3.

---

### Sprint 4 — Custo, Preço e Proposta (semanas 9–10)

**Meta:** Sistema forma preço completo e gera proposta em PDF/DOCX.

| Story | Descrição | SP |
|---|---|---|
| S-020 | BOM automático a partir dos componentes | 8 |
| S-021 | Roteiro de fabricação automático | 8 |
| S-022 | Formação de preço + breakdown + impostos | 8 |
| S-023 | Template de proposta customizável por tenant | 5 |
| S-024 | Geração assíncrona de DOCX e PDF (Celery) | 8 |

**Total:** 37 SP
**Definition of Done do Sprint:**
- [ ] BOM da cotação COT-2025-001 gerado com pesos e custos corretos
- [ ] Preço de venda formado com breakdown material/MO/overhead/impostos/margem
- [ ] PDF da proposta gerado em < 30 segundos e disponível para download
- [ ] Download registrado no AccessLog (user, IP, timestamp)

---

### Sprint 5 — Aprovação Técnica, Audit e Dashboard (semanas 11–12)

**Meta:** Produto completo e auditável. Pronto para piloto com cliente real.

| Story | Descrição | SP |
|---|---|---|
| S-025 | Aprovação técnica vinculada ao snapshot de cálculo | 8 |
| S-026 | Tela de auditoria e histórico (django-simple-history) | 5 |
| S-027 | Validação PVElite manual + dashboard de qualidade do motor | 5 |
| S-028 | Dashboard principal (cotações, taxa de conversão, rentabilidade) | 5 |
| S-029 | Relatórios exportáveis (CSV + PDF) | 5 |
| — | Testes de aceitação com cliente piloto | — |
| — | Documentação de usuário (guia rápido PDF) | — |
| — | Runbook de operação e restore | — |

**Total:** 28 SP
**Definition of Done do Sprint (= Definition of Done do MVP):**
- [ ] Fluxo completo end-to-end testado: cotação → cálculo → aprovação técnica → proposta → download
- [ ] Audit trail completo: toda ação rastreada e exportável em CSV
- [ ] 1 cliente piloto fez login, criou cotação e gerou proposta sem suporte do dev
- [ ] Backup off-site rodando e restore testado (exercício de DR documentado)
- [ ] Nenhum item P0 em aberto no backlog

---

## Burndown de Story Points (MVP)

```
Sprint 0:  197 SP restantes → entrega 16 SP → 181 SP
Sprint 1:  181 SP restantes → entrega 37 SP → 144 SP
Sprint 2:  144 SP restantes → entrega 29 SP → 115 SP
Sprint 3:  115 SP restantes → entrega 50 SP →  65 SP
Sprint 4:   65 SP restantes → entrega 37 SP →  28 SP
Sprint 5:   28 SP restantes → entrega 28 SP →   0 SP ✅
```

---

## H2 — Gestão da Produção (meses 6–18)

### Milestones H2

| Milestone | Prazo estimado | Entrega |
|---|---|---|
| **H2.1** — Conversão cotação → OF ✅ **(entregue, #47)** | mês 7 | Ordem de Fabricação herdando BOM e roteiro da cotação; zero retrabalho de digitação. Exige aprovação técnica ativa; deep-copy com snapshot_hash pinado; workflow de status com autoria por transição |
| **H2.2** — Apontamento de produção ✅ **(entregue, PR)** | mês 9 | Operador registra horas por operação; no fechamento da OF calcula R$/h observado (= custo ÷ horas reais) → `ActualRate` (Welford). Baseline = custo (o motor não expõe horas estimadas) |
| **H2.3** — Motor de aprendizado de índices ✅ **(entregue, `aa3127c`)** | mês 10 | Sistema sugere atualização do `TenantRate` quando `ActualRate` tem N ≥ 20 amostras e confidence ≥ 70%; aplicação/descarta via UI com RBAC |
| **H2.4** — ITP básico ✅ **(entregue)** | mês 11 | Plano de inspeção gerado a partir do roteiro; aceite por item com responsável e data |
| **H2.5** — Conector TOTVS Protheus 🚧 **(foundation entregue, PR #52)** | mês 13 | Sincronização bidirecional: OF, BOM, materiais, fornecedores |
| **H2.6** — Conector Omie / Bling | mês 14 | Emissão de NF-e via Omie a partir da OF concluída |
| **H2.7** — Conector SAP B1 | mês 16 | Sincronização de pedidos e BOM com SAP B1 (clientes enterprise) |
| **H2.8** — Expansão normativa: API 650 | mês 15 | Tanques atmosféricos dimensionados conforme API 650/620 |
| **H2.9** — Expansão normativa: ASME B31.3 | mês 17 | Tubulações de processo dimensionadas |
| **H2.10** — Multi-moeda e exportação | mês 18 | Cotações em USD/EUR; conversão automática; adequação PED para exportação EU |

### Arquitetura de integração ERP (H2)

```
SmartQuotation API (DRF)
    │
    ├── /api/v1/webhooks/        ← push de eventos para ERP
    │
    └── apps/integrations/
          ├── protheus/          ← conector TOTVS (REST API Protheus 12)
          ├── sap_b1/            ← conector SAP Business One (Service Layer)
          ├── sankhya/           ← conector Sankhya (SankhyaW API)
          ├── omie/              ← conector Omie (API REST)
          ├── bling/             ← conector Bling (API v3)
          └── generic_csv/       ← fallback universal (import/export CSV padronizado)
```

Cada conector é uma Django app plugável, ativável por tenant via feature flag.
Autenticação por conector: API key ou OAuth2 armazenados em campo cifrado em `TenantIntegrationConfig`.

---

## H3 — ERP Especializado Caldeiraria (18m+)

### Roadmap de alto nível H3

| Módulo | Descrição |
|---|---|
| **PCP completo** | Programação de produção por máquina/centro de custo, kanban de OF, sequenciamento |
| **MES — chão de fábrica** | App mobile para apontamento por QR code de OF; dashboard de OEE por máquina |
| **Qualidade integrada** | NC, AC/AP, FMEA, ITP completo com aceite digital, rastreabilidade de materiais (certificados) |
| **Fiscal completo** | NF-e, NFS-e, SPED, EFD-ICMS, integração com contabilidade |
| **Portal do cliente** | Acompanhamento de pedido, aprovação de documentos de engenharia, NF-e |
| **BI executivo** | Dashboards de rentabilidade, OEE, lead time, win rate, forecast |
| **Marketplace de fornecedores** | Cotação automática de materiais para as distribuidoras parceiras |
| **Certificação ISO 27001** | Auditoria formal + certificado para grandes clientes e licitações |

---

## Dependências Externas e Riscos

| Risco | Probabilidade | Impacto | Mitigação |
|---|---|---|---|
| Delta PVElite > 1% em casos de borda (tampos cônicos, bocais inclinados) | Alta | Alto | Gate de CI com casos progressivos; modo Importado como fallback imediato |
| Sprint 3 sobrecarregado (50 SP) | Alta | Médio | Avaliar split no planning; S-019 pode mover para Sprint 4 sem impacto no fluxo principal |
| Dev parceiro com capacidade reduzida em sprint específico | Média | Alto | Buffer de 10% de SP não alocados por sprint; P.O. assume stories de menor complexidade |
| Acesso ao PVElite para validação | Baixa | Alto | Engenheiro de domínio confirma acesso; sem acesso → usar casos de literatura ASME como baseline |
| Cliente piloto sem tempo para testar no Sprint 5 | Média | Médio | Iniciar onboarding do piloto no Sprint 4 com dados reais (não esperar Sprint 5) |
| Regulação: NR-13 exigir registro formal do software | Baixa | Alto | Acompanhar portaria MTE; arquitetura de rastreabilidade já supera o mínimo exigido |

---

## Métricas de Sucesso

### MVP (H1)
| Métrica | Meta |
|---|---|
| Tempo médio de elaboração de cotação | < 4 horas (vs. 1–3 dias manual) |
| Delta vs. PVElite em espessura | ≤ 1% em 100% dos casos de regressão |
| NPS do cliente piloto | ≥ 8/10 |
| Uptime em produção | ≥ 99.5% |
| Cobertura de testes do motor de cálculo | ≥ 90% |

### H2
| Métrica | Meta |
|---|---|
| Clientes pagantes | ≥ 10 tenants ativos |
| MRR | R$ 15.000/mês |
| Taxa de conversão cotação → pedido | Rastreada (baseline estabelecido no H1) |
| Tempo de conversão cotação → OF | < 30 minutos |

### H3
| Métrica | Meta |
|---|---|
| Clientes pagantes | ≥ 50 tenants ativos |
| MRR | R$ 100.000/mês |
| Churn mensal | < 2% |
| NPS geral | ≥ 50 |
