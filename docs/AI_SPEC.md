---
# Contrato de documentação (Maestro E16).
#
# Onde a IA toca o SmartQuotation na Fase 1 do Quantum Cognitive Core, e onde ela nunca
# entra. Cover estreito: a futura borda com o Core e o app que hoje guarda a única
# "sugestão com confiança" do produto (RateSuggestion, estatística, não modelo).
#
# `backend/apps/core_bridge/**` ainda não existe: é o caminho previsto pela
# cognitive-core/docs/ARQUITETURA.md §6.1 para a F1-02. O glob fica declarado para o doc
# ser emendado no mesmo changeset que criar o módulo.
covers:
  - backend/apps/core_bridge/**
  - backend/apps/engineering_params/**
reviewed: 2026-09-27
---

# AI_SPEC.md — SmartQuotation

> **Status:** rascunho do Conformador, 27/09/2026 | **Direção:** `.maestro/INTENT.md` v2 (carimbado, DP-52)
> **Fontes:** `cognitive-core/docs/FASES.md` §1, §4.4, §9; `ARQUITETURA.md` §3 e §6.2;
> `DECISOES-CAPITAO.md` (DP-06, DP-14, DP-17, DP-19, DP-20).
> **Este doc não escolhe modelo nem limiar.** Modelos candidatos, métricas e números de admissão
> são do Core e do Capitão; aqui só se registra o que o SQ expõe, o que ele proíbe e o que já decidiram.

## 1. Onde a IA mora e onde não mora

**No SmartQuotation não há modelo.** Conferido em 27/09/2026:
`grep -rniE "openai|anthropic|llm|embedding" backend pricing_engine` não acha cliente de modelo,
SDK de provedor, embedding nem prompt. A ARQUITETURA §6.2 diz o mesmo ("Não há LLM no produto hoje").

A cognição da F1 vive no **Quantum Cognitive Core**, numa instância por cliente, com inferência no
`qcc-infer` do R640 (F1-35, DP-06). O SQ é a primeira vertical e continua **dono do próprio negócio**
(VISAO §6): o Core usa capabilities do produto, com token delegado de um usuário real, pelos mesmos
serviços que a interface usa. Nunca pelo ORM, nunca com conta de serviço.

| Camada | Tem modelo? | Regra |
|---|---|---|
| `pricing_engine/` (motor) | **Nunca** | Lib pura. Custo, horas, peso, preço saem só daqui. |
| `apps/quotations/adapter.py` (único acoplamento) | **Nunca** | `recompute()` é a fonte de todo número que a guarda compara. |
| Cadeia de custo, markup, impostos, `CalculationSnapshot` | **Nunca** | Custo é derivado (motor ou roll-up), nunca digitado nem inferido. |
| Aprovação técnica CREA e assinatura | **Nunca** | L3 humano habilitado; classe C5, travada (ARQUITETURA §3.6). |
| `core_bridge` (previsto, F1-02) | Não. É a borda: manifesto, endpoints finos, `preview` | Recebe `Draft`/`Advice` do Core como **proposta**; nada escrito em dado de negócio sem L0 + L3. |
| Core (repo `cognitive-core`) | Sim: L1 (System One) e L2 (LLM) | Sugere, ordena e sinaliza. **Nunca decide sozinho.** |

**Regras do INTENT que este doc apenas repete e não relaxa:**

1. Modelo sugere, ordena e sinaliza; nunca decide sozinho. L0 (regra) e L3 (humano) decidem; L1 e L2 propõem.
2. Antes de todo efeito externo, regra determinística: recálculo pelo motor, hash canônico do payload
   aprovado, destinatário em cadastro, limites (F1-06, F1-09). Total vindo de modelo que difere do
   recálculo em ≥ R$ 0,01 é bloqueado (T-SEG-02).
3. Dado externo (e-mail, PDF, planilha do cliente) é dado, não instrução (F1-13).
4. O Core roda em **sombra** e depois em **`act_with_approval`**, nunca além, na F1. Promoção automática
   de classe está fora de escopo.
5. Custo é derivado do motor, nunca de modelo. LLM pode **extrair** a string de um valor da folha de
   dados; nunca calcula total, imposto, desconto, margem ou horas.

## 2. Casos de uso da F1 que tocam o SQ

Tarefas da ARQUITETURA §6.2. SQ-3, SQ-4 e SQ-5 **não têm ordem na F1** e ficam fora deste inventário
(ver §7, pergunta P3).

| | SQ-1 Casar material do ERP | SQ-2 Ler a folha de dados | Sugestão de `Rate` (não é IA) |
|---|---|---|---|
| **Tarefa** | Material vindo do ERP → material do catálogo do tenant, ou "material novo" | Pedido/folha de dados → campos de `FeixeInputs` (designação TEMA, nº de tubos, OD, comprimento, liga por lado, pressão) com lacunas marcadas | Propor novo R$/h de uma operação a partir do realizado (`ActualRate`) |
| **Classe** | Classificação (`Choice` sobre opções fechadas + `__none__`) | Extração por schema + verificação (NLI) | Estatística descritiva com regra fixa |
| **Braço** | L0 código igual → L1 `Choice` sobre top-20 do FTS; braços FTS e bge-m3 + Qwen3-Reranker (F1-23) → L3 confirma | Parser → L2 por schema → L1 NLI "o valor está no documento?" → L3 confirma (F1-25) | Nenhum modelo. Média de Welford + fórmula de confiança em código (§5) |
| **Admissão exigida** | Registro de admissão carimbado pelo Capitão (F1-24). Números **propostos**, ainda não carimbados (DP-14 aberta): top-1 ≥ FTS + 10 pp; top-3 ≥ 95%; AUC ≥ 0,80; ECE ≤ 0,08; recall de `__none__` ≥ 90%; p95 ≤ 2 s; pelo limite inferior do IC 95% | Propostos (DP-14 aberta): exatidão por campo ≥ 95%; recall de "campo ausente" ≥ 95%; em ≥ 30 folhas reais rotuladas. **Gate humano de 100% nos campos de alta elasticidade, sem relaxar** | Nenhuma: não é modelo. O limiar `CONF_MINIMA = 0.70` segue como **regra declarada** até a medição da F1-27 (DP-17) |
| **Modo na F1** | Sombra no staging do ERP (≥ 300 decisões, 0 diferença na tela); se carimbado, `advise` com L3 confirmando | **Sombra** (F1-25). Nenhum campo chega à cotação sem o engenheiro | Já em uso: sugestão `pending` → aceite ou descarte humano (`apply_suggestion`) |
| **Dado que usa** | Descrição, norma e código do material remoto; catálogo `Material` do tenant; ≥ 300 pares rotulados por comprador ou engenheiro (F1-22) | Texto da folha de dados e do e-mail; ≥ 30 folhas confirmadas pelo engenheiro; casos OF-3672 e OF-3683 | `ProductionObservation` / `ActualRate` do próprio tenant |
| **Onde roda** | Local: `qcc-infer` em CPU no R640, canal mTLS por instância (F1-35) | **Local por padrão.** Nuvem só por cliente, com provedor nomeado no DPA e retenção zero (DP-19 aprovada; J-19 jurídico **aberto**) → hoje: local | Dentro do SQ (Django), sem rede |
| **Fallback manual** | Hoje: casa só por código igual; código diferente vira material novo. Continua sendo o caminho se o Core cair | Orçamentista digita no data sheet (`apps/tema_templates`), como hoje | Engenheiro edita `Rate` na calibração |

Campos de alta elasticidade: metalurgia do feixe, espessura e diâmetro do casco, comprimento do tubo,
liga, número de tubos (`docs/SENSIBILIDADE_MOTOR.md` §1 — **o arquivo não está neste branch**; existe
no commit `87392e0` de outro branch; ver pergunta P5).

Toda falha do Core (schema, tempo, orçamento, provedor fora da allowlist, córtex desligado) cai no
fluxo manual de hoje. A F1-16 prova 72 h com córtex desligado e 0 execução essencial falhada.

## 3. O que o SQ precisa expor

Nada aqui existe ainda, salvo onde indicado. Tudo é **previsto** e cada item é aberto pelo gerente do SQ.

| Item | Para quê | Estado |
|---|---|---|
| Token delegado curto por usuário e escopo de capability | O Core age como o usuário logado; 403 fora do escopo | **Previsto (F1-01)** |
| `core_bridge`: manifesto assinado + `quotation.read`, `quotation.create_draft`, `quotation.recompute` | Criar rascunho a partir do `Draft` do SQ-2 e recalcular **pelo motor** | **Previsto (F1-02)**; gates do motor inalterados |
| `proposal.render`, `proposal.send` com `preview` e `idempotency_key` | Efeito externo com prévia, hash e recusa de reenvio | **Previsto (F1-03)**. Hoje `send_email` (`apps/proposals/services.py:266`) não é idempotente |
| Fonte de recálculo para a guarda | G0–G2/G4 recomputam total e conferem hash do payload aprovado | **Previsto (F1-06)**, consome `adapter.recompute` e `CalculationSnapshot` (`apps/quotations/models.py:92`) |
| Staging do ERP como entrada do SQ-1 (descrição, norma, código remoto) + lista de opções do catálogo | O Core recebe opções fechadas geradas **pelo código**, nunca criadas pelo modelo | Staging existe para Protheus (`ProtheusCatalogStaging`, `apps/integrations/protheus/models.py:176`); a capability de leitura é **prevista (F1-02/F1-22)** |
| Exportação de pares para o golden SQ-1 (material remoto → material do catálogo, ou `__none__`) + ferramenta de rotulagem | Conjunto de prova com dupla rotulagem em 10% e kappa | **Previsto (F1-22)**, dado fica na instância (DP-20) |
| Folhas de dados rotuladas para SQ-2 (campo, valor confirmado, "ausente") | Exatidão por campo e recall de "ausente" | **Previsto (F1-25)** |
| Evento de correção ligado à decisão: responsável, habilitação, desfecho (`aceito_sem_correcao`, `aceito_com_correcao`, `rejeitado`, `expirado`), valor corrigido, motivo por código fechado, tempo até resolver | É o rótulo; alimenta admissão, deriva e a métrica de autonomia (só relatório na F1) | **Previsto (F1-26)** |
| Registro de aceite/descarte do `RateSuggestion` com desfecho posterior | Medir se o `CONF_MINIMA` acerta | **Previsto (F1-27)**; o status `accepted`/`dismissed` já existe no modelo |
| Tempo humano por proposta emitida (revisão, tela, correção, retrabalho em 30 dias) | Linha de base da métrica norte antes da sombra (FASES §9) | **Previsto (F1-34)** |

**Regra de fronteira:** o `core_bridge` só chama serviços existentes. Nenhum termo de domínio do SQ
(TEMA, ASME, EAP, cadeia de custo) sobe para o núcleo do Core (F2-01), e nenhum código do Core entra no
`pricing_engine`.

## 4. Flywheel (o que acumula e onde fica)

Pares material remoto → catálogo corrigidos, folhas de dados confirmadas campo a campo e o evento de
correção de cada decisão são o dado proprietário. **Ficam na instância do cliente** (prompt, resposta,
estado, embeddings, golden set, texto de motivo). Sobe para o córtex só padrão abstrato agregado, cujo
formato ainda não existe (DP-13, F3A). **Nenhum rótulo vem de LLM**: quem rotula é o comprador ou o
engenheiro com CREA. Nada disso é fixture do repo: o repo só guarda dado sintético ou referencial já
versionado (INTENT, Limites).

## 5. O que já existe no SQ e parece IA, mas não é

| Onde | O que é | Limiar | Situação |
|---|---|---|---|
| `backend/apps/engineering_params/services.py:9-11` | `RateSuggestion`: sugere novo R$/h quando o realizado diverge do vigente | `N_MINIMO = 20`, `CONF_MINIMA = 0.70`, `DELTA_MINIMO_PCT = 5.0` | **Regra declarada, não medida** (DP-17). Medição na F1-27: acerto das sugestões aplicadas e descartadas, com n e IC. Até lá o número fica como está |
| `backend/apps/production/services.py:638` | "Confiança" do `ActualRate` = `(1 − CV) × min(n/20, 1)` | — | Heurística, não probabilidade calibrada. `CONF_MINIMA` é um corte nessa escala; 0,70 **não** significa "acerta 70%" |
| `backend/apps/engineering_params/models.py:226` | Modelo `RateSuggestion` (`pending → accepted/dismissed`, 1 pendente por operação) | — | Humano no loop; `apply_suggestion` versiona o `Rate` e audita |
| `backend/apps/production/models.py:182,233` | Sinal de revisão SQ-COST-6: `review_recommended` se ≥ 3 amostras e média de \|Δhoras\| > 5% | `REVIEW_MIN_SAMPLES = 3`, `TOLERANCIA_HORAS_PCT = 5.00` | Limiar sem medição e **sem ordem de medição** na F1 (pergunta P4) |
| `backend/apps/production/services.py:530` | `processparameter_suggestion` (SQ-COST-7): fator realizado/estimado, somente leitura | herda o sinal acima | Não escreve em `ProcessParameter` |
| `backend/apps/integrations/protheus/services.py:583` (e `:429`) | Casamento de material por código igual (`sigla=payload["code"]`) | — | É o L0 do SQ-1. Código diferente vira material novo (lacuna que o SQ-1 ataca) |

Nenhum desses caminhos chama modelo, e nenhum altera cotação, snapshot ou preço sem aceite humano.

## 6. Threat Surface (LLM) — para o security-architect

O SQ não chama modelo, então a superfície de LLM está no Core; o SQ é o **alvo** do efeito. Guardas
já nas ordens F1:

| Ameaça | Vetor no SQ | Guarda (ordem) |
|---|---|---|
| Injeção por conteúdo de terceiro | Texto na folha de dados, PDF, planilha ou e-mail do cliente ("ignore as instruções", destinatário novo, valor forjado) | Quarentena e parse tipado; template com campo delimitado; `externo_texto` nunca concatenado; tool com id vindo do modelo recusada; corpus adversarial ≥ 50 casos com 0 efeitos (F1-13, T-SEG-45/46/48) |
| Número de negócio vindo do modelo | `Draft` com total, preço ou horas | Guarda recomputa pelo motor; divergência ≥ R$ 0,01 bloqueia (F1-06, T-SEG-02). Guarda não aceita `Advice` (F1-19) |
| Mutação depois da aprovação | Payload trocado entre aprovar e enviar | Hash canônico do payload aprovado (F1-06, T-SEG-01 200/200); item cai quando o hash do cálculo muda (F1-30); passkey com step-up e assinatura do hash (F1-32) |
| Exfiltração por envio | Proposta a destinatário fora do cadastro | Cadastro de destinatário com origem; novo ou alterado vira C4 (F1-09, T-SEG-03) |
| Duplicidade / replay | `proposal.send` repetido, queda no meio | `idempotency_key` (F1-03), ledger com reserva prévia (F1-07, T-SEG-04), conciliação sem retry cego (F1-08, T-SEG-05) |
| Dado de cliente para provedor não contratado | SQ-2 mandado à nuvem | Allowlist de provedor por instância + DPA, fail-closed (F1-10, T-SEG-60); `qcc-infer` sem log de conteúdo (F1-35, T-SEG-56); local por padrão (DP-19) |
| Escalada de escopo do Core | Token com mais capability do que a tarefa | Token delegado por escopo (F1-01); interseção de permissões recalculada na execução (F1-11, T-SEG-30/31) |
| Envenenamento do golden | Rótulo errado ou malicioso no SQ-1/SQ-2 | Rótulo só de humano habilitado; dupla rotulagem 10% com kappa (F1-22); calibração e teste separados por hash (F1-21) |
| Promoção silenciosa | Sombra virando decisão | `admission_id` nulo força sombra (F1-19, T-SEG-10 a 13); deriva só rebaixa (ARQUITETURA §3.3) |
| Custo como DoS | Inundação de pedidos ao `qcc-infer` | Fila e canal por instância; p95 sob carga de vizinho ≤ 2× (F1-35) |

Fora do escopo da F1 e não coberto aqui: agentes com ferramenta de argumento livre (proibido em L2) e
autonomia além de `act_with_approval`.

## 7. Perguntas abertas (não decididas aqui)

- **P1 — Números de admissão.** SQ-1 e SQ-2 têm números propostos, não carimbados (DP-14 aberta).
  Até o carimbo, as duas tarefas só rodam em sombra.
- **P2 — Nuvem para SQ-2.** DP-19 aprovada, J-19 (contrato) e DP-24 (DPA) abertos. Até lá, SQ-2 é local.
- **P3 — SQ-3, SQ-4, SQ-5** constam da ARQUITETURA §6.2 sem ordem F1. Ficam fora deste doc até ganharem ordem.
- **P4 — Sinal SQ-COST-6** (`REVIEW_MIN_SAMPLES = 3`, `TOLERANCIA_HORAS_PCT = 5.00`) é limiar sem número
  e sem ordem de medição; a DP-17 só nomeia o `CONF_MINIMA`.
- **P5 — `docs/SENSIBILIDADE_MOTOR.md`**, que define os campos de gate 100% do SQ-2, não está neste branch.

## Flags para o orchestrator

Nenhuma que mude escopo. P1 a P5 estão no relatório do Conformador.
