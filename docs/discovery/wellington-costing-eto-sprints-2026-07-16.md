# SmartQuotation — Descoberta Wellington: custos, margem e roadmap ETO

**Data:** 2026-07-16 19:20 -03
**Origem:** áudios encaminhados por Romulo/Wellington no Telegram
**Contexto:** SmartQuotation / ENGEMATEX / evolução CPQ → precificação → ETO leve
**Status:** insumo de discovery para PMO Legatus; ainda não é contrato de implementação fechado.

---

## 1. Executive summary

Os áudios trazem uma mudança importante de leitura de produto: o SmartQuotation continua válido como MVP de produtividade para propostas, mas o diferencial mais forte pode estar na **formação de preço industrial para pequenas e médias empresas**, especialmente no rateio de custo fixo, mão de obra e margem de contribuição.

A leitura consolidada é:

1. **MVP atual não é tempo perdido.** Para a ENGEMATEX, usar as propostas do Mané como referência permite cotar mais rápido e validar se o sistema chega perto do orçamento que ele faria.
2. **A referência histórica tem limite.** As propostas atuais servem como formato e benchmark operacional, mas não provam que o preço cobre a operação.
3. **O problema real da ENGEMATEX está menos em matéria-prima e mais em mão de obra/custo fixo.** Materiais relevantes, como tubos/chapa de fornecedores de qualidade, tendem a ter menor variação; o prejuízo aparece na hora de mão de obra, setup, produtividade, retrabalho e rateio de estrutura.
4. **Há dor transversal em PMEs.** Salão, padaria, oficina e indústria pequena/média compartilham dificuldade de distribuir custo fixo e custo operacional dentro do preço.
5. **Caminho de produto:** CPQ industrial primeiro; depois diagnóstico de risco de preço; depois motor de custo/margem; no horizonte, ERP/ETO leve por camadas.

Frase-guia:

> SmartQuotation deve ajudar a empresa a fazer proposta rápido **e** saber se está ganhando dinheiro — mas sem sacrificar o MVP atual.

---

## 2. Transcrições anexadas

### Áudio 1 — Estrutura de custos como diferencial

> Romulão, sobre o nosso projeto lá do Smart Cotation, tem uma parte cara que eu acho que o sistema está deixando para trás, que é a parte do custo. A gente precisa depois dar uma alinhada com o time de desenvolvimento, com asias lá, os personagens, para eles olharem a estrutura de custo para uma pequena, média empresa do tipo industrial. Como a gente, antes de começar a fazer cotação, colaborar para que as empresas desses níveis aí tenham uma estrutura de custo avaliada. Tipo, eles possam colocar lá despesas fixas, despesas variáveis, custos fixos, custos variáveis. Criar a estruturinha para compor o preço de venda do produto, levar em consideração esse custo fixo na composição do preço. A maioria dessas empresas tem dificuldade de fazer esse levantamento, de estruturar a cadeia de custo deles. E um diferencial do software seria isso. Porque hoje, por exemplo, ele está fazendo um cruzamento com a proposta que eu mandei lá da Ingematex.

**Extração:** o sistema pode ir além da cotação e ajudar a montar a estrutura mínima de custos: despesas fixas/variáveis, custos fixos/variáveis, composição de preço de venda e rateio de custo fixo.

---

### Áudio 2 — Problema específico ENGEMATEX: custo fixo, margem e mão de obra

> Qual é o problema da Engematex? A Engematex não sabe cobrar o custo fixo dela, ela não tem a ideia de qual é a margem de contribuição, de qual é a composição desses custos, sabe? E aí o custo é meio que chutado por benchmark, então ele nunca é aferido no sentido de saber se aquilo está cobrindo as despesas da empresa. Aí se ele partir, se nós partirmos para o princípio de que o aferidor, o nosso bloco padrão, vamos dizer assim, para comparação, vai ser as propostas da Engematex, a questão de custo a gente nunca vai saber se está correto. A parte de matéria prima, essas coisas estão ok, agora a parte mão de obra não vai estar ok. E é nisso aí que eu acho que a gente podia se concentrar, porque todas as pequenas e médi empresas, independente qual seja a área, o que eu percebo que tem grande dificuldade de salão de beleza, padaria, oficina mecânica, é fazer a distribuição do custo fixo, todo o custo da operação, dentro da precificação. Esse é um grande desafio.

**Extração:** propostas antigas são úteis como referência, mas podem estar contaminadas por preço errado. O foco de produto deve observar margem de contribuição, custo fixo, composição de custos e mão de obra.

---

### Áudio 3 — MVP atual continua válido; benchmark tem limite

> Então, o que a gente fez até agora não é tempo perdido, porque para trabalhar com MVP na Engematec isso vai funcionar porque vai ter como parâmetro a própria proposta do Mané, que aí ele vai fazendo o orçamento rapidamente, montando isso aí funcionando bem, e ele vai aprovar se o preço fica perto dele, porque ele acha que ele é a pessoa mais... Deixa eu corrigir aqui o que eu ia falar. Ele acredita que ele tem um bom feeling para montar o preço, que ele é um bom orçamentista e que os preços dele são bons, porque ele tem ganhado as concorrências. É lógico que eu fiz uma pequena avaliação, olhei lá às vezes, por exemplo, o trocador de calor que a Engematec venceu a concorrência no site da Petrobras lá. Aí quando ela é a primeira colocada e o segundo colocado tem tipo um valor quase o dobro, eu já sei que ele tomou na cabeça. Agora quando a diferença é 5%, 10%, aí é provável que ele tenha feito um orçamento razoável. Mas como eu disse, o valor que ele leva em consideração no orçamento dele é por benchmark, ele olha para o mercado e vai tentando balizar a hora de mão de obra dele por ali, porque material todo mundo compra dos mesmos lugares. Importa ou compra no mercado nacional, e aí chapa, tubo vai ter preço similar. A maior fornecedora é a Mannesmann, eles compram dela, a Valorek Mannesmann no Brasil. Então eles não abrem mão da qualidade da Mannesmann, sabe que se alguém estiver comprando tubo mais barato da China, vai dar problema lá na frente. Isso aí eles não abrem mão. E já sabemos que vai ter uma diferença de matéria-prima pequena em relação a tubo, por exemplo, mas no geral a mão de obra é o que dá o prejuízo na Engematec.

**Extração:** o MVP pode ser validado pelo “preço próximo ao Mané”, mas vitórias com diferença extrema contra concorrentes podem indicar subprecificação. Matéria-prima é menos problemática; mão de obra e custo fixo são os grandes riscos.

---

### Áudio 4 — Caminho para ERP/ETO, sem perder o que já foi feito

> Aí eu tô te avisando aqui, mas eu vou ficar usando as ferramentas gratuitas aqui, o cloud gratuito e tal, pra tentar estruturar como passar essa parte sem... Depois eu vou ver se eu consigo pegar lá no Git também, dar uma entrada lá no nosso diretório e pegar o documento mestre que está sendo atualizado lá, pra passar pro meu agentezinho aqui dar uma avaliada e me ajudar a organizar de forma que a gente não perca nada do que fez até agora, só vá arredondando e melhorando o caminho aí, e acrescentando essas coisas que vão ser diferenciais no primeiro momento. E eu acho que no fim, cara, isso vai acabar virando realmente um RP dessa linha engineering to order. Eu acho que vai acabar sendo isso, porque pra empresas desse tipo aí, não tem quase nenhuma solução, tem aqueles que eu te mandei lá. Eu vi que a Mega criou um módulo pra isso, porque viu que é uma puta oportunidade. O SAP B1 nem sei se terminou o módulo, eles tinham também quando lá em 2000 e sei lá, acho que era 2016, 2014, me lembro, eles tinham sinalizado que ia ter um módulo pra isso, então é uma tendência, né, atrasada no Brasil, seja realidade fora, mas talvez seja um caminho. Mas vamos devagar, não passei de cada vez, né?

**Extração:** visão expandida: SmartQuotation pode evoluir para ERP/ETO leve. Porém, a orientação é preservar o MVP e avançar por camadas, sem “boil the ocean” antes de validar.

---

## 3. Decisões de produto propostas

### D1 — Não trocar o objetivo do MVP

O MVP atual continua sendo **cotação/proposta rápida para ENGEMATEX**, usando proposta histórica e feeling do orçamentista como referência inicial.

**Risco evitado:** tentar resolver contabilidade/ERP completo antes de provar o fluxo de cotação.

### D2 — Marcar preço histórico como “referencial”, não “validado por custo”

As propostas históricas podem alimentar formato, itens, linguagem e benchmark, mas não devem ser tratadas como verdade de margem.

**Risco evitado:** o sistema aprender preço errado e reproduzir subprecificação.

### D3 — Priorizar mão de obra e custo fixo como próxima camada de inteligência

A tese dos áudios é que o prejuízo da ENGEMATEX aparece principalmente em mão de obra e rateio de estrutura, não em tubos/chapas.

**Implicação:** o próximo discovery/sprint deve olhar `Rate`, `ProcessParameter`, `ActualRate`, back-solve e custo fixo por capacidade produtiva.

### D4 — Produto caminha para ETO por camadas

SmartQuotation pode se tornar um vertical ETO/ERP leve, mas a entrada continua CPQ industrial. A arquitetura já tem pistas disso: cotação → OF, apontamento, `ActualRate`, integrações ERP.

---

## 4. Modelo de roadmap proposto

### Camada 1 — CPQ industrial / MVP atual

**Promessa:** gerar proposta técnica rápido e perto do que o orçamentista faria.

- Data sheet → EAP → custos materiais/MO → proposta.
- Histórico/revisão/aprovação.
- Gabaritos ENGEMATEX como contrato inicial.
- Ajuste manual preservado.

**Critério de sucesso:** Mané consegue gerar orçamento com menos trabalho e aceita que o resultado está próximo do seu método.

### Camada 2 — Diagnóstico de risco de preço

**Promessa:** avisar quando o preço pode estar perigoso.

- Diferença contra histórico.
- Diferença contra concorrência quando informada.
- Alerta de “vitória perigosa” quando o preço vencedor fica muito abaixo do 2º colocado.
- Flag de preço baseado em benchmark vs validado por custo.

**Critério de sucesso:** usuário entende que ganhar concorrência por diferença extrema pode significar prejuízo.

### Camada 3 — Formação de preço / estrutura de custos

**Promessa:** ajudar PMEs a formar preço considerando custo fixo, mão de obra, margem e capacidade.

- Assistente de custo fixo mensal.
- Capacidade produtiva mensal.
- Custo fixo por hora produtiva.
- Custo/hora de mão de obra e/ou centro de custo.
- Margem de contribuição mínima.
- Preço mínimo saudável.

**Critério de sucesso:** sistema responde “este orçamento cobre a operação?”.

### Camada 4 — Orçado vs realizado como calibrador

**Promessa:** orçamento aprende com a fábrica.

- Comparar horas estimadas vs reais por operação.
- Sugerir atualização de índices (`RateSuggestion`/`ActualRate`).
- Separar material, MO, setup, retrabalho e produtividade.
- Dar evidência de onde o preço foi perdido.

**Critério de sucesso:** sistema identifica operações que causam prejuízo e melhora próximos orçamentos.

### Camada 5 — ERP/ETO leve

**Promessa:** operação ETO ponta-a-ponta para PMEs industriais.

- Proposta aprovada vira projeto/OF.
- Materiais/compra/estoque básico.
- Produção/qualidade/documentação.
- Integração fiscal/financeira quando fizer sentido.

**Critério de sucesso:** cliente vive no SmartQuotation para engenharia sob encomenda, sem depender de ERP genérico para o domínio técnico.

---

## 5. Sprint preparation — proposta inicial Legatus

> Esta seção prepara sprints. A sonda Opus deve revisar, quebrar e ajustar antes de implementação.

### Sprint SQ-COST-0 — Consolidar visão e alinhar docs

**Tipo:** documentação/produto
**Objetivo:** incorporar esta descoberta aos documentos mestre sem quebrar o roadmap existente.

**Tasks:**

1. Atualizar `docs/PRODUCT_VISION.md` com a nuance: MVP CPQ preservado; custo/margem como diferencial progressivo.
2. Atualizar `docs/ROADMAP.md` com um bloco H2/H3 “Cost Discovery / Pricing Intelligence”.
3. Criar seção explícita “preço referencial vs preço validado por custo”.
4. Registrar riscos: base histórica contaminada; benchmark não comprova margem; custo de MO como risco principal.
5. Manter H2/H3 existentes; não apagar entregas já concluídas.

**DoD:** docs atualizados; sem código de domínio; `git diff --check` verde.

---

### Sprint SQ-COST-1 — Modelo conceitual de estrutura de custos

**Tipo:** design/spec
**Objetivo:** especificar entidades/fluxos para custo fixo, capacidade e margem sem implementar banco ainda.

**Tasks:**

1. Mapear conceitos: custo fixo, despesa fixa, custo variável, despesa variável, MO direta, MO indireta, margem de contribuição.
2. Definir fórmulas iniciais:
   - `custo_fixo_por_hora = custo_fixo_mensal / horas_produtivas_mensais`
   - `custo_total = material + mao_obra + rateio_custo_fixo + serviços`
   - `preco_minimo = custo_total / (1 - margem_desejada)`
3. Definir UX de assistente guiado para PME.
4. Decidir como isso conversa com `TenantCostChain`, `Rate`, `ProcessParameter`, `ActualRate` e `RateSuggestion`.
5. Produzir spec de testes/fixtures sem tocar produção.

**DoD:** spec revisada pelo domínio; nenhuma migration ainda.

---

### Sprint SQ-COST-2 — Indicador “referencial vs validado” na cotação

**Tipo:** implementação leve
**Objetivo:** permitir que uma cotação indique se o preço vem de benchmark/histórico ou de custo aferido.

**Tasks candidatas:**

1. Adicionar enum/metadata no modelo de cotação ou snapshot de pricing.
2. Exibir na UI: “Preço referencial / benchmark” vs “Preço validado por cadeia de custos”.
3. Registrar audit log quando usuário muda status/assunção.
4. Testes de modelo, view e regressão.

**DoD:** usuário não confunde preço gerado por referência histórica com preço validado por custo.

---

### Sprint SQ-COST-3 — Assistente mínimo de custo fixo e capacidade

**Tipo:** implementação
**Objetivo:** primeira fatia funcional de estrutura de custo para tenant.

**Tasks candidatas:**

1. Modelar `TenantCostStructure` ou extensão equivalente.
2. Campos mínimos: custo fixo mensal, horas produtivas mensais, observações, versão/validade.
3. Calcular custo fixo/hora.
4. UI HTMX simples para cadastro/edição.
5. Testes tenant-scoped e RBAC.

**DoD:** tenant consegue cadastrar custo fixo/capacidade e ver custo fixo/hora calculado.

---

### Sprint SQ-COST-4 — Mão de obra e risco de margem

**Tipo:** implementação
**Objetivo:** conectar estrutura de custo a operações/horas para apontar risco.

**Tasks candidatas:**

1. Calcular rateio de custo fixo por horas estimadas da cotação/OF.
2. Apresentar breakdown: material, MO, fixo rateado, serviços, margem.
3. Alerta se preço de venda < preço mínimo estimado.
4. Alerta de operação com alto peso de MO.
5. Testes de golden cases.

**DoD:** orçamento mostra se cobre custo mínimo estimado e destaca mão de obra como risco.

---

### Sprint SQ-COST-5 — Competitividade e “vitória perigosa”

**Tipo:** implementação/opcional pós-validação
**Objetivo:** registrar dados de concorrência e alertar subprecificação.

**Tasks candidatas:**

1. Registrar preço da proposta própria e preço/posição de concorrentes quando conhecidos.
2. Calcular delta para 2º colocado.
3. Alertar quando diferença é extrema.
4. Relatório de vitórias saudáveis vs perigosas.

**DoD:** usuário entende que vencer por 50–100% abaixo do 2º colocado pode indicar prejuízo.

---

## 6. Perguntas para domínio/Wellington

1. Qual custo fixo mensal aproximado da ENGEMATEX entraria no primeiro modelo?
2. Quantas horas produtivas/mês são realistas?
3. Separar por centro de custo ou começar com um custo fixo/hora global?
4. O Mané estima horas por operação ou apenas preço fechado?
5. Quais operações mais costumam estourar: solda, furação, montagem, teste, retrabalho?
6. Existe histórico de concorrências com 2º colocado/valores para calibrar “vitória perigosa”?
7. O primeiro piloto deve mostrar alerta apenas informativo ou bloquear preço abaixo do mínimo?
8. O custo fixo deve entrar como overhead separado ou embutido no rate de MO?

---

## 7. Artefatos Legatus sugeridos

- Sprint contract: `.legatus/sprints/2026-07-16-wellington-cost-discovery.md`
- Evidence: `.legatus/evidence/2026-07-16-wellington-cost-discovery.md`
- Opus probe output: `/tmp/sq_wellington_cost_opus_probe.md`
- Este documento: `docs/discovery/wellington-costing-eto-sprints-2026-07-16.md`

---

## 8. Nota PMO

Não implementar `SQ-COST-3+` sem antes reconciliar com o estado real do repo, porque o projeto já tem `apps/cost_discovery`, `TenantCostChain`, `ActualRate`, `RateSuggestion` e loops H2 entregues. O primeiro trabalho deve ser **reconciliação + spec**, não criar modelo duplicado.
