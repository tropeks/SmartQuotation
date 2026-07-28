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

**Todos os campos já existem** em `quotation.inputs` e nos relacionamentos — é composição, não
dado novo. Micro-rótulo em Condensed caixa alta; valor em Mono (ou Sans quando for texto
corrido, ex. nome do cliente).

### 5.2 Marca de proveniência

Quatro origens, distinguíveis por **forma além de cor** — daltonismo não pode apagar a
diferença entre "o motor calculou" e "alguém digitou".

| Origem | Marca | Token |
|---|---|---|
| Motor de custeio | círculo cheio | `--p-bp` |
| Catálogo / preço vigente | círculo vazado | `--p-ink-3` |
| **Ajuste manual** | **losango cheio** | **`--p-hot`** |
| Importado | quadrado vazado | `--p-bp` |

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

**Fora de escopo nesta sprint:** a proposta em PDF/DOCX tem estilo próprio. Se a identidade
nova for pra valer, o documento que chega ao cliente devia falar a mesma língua — mas o
WeasyPrint tem regras próprias e isso é outra sprint.

---

## 7. Rede de segurança

Não há teste de UI no repo. Antes de mergear: screenshot antes/depois das telas críticas
(data sheet, detalhe/EAP, lista, login) pelo harness da sprint.
