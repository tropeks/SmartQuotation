# SPEC — Beta 100% Funcional (v1, 2026-07-10)

**Autor:** Fable 5 (CEO) · **Validado por:** Rom (2026-07-10) · **Revisão técnica de domínio:** Wellington (PE)
**Objetivo:** fechar os gaps que separam o SmartQuotation de uma beta operável de ponta a ponta pela ENGEMATEX sem tocar no Django admin, com o fluxo cotação→OF→ERP completo. "Beta 100%" = um orçamentista e um engenheiro operam o ciclo inteiro no produto.

**Origem dos gaps:** feedback Rom/Wellington pós-deploy das telas 05/06/07 (quotation.qtec.me) + auditoria de código/UI + grafo (`graphify-out/GRAPH_REPORT.md`).

---

## Épico 1 — EAP-MO editável na cotação ⭐ (prioridade 1, estrutural)

**Problema:** `ItemOperation` (apps/quotations/models.py:120) persiste só `custo` (R$). As horas calculadas pelo motor (ProcessParameter → horas → R$ via Rate) são descartadas na persistência. O drawer da EAP (`eap_item_save`, views.py:354) permite editar peso+custo de material e apenas o custo em R$ da operação. Regra de negócio (Wellington): **enquanto é cotação, o usuário precisa editar a quantidade de HORAS orçadas de cada operação do roteiro** — tanto estrutura do produto quanto roteiro — pois esses dados seguem para a OF na conversão.

**Escopo:**
1. **Modelo:** `ItemOperation` ganha `horas` (Decimal) e `taxa_hora` (Decimal, snapshot da Rate usada). `custo` passa a ser DERIVADO (horas × taxa_hora) quando houver horas; operações sem base horária (serviços de terceiros a preço fechado) continuam custo-direto — flag `custo_direto`.
2. **Adapter:** `recompute()` passa a persistir horas/taxa vindas do motor (o motor já as calcula — expor no resultado da EAP, sem mudar a API pública do pricing_engine além de adicionar campos ao dataclass de saída).
3. **UI (drawer/aba EAP):** editar horas por operação (custo recalcula on-the-fly), manter edição de custo-direto onde aplicável. Padrão visual Design System G, HTMX como o drawer atual.
4. **Override e auditoria:** edição manual é override (como hoje: NÃO dispara motor, não cria revisão); gravar trilha de quem/quando/campo/valor-anterior (reusar app `audit`).
5. **Propagação pra OF:** `OFOperation` ganha os mesmos campos; `convert_quotation_to_of` transfere horas/taxa. OF detail exibe roteiro com horas.
6. **Aceite:** criar cotação → editar horas de 2 operações e 1 material → converter em OF → OF exibe roteiro com horas editadas → export ERP (épico 2) recebe horas. Golden gates do motor intactos (feixe −2,9%, permutador 0,0%). Testes de drawer/convert atualizados.

**Riscos:** migração de dados das cotações existentes (backfill horas=NULL, custo-direto=True); não quebrar o override existente de custo.

## Épico 2 — Integração Nomus (prioridade 2)

**Problema:** decisão Rom 2026-07-10: ERP prioritário é **Nomus** (não SAP B1). Não existe `integrations/nomus`. O vira-OF deve transferir **lista de material + roteiro de fabricação** pro ERP.

**Escopo:**
1. Novo módulo `apps/integrations/nomus/` seguindo o padrão do `sap_b1` (client, serviços, ExportLog com status/conflito/retry, tasks Celery, admin de credenciais write-only cifradas).
2. Investigar API do Nomus (REST; documentação pública) — task de pesquisa ANTES das tasks de código; se a API real não estiver acessível, implementar contra client fake nos testes + interface bem definida (mesma técnica do SAP B1).
3. Export no evento de conversão (e re-export manual na OF): lista de material (OFMaterial) + roteiro com horas (OFOperation, depende do Épico 1).
4. Config por tenant: qual ERP ativo (nomus | sap_b1 | nenhum). SAP B1 permanece funcional.
5. **Aceite:** converter cotação → OF gera export Nomus (ou fila com retry se ERP fora); log visível; conflito (OF já exportada) tratado como no SAP B1.

## Épico 3 — UI de materiais e preços (prioridade 3)

**Problema:** `apps/materials` não tem views/urls/templates. Material (423 seed) e MaterialPrice (cifrado, por forma) só via Django admin.

**Escopo:** tela de listagem/busca de materiais com preços por forma; edição de preço com histórico (quem/quando/de-para — reusar `audit`); indicação de "preço usado na última cotação X". RBAC: papel comercial/engenharia edita, viewer não. Sem CRUD de Material em si nesta fase (seed é normativo) — só preços.
**Aceite:** alterar um preço → nova cotação usa o preço novo → histórico registra.

## Épico 4 — UI de calibração (Rates + ProcessParameter) (prioridade 4)

**Problema:** só existe UI de suggestions. Rate (R$/h por recurso) e ProcessParameter (física→horas, por operação×máquina) são editáveis só no admin. O conhecimento de calibração fica preso no Wellington.

**Escopo:** tela única de calibração com 2 abas (Taxas | Parâmetros de processo); edição com **impacto simulado**: antes de salvar, recotar 1 golden case do tenant e exibir o delta de custo (usa o motor puro, sem persistir). Trilha de auditoria. Integrar as suggestions existentes (aceitar sugestão = aplicar valor com origem "apontamento").
**Aceite:** editar uma taxa → simulação mostra delta no golden case → salvar → recompute de cotação usa valor novo.

## Épico 5 — Gestão de usuários do tenant (prioridade 5)

**Problema:** criar usuário/definir papel = admin cru. Tenant não se auto-administra.

**Escopo:** tela de membros do tenant (listar/convidar por e-mail/definir papel RBAC/desativar); regra engenheiro→CREA preservada; convite gera senha provisória com troca obrigatória (fluxo simples, sem e-mail transacional externo nesta fase — exibir link/senha pro admin copiar).
**Aceite:** admin do tenant convida orçamentista → novo usuário loga e cria cotação; viewer não edita.

---

## Regras globais (todas as sprints)

- **Gates intocáveis:** validate_feixe_completo, validate_permutador_completo, golden_anchors, suíte Django (`bash .orch-test.sh`, DB por branch).
- **Design System G** (UX_SPEC v2) em toda UI nova; HTMX+Alpine, sem SPA.
- **Multi-tenant:** tudo por schema; nada de vazamento cross-tenant (MEDIA por schema já corrigido — manter padrão).
- **pricing_engine continua puro** — único acoplamento via adapter.
- **TDD** — teste que falha primeiro; evidência de execução.
- Ordem dos épicos: 1 → 2 → 3 → 4 → 5. Fila antiga (saas/api650/b313/multicurrency) REPRIORIZADA para depois da beta (decisão Rom 2026-07-10).
