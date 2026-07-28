# SmartQuotation — Features & Melhorias (áudios do Wellington)

> **Origem:** 9 áudios de voz enviados por **Wellington** (co-autor, engenheiro/tester do sistema) em **17/07/2026**, entre 12:21 e 12:27.
> **Objetivo deste documento:** repassar as demandas de forma estruturada para o agente de desenvolvimento (IA).
> **Ordem:** cronológica (pelo horário de cada áudio).
> **Domínio:** SmartQuotation é um sistema de **cotação de trocadores de calor** baseado na norma **TEMA**. Envolve composição de custo (hora-homem / hora-máquina), estrutura de produto (**EAP**) e roteiro de fabricação.
>
> ⚠️ **Nota de transcrição:** os áudios foram transcritos automaticamente (Whisper). Termos técnicos foram corrigidos/interpretados no texto estruturado. Onde houve dúvida, está marcado com `⚠️`. A transcrição bruta de cada áudio está preservada em [Anexo — Transcrição literal](#anexo--transcrição-literal).

---

## Glossário rápido (para o agente dev)

| Termo | Significado |
|---|---|
| **TEMA** | Norma da *Tubular Exchanger Manufacturers Association*; define tipos e parâmetros de trocadores de calor casco-tubo. |
| **Tipo TEMA (ex: BEM, AES)** | Código de 3 letras: cabeçote frontal + casco + cabeçote traseiro. |
| **Equipamento completo** | Trocador inteiro (cabeçote frontal + casco + cabeçote traseiro + feixe). |
| **Feixe tubular** | Conjunto: espelho(s) + tubos + chicanas + espaçadores + tirantes. |
| **Feixe reto × Feixe em U** | Tubos retos (dois espelhos ou espelho fixo + flutuante) vs. tubos curvados em U. |
| **Espelho** | *Tubesheet* — chapa perfurada onde os tubos são fixados. |
| **Espelho fixo / flutuante** | Configurações do espelho no feixe reto. |
| **Cabeçote frontal / Casco / Cabeçote traseiro** | Partes principais do equipamento. |
| **Chicanas** | *Baffles* — defletores internos. |
| **Tirantes / Espaçadores** | Barras e espaçadores que montam o feixe. |
| **EAP** | Estrutura Analítica do Produto (árvore de itens do produto). |
| **Roteiro (de fabricação)** | Sequência de operações de produção (usinar, cortar, expandir, traçar furos…). |
| **Hora-homem / Hora-máquina** | Componentes de custo de mão de obra/máquina na composição da cotação. |

---

## Backlog resumido (visão do agente dev)

| # | Áudio | Feature / Fix | Tipo | Prioridade sugerida |
|---|---|---|---|---|
| F1 | 12:21:03 | Hora-máquina não entra no cálculo + tornar valores de hora-homem/hora-máquina editáveis | 🐞 Bug + ✨ Feature | Alta |
| F2 | 12:21:56 | Separar EAP (produto) de Roteiro (mão de obra); editar dimensões e operações por item | ✨ Feature | Alta |
| F3 | 12:22:25 | Definição de layout UI (roteiro separado × aninhado) — a critério do UI/UX | 🎨 UX (decisão) | Média |
| F4 | 12:24:24 | Tela TEMA parametrizável: perguntar "equipamento completo × partes"; compor partes | ✨ Feature | Alta |
| F5 | 12:24:47 | Faseamento: Fase 1 = completo/feixe; Fase 2 = partes individuais do trocador | 🗺️ Escopo | Alta |
| F6 | 12:25:06 | Pedido de análise ao arquiteto: vale separar "completo × partes" já agora? | ❓ Decisão técnica | Média |
| F7 | 12:25:44 | Ao escolher tipo TEMA (BEM, AES…), carregar/editar parâmetros conforme norma por parte | ✨ Feature | Alta |
| F8 | 12:26:26 | Fluxo do feixe reto: perguntas de espelho, tubos, chicanas, furação conforme TEMA | ✨ Feature | Alta |
| F9 | 12:27:26 | Tubos em U: informar comprimento; sistema calcula tubo desenvolvido (reto) e emenda | ✨ Feature (desejável) | Média |

---

## Detalhamento cronológico

### F1 — Composição da cotação: hora-máquina no cálculo + valores editáveis
**Áudio:** `12.21.03` (55s)

**Contexto:** vamos passar a mexer na composição da cotação (campos editáveis). No item de mão de obra existem os campos **hora-homem** e **hora-máquina**.

**Problema (bug):**
- O campo **hora-máquina** é editável, mas **não influencia o cálculo**. Ex.: valor padrão 0; ao inserir 5 horas-máquina, o **valor total da cotação não muda**. Só hora-homem está sendo considerada.

**Requisito:**
1. Passar a **considerar a parcela de hora-máquina** no cálculo do total (junto com hora-homem).
2. Tornar **editáveis** os campos de **valor da hora-homem** e **valor da hora-máquina** (além das quantidades de horas).
3. O sistema traz o **valor default** (o que estiver cadastrado/parametrizado); o usuário **edita conforme a cotação**.

**Critérios de aceite:**
- Alterar quantidade de hora-máquina recalcula o total.
- Valor unitário de hora-homem e de hora-máquina são editáveis por cotação, com default vindo do cadastro.
- Total = (qtd_hh × valor_hh) + (qtd_hm × valor_hm) + demais parcelas.

---

### F2 — Separar EAP (produto) do Roteiro (mão de obra) e editar por item
**Áudio:** `12.21.56` (51s)

**Requisito:** ao construir a **EAP**, separar claramente:
- **Produto** (ex.: espelho, tubo, chicanas) → chamado de **EAP**.
- **Mão de obra** → chamado de **Roteiro de fabricação**, listado separadamente (embaixo).

**Interação desejada:** ao **clicar em um item da EAP** (ex.: *espelho*), abrir uma tela para:
- Editar **dimensões**: material, espessura, diâmetro, quantidade.
- Editar as **operações** do roteiro que produzem o item, carregadas **na ordem** (ex.: usinar, cortar, expandir ⚠️, traçar furos…).
- Recalcular/considerar o valor na **composição do preço** do item (ex.: preço do espelho).

**Critérios de aceite:**
- EAP e Roteiro são entidades/listas distintas.
- Clicar num item da EAP abre edição de dimensões + operações.
- Editar dimensões/operações reflete no preço composto do item.

---

### F3 — Decisão de layout (UI/UX): roteiro separado × aninhado
**Áudio:** `12.22.25` (27s)

**Conteúdo:** existem duas formas possíveis de apresentar (relacionado à F2):
- **(A)** Estrutura de produto em cima e **roteiro separado** embaixo (duas listas na mesma tela); edita-se o roteiro direto na lista de baixo.
- **(B)** Clicar no item (ex.: espelho) e o **roteiro abre dentro** do item.

**Decisão do Wellington:** "para mim é indiferente / **está aceito** o que o sistema e o **especialista de UI/UX** entenderem como melhor."

**Ação para o dev:** deixar a cargo do UI/UX; ambas abordagens são aceitas. (Não bloqueia F2.)

---

### F4 — Tela TEMA parametrizável para compor o equipamento
**Áudio:** `12.24.24` (83s)

**Contexto:** hoje, ao clicar no botão **TEMA**, abre uma tela com um equipamento e permite posicionar **cabeçote frontal**, **casco** e **cabeçote traseiro**. Wellington gostou muito da ideia ("fantástica"), mas quer **parametrizar** e usar essa tela para **compor** o equipamento.

**Requisito:**
1. Poder **selecionar apenas uma parte** do equipamento (não só o completo).
2. Ao clicar no botão TEMA, **perguntar**: a cotação é de **equipamento completo** ou de **partes do trocador**?
   - Se **partes**: abrir para compor cabeçote, casco, espelho, feixe tubular, anel de teste, etc.
3. **Escopo inicial (limitar):** oferecer apenas **"Equipamento completo"** ou **"Feixe tubular"**.
   - No **feixe** entram: **espelho, tubos, chicanas, espaçadores, tirantes** (o que compõe o feixe conforme TEMA).
   - Ao montar o feixe, o sistema deve **perguntar se é feixe reto ou feixe em U**.

**Critérios de aceite:**
- Botão TEMA dispara pergunta "completo × partes".
- Versão inicial suporta *completo* e *feixe tubular*.
- Ao escolher feixe, pergunta reto × U.

*(Wellington cita "o UX/o analista avalia também" — ver F6.)*

---

### F5 — Faseamento do escopo (completo/feixe agora; partes depois)
**Áudio:** `12.24.47` (20s)

**Requisito de escopo:**
- **Fase 1 (agora):** **equipamento completo** OU **feixe**.
- **Fase 2 (posterior):** cotar **partes individuais** do trocador — tampa, só cabeçote frontal, só casco, só feixe, só cabeçote traseiro, e assim por diante.

---

### F6 — Análise do arquiteto: vale separar "completo × partes" já agora?
**Áudio:** `12.25.06` (16s)

**Pedido (para o analista/arquiteto do sistema):** avaliar se é um **bom momento** para já estruturar nesse formato proposto — **"equipamento completo × partes de um equipamento"** — e tratar isso desde já, ou deixar para depois.

**Ação para o dev:** trazer recomendação técnica (impacto de arquitetura/dados) sobre adotar a separação completo × partes agora vs. na Fase 2.

---

### F7 — Parâmetros por tipo TEMA (BEM, AES…) conforme a norma
**Áudio:** `12.25.44` (35s)

**Requisito:** ao montar o equipamento e **escolher o tipo TEMA**, dar acesso a **editar os parâmetros daquela configuração**:
- Ex.: escolheu **BEM** → liberar edição das informações do BEM.
- Ex.: escolheu **AES** → carregar as informações/parametrizações conforme a **norma TEMA**.
- Parâmetros por parte: **tipo de material do cabeçote, diâmetro, espessura da chapa**, etc.
- O sistema deve saber **quais parâmetros são necessários para cada parte**, conforme descrito pela TEMA, e considerar **cada parte** do equipamento.

**Critérios de aceite:**
- Seleção do tipo TEMA carrega o conjunto de parâmetros correto por parte.
- Parâmetros editáveis (material, diâmetro, espessura, etc.).

---

### F8 — Fluxo de configuração do Feixe Tubular (reto)
**Áudio:** `12.26.26` (38s)

**Contexto:** o feixe tubular é o caso "mais fácil". Ao cotar/criar um feixe conforme TEMA:

**Se feixe reto**, o sistema pergunta em sequência:
1. Qual o **espelho do lado fixo**; se há **espelho flutuante** ou se são **dois espelhos iguais**.
2. **Quantidade de tubos**.
3. **Bitola/diâmetro do tubo** ⚠️ ("âmbito de tubo").
4. **Material do tubo** (já existem os **padrões** cadastrados previamente).
5. **Recorte da chicana** (baffle cut).
6. **Disposição da furação** (layout de tubos) e **ângulo do layout de furação** (ex.: 30/45/60/90).
7. **Detalhes do feixe**: **tirantes**, **barras espaçadoras**, e o que houver conforme TEMA.

**Critérios de aceite:**
- Wizard do feixe reto solicita os itens 1–7.
- Materiais/padrões de tubo pré-carregados dos cadastros.

---

### F9 — Tubos em U: comprimento, tubo desenvolvido e emenda (desejável)
**Áudio:** `12.27.26` (58s)

**Requisito:** poder **editar**: espessura da chapa, comprimento, dimensões (largura, comprimento, espessura, material).

**Tubo de troca térmica em U:**
- Usuário informa o **comprimento do tubo curvado**.
- O sistema deve **considerar o tubo desenvolvido (reto)** e **calcular** o comprimento reto necessário para depois curvar.
- O **roteiro de fabricação** considera o **tubo reto no comprimento total**.
- Calcular conforme os **comprimentos padrão de mercado** (aprox. **6,95 m** ou **12 m** ⚠️ confirmar valores).
- Se o tubo desenvolvido reto **exceder** o comprimento padrão, o sistema deve **indicar que será necessário soldar/emendar tubo**.

**Prioridade:** marcado por Wellington como **"parte desejável"** do sistema (nice-to-have).

**Critérios de aceite:**
- Entrada do comprimento curvado (U) → cálculo do tubo reto desenvolvido.
- Comparação com comprimentos padrão e sinalização de emenda quando exceder.

---

## Pontos em aberto / a confirmar com o Wellington

- ⚠️ **F8:** "âmbito de tubo" — confirmar se é **bitola/diâmetro** do tubo.
- ⚠️ **F9:** comprimentos padrão de mercado — confirmar se são **6,95 m** e **12 m** (ou 6 m / 6,10 m).
- ⚠️ **F2:** operação "espicionar/expandir" — confirmar nome correto da operação do roteiro do espelho.
- **F6:** aguarda recomendação do arquiteto sobre separar "completo × partes" já na Fase 1.

---

## Anexo — Transcrição literal

> Transcrição automática (Whisper, modelo *small*, pt-BR). Erros de termos técnicos preservados aqui; interpretação correta está nas seções acima.

**1. `WhatsApp Ptt 2026-07-17 at 12.21.03.ogg` (55,4s)**
> O que eu percebi que a gente vai passar a mexer é na composição da cotação, né? Os campos editáveis, incluir, no caso de mão de obra, ele tem até o campo lá, hora homem, hora máquina, mas ele só está considerando hora homem. Não está contando, quando eu acrescento um valor na hora máquina, está editável o campo, mas vamos supor que o valor está lá zero, vem ver o padrão como zero, eu coloco cinco horas, por exemplo. Ele não influencia nada no cálculo, o valor total que está na frente da cotação continua mesmo. Então a gente precisa dar esse valor dessa parcela de hora máquina, hora homem, e além das horas, eu acho que ele precisa deixar os campos editáveis para o valor da hora homem e o valor da hora máquina. Então eu posso colocar a quantidade de valor. Ele pode trazer o que ele tem lá acetado, como o valor default, e aí a gente edita esse valor conforme a cotação.

**2. `WhatsApp Ptt 2026-07-17 at 12.21.56.ogg` (51,5s)**
> Outra coisa é quando ele constrói a EAP, ele separar o que é produto, então espelho, tubo, chicanas, do que é mão de obra. Então ele chama de EAP o que é do produto e mão de obra ele vai chamar de roteiro, de fabricação e separar isso embaixo. Ou criar de uma forma que eu possa chamar, por exemplo, o EAP, clicar lá no espelho e ele abre para mim uma tela onde eu posso editar as dimensões do espelho. Então material, espessura, diâmetro, quantidade e também editar as operações. Aí ele carregaria as operações para a produção do espelho, lá o [usinar] espelho, cortar, [expandir], traçar furos, essas coisas todas na ordem. E a gente pode editar por ali e aí ele considerar o valor da composição do preço do espelho.

**3. `WhatsApp Ptt 2026-07-17 at 12.22.25.ogg` (27,4s)**
> A forma como vai trabalhar se vai se separando os roteiros, separando o roteiro da estrutura de produto e editando o roteiro direto na tela de roteiro embaixo e a estrutura de produto diretamente em cima. Pra mim é diferente. Se eu vou clicar no espelho e vai abrir o roteiro dentro do espelho, se vai aparecer como duas listas separadas na tela, pra mim é diferente. O que o sistema entender, aí o especialista de UI UX entender como melhor, pra mim tá aceito.

**4. `WhatsApp Ptt 2026-07-17 at 12.24.24.ogg` (83,7s)**
> No site quando eu clico no botão TEMA ele abre a tela, tem um botãozinho aí em cima com o equipamento. Essa ideia é fantástica, legal clicar lá, abrir a tela, poder colocar o cabeçote frontal, o casco e o cabeçote traseiro. Bacana, mas eu preciso parametrizar isso. Eu queria usar essa tela do TEMA para compor o equipamento e também que eu pudesse, por exemplo, selecionar apenas uma parte do equipamento. Então, se eu for acessar essa tela de criar o equipamento pelo TEMA, ele deveria ter uma pergunta quando eu clicar lá no botão — imagino, aí o [UX] analisa também — é uma pergunta se eu vou fazer uma cotação de um [equipamento] completo ou só de [algumas] partes do trocador. Aí, se a resposta for [algumas] partes do trocador, ele abriria para eu compor ali cabeçote, casco, espelho, feixe tubular completo, anel de teste, coisas assim que estão relacionados a TEMA. Inicialmente podemos limitar a ter equipamento completo ou feixe tubular, onde entraria então espelho, tubos, chicanas, né, espaçadores, tirantes, essas coisas aí que compõem o [feixe]. Então pegaria o [feixe] completo conforme TEMA e colocaria ali, e nesse caso ele me perguntaria se o feixe é reto ou feixe em U.

**5. `WhatsApp Ptt 2026-07-17 at 12.24.47.ogg` (20,1s)**
> Podemos começar assim, equipamento completo ou feixes, e posteriormente equipamento completo para partes de um trocador. Na parte do trocador poderia fazer a tampa, poderia fazer só o cabeçote frontal, poderia fazer só o casco, poderia fazer só o feixe, poderia fazer só o cabeçote traseiro e assim por diante.

**6. `WhatsApp Ptt 2026-07-17 at 12.25.06.ogg` (16,8s)**
> Talvez valha a pena analisar também, passar aí para o seu analisador para ele verificar se é um momento bom de separar nesse formato que eu propus, equipamento completo e [partes]. Inicialmente, ou seja, vale a pena ir para equipamento completo ou partes de um equipamento e tratar isso já agora.

**7. `WhatsApp Ptt 2026-07-17 at 12.25.44.ogg` (35,5s)**
> E aí de novo, quando eu montar o equipamento e escolher ali, eu preciso ter acesso aos parâmetros. Então, se eu vou escolher um BEM, então ele vai ter que me dar acesso a editar as informações do BEM. Se for um AES, ele vai precisar carregar informações para que eu dê, de acordo com a norma TEMA, as parametrizações. Ou seja, tipo de material do cabeçote, diâmetro, espessura da chapa, essas coisas que ele pode ter da norma TEMA, quais são os parâmetros necessários para cada parte. E ele vai levar em consideração cada parte, mesmo do equipamento, descrito ali pela TEMA.

**8. `WhatsApp Ptt 2026-07-17 at 12.26.26.ogg` (38,8s)**
> No caso de feixe tubular é mais fácil, né? Eu optei lá para eu estar cotando, criando, conforme [TEMA], um feixe tubular. [Se for] feixe reto, ele vai me perguntar qual o espelho do lado fixo, [se] tem um espelho flutuante ou se são dois espelhos iguais. Se o feixe for reto, então ele vai perguntar depois só a quantidade de tubos, [bitola/diâmetro] do tubo, material do tubo, que já tem os padrões que a gente passou para ele, o recorte da chicana, disposição da furação, o ângulo da disposição do [layout] de furação, e detalhes relacionados ao feixe, as barras [espaçadoras/tirantes], o que tiver lá conforme TEMA também.

**9. `WhatsApp Ptt 2026-07-17 at 12.27.26.ogg` (58,8s)**
> E aí mais uma vez eu preciso poder editar a espessura da chapa, comprimento, [dimensões] — largura, comprimento, espessura, material. Tubo de troca térmica: quando for em U, preciso poder passar para ele o comprimento do tubo curvado, [mas] considerar o tubo desenvolvido; o sistema deveria calcular para nós então os tubos retos para eu curvar. E aí, nessa situação de tubos em U, o roteiro de fabricação vai considerar o tubo reto com o comprimento total e vai precisar calcular de acordo com os comprimentos padrões de mercado, que eu acho que é 6 metros e 95 ou 12 metros. Então, se passar do comprimento, o tubo desenvolvido reto precisa ser mais comprido que isso: indicar que vai precisar soldar tubo e emendar tubo. Isso é uma parte desejável para o sistema.
