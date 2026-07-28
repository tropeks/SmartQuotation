# Prancha — sistema visual do SmartQuotation

**Decisão (Rômulo, 2026-07-28, tarde):** o SmartQuotation ganha identidade própria, com o
Vitali como *inspiração* e não como cânone.

Supersede a decisão da manhã do mesmo dia, que adotava a pele *Tasy Neumorphic* integralmente.
Aquele registro é o `docs/DESIGN_IDENTIDADE_VISUAL.md`, que **chega com o PR #111** e ainda não
está nesta branch — quando ele mergear, marcar lá o banner de *superseded* apontando para cá
(item aberto no `BACKLOG.md`). Ele segue valendo como registro do que foi considerado e,
principalmente, do que **sobreviveu** da Tasy (§2 abaixo).

Este documento é a **fonte da verdade dos tokens**. Quem implementa lê daqui e não inventa
valor.

---

## 1. A tese

A tela é um **documento de engenharia que por acaso é interativo**. A referência não é painel
de SaaS — é o carimbo da prancha, a folha de cálculo, a norma.

O produto não compete com aplicativo de consumo; compete com **a planilha que o orçamentista
já domina**. A planilha ganha em densidade e confiança no número, e perde em **proveniência**:
ninguém sabe de onde veio cada célula. É exatamente ali que a margem vaza. O sistema visual
ataca essa fraqueza em vez de imitar dashboard.

Três princípios atravessam tudo:

1. **Profundidade só onde significa.** Campo afunda (é onde se deposita algo). Painel é papel
   sobre a mesa, separado por fio de 1 px — não almofada. Sombra real só no que flutua de
   verdade: gaveta e modal. **Três níveis, não nove.**
2. **O número é o herói tipográfico.** Toda grandeza em monoespaçada com algarismo tabular,
   alinhada à direita, casa decimal sob casa decimal. O texto ao redor recua para que a coluna
   de dinheiro seja a coisa mais escura da tela.
3. **Proveniência é classe visual de primeira ordem.** Todo número tem origem — motor,
   catálogo, importado, ou digitado por alguém. Essa distinção é o diferencial do produto e
   não existe em pele genérica.

### Por que não a Tasy inteira

Não é crítica ao Vitali: lá é painel clínico de **campo esparso**, e a pele serve muito bem.
Aqui há EAP com 64 operações e 17 componentes. Em grade de muitas colunas, **borda difusa
apaga a malha** — e aqui a malha é a informação. Mesmo remédio, dose errada.

| Do Vitali, fica | Do Vitali, cai |
|---|---|
| Campo escavado (`inset`) — boa affordance | Painel almofadado |
| Um só acento de marca | Cinza-azulado leitoso `#DFE5EB` |
| Mundo único, sem tema escuro | Inter (a fonte segura de todo mundo) |
| Semântica de cor tipo Primer | Cantos de 12 px |

---

## 2. Tokens — cor

```css
:root{
  /* --- neutros: mesa, papel, campo --- */
  --p-desk:#E4E9EE;      /* fundo da aplicação (a mesa) */
  --p-paper:#FBFCFD;     /* painel de conteúdo (o papel) */
  --p-paper-2:#F3F6F9;   /* cabeçalho de painel, rodapé de tabela */
  --p-field:#EDF1F5;     /* campo de entrada — escavado */
  --p-chrome:#1E242B;    /* rail e cabeçalho (a chapa) */
  --p-chrome-2:#2A323B;  /* item ativo do rail */

  /* --- tinta --- */
  --p-ink:#161B22;       /* número, título */
  --p-ink-2:#4A5561;     /* texto secundário */
  --p-ink-3:#8894A2;     /* rótulo, desabilitado, valor zero */

  /* --- traço --- */
  --p-rule:#DDE3EA;      /* fio interno (linha de tabela) */
  --p-rule-2:#C4CDD7;    /* fio de borda (contorno de painel) */

  /* --- marca: azul de prancheta --- */
  --p-bp:#174E7A;
  --p-bp-2:#0F3A5C;      /* pressionado / borda de botão primário */
  --p-bp-soft:#E4EDF4;   /* fundo de realce */

  /* --- metal quente: RISCO E ORIGEM MANUAL, NADA MAIS --- */
  --p-hot:#C1440E;
  --p-hot-soft:#FAEAE2;

  /* --- semânticos --- */
  --p-ok:#1A7F4B;    --p-ok-soft:#E4F1EA;
  --p-warn:#8A6100;  --p-warn-soft:#F7EEDC;
  --p-bad:#A82824;   --p-bad-soft:#F8E7E6;
}
```

> ⚠️ **A regra do laranja.** `--p-hot` significa **uma coisa só**: risco de margem e valor de
> origem manual. Não é cor de link, de rótulo, de código de item nem de foco. Se virar cor de
> botão, o sinal morre e o produto perde o instrumento que justifica a sprint. Qualquer PR que
> use `--p-hot` fora desse escopo deve ser barrado na revisão.

---

## 3. Tokens — tipografia

Uma família, três papéis. **IBM Plex** tem Sans, Condensed e Mono desenhadas juntas.

```css
--p-sans:'IBM Plex Sans',ui-sans-serif,system-ui,-apple-system,sans-serif;
--p-cond:'IBM Plex Sans Condensed','IBM Plex Sans',ui-sans-serif,system-ui,sans-serif;
--p-mono:'IBM Plex Mono','JetBrains Mono',ui-monospace,SFMono-Regular,Menlo,monospace;
```

| Papel | Família | Tamanho | Peso | Uso |
|---|---|---|---|---|
| Título de tela | Sans | 20–23 px | 600 | cabeçalho, `h1` |
| Título de seção | Sans | 15–17 px | 600 | `h3` |
| Corpo / rótulo de form | Sans | 13 px | 400 | padrão da interface |
| Cabeçalho de tabela | **Condensed** | 10,5 px | 600 | `letter-spacing:.11em`, caixa alta |
| Micro-rótulo | **Condensed** | 10 px | 600 | `letter-spacing:.14em`, caixa alta |
| Grandeza | **Mono** | 12,5–22 px | 500 | `font-variant-numeric:tabular-nums` |
| Código / hash | **Mono** | 11–12,5 px | 400 | `COT-…`, designação TEMA, hash |

**Por que Plex e não Inter:** Inter é a escolha segura de todo produto SaaS. A Plex foi
desenhada para uma empresa técnica, tem condensada da mesma família (resolve cabeçalho de
tabela larga sem trocar de voz) e a mono distingue bem `0`/`O` e `1`/`l`. **Em orçamento, ler
`1` como `l` custa dinheiro.**

A fonte entra pelo `base.html`, que já carrega Google Fonts. Trocar
`Archivo` por `IBM Plex Sans:wght@400;500;600` + `IBM Plex Sans Condensed:wght@600` +
`IBM Plex Mono:wght@400;500`.

---

## 4. Tokens — forma e profundidade

```css
--p-radius:4px;          /* padrão — precisão, não suavidade de consumo */
--p-radius-sm:3px;       /* pílula, marca, chip */

/* NÍVEL 1 — campo escavado (única herança de relevo) */
--p-sunken:inset 0 2px 3px rgba(22,27,34,.07);
/* NÍVEL 2 — flutuante de verdade: gaveta, modal, popover */
--p-float:0 12px 32px rgba(22,27,34,.16);
/* foco de teclado */
--p-focus:0 0 0 3px rgba(23,78,122,.16);
```

Painel **não tem sombra**: `background:var(--p-paper); border:1px solid var(--p-rule-2)`.

**Densidade:** linha de tabela **29 px**. É o que abre espaço para a coluna de horas na EAP
sem estourar a largura. Risco registrado: validar com o Wellington que não aperta demais.

---

## 5. Componentes que são novos (não é só troca de pele)

### 5.1 Carimbo — bloco de título da prancha

Substitui o cabeçalho atual da tela de detalhe (`.q-header`). Malha regrada de 4 colunas com
os metadados que essas pessoas já leem nesse formato:

```
CLIENTE (2 col) │ TAG DO EQUIPAMENTO │ DESIGNAÇÃO TEMA
EQUIPAMENTO (2 col) │ NORMA DE PROJETO │ PRESSÃO · TEMPERATURA
RESPONSÁVEL TÉCNICO + CREA (2 col) │ EMISSÃO │ ORIGEM DO PROJETO
```

Micro-rótulo em Condensed caixa alta; valor em Mono (ou Sans quando for texto corrido, ex. nome
do cliente).

> **Correção.** Uma versão anterior afirmava que "todos os campos já existem em
> `quotation.inputs`". **Falso**, e a investigação do implementador provou. O que existe:

| Célula | Fonte real | Ressalva |
|---|---|---|
| Cliente | `customer.company_name` | — |
| Equipamento | `title` + `get_scope_display` | — |
| Emissão | `created_at` | — |
| Designação TEMA | `inputs["designacao"]` | só em `scope='complete'` |
| Pressão · Temperatura | `inputs["pressao_projeto_bar"/"temperatura_projeto_c"]` | só em `complete` — o data sheet do feixe não pergunta |
| Norma de projeto | `CalculationSnapshot.standard_refs` | só quando há memorial ASME |
| Responsável técnico | `TechnicalApproval.approved_by` + CREA | é quem **assinou** |
| **TAG do equipamento** | — | **não existe no modelo** |
| **Origem do projeto** | — | **não existe**; é o *tipo de projeto* do `PLAN_TIPO_PROJETO_V2` |

Célula sem fonte renderiza `—` **com o rótulo presente**. Carimbo com menos campos é
informação; carimbo com campo inventado é defeito.

**Defeito descoberto de raspão:** o `engineer_responsavel` do formulário de entrada
**nunca foi persistido** — `create_feixe_quotation` não o recebe. Hoje a única fonte de
responsável técnico é quem assinou a aprovação.

### 5.2 Marca de proveniência

Quatro origens, distinguíveis por **forma além de cor** — daltonismo não pode apagar a
diferença entre "o motor calculou" e "alguém digitou".

| Origem | Marca | Token |
|---|---|---|
| Motor de custeio (`seed`) | círculo cheio | `--p-bp` |
| Catálogo / template (`template`) | círculo vazado | `--p-ink-3` |
| **Ajuste manual** (`manual`) | **losango cheio** | **`--p-hot`** |

São **três**, não quatro. Eu havia especificado uma quarta marca (*importado*), mas
`ItemOperacao.ORIGEM` só admite `seed | template | manual` — ela não tinha fonte e foi
removida do CSS em vez de ficar prometendo o que a tela não entrega.

**Regra de origem no nível do item:** `origem` vive na operação (N2) e a linha da EAP é o
item (N1). Prevalece a mais forte — **manual > template > seed**. Basta *uma* operação
manual para o item inteiro ser manual: exigir que todas fossem esconderia justamente o
caso do vazamento de margem. Item só com matéria-prima conta como catálogo.

O dado já existe: **`ItemOperacao.origem`**. Entrou no payload do snapshot no M1 e nunca
chegou à tela. Linha com origem manual ganha fundo `--p-hot-soft` e faixa de 3 px na primeira
célula.

### 5.3 Selo — instrumento de confiança

Binário e crítico: ou a assinatura cobre o cálculo, ou não cobre. Faixa lateral de 5 px carrega
o estado antes de qualquer palavra ser lida.

| Estado | Faixa | Significado |
|---|---|---|
| Íntegro | `--p-ok` | hash vigente = hash assinado; conversão em OF liberada |
| **Divergente** | **`--p-hot`** | o cálculo mudou depois da assinatura; conversão bloqueada |
| Sem aprovação | `--p-warn` | nenhuma assinatura ativa |

A comparação já é calculada pelo `convertibility_panel` (`apps/audit`). É a mesma verdade,
ganhando forma.

### 5.4 Campo derivado ≠ campo de entrada

No data sheet, campo que o motor calcula (espessura ASME, peso bruto, área, refugo) fica
**raso e em papel**, sem `--p-sunken`, cor `--p-ink-2`. A diferença tem de ser óbvia sem
legenda: não se digita ali.

---

## 6. Escopo e regra de ouro da migração

**Preservar os nomes de classe.** `.g-rail`, `.q-btn`, `.g-section`, `.g-table`, `.q-badge`,
`.command-center-layout`… Se os seletores forem preservados, a maioria dos templates não muda
— é troca de pele, não de estrutura. O contrato exato está no levantamento da sprint.

Não perder na reescrita:
- regras de `:focus-visible` em toda superfície interativa;
- `.skip-link`;
- `[x-cloak]` (Alpine) e `.htmx-request` — se sumirem, aparece flash de conteúdo não inicializado.

### 6.1 A proposta em PDF entra no escopo (mudei de ideia)

Eu tinha deixado `proposals/proposal_pdf.html` de fora, supondo complexidade do WeasyPrint. O
levantamento mostrou outra coisa: o arquivo é um HTML completo e independente, sem `extends` e
sem link para o design system, com a paleta antiga **duplicada à mão em 8 valores hex**
(`#d94e1f` na marca e no título de seção, `#16151a`, `#f4f1ea`, `#f5c542`, mais neutros).

Isso significa que a troca de tokens **não vaza** para ele — nem para o bem. Deixar fora não é
"adiar", é **estampar a identidade morta no único documento que chega ao cliente**. São 8
linhas. Entra.

### 6.2 Defeitos vivos encontrados no levantamento

Consertar junto, porque a reescrita passa por cima deles de qualquer jeito:

- **`--g-bg` não existe.** `detail.html:98,275` usam `var(--g-bg,#fff)`. Funcionam hoje **por
  acidente**, só pelo fallback.
- **`var(--g-amber,#b8860b)` já diverge** do `--g-amber:#b8851a` do CSS
  (`data_sheet.html:105,120`). É a prova viva do risco do fallback: cor levemente diferente,
  sem erro e sem aviso.
- **`.approval-state--ok/--pending` não existem no CSS.** São 100% inline em `detail.html`,
  duplicando o que `.q-status--*` já faz, com paleta e fallback próprios.

---

## 6.3 Contrato duro da reescrita (levantado, não presumido)

O CSS tem 527 linhas, 164 classes, 28 custom properties. **139 classes são consumidas por
template.** O que segue é o que a reescrita não pode quebrar.

### Armadilhas que não aparecem no HTML

- **`.q-status--{draft,review,approved,sent,won,lost}` são montadas em Python**, no dict
  `_STATUS_PILL_CLASSES` de `apps/quotations/views.py:52-57`, e injetadas por contexto. Não
  existem como texto literal em template nenhum. Renomear no CSS sem tocar no `views.py`
  quebra **seis estados de UI em silêncio**.
- **Classes aplicadas por binding do Alpine** (`:class="{...}"`): `.active`, `.open`,
  `.drawer--open`, `.is-invalid`, `.toast--err`. O nome é contrato mesmo sem aparecer no HTML
  estático.
- **`.htmx-request` nunca aparece em `class=`** — é injetada em runtime pelo HTMX. As duas
  regras (`.btn-spin` e `.q-btn`) servem **20 templates**. Se sumirem, toda ação HTMX perde o
  "carregando" e fica clicável em duplicidade. Regressão silenciosa clássica.

### Nomes genéricos reescopados — cuidado redobrado

`.val` `.lbl` `.num` `.id` `.name` `.meta` `.l` `.u` `.v` `.n` `.res` `.rev` `.delta` são
reaproveitados por componentes **não relacionados**, cada um reescopado por seletor descendente
(`.stat .val`, `.price-line .val`, `.param-grid .val`…) com tamanho e peso diferentes. Mudar
uma dessas globalmente atinge vários componentes de uma vez.

### Acessibilidade que já existe e não pode regredir

1. `:focus-visible` cobrindo `a`, `button`, `.q-btn`, `[tabindex]`, `[role="tab"]`,
   `[role="button"]`, mais `.eap-row:focus-visible`.
2. `.skip-link` — o par classe + `id="conteudo"` (em `base.html:50`) é o contrato; mexer em um
   sem o outro quebra o salto.
3. Foco dedicado em input (genérico e o refinado do login).
4. **`@media (pointer: coarse)` com alvo mínimo de 44 px** em `.q-btn`, rail, `.g-tab` e links
   de tabela. É WCAG 2.5.5/2.5.8 implementado por *media feature*, não por largura — some sem
   o desktop mudar de aparência.
5. `[x-cloak]{display:none!important}` — sem ele, flash de componente Alpine cru.

**Lacuna atual:** não existe `prefers-reduced-motion`, e o `@keyframes spin` não é guardado.
Aproveitar a reescrita para corrigir.

### Órfãs — pode descartar

`.approval-banner--revoked` · `.async-progress` (widget inteiro) · `.g3-minimap .progress` e
subárvore · `.comp-status--*` · `.login-wrap .errors` · `.q-badge--neutral`.

### Fantasmas — usadas em template, nunca definidas

`.q-input` `.g-input` `.q-modal*` `.approval-state*` `.login-card` `.g-card` `.notice`
`.pricing-basis-badge` `.impact-preview` `.drawer-origem-chip` e outras vivem só de `style=`
inline. **Não definir nenhuma com semântica que colida** — há um `.g-input` fantasma que é
campo de texto em 4 templates.

### Mudanças deliberadas (não são preservação — declarar no PR)

Três casos onde "consertar" muda o visual. Faço, e digo que fiz:

- **`.col-8`** existe em dois templates mas nunca foi definida — hoje cai no auto-placement e
  ocupa **1 coluna, não 8**. Definir corrige um layout que está errado desde sempre.
- **`--shadow-card`** é referenciada em `proposals/_history_and_email.html:40` e não existe:
  aquele modal hoje é chapado. Passa a ter sombra.
- **`.is-disabled`** (data sheet, via Alpine) é hoje um **no-op visual** — o campo não muda de
  aparência quando desabilitado. Passa a mudar.

---

## 7. Componentes que absorvem o estilo inline

O levantamento achou **149 ocorrências de `style=` com cor em 39 templates**. Não dá para
trocar a pele e deixar isso para trás: cada um vira um órfão com a cor velha. A saída não é
utilitário de cor — é **componente semântico**, para o template dizer *o que a coisa é*, não
*de que cor ela é*.

| Classe | Substitui hoje |
|---|---|
| `.q-pill` + `--ok` `--warn` `--bad` `--hot` `--neutral` | `.approval-state--*` inline, badges de `audit/inbox.html`, pílula de proveniência de preço |
| `.g-note--warn` / `.g-note--block` | ternários de `mode` em `_compose_result.html`, blocos de aviso do data sheet |
| `.g-err` | os `color:var(--g-red)` espalhados por erro de formulário |
| `.g-num` | valor monetário hoje pintado de laranja (`data_sheet`, `_compose_result`) |
| `.g-code` | `codigo_item` / letra TEMA hoje em laranja |

**Onde o laranja perde o emprego.** Hoje `--g-orange` é cor de link (`a` global), de foco, de
rótulo de revisão, de código de item, da barra de `.g-section-head` e de preço. Na Prancha
tudo isso vira `--p-bp` (azul) ou tinta neutra.

**E o laranja não herda os avisos de engenharia.** Uma versão anterior desta seção dizia que
ele "fica onde já era aviso de verdade" — isso contradizia a regra da §2 e estava errado.
Aviso de engenharia (*geometria inviável*, *corte fora de TEMA*) é **outra coisa** que risco de
margem; se os dois usarem `--p-hot`, o sinal dilui e o produto perde o instrumento. Bloco de
aviso usa `--p-warn` (âmbar); bloco impeditivo usa `--p-bad`.

**`--p-hot` tem exatamente dois empregos, e nenhum a mais:** valor de origem manual e selo
divergente. Que `.q-pill--warn` e `.g-note--warn` dividam o âmbar é o esperado — mesmo
significado em componentes diferentes é precisamente o que "cor semântica" quer dizer.

Caso que exige decisão explícita e **não** é automático: a pílula **"Pendente"** de aprovação
(`detail.html:245`) é laranja hoje. Isso é *estado de fluxo*, não risco de margem → vai para
`--p-warn` (âmbar), não para `--p-hot`.

---

## 7. Rede de segurança

Não há teste de UI no repo. Antes de mergear: screenshot antes/depois das telas críticas
(data sheet, detalhe/EAP, lista, login) pelo harness da sprint.
