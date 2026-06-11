# SmartQuotation — Resumo p/ o Wellington (engenharia de domínio)

**De:** Romulo + assistente de dev · **Para:** @WellToMcAt
**Assunto:** o motor de custeio do permutador completo está pronto até onde dá sem você. Preciso das suas decisões de engenharia pra destravar a próxima camada.

---

## 1. O que o motor já faz (validado contra os seus gabaritos)

Construímos o custeio **paramétrico** do trocador casco-tubo completo, a partir das suas 3 planilhas (Feixe, BEU, BEM). Ele reproduz os gabaritos reais a **0,0% de erro**:

| Equipamento | Motor | Gabarito |
|---|---:|---:|
| Feixe tubular (136 tubos) | — | R$ 35.353 / venda R$ 44.192 (−2,9%) |
| **BEU** (bonnet + casco + feixe-U) | R$ 128.160 | R$ 128.160 ✓ |
| **BEM** (espelho fixo, tubos retos) | R$ 119.295 | R$ 119.295 ✓ |

E agora **responde às dimensões** do projeto (não é mais "replay" do gabarito). O orçamentista informa nº de tubos, comprimento, OD/parede, nº de chicanas, diâmetro/espessura do casco, nº de passes, classe metalúrgica — e o custo recalcula:

- **Matéria-prima:** peso recomputado pela geometria de cada peça (tubo, virola, espelho, chicana, tampo, anel, pescoço, flange).
- **Mão de obra:** horas escalam pelo driver físico de cada operação (furação ∝ nº tubos, soldas ∝ comprimento/diâmetro, etc.), **com parcela de setup fixo**.
- **Ensaios/serviços:** raio-X e ultrassom ∝ metros de solda; tratamento térmico e consumíveis ∝ massa; teste hidrostático ∝ volume.
- **Soldas** crescem com a **espessura²** (chapa grossa = mais passes).
- **Metalurgia bimetálica:** feixe e casco podem ter ligas diferentes (ex.: feixe inox + casco aço-carbono) — afeta horas, densidade e preço/kg.
- **Aviso de arranjo:** se o feixe não couber no casco informado (regra de pitch TEMA), ele alerta.

> Tudo isso já é cotável hoje na tela "Permutador". O motor é honesto: cada aproximação está marcada na própria interface.

---

## 2. O que precisa de VOCÊ — decisões que não dá pra "chutar"

Estas são de **segurança/processo** — só você tem os números certos. Dividi em **(A) bloqueadores** do próximo salto e **(B) calibrações** que melhoram a precisão.

### (A) Bloqueadores do próximo tier

**A1 — Pressão de projeto → espessura.**
Hoje o orçamentista digita a espessura do casco. O ideal é o motor calcular a espessura mínima (casco, tampo, espelho) a partir da **pressão de projeto**.
- A ENGEMATEX usa qual norma/prática? (ASME VIII Div.1 UG-27? TEMA?)
- Você tem as **tensões admissíveis (S)** por material × temperatura que usam? Ou prefere manter a espessura como entrada manual (e o motor só valida)?

**A2 — Lado do cabeçote (qual fluido é corrosivo).**
O cabeçote é molhado pelo fluido **dos tubos**. Se o tubo for inox por corrosão, o cabeçote também é. Hoje tratamos o cabeçote como "lado casco".
- Existe regra fixa, ou é caso a caso? Vale a pena um campo "fluido corrosivo: tubos / casco / ambos"?

**A3 — Flanges por classe de pressão.**
Hoje o flange entra com preço de catálogo fixo.
- Querem que o motor puxe peso/dimensão de tabela (ASME B16.5 / B16.47) por **rating × diâmetro**? Você tem essa tabela na mão (vimos abas "FLANGES WN" e "KGF FL" nas planilhas)?

### (B) Calibrações — confirmar/corrigir os números (não bloqueiam, mas melhoram)

Coloquei **defaults de engenharia** (chutes razoáveis) onde não tínhamos seu dado. **Me corrija os que estiverem fora:**

| Item | Default atual | Confere? |
|---|---|---|
| **Fator de liga na MO** (vs aço-carbono) | inox **1,4** · duplex **1,7** · níquel **2,3** | ? |
| **Fator de preço/kg do material** (vs CS) | inox **4,5×** · duplex **6×** · níquel **12×** | ? |
| **Parcela de setup fixo** (furação/calandragem têm setup alto) | furação **20%** · solda/ensaio **10%** · calandragem ~30% | ? |
| **Perda (bruto/líquido)** por família | espelho/chicana **25%** · tampo **20%** · anel **15%** · tubo/chapa **10%** | ? (o agy sugeriu espelho perto de 40%) |
| **Folga feixe↔casco** por cabeçote | fixo/U **12-15mm** · flutuante (S/T/P/W) **45-75mm** | ? |
| **Escopo de radiografia** | hoje escala linear com metros de solda | total vs spot (RT1-4) muda muito? |
| **Nº de passes de referência** (BEU/BEM) | assumi **2** | ? |
| **Gross-up de ICMS** | calibrado p/ bater seu gabarito (não é fórmula fiscal pura) | qual o regime tributário real? |

---

## 3. Como responder

Não precisa mexer em nada técnico. Pode só responder no grupo, item por item (ex.: *"A1: usamos ASME, tenho as tensões; B-fator de liga inox é 1,5"*). Cada número seu substitui um default e melhora a precisão; cada decisão de (A) destrava um pedaço novo do motor.

**Pergunta-chave pra começar:** dos bloqueadores (A1/A2/A3), qual é o mais importante pro dia a dia da cotação de vocês?
