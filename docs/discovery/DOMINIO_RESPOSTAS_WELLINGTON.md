# Livro-razão de domínio — respostas do Wellington

> **Regra de uso:** antes de perguntar QUALQUER coisa ao Wellington, consultar este arquivo.
> Cada linha traz a resposta, a data e a fonte. Se está aqui, **não pergunta de novo**.
> Perguntas ainda abertas ficam no fim, numeradas.

---

## 1. Origem do valor (decidido 2026-07-27)

**Princípio:** o que define o tratamento de um campo não é o campo, é **de onde o valor veio**.

| Situação | Fonte do projeto térmico + mecânico |
|---|---|
| **Reposição / parte** | Data sheet vem **pronto do cliente** |
| **Projeto novo** | ENGEMATEX **contrata escritório de engenharia**, que entrega o **memorial de cálculo** |

Nos dois casos o projeto nasce **fora** da cotação. Ninguém na ENGEMATEX é autor desses
números — os dois casos são **transcrição**. O "tipo de projeto" não é gate de permissão:
é **qual documento ancora a cotação**.

### Classificação dos campos

| Tipo | Campos | Regra |
|---|---|---|
| **Valor exato do projeto** | parede do tubo, nº de chicanas, corte de chicana, folga, passo, OD, comprimento | 🔒 **não altera.** "Sempre seguir o projeto térmico e mecânico; desvios não são permitidos." Mudou = erro de transcrição ou desvio → evento de engenharia |
| **Mínimo do projeto** | espessura de casco/tampo/espelho/bocal, sobrespessura de corrosão | ⬆️ **pode engordar** (chapa comercial disponível). Ex.: mínimo 6 mm, usa 10 mm → sem problema de engenharia, só de custo → **alerta ao comercial, não bloqueia** |
| **Escolha de compra/processo** | comprimento comercial de tubo, radial vs CNC, setup, scrap | 🟢 livre |

**Consequência:** o vetor "vazamento por engenharia" quase não existe como liberdade
legítima — vira **detecção de desvio de transcrição**. Re-assinatura só é disparada por
mudança que ande **na direção do risco**, não por qualquer edição.

---

## 2. Controle de vazamento de margem (respondido 2026-07-24)

Fonte: `resposta_wellington_controle_margem.md`

| Ponto | Decisão |
|---|---|
| Os 4 vetores (comercial / produção / engenharia / ajuste manual na EAP) | ✅ corretos e completos |
| Modelo de controle | ✅ **verificação suave** — assinatura é o gate, não o teclado. Bloqueio duro vira gargalo e incentiva gambiarra (login compartilhado, classificar tudo como "reposição") |
| Diff pós-assinatura | ✅ quer, **com impacto percentual na margem**, não só R$ |
| Reposição/parte | ✅ libera o orçamentista, com **anexo obrigatório do PDF** + nº do desenho, revisão, data |
| M1 | 🔴 **prioridade máxima** — "correção de vulnerabilidade de segurança financeira, não feature" |

**Requisitos adicionados por ele:** justificativa obrigatória no ajuste manual da EAP (sem
justificativa não salva) · notificação automática ao gestor da margem · indicador visual
amarelo "não verificado" → verde após assinatura · impacto em % além de R$.

---

## 3. Como a ENGEMATEX forma preço hoje (respondido 2026-07-16, áudios)

Fonte: `wellington-costing-eto-sprints-2026-07-16.md`

- **Projeto novo é cotado por benchmark + feeling do orçamentista (Mané)** — o memorial de
  cálculo só existe depois; ninguém paga escritório para montar orçamento de pedido que
  talvez não venha.
- **A ENGEMATEX não sabe cobrar o custo fixo dela** e não conhece sua margem de contribuição.
  "O custo é meio que chutado por benchmark, nunca é aferido."
- **Matéria-prima não é o problema:** todos compram dos mesmos lugares (Vallourec Mannesmann;
  não abrem mão da qualidade). Chapa e tubo têm preço similar no mercado.
- **O prejuízo está em mão de obra, setup, produtividade, retrabalho e rateio de estrutura.**
- **"Vitória perigosa":** ganhar concorrência da Petrobras com o 2º colocado ao dobro do preço
  indica subprecificação. Diferença de 5–10% = orçamento razoável.
- **Visão de produto (dele):** CPQ industrial → diagnóstico de risco de preço → motor de
  custo/margem → ERP/ETO leve, por camadas. Quase não há solução para ETO em PME no Brasil
  (Mega criou módulo; SAP B1 sinalizou).

### ⚠️ Vocabulário (correção do Wellington, 2026-07-27)

**Não é "g‑a‑b‑a‑r‑i‑t‑o". É "referencial".** A palavra evitada significa *resposta certa*; chamar assim
embute a premissa de que o preço histórico está correto — que é justamente o que ele não
está. O termo correto para o orçamento fechado que usamos na calibração é **referencial**.

> ✅ **Dívida quitada em 2026-07-28 (S5).** O repo usava "referencial" em ~90 pontos e
> `ground_truth` em código e em 4 seeds — este último era o pior, porque *ground truth*
> afirma verdade fundamental sobre um número que é só referência. Renomeados para
> `referencial` / `*_referencial.json`, inclusive nos nomes dos jobs de CI.

### ⚠️ Consequência que precisa ficar registrada

O motor bate **0,0% contra o referencial real** de BEU/BEM. Pelo que está acima, isso mede
**fidelidade ao preço que o Mané faria** — não prova que o preço cobre a operação. São
**duas réguas diferentes**:

1. **Régua de fidelidade** (bate com o que a empresa cotaria) → gera adoção e confiança.
2. **Régua de verdade** (custo aferido: horas reais + rateio de custo fixo) → prova lucro.

Decisão já registrada como D2 no doc de 2026-07-16: preço histórico é **"referencial"**,
nunca **"validado por custo"**. Calibrar um tenant novo contra o histórico dele **copia os
erros dele** — a calibração precisa evoluir para a régua 2.

---

## 3b. Quem aprova mudança no VALOR-PADRÃO da empresa (respondido 2026-07-18)

**Princípio-mestre:** *usar* um valor numa cotação é sempre livre; mudar o **padrão da empresa**
(a régua / knob do tenant) é que exige aprovação. Duas camadas distintas.

| Classe de knob | Aprovador | Fundamento (Wellington) |
|---|---|---|
| Geometria/segurança — corte de chicana, u-bend, folgas, modo TEMA, espessura ASME | **Engenharia** | responsabilidade técnica |
| Produção/calibração — `setup_frac`, **perda/scrap por família**, `ProcessParameter` (tempo/furo, taxa de solda) | **Engenharia** | "é know-how de fabricação" — **não é comercial e não é livre** |
| Comercial — rates R$/h, preço de material, markup, impostos, `fator_correcao_mo` | **Gestor comercial** | risco é preço, não acidente; evita orçamentista "comprar" a venda baixando markup |

**Resumo:** engenharia é dona de tudo que é físico ou de fabricação; comercial é dono só de
rates/preços/markup/impostos/fator_mo. Nenhum knob cruza.

> Isso **contradiz** o que está em `CLASSIFICACAO_KNOBS_WELLINGTON.md` (que propunha
> produção → comercial). Aquele doc está **desatualizado** — este aqui vale.

---

## 4. Defaults técnicos validados

| Item | Valor | Quando |
|---|---|---|
| Pressão → espessura (ASME UG-27/32, Ap.2, UG-21) | validado pelo PE | 2026-06-19 |
| Baffle cut | input em **% do diâmetro**, default **25%**; converte para mm (altura restante) | 2026-07-17 |
| Comprimento padrão de tubo | **6,10 m e 12 m** (o "6,95 m" do áudio era erro de transcrição) | 2026-07-17 |
| Raio mínimo de curva em U | **1,5 × OD** (TEMA RCB-2.3) | 2026-07-17 |
| Passo mínimo de furação | **1,25 × OD** (TEMA) | 2026-07-17 |
| União tubo–espelho | input do cliente (`solda_selagem`) — OF-3399 soldado+expandido, OF-3672 só mandrilado | 2026-07-02 |
| Designações custeáveis a 0,0% | **BEU** e **BEM** (job real fechado é pré-requisito para cada nova) | — |
| Orçamentista converte cotação em OF | **configurável por tenant**, default conservador (não converte) | 2026-07-17 |

---

## 5. Ainda ABERTO — não perguntar o que já está acima

### 5.1 Bloqueiam precisão do motor (só o Wellington resolve)

1. **Orçamento fechado real de designação nova** (AES? NEN? outra?) — sem job real não há
   calibração; a norma não dá horas de solda/usinagem nem peso.
2. **Um segundo BEU ou BEM fechado** — hoje há 1 caso por designação, então o motor está
   *ajustado*, não *validado* contra caso que nunca viu.
3. **Tabela de R$/hora-máquina por recurso** — só a mandrilar tem taxa (~R$80/h); o resto
   entra 0 e o usuário digita à mão. (Q1 de 2026-07-17)
4. **Roteiro do espelho (tubesheet)** — sequência e nomes reais; o áudio ficou dúbio em
   "expandir/espicionar". (Q2 de 2026-07-17)
5. **Passo praticado por bitola** e se o ângulo (30/45/60/90) deve entrar no custo ou ficar
   documental. (Q3 de 2026-07-17)

### 5.2 Estrutura de custo — as 8 perguntas de 2026-07-16 que nunca foram respondidas

6. Qual o **custo fixo mensal** aproximado da ENGEMATEX para o primeiro modelo?
7. Quantas **horas produtivas/mês** são realistas?
8. Separar por **centro de custo** ou começar com custo fixo/hora global?
   *(o formulário faz global; a pergunta que sobra é se vale quebrar por centro)*

> ✅ **APOSENTADAS pelo formulário de https://form.qtec.me** (2026-07-28) — não perguntar:
> custo fixo mensal · horas produtivas/mês realistas · se o Mané estima horas por operação
> ou preço fechado · quais operações estouram · histórico do 2º colocado · alerta vs bloqueio
> abaixo do custo · overhead separado ou embutido (o método embute: tudo cai no custo/hora,
> e a abertura por bloco fica visível na resposta).

### 5.4 Decorrentes da regra de origem do valor (2026-07-27)

9. **Espessura é o único campo do tipo "mínimo"?** Ou existe outro que o projeto dá como
   piso e a fábrica pode subir? (parede de tubo, nº de chicanas, corte e folga já ficaram
   como valor exato — não se alteram)
10. **Engrossar demais dispara outra coisa?** Existe espessura-limiar na ENGEMATEX acima da
    qual é exigido tratamento térmico (PWHT) ou transição de junta? Se sim, qual o número —
    acima dele a mudança volta a ser evento de engenharia.
11. Depois que a cotação **já foi aprovada**, um aumento de custo (ex.: chapa mais grossa)
    deve exigir **re-aprovação do gestor comercial**, ou segue só como alerta?
12. Quando o **memorial chega depois** e diverge do que foi estimado na cotação: com que
    frequência acontece e quanto come de margem? (é o vetor anterior aos 4 mapeados)

### 5.5 Negócio

13. Primeiro cheque: ENGEMATEX comprando licença, ou empresa atendida pelo Wellington como
    consultor freelance?
14. Quantas empresas ele atende hoje e quantas cotam trocador com regularidade?
15. Preço e unidade de cobrança (assento / tenant-mês / cotação emitida).

### 5.6 Não é pergunta — é captura

16. **Gravar 20–30 min dele orçando um equipamento do zero, narrando em voz alta:** por que
    escolhe cada coisa, onde "sente" que o número está errado, o que confere por último antes
    de mandar. Metade do motor saiu de áudio dele; nenhum formulário captura isso.
