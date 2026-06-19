# SmartQuotation — Resumo p/ o Wellington (engenharia de domínio)

**De:** Romulo + assistente de dev · **Para:** @WellToMcAt
**Assunto:** o tier de design mecânico está **fechado** — tudo funciona marcado como *provisório*. Preciso da sua **chancela de PE** em 7 itens pra promover os números de "estimativa de engenharia" para "valor de norma".

---

## 1. O que ficou pronto desde a última conversa

O motor já não é só custeio — ele agora **verifica o projeto** e **documenta a memória de cálculo ASME** na proposta (PDF e DOCX). Entregue e validado:

- **UG-27 / UG-32** — espessura mínima de casco e tampo 2:1 (com corrosão CA); alerta crítico se a espessura informada for menor que a norma.
- **Apêndice 2** — espessura mínima do flange de corpo (girth flange).
- **UG-21** — a pressão de projeto passa a incluir a coluna estática do fluido (ρ·g·h).
- **RT por nº de exposições** — estimativa de chapas de filme (Seção V, Art. 2).
- **Tabela S data-driven** — 3213 materiais da **ASME II-D MÉTRICA 2025** (sua edição licenciada); cada valor S carrega **norma + edição + tabela + linha** e é citado na memória de cálculo.
- **Cadastro de ligas editável por tenant** — dá pra adicionar/ativar liga nova sem deploy.

> Tudo cotável hoje. Cada aproximação está marcada como estimativa na própria tela e no código.

---

## 2. O que precisa do seu AVAL (você é o PE responsável)

Os 7 itens abaixo **já estão funcionando** — falta sua chancela técnica pra deixarem de ser provisórios.

| # | Item | O que confirmar |
|---|---|---|
| 1 | **Valores S 2025** | Extraí da sua edição licenciada (BPVC.II.D.M-2025) via parser. Confere a extração e dá o aval de PE pro uso documental? |
| 2 | **UNS do duplex** | Default = **S31803** (conservador). Pelo MTR, é S31803 ou **S32205**? Muda o S em ~6%. |
| 3 | **Inconel Grade** | Usei **Grade 1 recozido** (217 MPa). Grade 2 solubilizado (184) é p/ alta temp. OK manter Grade 1? |
| 4 | **Gaxeta do flange (Ap. 2)** | Default = **espiralada m=3,0 / y=69 MPa**; furação proporcional ao flange. Confirma gaxeta e disposição dos parafusos? |
| 5 | **Coluna estática (UG-21)** | Altura ≈ **Ø do casco** (trocador horizontal); densidade default = água. OK pros casos de vocês? Vertical/kettle precisaria de altura própria. |
| 6 | **RT por exposições** | Filme útil = **315 mm** (350 − 10% sobreposição); nº de costuras circunferenciais default = 2. Confirma valores de chão de fábrica? |
| 7 | **Fatores MO/preço por liga** | Inconel **2,3× / 13×** e Monel **2,0× / 9×** são defaults de engenharia (editáveis no cadastro). Refinar com dado real quando der. |

---

## 3. Como responder

Não precisa mexer em nada técnico. Responde no grupo, item por item — ex.: *"#2: é S31803 mesmo; #3: Grade 1 OK; #4: gaxeta confere"*. Cada confirmação sua tira um "provisório" do sistema.

**Pra começar:** dos 7, o mais urgente pra liberar cotação certificável é o **#1 (aval dos valores S)** — os outros são refinamentos. Se topar fechar só esse hoje, já destrava muita coisa.
