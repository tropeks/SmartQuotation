# Aferição de custo real — mecanismos + o que a indústria já mapeou

**Data:** 2026-07-27 · **Pedido:** Wellington — "o enigma é o custo de horas reais, rateio etc.;
criar mecanismos para aferir melhor e conseguir os dados; e pesquisar se a indústria já tem algo."

> **Disciplina de vocabulário (correção do Wellington, mesmo dia):** todos os números de
> literatura citados aqui são **referenciais externos**, não gabaritos. Servem para diagnosticar
> desvio, não para afirmar verdade sobre a ENGEMATEX.

---

## 0. O achado principal

**O SmartQuotation já é metade de um modelo TDABC — e não sabia.**

Time-Driven Activity-Based Costing (Kaplan & Anderson) tem exatamente duas peças:

| Peça do TDABC | Situação no SmartQuotation |
|---|---|
| **Equações de tempo** — quanto tempo cada atividade consome, em função de parâmetros físicos | ✅ **é o `ProcessParameter`** (física → horas). Já existe, validado, 64 operações |
| **Taxa de custo da capacidade** — `custo total da capacidade fornecida ÷ capacidade prática` | ❌ **não existe.** Hoje o rate R$/h vem de benchmark, não é calculado |

O "enigma" tem nome, tem fórmula publicada e tem literatura de 20 anos. O que falta no produto é
o denominador — e ele **não exige apontamento de chão de fábrica para começar**.

**Capacidade prática** no TDABC = ~**80–85% da capacidade teórica** (o resto é pausa, treinamento,
manutenção, setup improdutivo). Não é opinião: é o default do método.

---

## 1. Escada de mecanismos — do que dá para fazer amanhã ao que exige instrumentação

Desenhada para uma caldeiraria que **hoje não mede nada**. Cada nível entrega valor sozinho e
não depende do nível seguinte.

### Nível 0 — Taxa de capacidade · *só dados do contador, zero chão de fábrica*

**Insumo:** um mês fechado de despesas + headcount. O contador já tem tudo.

```
custo da capacidade fornecida (mês)
  = folha + encargos + benefícios (diretos E indiretos que sustentam a produção)
  + aluguel + energia + depreciação + manutenção + consumíveis não apropriados
  + administrativo rateado

capacidade prática (mês)
  = Σ (horas contratadas de cada recurso produtivo) × 0,80…0,85

custo/hora REAL = custo da capacidade ÷ capacidade prática
```

**Primeiro resultado, na primeira semana:** comparar `custo/hora real` com o **rate praticado
hoje**. Se o rate cobrado for menor, **toda hora vendida perde dinheiro** — e isso passa a ser um
número, não um pressentimento. É o diagnóstico que a ENGEMATEX nunca teve.

**Refinamento:** começar com uma taxa global e evoluir para **taxa por centro de recurso**
(caldeiraria / solda / usinagem / montagem / testes), porque uma hora de CNC não custa o mesmo
que uma hora de bancada. Global primeiro — perfeito é inimigo de existente.

> Isto responde diretamente as perguntas 6, 7, 8 e 13 do livro-razão
> (`DOMINIO_RESPOSTAS_WELLINGTON.md` §5.2) — que estão abertas desde 2026-07-16.

#### Decisão (Wellington, 2026-07-27): o Nível 0 é o **onboarding do sistema**

Os dados de estrutura de custo entram por um **painel de onboarding**, e precisam ser
**revisáveis** — o cliente troca de galpão alugado, muda a área, muda o turno, e o custo/hora
tem que ser refeito.

**Requisito de arquitetura:** estrutura de custo **versionada por vigência**, nunca sobrescrita —
mesmo padrão que `MaterialPrice` / `Rate` / `ProcessParameter` já usam. Uma cotação feita em
março tem de continuar reproduzindo o custo/hora de março; a mudança de galpão abre **nova
vigência**, não corrige o passado.

Blocos do painel: **instalação** (área, aluguel, energia, IPTU) · **pessoas** (headcount por
centro, salário + encargos, turnos, jornada) · **máquinas** (depreciação, manutenção, potência)
· **estrutura** (administrativo, comercial, contabilidade) · **capacidade** (turnos × jornada ×
dias úteis × fator de capacidade prática, default 0,80–0,85, editável).

Ao revisar: mostrar o **diff do impacto no custo/hora** e sinalizar quais cotações abertas ficam
desatualizadas. Como a mudança mexe em rate, o roteamento de aprovação é do **gestor comercial**
(§3b do livro-razão) — reusa o `KnobChangeProposal`.

Candidatos a também entrarem no onboarding: regime tributário (Simples/Presumido/Real), markup
alvo, calendário de turnos e feriados, e o job fechado que serve de **referencial** de calibração.

### Nível 1 — Reconciliação top-down · *ainda sem apontamento*

**Insumo:** N meses fechados + as OFs faturadas nesses meses.

```
fator de correção da MO = horas realmente disponíveis no período
                          ÷ horas estimadas pelo motor para as OFs daquele período
```

Se o motor estimou 1.200 h e a fábrica pagou 2.000 h produzindo aquelas OFs, o fator é **1,67** —
e ele está ancorado em **folha de pagamento**, não em preço de proposta. É o mesmo back-solve que
o `cost_discovery` já faz, com a âncora trocada: sai do preço histórico (contaminado) e entra na
realidade contábil.

**Limite honesto:** corrige o **viés agregado**, não diz qual operação estoura. Mas é a maior
alavanca isolada do projeto, e o dado já existe.

### Nível 2 — Apontamento mínimo viável · *o dado que realmente falta*

Regras de projeto, todas contra o atrito:

1. **Granularidade certa:** `OF × família de operação` (solda / usinagem / montagem /
   traçagem-furação / testes). **Nunca** por micro-tarefa — apontamento fino não sobrevive ao
   chão de fábrica.
2. **Menor atrito possível:** QR code na folha viajante da OF; operador escaneia início/fim pelo
   celular. Alternativa ainda mais barata: o **encarregado fecha o dia** num tablet, 5 linhas,
   30 segundos. A literatura de shop-floor é unânime: menos passos no ponto de entrada = menos
   lançamento pulado.
3. **Regra de ouro — a conciliação é o controle:**
   `cobertura = horas apontadas ÷ horas pagas`.
   O que **não** fecha é ociosidade e trabalho indireto — e é exatamente isso que precisa de
   rateio. **O buraco não é erro de apontamento: é o dado.**
4. **Piloto de 1 OF**, não a fábrica inteira. Uma OF apontada de ponta a ponta vale mais que seis
   meses de apontamento pela metade.

### Nível 3 — Loop de aprendizado · *isto é o produto*

Para cada OF fechada: `estimado × real`, por operação → **viés por operação**.

O sistema aprende que a ENGEMATEX subestima solda em 35% e superestima montagem em 10%, e
**corrige a próxima cotação sozinha**. É a régua de verdade, e é o que nenhum concorrente
entrega — porque exige motor de tempo e apontamento **no mesmo sistema**.

---

## 2. Réguas externas — como furar a contaminação do benchmark

O problema registrado: calibrar contra o histórico da própria empresa **copia os erros dela**.
A saída é ter réguas que não venham do histórico.

### 2.1 Solda por primeiros princípios *(a mais forte, e aplicável já)*

```
peso de metal depositado (kg)  ──→  tempo de arco = peso ÷ taxa de deposição
tempo real de trabalho = tempo de arco ÷ FATOR DE OPERAÇÃO
```

O **fator de operação** (arc-on time) é o % do dia do soldador efetivamente soldando — em
processo manual a literatura trabalha na faixa de **20–40%**.

Exemplo publicado: 5 lb de metal depositado, taxa 8 lb/h, fator de operação 30% →
0,625 h de arco → **2,08 h de trabalho real**. O tempo de arco é **um terço** do custo.

**Duas coisas caem disso:**
- Dá para calcular horas de solda **sem olhar o histórico** — e comparar com o que a ENGEMATEX
  estima. Se ela estima 1,2 h onde a física diz 2,08 h, o vazamento está localizado.
- **Medir o fator de operação real** da ENGEMATEX é diagnóstico e é vendável: "seus soldadores
  passam X% do dia com arco aberto" é uma frase que muda uma reunião de diretoria.

O motor já modela solda ∝ espessura² e tem `PERDA_POR_FAMILIA` — falta trocar o proxy por
`peso de metal depositado ÷ taxa de deposição ÷ fator de operação`, que é fisicamente correto.

### 2.2 Correlações de custo de equipamento (régua de mercado)

Literatura clássica de custo de trocador casco-e-tubo: **Purohit** (*Chemical Engineering*, 1983)
e **Towler & Sinnott** (*Chemical Engineering Design*) dão custo do equipamento como função de
**área, material e pressão**. Serve como **terceira régua**: se a cotação sai muito abaixo da
correlação de mercado, é sinal de subprecificação — o mesmo instinto da "vitória perigosa" do
Wellington, só que quantificado e disponível **antes** de perder a concorrência.

### 2.3 Bases comerciais de man-hours

**Richardson Process Plant Construction Estimating Standards** (CostDataOnLine) cobre man-hours
de fabricação de vasos de pressão, com preços unitários compostos. Referência pública de ordem de
grandeza para estrutura metálica: **~113 man-hours por tonelada fabricada**, variando com
estrutura leve/média/pesada. É base paga e americana — serve como sanity check, não como seed.

---

## 3. O que a indústria já tem — e o buraco que sobra

| Categoria | O que existe | Cobre o quê |
|---|---|---|
| **Framework de custeio** | TDABC (Kaplan & Anderson) — capacity cost rate + time equations | Níveis 0 e 3. É o método certo, consolidado |
| **Calculadoras de shop rate** | MIE Solutions, CustomPartNet, SWARF, calculadoras de burden rate | Nível 0. Abundantes, simples, gratuitas |
| **Coleta de chão de fábrica** | JobBOSS² (QR na folha viajante), Standard Time, QT9 ERP, Dynamics 365 BC + Shop Floor Insight, OEE Coach | Nível 2. Maduro — mas vem acoplado a ERP |
| **ERP ETO** | Epicor Kinetic, Infor CloudSuite Industrial (SyteLine), SYSPRO, Genius ERP, JobBOSS² | Tudo, em teoria. **TCO US$ 40k–200k**, licença a partir de US$ 80/usuário/mês |
| **Engenharia de trocador** | HTRI, Aspen EDR, Codeware Compress, PV Elite | Dimensionamento. **Não** custo real de fábrica |

### O buraco

**Ninguém junta as três coisas:** (a) motor de tempo paramétrico **específico de trocador de
calor**, (b) apontamento de horas reais, (c) o loop que usa (b) para corrigir (a).

- Os **ERPs ETO** têm apontamento, mas a estimativa é manual ou histórica — reproduzem o mesmo
  problema da ENGEMATEX, só que informatizado.
- Os **softwares de engenharia** dimensionam o equipamento e não sabem o custo da sua fábrica.
- E **US$ 40–200 mil de TCO** está fora do alcance da caldeiraria média brasileira, que é
  exatamente o cliente.

Isso sustenta a tese que o Wellington levantou em 2026-07-16: *"quase não tem solução para esse
tipo de empresa"*. A pesquisa confirma — e mostra **por onde** entrar.

---

## 4. Recomendação de sequência

1. **Nível 0 agora** — é uma planilha e uma tela. Precisa só das 8 perguntas de estrutura de
   custo (§5.2 do livro-razão) respondidas. Entrega o primeiro número duro: custo/hora real
   × rate praticado.
2. **Nível 1 em seguida** — trocar a âncora do back-solve de "preço histórico" para "folha do
   período". Reaproveita o `cost_discovery` que já existe.
3. **Régua de solda (§2.1)** em paralelo — é mudança de fórmula no motor, não precisa de dado novo
   da fábrica, e ataca justamente onde o Wellington diz que o dinheiro vaza.
4. **Nível 2 como piloto de 1 OF** — só depois que 1 e 2 provarem valor.
5. **Nível 3** é a visão: o sistema que aprende a fábrica. Só existe depois do Nível 2.

---

## Fontes

- [Time-Driven ABC — guia completo (CostPerform)](https://www.costperform.com/time-driven-activity-based-costing-tdabc-a-complete-guide/)
- [TDABC — modelo e capacidade prática (TXCPA, PDF)](https://www.tx.cpa/docs/default-source/default-document-library/activitybasedcostmodel_marapril2015.pdf?sfvrsn=2)
- [TDABC: implementação em empresa de manufatura (Academia.edu)](https://www.academia.edu/119269393/Time_driven_activity_based_costing_An_implementation_in_a_manufacturing_company)
- [Deposition rate, deposition efficiency e output (The Fabricator)](https://www.thefabricator.com/thewelder/article/consumables/understanding-the-relationship-between-deposition-rate-deposition-efficiency-and-production-output)
- [Welding cost estimation e fator de operação (WeldingInfo)](https://www.weldinginfo.org/welding-technology/welding-cost-estimation-and-calculation/)
- [Weld deposition rate — fórmulas e tabelas (Clause5)](https://clause5.io/welding/deposition-rate/)
- [Estimating basics em fabricação metálica sob medida (The Fabricator)](https://www.thefabricator.com/thefabricator/article/shopmanagement/estimating-basics-and-quoting-jobs-in-custom-metal-fabrication)
- [Manufacturing hourly rate calculation (MIE Solutions)](https://mie-solutions.com/how-to-manufacturing-hourly-rate-calculation/)
- [Hourly shop rate, overhead e labor burden (WOODWEB)](https://woodweb.com/knowledge_base/Hourly_Shop_Rate_Overhead_and_Labor_Burden.html)
- [JobBOSS — coleta de dados com QR na folha viajante](https://excellerant-mfg.com/feeds/blog/jobboss-data-collection)
- [Shop floor data collection: alternativas à entrada manual (iFactory)](https://ifactoryapp.com/blog/shop-floor-data-collection)
- [ERP para Engineer-to-Order 2026 — mercado e TCO (ERP Research)](https://www.erpresearch.com/en-us/erp-for-engineering)
- [Correlações de custo para equipamentos de planta (MDPI Energies)](https://www.mdpi.com/1996-1073/14/9/2665)
- [Shell and tube heat exchanger cost estimation (Cheresources)](https://www.cheresources.com/invision/blog/4/entry-278-shell-and-tube-heat-exchanger-cost-estimation/)
- [Richardson knowledgebases — man-hours de fabricação (PDF)](https://www.costengineering.eu/downloads/12_Richardson_knowledgebases.pdf)
- [Custo hora-máquina: metodologia (Quisi Contabilidade)](https://quisicontabilidade.com.br/custo-hora-maquina-na-industria-como-calcular-corretamente-e-evitar-prejuizos/)
- [Apurar custo por hora-máquina com apoio do PCP (Nomus)](https://www.nomus.com.br/blog-industrial/6-passos-para-apurar-o-custo-maquina-com-apoio-do-pcp/)
