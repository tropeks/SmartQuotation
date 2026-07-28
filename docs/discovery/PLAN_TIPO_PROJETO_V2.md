<!-- rascunho para /autoplan — v2, reframe: controle de vazamento de margem -->
# Plano — Controle de vazamento de margem (e o tipo de projeto como modulador)

## Missão
SmartQuotation é solução COMERCIAL multi-tenant cuja missão é **estancar vazamento de margem**
(ver memória `missao-produto-estancar-vazamento-margem`). Esta feature NÃO é "trava de edição por
tipo de projeto" (o reframe veio do autoplan CEO phase: os dois modelos mostraram que travar o
teclado ataca a camada errada — a segurança já é coberta pela assinatura ART por-cotação do F10).
O objetivo aqui é **margem**, não segurança.

## Problema
Numa cotação, certas mudanças **vazam margem** e hoje podem ser feitas sem revisão do dono certo.
Vetores de vazamento:
1. **Knobs comerciais** — markup, rates (R$/h), preço de material. Baixar "compra" a venda.
2. **Params de produção** — setup_frac, scrap/perda, tempos de processo. Inflam/deflacionam custo.
3. **Params de engenharia** — geometria (corte de chicana, u-bend, folgas, espessura) muda
   peso→material e horas.
4. **Overrides manuais na EAP** — `eap_item_save` (`views.py:496`) grava direto em
   `ItemMaterial`/`ItemOperation` SEM passar pelo motor. Vazamento mais direto; o desenho antigo
   ignorava.

## Princípio
**Usar/rascunhar** um valor numa cotação é livre; o que muda a margem além da **linha de base
calculada** SINALIZA a cotação para (re)aprovação do dono certo. O bloqueio vive na
**assinatura/conversão em OF**, não na tecla (soft-verify). Configurável por tenant.

## O tipo de projeto como MODULADOR (não como gate)
`design_basis` (proveniência técnica), eixo próprio, ortogonal a `scope`:
- `internal_design` — engenharia originada na casa (equivalente a "projeto novo"). Mudança de
  param de engenharia por não-engenheiro = suspeita de vazamento → sinaliza.
- `external_design` — transcrição de projeto assinado do cliente (reposição/parte). Mudança de
  param de engenharia pelo orçamentista = FIDELIDADE ao doc do cliente, esperada → NÃO sinaliza
  (mas registra a fonte documental estruturada).

Nota: o descritor comercial "novo/reposição/parte" é derivado/independente; o driver de governança
é `design_basis` (binário), não o enum de 3 valores.

## Decisões de design (rascunho, endereçando os achados CEO)

### D1. Dois eixos, corrigindo a semântica do `scope` (achado Codex/Claude #1,#3,#6)
- `scope` (tube_bundle | complete | parts) passa a ser SÓ geometria; renomear o rótulo de
  `parts` para não dizer "Reposição" (hoje `models.py:35-36`).
- `design_basis` (internal_design | external_design) = proveniência. Campo novo.
- NÃO adicionar um enum `project_type` de 3 valores ao lado de `scope=parts` (recriaria a
  confusão de rótulos parecidos no `tema_entry`).

### D2. Taxonomia por-campo é pré-requisito (achado #5 — "o coração que falta")
Hoje o data sheet é um `inputs` JSONField único, sem separação de campos de engenharia vs
comercial. Antes de qualquer gate, ENUMERAR cada campo editável (data sheet + EAP) numa
classificação `engenharia | producao | comercial | livre`, reusando a classificação do Wellington
(`CLASSIFICACAO_KNOBS_WELLINGTON.md`, memória `knobs-governanca-por-tipo-cotacao-wellington`).
Essa tabela campo→classe→dono é o artefato central.

### D3. Enforcement pela matriz de capability existente, NÃO gate in-view (achado #2)
Não criar `if design_basis == 'internal'` espalhado em views. Expressar a regra pela matriz
`RolePermission` (RBAC V2 / F10), configurável por tenant. Capabilities por classe de mudança,
resolvidas via `role_can`. Cobrir TODAS as portas: data sheet feixe (`quotation_edit`), permutador
(`tema_templates/views.py`), EAP override (`eap_item_save`, `eap_op_restore`), E a API
(`serializers.py` — hoje nem tem o campo).

### D4. Detecção de vazamento = delta vs base calculada + reaprovação
Reusar o mecanismo de snapshot/staleness que já existe (o `KnobChangeProposal` e a invalidação
por hash de cálculo do F10). Uma mudança que afeta custo/preço além de um limiar (por tenant)
marca a cotação como "margem alterada → requer aprovação de [classe]". A assinatura CREA/ART do
F10 vira **diff-aware**: "campos de engenharia mudaram desde a última assinatura → re-assinar".

### D5. Proveniência estruturada, não texto livre (achado #7 — exposição jurídica)
Quando `external_design`: origem documental ESTRUTURADA (nº do documento do cliente, revisão,
data, referência de arquivo anexo), não `CharField` livre. Só isso pode ir na proposta como
disclaimer ("dados conforme doc cliente X rev.Y"). Suportar múltiplas fontes / origem mista por
grupo de campos (achado Codex).

### D6. Imutabilidade e anti-bypass (achados #2 mutabilidade, #8 null)
- `design_basis` e a classificação ficam IMUTÁVEIS após cálculo/assinatura/conversão, salvo
  reabertura auditada. Sem isso, troca-se o eixo, edita-se, e volta.
- Backfill: NÃO deixar `null` = "regra antiga" (corredor de bypass permanente). Forçar
  classificação na próxima edição de cotação legada, ou migração explícita.
- `requires_crea` é trait de responsabilidade profissional, NÃO capability de edição — não
  acoplar (achado #4). "Admin edita engenharia" também não (sysadmin ≠ competência técnica).

## Impacto
- `apps/quotations/models.py`: +`design_basis`, +proveniência estruturada; ajuste rótulo `scope`.
  Migration `quotations/0009`.
- `apps/access/capabilities.py`: capabilities por classe de mudança + seed `RolePermission`.
- `apps/quotations/views.py` + `tema_templates/views.py` + `serializers.py`: enforcement via
  matriz nas 4 portas + API; detecção de delta de margem.
- Assinatura F10 diff-aware.
- Tabela campo→classe (novo módulo/config).

## Testes
- Cada vetor de vazamento (comercial/produção/engenharia/EAP override) dispara o sinal certo.
- `external_design`: orçamentista edita engenharia sem sinalizar; origem documental registrada.
- `internal_design`: mudança de engenharia por não-engenheiro sinaliza.
- API não é porta esquecida.
- Imutabilidade após assinatura; sem bypass por null.
- Assinatura vira stale quando campo de engenharia muda.

## Resultado do autoplan (dual-voice CEO+Design+Eng) — reestruturação em fatias

Achados críticos das vozes de Eng (Codex+Claude convergiram):

- **BUG VIVO (independe da feature):** `eap_item_save`/`eap_op_restore` (`views.py:496,592`) e
  `compose_parts_create` (`:415`) gravam direto nas linhas SEM emitir `CalculationSnapshot` e sem
  tocar `computed_at`. Logo `_case_is_stale` NÃO invalida um case aprovado após override, e a
  assinatura CREA continua "válida". Exploit hoje: aprovar → baixar custo/horas no drawer da EAP →
  hash inalterado → converter em OF com margem vazada. É o vetor #4 do plano, explorável já.
- **"Reusar o snapshot/staleness" não fecha:** o `snapshot_hash` é UM sha256 do payload inteiro
  (binário: mudou/não mudou). Roteamento "qual CLASSE moveu a margem" exige um **motor de diff
  por-campo→classe** (net-new), não o hash. É o 2º maior subsistema depois da taxonomia.
- **Capability matrix faz ROTEAMENTO, não gating:** soft-verify = marcar "requer aprovação da
  classe X", não `PermissionDenied`. As capabilities novas são de APROVADOR
  (`ApprovalStage.approver_capability`), checadas DENTRO da view contra o conjunto de campos que
  mudou. Se implementar como decorator/lock, recria o keyboard-lock que o reframe rejeitou.
- **Taxonomia = 4-5 namespaces distintos** (FeixeInputs / inputs `complete` / `QuotationPart.params`
  / colunas EAP `ItemMaterial`/`ItemOperation` / tema_templates), cada um com storage diferente.
  "Configurável por tenant" = DB + seed por schema + UI + cache (padrão do RBAC matrix).
- **Dois modelos de edição:** data sheet FORKA nova `Quotation` (revisão+1); EAP muta a mesma
  linha. "Diff desde a assinatura" são DUAS implementações (cross-revisão vs in-row).
- **Deadlock fail-closed (risco de outage):** capability de aprovador nova sem semear
  `RolePermission` em TODOS os schemas → `is_qualified` False p/ todos → toda cotação trava na
  conversão, tenant-wide. `ensure_capabilities` não persiste (by design).
- **Correções:** default seguro `design_basis=internal_design` (conservador); copiar forward no
  fork (precedente `pricing_basis editable=False`); não re-hashear snapshots existentes (invalida
  assinaturas em massa); tratar snapshot pré-taxonomia como branch explícito (mais seguro:
  re-assinar). **API NÃO é porta viva** (serializers read-only, sem write path pra `inputs`) —
  achado do plano estava superestimado; manter no checklist p/ quando surgir write endpoint.
- **Design (ambas as vozes):** falta a máquina de estados do sinal (`clean/drafting/leak_pending
  (owner,classes)/stale_signature/error`); proveniência = passo guiado explícito (não dropdown
  derivado do scope) + doc-âncora com divulgação progressiva; campo **editável-mas-sinalizado**,
  não disabled; re-assinatura com diff agrupado por classe; proposta bloqueada enquanto pendente.
  Adicionar seção "telas & estados" ao plano.

### Fatiamento recomendado (ambas as vozes de Eng pediram o mesmo)
- **M1 — tampar o vazamento vivo (ship sozinho, alto valor):** emitir snapshot nos caminhos
  EAP/parts; `eap_item_save` virar `transaction.atomic` + lock; default seguro e imutabilidade de
  `design_basis`. Fecha o exploit sem esperar a taxonomia.
- **M2 — taxonomia estática em código só p/ FeixeInputs + diff por-classe no data sheet** +
  assinatura diff-aware com snapshot por-campo.
- **M3 — taxonomia configurável por tenant** (demais namespaces) + roteamento de aprovador via
  `ApprovalStage` + máquina de estados + change ledger transacional.
- **M4 — UI:** guided provenance step, margin-integrity strip, re-sign diff panel, proposta.

## Fora de escopo (planos separados)
- Reclassificação completa dos knobs do tenant em trilhas (é insumo, via memória do Wellington).
- Condição-por-valor de aprovação (G5) — pode compor depois com a detecção de delta.
- Importação de desenhos/datasheets do cliente (a feature "documento→dado rastreável" que os
  modelos citaram como o 10x de mercado; registrar no backlog).
