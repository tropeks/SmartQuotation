# SmartQuotation — Visão de Produto (v1, 2026-07-10)

**Autor:** Fable 5 (CEO) · **Validado por:** Rom · **Ambição declarada:** evoluir para ERP.

## Tese

Fabricação sob encomenda de equipamentos de processo (trocadores de calor, vasos, caldeiraria média/pesada) é um nicho mal servido: a realidade é planilha Excel artesanal ou ERP genérico que não entende EAP paramétrica, ASME, TEMA, nem o ciclo orçamento→fabricação. O SmartQuotation ataca esse vazio com um ativo raro: **motor de custeio paramétrico validado por PE contra orçamentos reais (±3,5%)**.

## Moat (o que defende o produto)

1. **Motor de custeio calibrável** — 64 operações + componentes paramétricos fiéis ao processo real; ProcessParameter (física→horas) separado de Rate (custo→R$); validado nos golden cases Petrobras (OF-3672) e ELEKEIROZ (OF-3683).
2. **Golden cases como contrato** — cada tenant entra com 2-3 jobs históricos que calibram (back-solve) e TRAVAM o motor para a realidade dele. Onboarding = calibração. Isso é inimitável por ERP genérico.
3. **Preço referencial vs. preço validado por custo** — golden cases e back-solve provam fidelidade ao histórico/planilha, mas não provam que a empresa cobre custo fixo, mão de obra real e margem de contribuição. O próximo moat é tornar essa diferença explícita e auditável.
4. **Loop orçado→realizado** (fase 2) — apontamento na OF alimenta sugestões de ProcessParameter: o orçamento aprende com a fábrica. Nenhum concorrente do nicho tem.
5. **Fábrica de software autônoma** — o custo marginal de feature é baixo (orchestrator/Legatus), permitindo velocidade de produto incompatível com o tamanho do time.

## Estratégia: ETO-first, ERP por camadas

**Não competir com Totvs/Nomus/Omie em fiscal/financeiro agora.** Rota:

| Fase | Entrega | Posição |
|------|---------|---------|
| **1 (agora)** | CPQ industrial completo: data sheet → cotação (EAP editável: materiais E horas de MO) → proposta → aprovação → OF. **Integra** com ERP (Nomus 1º, SAP B1 pronto) | "A melhor cotação técnica do Brasil industrial" |
| **2** | Produção: apontamento, orçado vs realizado por operação, calibração assistida por dados reais | O cliente passa a viver no produto |
| **3** | Inteligência de custo e margem: preço referencial vs validado, custo fixo/capacidade, overhead por hora produtiva, margem de contribuição e alertas de preço mínimo | O cliente sabe se a cotação paga a operação |
| **4** | Materiais: necessidade de compra puxada pela lista de material da OF, estoque básico, recebimento | A dor seguinte natural do mesmo usuário |
| **5** | "ERP de engenharia sob encomenda" (ETO): financeiro/fiscal POR INTEGRAÇÃO ou módulo adquirido — nunca reconstruir NFe/SPED do zero | Categoria própria, vazia no Brasil |

**Em uma frase: não competir com o Nomus agora; usá-lo como ponte até substituí-lo por camadas.**

## Recomendações estratégicas ativas

1. Golden cases por tenant como contrato de regressão permanente (gate de CI por cliente).
2. Elevar o loop orçado→realizado a épico prioritário da fase 2.
3. Rotular explicitamente a origem do preço: `referencial` quando veio de benchmark/back-solve/histórico; `validado por custo` somente quando houver cadeia de custo/capacidade/margem rastreável.
4. Tratar custo fixo/overhead como linha separada e inspecionável, não escondida em `rate_hh` ou `fator_preco`.
5. **Beta multi-empresa**: 1-2 caldeirarias além da ENGEMATEX antes de escalar vendas (valida generalização do motor; infra multi-tenant pronta).
6. Produção-grade antes de cliente pagante: backup automatizado do Postgres, monitoramento de erros (Sentry ou similar), runbook de deploy (hoje: 1 container + cloudflared numa VPS).
7. Mitigar bus factor Wellington: UI de calibração (épico 4 da beta) externaliza o conhecimento em parâmetros auditáveis; documentar decisões normativas em `docs/`.

## Riscos honestos

- **Calibração a 1 empresa** — o motor pode estar ENGEMATEX-shaped; mitigação = beta multi-empresa (rec. 3).
- **Histórico contaminado por benchmark** — back-solve com erro 0,0% mede fidelidade ao preço histórico, não cobertura de custo operacional; mitigar com provenance `referencial` vs `validado por custo`.
- **Markup não é margem** — `fator_preco` ajuda a formar venda, mas não responde sozinho se a empresa cobre custo fixo e margem de contribuição.
- **Proxies físicos do motor** (massa/solda/área/volume ≈ D·L) — suficientes na banda ±10%, precisarão refino com mais golden cases.
- **Nicho estreito por design** — é feature, não bug: dominar caldeiraria/trocadores primeiro; vasos/skids/estruturas são adjacências do MESMO motor.
- **Dependência de canal** — hoje 100% design-partner; fase 1 completa é pré-condição para qualquer venda externa.
