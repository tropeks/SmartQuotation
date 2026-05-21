# UX_SPEC.md — SmartQuotation
> **Versão:** 2.0 | **Referência:** PROJECT_BRIEF.md, DATA_MODEL.md, API_SPEC.md, EPICS.md
> **Stack front-end:** Django Templates + HTMX + Alpine.js + Tailwind CSS (com tokens G customizados)
> **Linguagem visual:** **G · Refined Bauhaus** (ver §3) | **Padrão arquitetural:** **Command Center** (ver §3.5)
> **Changelog v2.0:**
> - Substituído design system genérico (Inter + paleta azul-âmbar) pelo **G · Refined Bauhaus** (Archivo + paleta cru/preto/laranja/amarelo).
> - Padrão arquitetural canônico para telas de detalhe densas: **Command Center** (coluna única scrollável + minimap navegável).
> - COT-03 reescrita em padrão Command Center (era tabs horizontais).
> - Componentes-base reescritos para o novo DNA visual (StatusPill, QHeader, ApprovalBanner, StatRow, CompCard, ParamGrid, Minimap).

---

## 1. Design Principles

1. **Termos do domínio, sempre.** A interface usa a linguagem da caldeiraria: "Vaso de Pressão", "Tampo Elíptico", "MAWP", "Sobremetal", "Feixe Tubular". Nunca abstrações genéricas como "Item", "Produto" ou "Configuração".

2. **Zero ambiguidade em dados críticos.** Espessuras calculadas, pressões, temperaturas e resultados de cálculo normativo devem exibir unidade, norma de referência e status de aprovação em toda tela onde aparecem. Um engenheiro não pode ter dúvida sobre o que está vendo.

3. **Alta densidade, leitura eficiente.** O sistema é de uso profissional interno — não consumer. Tabelas com 8–12 colunas são esperadas e bem-vindas. Formulários usam grids de 2–4 colunas, seções com cabeçalho preto sólido e labels posicionados acima dos campos.

4. **Fluxo linear explícito, status sempre visível.** A cotação tem um workflow claro (Rascunho → Em Revisão → Aprovada → Ganha/Perdida). O status atual e as ações disponíveis a partir dele devem estar visíveis sem scroll em qualquer tela de cotação.

5. **Feedback imediato para ações assíncronas.** Cálculo ASME e geração de PDF são tarefas longas. A tela deve mostrar progresso em tempo real com mensagens descritivas do que está acontecendo, nunca um spinner genérico.

6. **Identidade visual industrial, não corporativa.** O SmartQuotation é uma ferramenta de engenharia, não um SaaS de gestão. A UI deve evocar **placas de equipamento industrial, prontuários NR-13, painéis de operação** — não dashboards genéricos. Geometria reta (sem cantos arredondados), tipografia condensada e uppercase, paleta blocada com personalidade. Ver §3 para o design system completo.

7. **Visão holística sobre tabs ocultos.** Em telas-hub (COT-03, dashboards), prefira **rolagem com minimap navegável** a abas horizontais que escondem contexto. O usuário deve ver o estado completo de uma cotação numa olhada — equipamentos, BOM, preço, aprovação técnica e proposta — sem trocar de tela. Ver §3.5 para o padrão Command Center.

---

## 2. Personas

### 2.1 Carlos — Orçamentista
**Cargo real:** Assistente de Orçamentos | **Role:** `orçamentista`
**Objetivo principal:** Criar cotações técnico-comerciais completas rapidamente, sem erros.
**Frustrações atuais:** Planilhas Excel que quebram ao copiar. Preço de material desatualizado. Ter que esperar o engenheiro para saber o peso do equipamento.
**Telas mais usadas:** COT-01, COT-02, COT-03, EQP-01, EQP-02, CST-01, PROP-01
**Contexto de uso:** Desktop, monitores duplos, alta frequência (4–8 cotações/dia).

### 2.2 Eng. Rodrigo — Engenheiro
**Cargo real:** Engenheiro Mecânico (CREA-SP) | **Role:** `engenheiro`
**Objetivo principal:** Validar e assinar cálculos normativos com confiança técnica.
**Frustrações atuais:** Recalcular manualmente o que o sistema já deveria calcular. Não ter rastreabilidade de quem aprovou o quê.
**Telas mais usadas:** EQP-01 a EQP-05, APR-01 a APR-04, MAT-01 a MAT-04
**Contexto de uso:** Desktop, uma cotação por vez com análise profunda.

### 2.3 Fernanda — Gestora Comercial
**Cargo real:** Gerente Comercial | **Role:** `gestor_comercial`
**Objetivo principal:** Garantir que as cotações saiam com margem adequada e dentro do prazo.
**Frustrações atuais:** Não saber qual cotação está travada onde. Descobrir a margem de uma proposta só depois que saiu.
**Telas mais usadas:** DASH-01, DASH-02, COT-01, CST-03, CST-04, COT-05
**Contexto de uso:** Desktop e tablet, visão gerencial, múltiplas cotações simultâneas.

### 2.4 Admin — Administrador do Tenant
**Cargo real:** Coordenador de TI / Dono | **Role:** `admin`
**Objetivo principal:** Manter o sistema configurado, os usuários ativos e os dados mestre corretos.
**Telas mais usadas:** CFG-01 a CFG-04, AUD-01 a AUD-03, MAT-01 a MAT-05
**Contexto de uso:** Desktop, uso esporádico mas crítico.

---

## 3. Design System · G · Refined Bauhaus

> **Conceito:** geometria assertiva e cor blocada com personalidade industrial (DNA Bauhaus), refinados com polish contemporâneo para uso prolongado (8h/dia). Inspiração visual: placas de equipamento industrial, prontuários NR-13, posters Bauhaus 1925, design system Vercel/Linear aplicado a contexto técnico.
> **Referências externas:** Caterpillar moderno, ABB digital, Vercel docs, Linear marketing.

### 3.1 Tokens de Cor

```css
:root {
  /* ============================================================
     PALETA G · REFINED BAUHAUS
     ============================================================ */

  /* Neutros — base da tela */
  --g-paper:      #f4f1ea;   /* papel-cru — page background */
  --g-paper-2:    #fafaf2;   /* papel claro — hover de linha, fundo de seção */
  --g-white:      #ffffff;   /* containers, cards, tabela */
  --g-black:      #16151a;   /* texto, headers, CTAs, sidebar dupla */

  /* Acentos — identidade visual */
  --g-orange:     #d94e1f;   /* laranja-segurança — IDs, faixa de stat, primary action accent */
  --g-yellow:     #f5c542;   /* amarelo — texto sobre preto, marca, badge "Ganha" */

  /* Semânticos */
  --g-green:      #2d6a3e;   /* verde — status approved/won, deltas positivos */
  --g-red:        #a23a2f;   /* vermelho — status lost, deltas negativos, alertas */
  --g-blue:       #2950b0;   /* azul — status sent, componente importado */
  --g-amber:      #b8851a;   /* âmbar — status in_review, warning */

  /* Cinzas e bordas */
  --g-gray-1:     #888278;   /* texto secundário, eyebrows, labels desativados */
  --g-gray-2:     #e3dfd2;   /* bege-borda — divisores estruturais */
  --g-gray-3:     #c8c2b2;   /* bege-claro — separadores leves */

  /* Backgrounds semânticos (alpha 0.08) */
  --g-bg-review:    #fff8e6;
  --g-bg-approved:  #eaf3ea;
  --g-bg-sent:      #e8edf8;
  --g-bg-lost:      #faeae8;
}
```

**Regras de uso da cor:**

| Cor | Quando usar | Quando NÃO usar |
|---|---|---|
| `--g-black` | Sidebar, headers de tabela, CTAs primários, texto principal | Fundo de tela (causa fadiga) |
| `--g-orange` | IDs (COT-2025-038), faixa de stat-card, primary action accent (chevron), título de seção (faixa de 3px), borda lateral de "tenant ativo" | Backgrounds amplos, texto longo |
| `--g-yellow` | Texto sobre preto, marca, badge "Ganha" (bolinha sobre verde), texto sobre header de tabela | Sobre fundos claros (contraste ruim) |
| `--g-paper` | Page background, área de scroll | Containers, cards (use `--g-white`) |

### 3.2 Tipografia

```css
:root {
  --font-display: 'Archivo', sans-serif;            /* títulos, UI, botões */
  --font-mono:    'JetBrains Mono', monospace;      /* números, IDs, códigos, eyebrows */

  /* Escala */
  --text-xs:    0.625rem;   /* 10px  — eyebrows, captions monospace */
  --text-sm:    0.75rem;    /* 12px  — labels de campo, status pills */
  --text-base:  0.8125rem;  /* 13px  — texto de tabela, corpo de formulário */
  --text-md:    0.875rem;   /* 14px  — texto padrão */
  --text-lg:    1.0rem;     /* 16px  — títulos de seção (uppercase) */
  --text-xl:    1.375rem;   /* 22px  — títulos de equipamento */
  --text-2xl:   1.75rem;    /* 28px  — número da cotação no header */
  --text-3xl:   2.0rem;     /* 32px  — display de stat-card */

  /* Pesos Archivo */
  --w-regular:   400;
  --w-medium:    500;
  --w-semibold:  600;
  --w-bold:      700;
  --w-black:     800;       /* títulos display, números grandes, marca */

  /* Letter-spacing — característico do G */
  --ls-display:  -0.025em;  /* títulos em Archivo Black */
  --ls-body:     -0.005em;  /* texto Archivo medium */
  --ls-eyebrow:  0.14em;    /* JetBrains Mono uppercase */
  --ls-uppercase: 0.10em;   /* botões, headers de tabela */
}
```

**Regras tipográficas:**

- **Títulos display** (números de cotação, títulos de equipamento): `Archivo 800 uppercase letter-spacing: -0.025em`. Nunca italic.
- **Botões e ações**: `Archivo 700 uppercase letter-spacing: 0.06–0.10em`.
- **Eyebrows** (rótulos acima de títulos, breadcrumbs técnicos): `JetBrains Mono regular/medium uppercase letter-spacing: 0.12–0.16em`.
- **Números** (preços, espessuras, MAWP, pesos, percentuais, IDs): SEMPRE `JetBrains Mono medium/semibold` com `font-feature-settings: 'tnum'` (números tabulares). Nunca italic.
- **Texto de tabela**: `Archivo 500–600` em 12–13px, sem italic.
- **Não usar serif em nenhum lugar** — proibido Fraunces, Instrument Serif, etc. (lição da rodada anterior: serif passou "cara de jornal").

### 3.3 Espaçamento, Grid e Geometria

```css
:root {
  /* Espaçamento — múltiplos de 2px (não 4px como Tailwind default) */
  --space-1: 2px;
  --space-2: 4px;
  --space-3: 6px;
  --space-4: 8px;
  --space-5: 10px;
  --space-6: 12px;
  --space-7: 14px;
  --space-8: 16px;
  --space-10: 20px;
  --space-12: 24px;
  --space-16: 32px;

  /* Bordas — sempre retas, sem radius */
  --border-thin:    1px solid var(--g-gray-2);    /* divisores leves */
  --border-medium:  1px solid var(--g-gray-1);    /* divisores estruturais */
  --border-strong:  1.5px solid var(--g-black);   /* containers principais, status pills */
  --border-accent:  3px solid var(--g-orange);    /* faixas de identificação no topo de cards */

  /* CRÍTICO: cantos sempre retos */
  --radius: 0;
  /* Nenhum componente usa border-radius. Exceção única: bolinhas decorativas (5–8px) podem ser circulares. */
}
```

**Grid de formulário:** 12 colunas (mantido). Campos curtos (UF, CEP): col-span-2. Médios (CNPJ, pressão): col-span-3. Longos (nome, descrição): col-span-6 a 12.

**Regras de geometria:**
- **Zero `border-radius`** em containers, cards, tabelas, botões, inputs. Tudo reto.
- **Bordas de 1.5px** quando estruturais (container principal, status pill, seção); 1px quando divisórias.
- **Sem sombras suaves** (`box-shadow` proibido em containers). Profundidade vem de **bordas pretas sólidas** + **faixas verticais coloridas** (3–4px) no topo/lateral.
- **Sem gradientes** (nem em backgrounds, nem em botões).

### 3.4 Componentes Base

#### StatusPill
Substituto do antigo StatusBadge. Pill industrial com borda 1.5px + bolinha à esquerda + uppercase Archivo 700.

```html
<span class="q-status q-status--{status}">{label}</span>
```

| Status (backend) | Modificador CSS | Label exibido | Visual |
|---|---|---|---|
| `draft` | `--draft` | "Rascunho" | borda cinza + bolinha cinza |
| `in_review` | `--review` | "Em Revisão" | borda âmbar + bg `#fff8e6` + bolinha âmbar |
| `pending_approval` | `--review` | "Aguard. Aprovação" | mesma família do review |
| `approved` | `--approved` | "Aprovada" | borda verde + bg `#eaf3ea` + bolinha verde |
| `sent_to_customer` | `--sent` | "Enviada" | borda azul + bg `#e8edf8` + bolinha azul |
| `won` | `--won` | "Ganha" | **fundo verde sólido + bolinha amarela** (recompensa visual) |
| `lost` | `--lost` | "Perdida" | borda vermelha + bg `#faeae8` |
| `cancelled` | `--draft` | "Cancelada" | mesmo do draft |

```css
.q-status {
  display: inline-flex; align-items: center; gap: 6px;
  padding: 5px 12px;
  font-family: var(--font-display);
  font-weight: var(--w-bold); font-size: 11px;
  letter-spacing: var(--ls-uppercase); text-transform: uppercase;
  border: var(--border-strong);
  color: currentColor;   /* cor é definida pelo modificador */
}
.q-status::before {
  content: ''; width: 6px; height: 6px; background: currentColor;
}
.q-status--won {
  color: var(--g-paper); background: var(--g-green); border-color: var(--g-green);
}
.q-status--won::before { background: var(--g-yellow); }
```

**Variante compacta** para tabelas: `comp-status` — mesma família visual, padding `2px 8px`, fonte `10px`, bolinha `5px`. Usar em listagens densas.

#### QHeader (Header da Cotação)
Header fixo no topo de qualquer tela de cotação. Sempre visível, contém número + revisão + cliente + equipamento + status + ações contextuais.

```html
<header class="q-header">
  <div class="row1">
    <div class="id-block">
      <div class="breadcrumb-q">COT-03 · Detalhe</div>
      <div class="number">COT-2025-038 <span class="rev">Rev. A</span></div>
      <div class="subtitle">
        <b>Petrobras Refinaria REDUC</b>
        <span class="equip">V-101 · Vaso Separador · 10 bar · 150°C</span>
      </div>
    </div>
    <div class="status-block">
      <span class="q-status q-status--review">Em Revisão</span>
      <div class="meta">
        Criado em <b>05/01/2025</b> por <b>Romulo Souza</b><br>
        Válido até <b>05/02/2025</b> · 18 dias restantes
      </div>
    </div>
  </div>
  <nav class="q-actions">
    <button class="q-btn">Editar Dados</button>
    <button class="q-btn primary">Enviar para Revisão</button>
    <button class="q-btn">Criar Revisão</button>
    <button class="q-btn ghost" disabled>Gerar Proposta</button>
  </nav>
</header>
```

**Botões em q-actions são contextuais** — renderizar conforme `quotation.status` × `request.user.role`. Ver §3.6 para matriz de ações.

#### ApprovalBanner
Faixa horizontal **verde sólida com checkmark amarelo** exibida sempre que há aprovação técnica registrada. Inclui CREA + ART + hash do snapshot para compliance NR-13 visível.

```html
<div class="approval-banner">
  <div class="lt">
    <div class="check">✓</div>
    <div>
      Cálculo técnico aprovado
      <div class="meta">por <b>Eng. Rodrigo Oliveira · CREA-SP 5063412</b> · ART 28051·2025 · há 2h</div>
    </div>
  </div>
  <div class="rt">Snapshot hash · <b>a4f9·2c8b·71de</b></div>
</div>
```

**Variantes por estado:**
- `approval-banner` (verde) → aprovação ativa
- `approval-banner--pending` (âmbar) → aguardando aprovação técnica, mostra componentes pendentes
- `approval-banner--revoked` (vermelho) → aprovação revogada, mostra motivo e data

#### StatRow
Barra horizontal de 4 KPIs com **faixas verticais coloridas** (3px) no topo de cada stat para categorização. Usar no topo de telas-hub e no padrão Command Center.

```html
<div class="stat-row">
  <div class="stat">
    <div class="lbl">Equipamentos</div>
    <div class="val">02</div>
    <div class="delta">1 vaso + 1 trocador</div>
  </div>
  <div class="stat">
    <div class="lbl">Peso Total Estimado</div>
    <div class="val">4.847<span class="u">kg</span></div>
    <div class="delta up">Δ +1,2% vs PVElite</div>
  </div>
  <!-- ... -->
</div>
```

**Cor da faixa segue ordem categórica fixa:** laranja → amarelo → verde → preto (sequência canônica). Se houver mais de 4 stats, repete a sequência.

#### CompCard
Card de componente calculado/importado, com **faixa lateral colorida** (4px) indicando status.

```html
<div class="comp-card">
  <div class="row1">
    <div class="name">Casco Cilíndrico<small>UG-27 · ASME VIII Div.1 (2021)</small></div>
    <span class="comp-status comp-status--calc">Calc.</span>
  </div>
  <div class="results">
    <div class="res"><div class="l">Espessura</div><div class="v">12,3<span class="u">mm</span></div></div>
    <div class="res"><div class="l">MAWP</div><div class="v">11,5<span class="u">bar</span></div></div>
    <div class="res"><div class="l">Peso</div><div class="v">1.247<span class="u">kg</span></div></div>
  </div>
</div>
```

**Cor da faixa lateral:**
- Verde (`--g-green`) → componente calculado pelo sistema
- Âmbar (`--g-amber`) → cálculo pendente / parcial
- Azul (`--g-blue`) → importado de terceiro (PVElite, planilha)

Componentes importados ganham também badge `comp-status--imported` (azul) e a tela exibe `imported_document_hash` para auditoria.

#### ParamGrid (Data Sheet Compacto)
Grid 4-colunas para exibir parâmetros de projeto de um equipamento (orientação, pressão, temperatura, material etc.). Substitui formulários longos quando o objetivo é **ver** o data sheet, não editar.

```html
<div class="param-grid">
  <div class="param"><div class="lbl">Orientação</div><div class="val">Vertical</div></div>
  <div class="param"><div class="lbl">Pressão Projeto</div><div class="val">10,0<span class="u">bar</span></div></div>
  <div class="param"><div class="lbl">Temperatura</div><div class="val">150<span class="u">°C</span></div></div>
  <div class="param"><div class="lbl">Sobremetal</div><div class="val">3,0<span class="u">mm</span></div></div>
  <!-- ... -->
</div>
```

Para EDIÇÃO do data sheet, ver §FormSection (preservado da v1, agora com estilo G).

#### Minimap (Navegação Lateral do Command Center)
Sidebar direita de 220px que substitui as abas horizontais em telas-hub. Cada `§` corresponde a uma seção que estaria em uma aba; rolagem da página atualiza o item ativo (scroll-spy).

```html
<aside class="g3-minimap">
  <h4>Navegação</h4>
  <a href="#sec-dados-gerais">§1 · Dados Gerais <span class="n">✓</span></a>
  <a href="#sec-equipamentos" class="on">§2 · Equipamentos <span class="n">2</span></a>
  <a href="#sec-bom">§3 · BOM & Roteiro <span class="n">42</span></a>
  <a href="#sec-preco">§4 · Formação Preço <span class="n">R$</span></a>
  <a href="#sec-aprovacao">§5 · Aprov. Técnica <span class="n">✓</span></a>
  <a href="#sec-proposta" style="color: var(--g-gray-3);">§6 · Proposta <span class="n">⊘</span></a>

  <div class="div"></div>

  <div class="progress">
    <div class="lbl">Progresso Cotação</div>
    <div class="val">67<span style="color: var(--g-gray-1);">%</span></div>
    <div class="bar"></div>
    <div class="steps">4 / 6 etapas</div>
  </div>
</aside>
```

**Comportamento:**
- Item ativo: borda esquerda laranja (`--g-orange`), texto laranja
- Item bloqueado (ex: proposta antes de aprovação): cinza claro com prefixo `⊘`
- Item concluído: badge `✓` à direita
- Badge numérico (count): tipo `2` para equipamentos, `42` para itens do BOM

#### AsyncProgressBar
Mantida da v1, com estilo G aplicado (faixa preta + bar laranja, sem radius).

```html
<div class="async-progress" hx-get="/api/v1/tasks/{id}/" hx-trigger="every 2s">
  <div class="progress-bar" style="width: 45%"></div>
  <span class="progress-label">Calculando espessura de casco (UG-27)... 45%</span>
</div>
```

```css
.async-progress { background: var(--g-paper); border: var(--border-strong); height: 8px; position: relative; }
.async-progress .progress-bar { background: var(--g-orange); height: 100%; }
```

#### DataTable (G)
Tabela padrão. Header **preto sólido** com texto creme, sem zebra (linhas alternadas removidas — hover em `--g-paper-2` é suficiente), bordas finas entre linhas.

```css
.g-table thead th {
  background: var(--g-black); color: var(--g-paper);
  font-family: var(--font-display); font-weight: var(--w-bold);
  font-size: 10px; letter-spacing: var(--ls-uppercase); text-transform: uppercase;
  padding: 8px 10px; text-align: left;
}
.g-table thead th.num { text-align: right; }
.g-table tbody td { padding: 9px 10px; border-bottom: var(--border-thin); }
.g-table tbody tr:hover td { background: var(--g-paper-2); }
.g-table tbody td.num { text-align: right; font-family: var(--font-mono); font-feature-settings: 'tnum'; }
.g-table tbody td.id { font-family: var(--font-mono); font-weight: var(--w-semibold); color: var(--g-orange); font-size: 11px; }
```

Funcionalidades: ordenação por coluna, filtro de busca inline, paginação, seleção de linha para ações em lote. **Sem zebra** (linhas alternadas removidas — fadiga visual em sessões longas).

#### Section (substitui FormSection colapsável)
Seção de conteúdo com **cabeçalho preto e faixa laranja** no título. Não colapsa por padrão (causa fadiga em telas-hub que mostram tudo de uma vez). Para formulários longos, manter `<details>` colapsável como exceção.

```html
<section class="g-section">
  <header class="g-section-head">
    <h3>§2 · Equipamentos · 02</h3>
    <div class="actions">
      <button class="btn-mini">+ Vaso</button>
      <button class="btn-mini">+ Trocador</button>
      <button class="btn-mini primary">Recalcular Todos</button>
    </div>
  </header>
  <div class="g-section-body">
    <!-- conteúdo -->
  </div>
</section>
```

```css
.g-section { background: var(--g-white); border: var(--border-thin); margin-bottom: 16px; }
.g-section-head { border-bottom: var(--border-strong); padding: 12px 18px;
  display: flex; align-items: center; justify-content: space-between; gap: 16px; }
.g-section-head h3 { font-weight: var(--w-bold); font-size: 13px;
  letter-spacing: 0.10em; text-transform: uppercase; }
.g-section-head h3::before {
  content: ''; display: inline-block; width: 16px; height: 3px;
  background: var(--g-orange); vertical-align: middle; margin-right: 8px;
}
```

#### AuditTrailEntry
Mantida da v1, agora com estilo mono nos timestamps e valores em laranja para destaque do que mudou.

```
[Carlos Oliveira] alterou [Pressão de Projeto]
  12:34:01 — 05/01/2025
  Antes: 8,0 bar
  Depois: 10,0 bar  ← em laranja (var(--g-orange))
```

### 3.5 Padrão Arquitetural · Command Center

**Quando aplicar:** toda tela-hub que combina múltiplas dimensões de uma mesma entidade. Casos canônicos: **COT-03** (cotação completa), **DASH-01** (dashboard principal do tenant), **EQP-05** (histórico de snapshots de equipamento), futuras telas de **ordem de fabricação** (H2).

**Princípio:** o usuário vê tudo de uma vez. Em vez de abas horizontais que escondem contexto cruzado (BOM em uma aba, preço em outra, aprovação em outra), o Command Center apresenta **uma coluna scrollável única** com seções verticais (`§1` a `§N`), navegáveis por **minimap lateral à direita**.

**Layout canônico (3 colunas):**

```
┌─────┬──────────┬─────────────────────────────┬────────────────┐
│     │          │                             │                │
│ R   │ Sidebar  │  Q-Header (sticky)          │                │
│ A   │ módulos  │  ─────────────────────────  │                │
│ I   │          │  §1 · Dados Gerais          │   Minimap      │
│ L   │ (cotações│  §2 · Equipamentos          │  (sticky)      │
│     │  vista, │  §3 · BOM & Roteiro          │                │
│ 60px│ esta cot.│  §4 · Formação de Preço     │   220px        │
│     │  ativa)  │  §5 · Aprovação Técnica     │                │
│     │ 200px    │  §6 · Proposta              │                │
│     │          │                             │                │
└─────┴──────────┴─────────────────────────────┴────────────────┘
```

**Comportamentos obrigatórios:**

1. **Q-Header é sticky** no topo do main — sempre visível enquanto o usuário rola entre seções.
2. **Minimap é sticky** no lado direito — item ativo segue scroll-spy (Alpine.js + IntersectionObserver).
3. **ApprovalBanner aparece como faixa horizontal logo abaixo do Q-Header** quando há aprovação técnica registrada.
4. **Cada seção `§N` tem `id="sec-nome"`** para navegação por anchor.
5. **Indicador de progresso no minimap** ("Progresso Cotação: 67%") calculado em função do número de etapas concluídas (Dados Gerais ok, Equipamentos calculados, BOM gerado, Preço formado, Aprovação técnica, Proposta enviada).
6. **Seções bloqueadas** (ex: Proposta antes de Aprovação) aparecem no minimap em cinza claro com `⊘` e a seção em si tem call-to-action ("Conclua a Aprovação Técnica para liberar").

**Quando NÃO usar Command Center:**
- Telas de lista (COT-01, MAT-01, CLI-01) → continuar com tabela paginada + filtros.
- Telas de formulário linear (COT-02 Nova Cotação, EQP-01 Data Sheet em edição) → usar `<form>` tradicional.
- Modais (APR-02 Assinar Cálculo, COT-05 Marcar como Ganha) → usar overlay simples.

### 3.6 Matriz de Ações por Status × Role

Botões em `q-actions` (e ações disponíveis em qualquer tela de cotação) renderizam condicionalmente. Tabela canônica:

| Status atual | Orçamentista | Engenheiro | Gestor Comercial | Admin |
|---|---|---|---|---|
| `draft` | Editar · + Equip · **Enviar p/ Revisão** | Editar · + Equip | Editar · + Equip | tudo |
| `in_review` | (ver) | **Aprovar Técnico** (assinar) · Revogar Aprov. | **Aprovar p/ Envio** · Reabrir | tudo |
| `approved` | (ver) | Revogar Aprov. | **Gerar Proposta** · Marcar Enviada · Editar Preço | tudo |
| `sent_to_customer` | (ver) | (ver) | **Marcar Ganha** · **Marcar Perdida** | tudo |
| `won` / `lost` | (ver) · Revisar | (ver) · Revisar | Revisar | Revisar · Reabrir |

**Botões sempre presentes** (qualquer status, qualquer role): `Criar Revisão`, `Ver Audit Trail`, `Export CSV`.

**Renderização condicional via Django template:**
```django
{% if quotation.status == 'draft' and user_role in 'orçamentista,engenheiro,admin' %}
  <button class="q-btn primary">Enviar para Revisão</button>
{% endif %}
```

---

## 4. Mapa de Navegação

```
┌─────────────────────────────────────────────────────────────────────┐
│  SIDEBAR FIXA (colapsável)                                          │
│                                                                     │
│  [Logo SmartQuotation]          [Tenant: Caldeiraria ABC]           │
│                                                                     │
│  ▶ Dashboard            (Gestor, Admin)                             │
│  ▶ Cotações             (Todos)                                     │
│      ├─ Lista de Cotações                                           │
│      ├─ Nova Cotação                                                │
│      └─ [cotação selecionada]                                       │
│           ├─ Dados Gerais                                           │
│           ├─ Equipamentos                                           │
│           │   ├─ Vaso de Pressão (data sheet)                       │
│           │   │   └─ Componentes + Resultado de Cálculo             │
│           │   └─ Trocador de Calor (data sheet)                     │
│           │       └─ Componentes + Resultado de Cálculo             │
│           ├─ BOM e Roteiro                                          │
│           ├─ Formação de Preço                                      │
│           ├─ Aprovação Técnica                                      │
│           └─ Proposta                                               │
│  ▶ Clientes             (Orçamentista, Gestor, Admin)               │
│  ▶ Materiais            (Engenheiro, Admin)                         │
│  ▶ Auditoria            (Admin, Gestor)                             │
│  ▶ Configurações        (Admin)                                     │
│      ├─ Dados do Tenant                                             │
│      ├─ Usuários e RBAC                                             │
│      ├─ Templates de Proposta                                       │
│      └─ Operações e Índices (Rates)                                 │
│                                                                     │
│  ─────────────────────────────────────────────────────              │
│  [Avatar] Carlos Oliveira — Orçamentista                            │
│  [Meu Perfil] [MFA] [Sair]                                         │
└─────────────────────────────────────────────────────────────────────┘
```

---

## 5. Fluxos Principais

### Fluxo 1 — Criar Cotação Completa (Orçamentista)
```
COT-01 Lista de Cotações
  → [+ Nova Cotação] → COT-02 Nova Cotação (cliente, título, validade)
  → [Salvar] → COT-03 Detalhe da Cotação (status: Rascunho)
  → [+ Adicionar Equipamento] → EQP-01 ou EQP-02 (data sheet)
  → [Preencher data sheet] → [Calcular] → EQP-03 Resultado (AsyncProgressBar)
  → [Resultado exibido] → EQP-04 (opcional: importar cálculo terceiro)
  → COT-03 → [Ver BOM] → CST-01 BOM
  → [Gerar Roteiro] → CST-02 Roteiro de Fabricação
  → [Enviar para Revisão] → COT-03 (status: Em Revisão)
```

### Fluxo 2 — Aprovar Tecnicamente (Engenheiro)
```
APR-01 Painel do Engenheiro (lista de cotações aguardando aprovação)
  → [Cotação selecionada] → EQP-05 Histórico de Snapshots
  → [Revisar snapshot] → APR-04 (opcional: validar contra PVElite)
  → [Assinar Cálculo] → APR-02 Modal de Assinatura (disclaimer ART/CREA)
  → [Confirmar com CREA + ART] → APR-03 Histórico de Aprovações (status: Aprovado)
  → COT-03 (ApprovalBanner verde)
```

### Fluxo 3 — Formas Preço e Gera Proposta (Gestor Comercial)
```
COT-01 → [Cotação aprovada] → COT-03
  → [Formação de Preço] → CST-03 (overhead %, margem %, impostos)
  → [Calcular Preço] → CST-04 Breakdown completo
  → [Aprovar Cotação] → COT-05 (status: Aprovada)
  → [Gerar Proposta] → PROP-01 (selecionar template, formato PDF/DOCX)
  → PROP-02 (AsyncProgressBar — geração assíncrona)
  → [Proposta pronta] → PROP-03 (download DOCX / PDF)
```

### Fluxo 4 — Marcar Cotação como Ganha/Perdida
```
COT-03 (status: Enviada ao Cliente)
  → [Marcar como Ganha] → Modal de confirmação → COT-03 (status: Ganha ✓)
  → [Marcar como Perdida] → Modal com campo "Motivo da perda" → COT-03 (status: Perdida)
  → DASH-01 atualiza KPIs automaticamente
```

---

## 6. Inventário de Telas

| ID | Nome | Módulo | Personas | Sprint | Telas relacionadas |
|---|---|---|---|---|---|
| AUTH-01 | Login | Auth | Todos | 0 | AUTH-02, AUTH-03, AUTH-04 |
| AUTH-02 | Setup MFA | Auth | Todos | 1 | AUTH-01 |
| AUTH-03 | Verificação TOTP | Auth | Todos | 1 | AUTH-01 |
| AUTH-04 | Recuperação de senha | Auth | Todos | 0 | AUTH-01 |
| DASH-01 | Dashboard principal | Dashboard | Gestor, Admin | 5 | COT-01, DASH-02 |
| DASH-02 | KPIs — gráfico de cotações | Dashboard | Gestor, Admin | 5 | DASH-01 |
| MAT-01 | Lista de materiais | Materiais | Engenheiro, Admin | 1 | MAT-02, MAT-03 |
| MAT-02 | Detalhe do material | Materiais | Engenheiro, Admin | 1 | MAT-04, MAT-05 |
| MAT-03 | Formulário de material | Materiais | Engenheiro, Admin | 1 | MAT-01 |
| MAT-04 | Tabela de tensões admissíveis | Materiais | Engenheiro | 1 | MAT-02 |
| MAT-05 | Histórico de preços | Materiais | Engenheiro, Admin | 1 | MAT-02 |
| CLI-01 | Lista de clientes | Clientes | Orçamentista, Gestor, Admin | 1 | CLI-02, CLI-03 |
| CLI-02 | Detalhe do cliente | Clientes | Orçamentista, Gestor, Admin | 1 | COT-01 |
| CLI-03 | Formulário de cliente | Clientes | Orçamentista, Gestor, Admin | 1 | CLI-01 |
| COT-01 | Lista de cotações | Cotações | Todos | 2 | COT-02, COT-03 |
| COT-02 | Nova cotação | Cotações | Orçamentista, Engenheiro, Admin | 2 | CLI-01 |
| COT-03 | Detalhe da cotação | Cotações | Todos | 2 | EQP-01, EQP-02, CST-01 |
| COT-04 | Revisão de cotação | Cotações | Orçamentista, Engenheiro, Admin | 3 | COT-03 |
| COT-05 | Ações de status (modais) | Cotações | Gestor, Admin | 3 | COT-03 |
| EQP-01 | Data sheet — Vaso de Pressão | Equipamentos | Orçamentista, Engenheiro | 3 | EQP-03, EQP-04 |
| EQP-02 | Data sheet — Trocador de Calor | Equipamentos | Orçamentista, Engenheiro | 3 | EQP-03, EQP-04 |
| EQP-03 | Resultado de cálculo | Equipamentos | Orçamentista, Engenheiro | 3 | EQP-05, APR-01 |
| EQP-04 | Importar cálculo de terceiro | Equipamentos | Engenheiro, Admin | 3 | EQP-01 |
| EQP-05 | Histórico de snapshots | Equipamentos | Engenheiro, Admin | 4 | APR-04 |
| CST-01 | BOM — lista de materiais | Custo/Preço | Orçamentista, Engenheiro, Gestor | 4 | CST-02 |
| CST-02 | Roteiro de fabricação | Custo/Preço | Orçamentista, Engenheiro | 4 | CST-03 |
| CST-03 | Formação de preço | Custo/Preço | Gestor, Admin | 4 | CST-04 |
| CST-04 | Breakdown de custo | Custo/Preço | Gestor, Admin | 4 | PROP-01 |
| PROP-01 | Seleção de template | Proposta | Orçamentista, Gestor, Admin | 4 | PROP-02 |
| PROP-02 | Status de geração | Proposta | Orçamentista, Gestor, Admin | 4 | PROP-03 |
| PROP-03 | Download e histórico | Proposta | Todos | 4 | — |
| APR-01 | Painel do engenheiro | Aprovação | Engenheiro | 5 | APR-02, EQP-05 |
| APR-02 | Assinar cálculo (modal) | Aprovação | Engenheiro | 5 | APR-03 |
| APR-03 | Histórico de aprovações | Aprovação | Engenheiro, Admin | 5 | — |
| APR-04 | Validação PVElite | Aprovação | Engenheiro | 5 | EQP-05 |
| AUD-01 | AccessLog | Auditoria | Admin, Gestor | 5 | AUD-02, AUD-03 |
| AUD-02 | Histórico de entidade | Auditoria | Admin, Gestor | 5 | AUD-01 |
| AUD-03 | Export CSV | Auditoria | Admin | 5 | AUD-01 |
| CFG-01 | Config. do tenant | Configurações | Admin | 1 | — |
| CFG-02 | Usuários e RBAC | Configurações | Admin | 1 | — |
| CFG-03 | Templates de proposta | Configurações | Admin | 4 | PROP-01 |
| CFG-04 | Operações e índices | Configurações | Engenheiro, Admin | 1 | CST-02 |

---

## 7. Especificação por Tela

---

### AUTH-01 — Login
**Rota:** `/login/`
**Personas:** Todos
**Sprint:** 0
**Objetivo:** Autenticar o usuário com email e senha.

**Dados exibidos:** Logo SmartQuotation, campo email, campo senha, botão entrar.

**Ações disponíveis:**
- [Entrar] → POST /api/v1/auth/login → se 200 com requires_mfa=false: redireciona para DASH-01 ou COT-01; se 400 MFA_REQUIRED: redireciona para AUTH-03
- [Esqueci minha senha] → AUTH-04

**Estados da tela:**
- default: formulário limpo
- loading: botão "Entrando..." desabilitado, spinner inline
- error INVALID_CREDENTIALS: banner "E-mail ou senha incorretos" em vermelho
- error ACCOUNT_LOCKED: banner "Conta bloqueada até HH:MM. Tentativas excessivas."
- error MFA_REQUIRED: redirecionamento automático para AUTH-03

**Validações inline:**
- email: formato inválido → "Informe um e-mail válido"
- senha: vazia → "Informe sua senha"

**Notas para vibe-coding:**
- Rate limiting 5/min por IP — exibir mensagem amigável no 429
- Subdomínio do tenant já resolvido antes do login (middleware django-tenants)
- Não exibir nome do tenant no login — apenas o logo customizado do tenant (se cadastrado) ou o logo padrão do sistema

---

### AUTH-02 — Setup MFA
**Rota:** `/accounts/mfa/setup/`
**Personas:** Todos (obrigatório para admin e gestor_comercial)
**Sprint:** 1

**Objetivo:** Configurar TOTP pela primeira vez (QR code + verificação de código).

**Dados exibidos:** QR code (base64 img), chave secreta em texto (para apps sem câmera), campo de código de 6 dígitos, lista de 10 backup codes para download.

**Ações disponíveis:**
- [Verificar Código] → valida TOTP → se OK: MFA ativado, redireciona para perfil
- [Baixar Backup Codes] → download TXT
- [Cancelar] → retorna sem ativar (bloqueado para roles que exigem MFA)

**Estados:** default, loading (verificando), success (ativado), error (código inválido)

**Notas para vibe-coding:**
- QR code via `GET /api/v1/users/me/mfa/setup/`
- Backup codes exibidos uma única vez — alertar o usuário com modal de confirmação antes de fechar

---

### AUTH-03 — Verificação TOTP
**Rota:** `/login/mfa/`
**Personas:** Todos com MFA ativo
**Sprint:** 1

**Objetivo:** Segundo fator de autenticação.

**Dados exibidos:** Campo numérico de 6 dígitos (auto-focus), link "Usar backup code".

**Ações disponíveis:**
- [Verificar] → POST /api/v1/auth/login com totp_code preenchido
- [Usar backup code] → campo alternativo para código de recuperação

**Estados:** default, loading, error (código expirado ou inválido)

**Notas para vibe-coding:**
- Input type="number" com maxlength=6, sem seta de incremento (CSS: -webkit-appearance: none)
- Auto-submit ao digitar 6 dígitos (Alpine.js `@input`)

---

### AUTH-04 — Recuperação de senha
**Rota:** `/accounts/password/reset/`
**Personas:** Todos
**Sprint:** 0

**Objetivo:** Solicitar reset de senha via e-mail.

**Dados exibidos:** Campo e-mail, botão enviar.

**Estados:** default, success ("E-mail enviado — verifique sua caixa de entrada")

---

### DASH-01 — Dashboard Principal
**Rota:** `/dashboard/`
**Personas:** Gestor, Admin
**Sprint:** 5
**Objetivo:** Visão executiva da operação de cotações do tenant.

**Dados exibidos:**
- Cards de KPI (linha superior):
  - Cotações do mês: total / aprovadas / ganhas / perdidas
  - Taxa de conversão (ganhas / total finalizadas %)
  - Ticket médio das cotações ganhas (R$)
  - Margem média (%)
- Gráfico de barras: cotações por status nos últimos 90 dias
- Tabela "Cotações em Aberto" (COT-01 inline, 10 linhas): número, cliente, valor, status, dias em aberto
- Mini-lista "Aprovações Pendentes" (3 itens): cotação, engenheiro responsável

**Ações disponíveis:**
- Click em qualquer cotação → COT-03
- [Ver Todas as Cotações] → COT-01
- [Ver Auditoria] → AUD-01 (apenas admin)

**Estados:** loading (skeleton), empty (nenhuma cotação ainda → CTA "Criar primeira cotação"), default

**Notas para vibe-coding:**
- Gráfico em SVG inline (sem Chart.js no MVP — recharts ou SVG puro via HTMX)
- KPI cards atualizados via `hx-trigger="load, every 60s"`

---

### DASH-02 — KPIs e Gráfico
**Rota:** `/dashboard/kpis/` (componente HTMX embutido em DASH-01)
**Personas:** Gestor, Admin
**Sprint:** 5

Componente parcial do dashboard. Ver DASH-01.

---

### MAT-01 — Lista de Materiais
**Rota:** `/materiais/`
**Personas:** Engenheiro, Admin
**Sprint:** 1
**Objetivo:** Consultar e gerenciar o catálogo de materiais.

**Dados exibidos (tabela):**
Código | Nome | Norma | Categoria | σ_t (MPa) | S (MPa) | ρ (kg/m³) | T_max (°C) | Preço (R$/kg) | Ativo

**Filtros:**
- Busca: código/nome
- Norma: ASME / ASTM / NBR / EN
- Categoria (dropdown)
- Ativo: Sim / Não

**Ações disponíveis (por role):**
- Todos: [Detalhe] → MAT-02
- Engenheiro, Admin: [+ Novo Material] → MAT-03
- Admin: [Importar CSV]

**Estados:** default, loading, empty ("Nenhum material encontrado. Importe o catálogo padrão ASME.")

**Notas para vibe-coding:**
- Coluna "S (MPa)" exibe o valor à temperatura ambiente (20°C) — tooltip indica "clique para ver tabela completa"
- Preço exibe "–" se não houver preço vigente

---

### MAT-02 — Detalhe do Material
**Rota:** `/materiais/{id}/`
**Personas:** Engenheiro, Admin
**Sprint:** 1
**Objetivo:** Ver todas as propriedades de um material e suas tabelas de dados.

**Dados exibidos:**
- Header: Código, Nome, Norma, Categoria, P-Number ASME
- Seção "Propriedades Mecânicas": σ_t, σ_y, S (20°C), ρ, dureza HB, elongação %
- Seção "Limites de Temperatura": T_min, T_max
- Aba "Tensões Admissíveis por Temperatura" → MAT-04 (tabela inline)
- Aba "Histórico de Preços" → MAT-05

**Ações disponíveis:**
- [Editar] → MAT-03 (engenheiro, admin)
- [+ Novo Preço] → modal de cadastro de preço
- [Desativar] → modal de confirmação (admin)

---

### MAT-03 — Formulário de Material
**Rota:** `/materiais/novo/` | `/materiais/{id}/editar/`
**Personas:** Engenheiro, Admin
**Sprint:** 1

**Campos (FormSection):**

*Identificação:*
- Código (obrigatório, único) | Nome (obrigatório) | Norma | Categoria | P-Number | Material Group

*Propriedades Mecânicas:*
- σ_t MPa (obrigatório) | σ_y MPa (obrigatório) | S MPa | ρ kg/m³ (obrigatório)
- Dureza HB | Elongação % | Condutividade Térmica W/m·K

*Limites:*
- T_min °C | T_max °C | Índice de Usinabilidade %

*Configurações:*
- Ativo (toggle) | Notas (textarea)

**Validações inline:**
- Código: único → "Código já cadastrado"
- σ_t: > σ_y obrigatório → "Resistência à ruptura deve ser maior que o limite de escoamento"
- ρ: 1000–25000 kg/m³ → "Densidade fora do range esperado"

---

### MAT-04 — Tabela de Tensões Admissíveis
**Rota:** `/materiais/{id}/allowable-stress/`
**Personas:** Engenheiro
**Sprint:** 1
**Objetivo:** Consultar e editar os valores de S por temperatura conforme ASME.

**Dados exibidos (tabela editável):**
Temperatura (°C) | S (MPa) | Edição da Norma | Ação

**Ações:**
- [+ Adicionar Temperatura] → linha editável inline
- [Consultar por temperatura] → campo de busca com interpolação (`?temp_c=250`)
- Resultado de interpolação exibe: "S = 118,60 MPa a 250°C (interpolado entre 200°C e 300°C)"

---

### MAT-05 — Histórico de Preços
**Rota:** `/materiais/{id}/precos/`
**Personas:** Engenheiro, Admin
**Sprint:** 1

**Dados exibidos (tabela):**
Forma | Espessura (mm) | Preço R$/kg | Fornecedor | Válido de | Válido até | Origem | Cadastrado por

**Ações:**
- [+ Novo Preço] → modal com campos: forma, espessura min/max, preço, fornecedor, validade
- Linha com ícone "Vigente" em verde para o preço atual

---

### CLI-01 — Lista de Clientes
**Rota:** `/clientes/`
**Personas:** Orçamentista, Gestor, Admin
**Sprint:** 1

**Dados exibidos (tabela):**
Empresa | CNPJ | Contato | Email | Telefone | Cidade/UF | Cotações (N) | Ativo

**Filtros:** Busca texto, UF

**Ações:**
- [Detalhe] → CLI-02
- [+ Novo Cliente] → CLI-03
- Click na linha → CLI-02

---

### CLI-02 — Detalhe do Cliente
**Rota:** `/clientes/{id}/`
**Personas:** Orçamentista, Gestor, Admin
**Sprint:** 1

**Dados exibidos:**
- Header: Nome da empresa, CNPJ, status (Ativo/Inativo)
- Dados de contato: nome, email, telefone, endereço
- Tabela de cotações do cliente (inline, últimas 10): número, título, status, valor, data

**Ações:**
- [Editar] → CLI-03
- [Nova Cotação para este Cliente] → COT-02 com cliente pré-preenchido
- [Desativar] → modal confirmação (admin)

---

### CLI-03 — Formulário de Cliente
**Rota:** `/clientes/novo/` | `/clientes/{id}/editar/`
**Personas:** Orçamentista, Gestor, Admin
**Sprint:** 1

**Campos:**
- Razão Social (obrigatório) | CNPJ (máscara XX.XXX.XXX/XXXX-XX) | CPF
- Nome do Contato | Email | Telefone
- Endereço | Cidade | UF (select 2 chars) | CEP
- Notas (textarea) | Ativo (toggle)

**Validações inline:**
- CNPJ: dígitos verificadores → "CNPJ inválido"
- CNPJ duplicado → "CNPJ já cadastrado para outro cliente"
- Email: formato → "Informe um e-mail válido"

---

### COT-01 — Lista de Cotações
**Rota:** `/cotacoes/`
**Personas:** Todos
**Sprint:** 2
**Objetivo:** Consultar e gerenciar todas as cotações do tenant.

**Dados exibidos (tabela):**
Número | Revisão | Cliente | Título | Status | Valor Total R$ | Validade | Criado por | Data Criação | Ações

**Filtros:**
- Status (multi-select)
- Cliente (autocomplete)
- Período (data de/até)
- Busca (número, título, cliente)
- Ordenação: -created_at (padrão), valor, status

**Ações:**
- [+ Nova Cotação] → COT-02 (orçamentista, engenheiro, admin)
- [Detalhe] → COT-03
- [Duplicar] → confirma → nova cotação draft baseada nesta

**Notas para vibe-coding:**
- StatusBadge na coluna Status com cores semânticas
- Linha em itálico para cotações canceladas/perdidas
- Coluna "Revisão" exibe "Rev. B" para revision=1, "Rev. C" para revision=2, etc.

---

### COT-02 — Nova Cotação
**Rota:** `/cotacoes/nova/`
**Personas:** Orçamentista, Engenheiro, Admin
**Sprint:** 2

**Campos:**
- Cliente (autocomplete, obrigatório) — [+ Criar novo cliente] abre modal inline
- Título (obrigatório, max 500)
- Descrição (textarea)
- Válido até (date picker)
- Moeda (BRL padrão, somente H2)
- Prazo de entrega (semanas, inteiro)
- Condições de pagamento (textarea)
- Engenheiro responsável (dropdown de engenheiros ativos)

**Ações:**
- [Salvar e continuar] → COT-03
- [Cancelar] → COT-01

**Validações:**
- Cliente obrigatório → "Selecione ou crie um cliente"
- Título obrigatório → "Informe o título da cotação"

---

### COT-03 — Detalhe da Cotação
**Rota:** `/cotacoes/{id}/`
**Personas:** Todos (visualização); Orçamentista, Engenheiro, Admin (edição)
**Sprint:** 2
**Objetivo:** Hub central de uma cotação — dados gerais, equipamentos, custo e proposta.
**Padrão arquitetural:** **Command Center** (ver §3.5)
**Linguagem visual:** **G · Refined Bauhaus** (ver §3)

**Estrutura geral:**
```
┌──────┬──────────┬──────────────────────────────────┬─────────────────┐
│ RAIL │ SIDEBAR  │  Q-HEADER (sticky)               │                 │
│ 60px │ MÓDULO   │  ApprovalBanner (se houver)      │   MINIMAP       │
│      │ 200px    │  ────────────────────────────    │   (sticky)      │
│      │          │  §1 Dados Gerais                 │   220px         │
│      │ Cotações │  §2 Equipamentos                 │                 │
│      │ ativas + │  §3 BOM & Roteiro                │   §1 ✓          │
│      │ esta cot │  §4 Formação de Preço            │   §2 (2)        │
│      │          │  §5 Aprovação Técnica            │   §3 (42)       │
│      │          │  §6 Proposta                     │   §4 R$         │
│      │          │                                  │   §5 ✓          │
│      │          │                                  │   §6 ⊘          │
│      │          │                                  │  ───────────    │
│      │          │                                  │   Progresso 67% │
└──────┴──────────┴──────────────────────────────────┴─────────────────┘
```

#### Q-Header (sticky)

Componente `QHeader` (ver §3.4). Exibe sempre:
- Eyebrow: `COT-03 · Detalhe`
- Número: `COT-2025-038` + revisão (`Rev. A`) em laranja monospace
- Cliente em bold + equipamento principal em mono cinza
- StatusPill à direita (ver §3.4)
- Meta: criado por, validade restante
- `q-actions`: botões contextuais (ver matriz em §3.6)

#### ApprovalBanner (faixa horizontal)

Aparece logo abaixo do Q-Header quando `quotation.has_technical_approval()`. Verde sólido + check amarelo + texto creme com CREA + ART + hash do snapshot. Ver §3.4 para HTML.

Variantes:
- **Verde** (`approval-banner`) → aprovação ativa
- **Âmbar** (`approval-banner--pending`) → "Aguardando aprovação técnica — N componentes pendentes"
- **Vermelho** (`approval-banner--revoked`) → "Aprovação revogada em DD/MM/YYYY · motivo"

#### §1 · Dados Gerais

Seção (componente `Section` §3.4) com header `§1 · Dados Gerais`.
Conteúdo: `ParamGrid` 4-colunas com os campos da Quotation:

| Cliente | CNPJ | Cidade/UF | Prazo Entrega |
| Cond. Pagamento | Validade Proposta | Moeda | Incoterm |

Sub-bloco abaixo: **Histórico de Revisões** em `DataTable` compacta (número · revisão · criado em · criado por · status final).

Ações da seção: `[Editar]` (abre COT-02 em modo edição inline)

#### §2 · Equipamentos

Seção com header `§2 · Equipamentos · {{ count }}`. Conteúdo em três níveis:

**Nível 2a — StatRow** (4 KPIs categorizados):
1. Equipamentos (laranja) — total + composição (vasos + trocadores)
2. Peso Total Estimado (amarelo) — kg + delta vs PVElite
3. Custo Material (verde) — R$ + material dominante
4. Cálculos Calculados (preto) — N/M + % calculado vs importado

**Nível 2b — DataTable de equipamentos:**
| Tag | Tipo / Norma | Material | Pressão · Temp | Peso (kg) | Componentes | Status Cálculo | Aprovação |

Cada linha clicável → expande inline para nível 2c.

**Nível 2c — Grid de CompCard** (2 colunas):
Para cada equipamento expandido, mostra todos os componentes em `CompCard` (ver §3.4) com espessura, MAWP, peso por componente. Faixa lateral colorida indica calc / import / pendente.

Ações da seção:
- `[+ Vaso de Pressão]` → abre EQP-01 (modal/sidebar)
- `[+ Trocador de Calor]` → abre EQP-02
- `[Recalcular Todos]` → POST `/calculate/` com AsyncProgressBar embutida

#### §3 · BOM & Roteiro · Resumo

Seção com header `§3 · BOM & Roteiro · Resumo`. Conteúdo: `DataTable` agregada por categoria:

| Categoria | Itens | Peso (kg) | Custo Material | Horas Total | Custo MO |
|---|---|---|---|---|---|
| Chapas | 14 | 3.247 | R$ 27.600 | — | — |
| Tubos / Bocais | 8 | 340 | R$ 4.182 | — | — |
| Tubos Feixe (E-204) | 187 | 560 | R$ 8.890 | — | — |
| Flanges + Acessórios | 12 | 420 | R$ 6.480 | — | — |
| Roteiro — Corte/Calandra/Solda/PWHT/RX/Pintura | 42 | — | — | 412 | R$ 18.540 |

Ações:
- `[Ver BOM Completo]` → CST-01 (em modal ou rota separada)
- `[Ver Roteiro]` → CST-02

#### §4 · Formação de Preço

Seção com header `§4 · Formação de Preço`. Conteúdo: `DataTable` em formato cascata (composição → subtotal → margem/impostos → preço de venda):

| Composição | % sobre custo | Valor (R$) | Observação |
|---|---|---|---|
| Custo Material | 100% | 47.152 | Aço SA-516-70 · tubos SA-179 · acessórios |
| Mão de Obra Direta | 39,3% | 18.540 | 412h · centro de custo CCF-01 |
| Overhead Industrial | 15,0% | 9.854 | Aplicado sobre (material + MO) |
| Serviços Externos | 7,4% | 3.500 | END · ART · Pintura especial |
| **Subtotal · Custo** | **100,0%** | **79.046** | (linha destacada em `--g-paper`) |
| Margem de Lucro | 22,0% | 17.390 | Política da empresa · 18–25% |
| Impostos · ICMS+PIS+COFINS | 21,25% | 23.014 | 12% + 9,25% sobre preço bruto |
| **Preço de Venda** | — | **R$ 287.450** | Margem líquida: 22,0% |

⚠ **Linha "Preço de Venda" é destaque visual canônico do G**: fundo `--g-black` sólido + texto e valor em `--g-yellow`. Esta é a "linha de chegada" da cotação — recompensa visual ao gestor comercial.

Ações: `[Editar Margem]` (abre CST-03) · `[Recalcular Preço]`

Restrição de acesso: §4 visível apenas para roles `gestor_comercial`, `admin`. Para `orçamentista` e `engenheiro` a seção mostra apenas: "Formação de preço gerenciada pelo Gestor Comercial — preço de venda atual: R$ 287.450".

#### §5 · Aprovação Técnica

Seção com header `§5 · Aprovação Técnica`. Conteúdo dividido em dois blocos:

**Bloco 5a — Aprovações ativas:** Lista de TechnicalApproval por componente:

| Componente | Aprovado por | CREA | ART | Snapshot Hash | Data | Ações |
|---|---|---|---|---|---|---|
| V-101 · Casco | Eng. Rodrigo Oliveira | CREA-SP 5063412 | ART 28051·2025 | `a4f9·2c8b·71de` | há 2h | [Ver Snapshot] [Revogar] |
| V-101 · Tampo Sup. | Eng. Rodrigo Oliveira | CREA-SP 5063412 | ART 28051·2025 | `b2a3·9e8f·2c11` | há 2h | [Ver Snapshot] [Revogar] |

**Bloco 5b — Componentes pendentes** (se houver): lista com call-to-action `[Aprovar Agora]` (abre APR-02 modal) para o engenheiro.

Restrição: §5 visível apenas para `engenheiro`, `admin`, e em modo somente-leitura para `gestor_comercial`. Para `orçamentista`, a seção mostra "Aprovação técnica gerenciada pelo Engenheiro".

#### §6 · Proposta

Seção com header `§6 · Proposta`. Comportamento condicional:

- **Se `quotation.status` é `approved`, `sent_to_customer`, `won` ou `lost`:**
  Lista de propostas geradas (`DataTable`): número da proposta · template usado · formato · gerada em · gerada por · ações `[Download DOCX] [Download PDF] [Ver Audit]`.
  Botão principal: `[+ Nova Proposta]` → abre PROP-01.

- **Se `quotation.status` é `draft` ou `in_review`:**
  Seção bloqueada visualmente (fundo `--g-paper-2` opacidade 0.6). Mensagem: *"Conclua a Aprovação Técnica e a Aprovação Comercial para habilitar geração de proposta."*
  Link `→ Ir para §5 · Aprovação Técnica`.

#### Minimap (sidebar direita, sticky)

Componente `Minimap` (§3.4). Itens:
1. `§1 · Dados Gerais` — badge `✓` se completos
2. `§2 · Equipamentos` — badge numérico (count)
3. `§3 · BOM & Roteiro` — badge numérico (total de itens)
4. `§4 · Formação Preço` — badge `R$` se calculado, `—` se pendente
5. `§5 · Aprov. Técnica` — badge `✓` se aprovado, `(N)` se pendente
6. `§6 · Proposta` — badge `✓` se gerada, `⊘` se bloqueado (e item em cinza claro)

Abaixo do minimap, dois blocos de progresso:
- **Progresso Cotação**: percentual 0–100 calculado pela função `quotation.progress_pct()` que retorna `(etapas_concluídas / 6) * 100`. Bar visual em laranja.
- **Validade**: dias restantes até `valid_until`; vira vermelho se < 7 dias.

#### Comportamento técnico

- **Scroll-spy**: usar Alpine.js + IntersectionObserver para destacar item ativo do minimap conforme rolagem.
- **Q-Header e Minimap são `position: sticky`** — sempre visíveis durante rolagem.
- **HTMX** para recarregar seções individuais sem recarregar a página inteira:
  - `hx-get="/cotacoes/{id}/secao/equipamentos/"` → swap `#sec-equipamentos`
  - `hx-trigger="every 5s"` durante cálculo assíncrono em §2
- **URL com hash** sincronizada com o item ativo do minimap: `/cotacoes/{id}/#sec-aprovacao`

#### Notas para vibe-coding

- **Q-Header é o mesmo componente** em todas as telas de cotação (COT-03, COT-04, COT-05). Criar um partial Django reutilizável `templates/cotacao/_q_header.html`.
- **Botões de ação são contextuais** — renderizar conforme `quotation.status` × `request.user.role` (matriz em §3.6). Centralizar lógica em template tag `{% can_action quotation 'submit_for_review' %}`.
- **§5 e §6 têm restrição de role** — esconder seção inteira no minimap se o usuário não pode ver.
- **ApprovalBanner é sticky logo abaixo do Q-Header** — não rola junto com o conteúdo da seção atual.
- **Linha "Preço de Venda" em §4 NUNCA muda de estilo** — preto sólido + amarelo é assinatura visual canônica do G. Documentar como pattern no design system.

---

### COT-04 — Revisão de Cotação
**Rota:** `/cotacoes/{id}/revisar/`
**Personas:** Orçamentista, Engenheiro, Admin
**Sprint:** 3
**Objetivo:** Criar nova revisão de uma cotação existente.

**Dados exibidos:**
- Cotação original (somente leitura): número, revisão atual, status, data
- Campo "Motivo da revisão" (textarea, obrigatório)
- Preview: nova cotação terá número COT-2025-001 Rev. B

**Ações:**
- [Criar Revisão] → POST /api/v1/quotations/{id}/revise/ → redireciona para nova COT-03 (draft)
- [Cancelar] → COT-03

---

### COT-05 — Ações de Status (Modais)
**Rota:** Modais embutidos em COT-03
**Personas:** Gestor (aprovar, marcar ganha/perdida), Orçamentista (enviar para revisão)
**Sprint:** 3

**Modal: Enviar para Revisão**
- Checklist automático: todos os componentes têm aprovação técnica? [✓/✗ por componente]
- Se faltam aprovações: bloqueado com lista dos componentes pendentes
- [Confirmar] → POST /api/v1/quotations/{id}/submit-for-review/

**Modal: Aprovar Cotação**
- Resumo: valor total, margem %, prazo de entrega
- Campo "Notas de aprovação" (opcional)
- [Aprovar] → POST /api/v1/quotations/{id}/approve/

**Modal: Marcar como Ganha**
- Campo "Observações" (opcional)
- [Confirmar] → POST /api/v1/quotations/{id}/mark-won/

**Modal: Marcar como Perdida**
- Campo "Motivo da perda" (obrigatório)
- [Confirmar] → POST /api/v1/quotations/{id}/mark-lost/

---

### EQP-01 — Data Sheet — Vaso de Pressão
**Rota:** `/cotacoes/{id}/equipamentos/{eq_id}/vaso/`
**Personas:** Orçamentista, Engenheiro
**Sprint:** 3
**Objetivo:** Parametrizar completamente um vaso de pressão para cálculo ASME VIII Div.1.

**Campos (FormSections colapsáveis):**

*Identificação:*
- Tag (ex: V-101) | Descrição | Classe NR-13 (I/II) | Serviço (fluido)

*Projeto:*
- Pressão de Projeto (bar) | Temperatura de Projeto (°C)
- Pressão de Operação (bar) | Temperatura de Operação (°C)
- Sobremetal (mm, padrão 3,0) | Eficiência de Junta E (padrão 1,0)

*Casco:*
- Material do Casco (autocomplete → mostra σ_t, S na T de projeto) [obrigatório]
- Orientação (Vertical / Horizontal)
- D.E. do Casco (mm) | Comprimento do Casco (mm)

*Tampos:*
- Tipo de Tampo (dropdown: Toriesférico / Elíptico 2:1 / Hemisférico / Cônico / Plano)
- Material do Tampo (autocomplete)
- Quantidade de Tampos (padrão 2)

*Bocais:* tabela inline com [+ Adicionar Bocal]:
- Tag | DN | Schedule | Material | Tipo (entrada/saída/dreno/inspeção)

*Tratamentos e END:*
- Tratamento Térmico (PWHT / Alívio / Normalizado / Nenhum)
- RX % | US | LP | PM

*Suportes:*
- Tipo (Sela / Saia / Pés / Orelhas)
- Acabamento Superficial

**Ações:**
- [Salvar] → PATCH equipment
- [Calcular] → POST .../calculate/ → mostra AsyncProgressBar → EQP-03
- [Cancelar] → COT-03

**Validações inline:**
- Pressão de projeto ≤ 0 → "Pressão deve ser positiva"
- Temperatura de projeto além de T_max do material → "Material {código} não é adequado para {T}°C (T_max = {T_max}°C)"
- Eficiência de junta: 0.0–1.0 → "E deve estar entre 0,0 e 1,0"

**Notas para vibe-coding:**
- Ao selecionar material: HTMX carrega propriedades inline (σ_t, S na T de projeto interpolado)
- Cálculo só disponível se campos obrigatórios preenchidos (validação no botão)
- Espessura adotada inicial = calculada (usuário pode aumentar, nunca diminuir)

---

### EQP-02 — Data Sheet — Trocador de Calor
**Rota:** `/cotacoes/{id}/equipamentos/{eq_id}/trocador/`
**Personas:** Orçamentista, Engenheiro
**Sprint:** 3

**Campos adicionais ao EQP-01 (FormSections):**

*Tipo e Classe TEMA:*
- Tipo TEMA (E/F/G/H/J/X/K) com diagrama SVG inline por tipo
- Classe TEMA (R/C/B)

*Lado Casco:*
- Fluido lado casco | Pressão projeto (bar) | Temperatura projeto (°C)
- Material casco (autocomplete) | D.E. casco (mm) | Comprimento (mm)

*Lado Tubo:*
- Fluido lado tubo | Pressão projeto (bar) | Temperatura projeto (°C)
- Material tubo | D.E. tubo (mm) | Espessura tubo (mm) | Comprimento dos tubos (mm)
- Número de passes no lado tubo

*Espelho (Tubesheet):*
- Material espelho | Tipo (fixo/flutuante/U-tube)

*Chicanas:*
- Tipo (Segmental simples/duplo/Disco-anel/Nenhuma) | Número de chicanas

*Saída calculada (readonly após cálculo):*
- Número de tubos | Área de transferência (m²) | Calor trocado (kW)

---

### EQP-03 — Resultado de Cálculo
**Rota:** `/cotacoes/{id}/equipamentos/{eq_id}/resultado/`
**Personas:** Orçamentista, Engenheiro
**Sprint:** 3
**Objetivo:** Visualizar os resultados do motor de cálculo por componente.

**Layout:** Tabela de componentes no lado esquerdo; painel de detalhes do componente selecionado à direita.

**Tabela de componentes:**
Tag | Tipo | Material | Modo (Calculado/Importado) | Esp. Calculada (mm) | Esp. Adotada (mm) | Peso (kg) | Status Aprovação

**Painel de detalhe (componente selecionado):**
- CalculationResultBlock com todos os outputs do snapshot mais recente
- Norma de referência e versão da função
- Espessura adotada (editável, mínimo = calculada)
- Badge "Calculado pelo sistema" (azul) ou "Importado — {source}" (âmbar)
- Histórico de snapshots (link → EQP-05)

**Estado loading (durante cálculo):**
```
[===========     ] 65%
Calculando reforço de bocal N1 (UG-37)...
```

**Estado error:**
Banner vermelho com `CalculationError.code` e mensagem em português.
Ex: "PRESSURE_OUT_OF_RANGE — Pressão de projeto (150 bar) excede o limite de aplicação de UG-27 (t/R ≥ 0,5). Use ASME VIII Div.2."

---

### EQP-04 — Importar Cálculo de Terceiro
**Rota:** Modal em EQP-01 ou EQP-03
**Personas:** Engenheiro, Admin
**Sprint:** 3

**Campos:**
- Componente (dropdown dos componentes do equipamento)
- Arquivo (upload: PDF/DOCX/DWG, max 20MB)
- Fonte do cálculo (texto: "PVElite calculado por Eng. João — CREA-SP 123456")
- Notas (textarea)

**Ações:**
- [Importar] → POST .../import-calculation/ → componente muda para modo "Importado"
- Badge âmbar aparece no componente

**Validações:**
- Arquivo obrigatório → "Selecione o arquivo do cálculo"
- Tipo não permitido → "Apenas PDF, DOCX e DWG são aceitos"
- Tamanho > 20MB → "Arquivo muito grande (máx. 20 MB)"

---

### EQP-05 — Histórico de Snapshots
**Rota:** `/cotacoes/{id}/equipamentos/{eq_id}/snapshots/`
**Personas:** Engenheiro, Admin
**Sprint:** 4

**Dados exibidos (tabela):**
Data/Hora | Função | Versão | Norma | Inputs (resumo) | Esp. Calculada | MAWP | PVElite ✓ | Delta % | Aprovado por

**Ações:**
- [Validar contra PVElite] → APR-04 (modal)
- [Detalhe] → modal com JSON completo de inputs/outputs

**Notas:**
- Registros são append-only — sem botão de excluir
- Hash SHA-256 exibido truncado (8 chars) com tooltip do hash completo

---

### CST-01 — BOM — Lista de Materiais
**Rota:** `/cotacoes/{id}/bom/`
**Personas:** Orçamentista, Engenheiro, Gestor
**Sprint:** 4
**Objetivo:** Revisar e editar a lista de materiais da cotação.

**Dados exibidos (tabela agrupada por equipamento):**
Item | Componente | Material | Forma | Peso Líq. (kg) | Aproveit. % | Peso Bruto (kg) | Preço R$/kg | Custo Total R$ | Notas

**Rodapé da tabela:** Peso total líquido | Peso total bruto | Custo total material R$

**Ações:**
- [Editar quantidade] → inline edit
- [Substituir material] → modal com autocomplete
- [Override de preço] → campo editável com campo "Motivo" obrigatório
- [Exportar CSV]
- [Regenerar BOM] → recalcula a partir dos componentes (modal de confirmação)

---

### CST-02 — Roteiro de Fabricação
**Rota:** `/cotacoes/{id}/roteiro/`
**Personas:** Orçamentista, Engenheiro
**Sprint:** 4

**Dados exibidos (tabela agrupada por equipamento):**
Seq. | Componente | Operação (código+nome) | Máquina | Qty | Unid | Rate (h/unid) | Layer | H. Estimadas | Setup (h) | Total (h) | Custo R$ | Notas

**Rodapé:** Total horas estimadas | Total custo mão-de-obra R$

**Ações:**
- [+ Adicionar Operação] → modal inline
- [Remover operação] → confirmação
- [Reordenar] → drag-and-drop (Alpine.js Sortable)
- [Exportar CSV]

**Notas para vibe-coding:**
- Coluna "Layer" exibe badge: "Padrão Ind." (cinza) / "Tenant" (azul) / "Atual" (verde)
- Tooltip no Rate: "Fonte: 0,82 h/m — Baseado em 34 ordens de fabricação — Confiança: 87%"

---

### CST-03 — Formação de Preço
**Rota:** `/cotacoes/{id}/preco/`
**Personas:** Gestor, Admin
**Sprint:** 4
**Objetivo:** Configurar overhead, margem e impostos e calcular o preço de venda.

**Layout:** Painel esquerdo (inputs) | Painel direito (resultado atualizado via HTMX)

**Painel de inputs:**
- Overhead %
- Margem %
- Impostos: ICMS % | PIS/COFINS % | ISS %

**Painel de resultado (atualiza on-change via HTMX):**
```
Custo Direto de Material:     R$ 45.000,00
Custo de Mão de Obra:         R$ 18.000,00
Overhead (15%):               R$  9.450,00
─────────────────────────────────────────
Custo Total:                  R$ 72.450,00
Margem (22%):                 R$ 20.421,43
Subtotal:                     R$ 92.871,43
Impostos (21,25%):            R$ 19.735,18
─────────────────────────────────────────
PREÇO DE VENDA:               R$ 112.606,61
─────────────────────────────────────────
Peso total:                      3.250 kg
Preço por kg:                R$ 34,65/kg
```

**Ações:**
- [Calcular e Salvar] → POST /api/v1/quotations/{id}/price-formation/ → atualiza resultado
- [Ver Breakdown Detalhado] → CST-04

---

### CST-04 — Breakdown de Custo
**Rota:** `/cotacoes/{id}/preco/breakdown/`
**Personas:** Gestor, Admin
**Sprint:** 4

**Dados exibidos:**
- Tabela por tipo de custo (material / mão-de-obra / overhead / serviço externo)
- Tabela por equipamento (tag, custo, % do total)
- Gráfico de pizza (SVG inline) — distribuição por tipo de custo

---

### PROP-01 — Seleção de Template
**Rota:** `/cotacoes/{id}/proposta/nova/`
**Personas:** Orçamentista, Gestor, Admin
**Sprint:** 4

**Campos:**
- Template (radio com preview thumbnail + nome + descrição)
- Formato (DOCX / PDF / Ambos)

**Ações:**
- [Gerar Proposta] → POST /api/v1/quotations/{id}/proposals/ → PROP-02

**Validação:**
- Cotação sem preço formado → "Forme o preço antes de gerar a proposta (CST-03)"

---

### PROP-02 — Status de Geração
**Rota:** `/cotacoes/{id}/proposta/{prop_id}/status/`
**Personas:** Orçamentista, Gestor, Admin
**Sprint:** 4

**Layout:**
- AsyncProgressBar com polling a cada 2s (`hx-trigger="every 2s"`, `hx-get="/api/v1/tasks/{task_id}/"`)
- Mensagens de progresso:
  - "Renderizando template DOCX..."
  - "Convertendo para PDF via WeasyPrint..."
  - "Calculando hashes de integridade..."
  - "Proposta pronta!"

**Estado done:** Redirect automático para PROP-03

**Estado error:** Banner vermelho + [Tentar Novamente]

---

### PROP-03 — Download e Histórico de Propostas
**Rota:** `/cotacoes/{id}/proposta/`
**Personas:** Todos
**Sprint:** 4

**Dados exibidos (tabela):**
Número | Template | Status | Data geração | Gerada por | DOCX | PDF | Enviada em | Enviada para

**Ações:**
- [Baixar DOCX] → GET .../download/?format=docx
- [Baixar PDF] → GET .../download/?format=pdf
- [Marcar como Enviada] → modal com campo "E-mail do destinatário"

**Notas:**
- Download registrado em AccessLog automaticamente
- Hash SHA-256 exibido para auditoria de integridade

---

### APR-01 — Painel do Engenheiro
**Rota:** `/aprovacoes/`
**Personas:** Engenheiro
**Sprint:** 5
**Objetivo:** Ver todos os cálculos que aguardam aprovação técnica.

**Dados exibidos (tabela):**
Cotação | Equipamento | Componente | Calculado em | Calculado por | Status Aprovação | Ação

**Filtros:** Status (Pendente / Aprovado / Revogado), Cotação, Período

**Ações:**
- [Assinar] → APR-02 modal
- [Ver Snapshot] → EQP-05
- [Validar PVElite] → APR-04

---

### APR-02 — Assinar Cálculo (Modal)
**Rota:** Modal em APR-01 ou COT-03
**Personas:** Engenheiro
**Sprint:** 5

**Conteúdo do modal:**
- Resumo do componente: tipo, material, pressão, temperatura, espessura calculada, MAWP
- Hash do snapshot (SHA-256 truncado)
- Campo ART Number (opcional)
- Campo Notas (opcional)

**Disclaimer (texto fixo, não editável):**
```
"Ao assinar este cálculo, o Engenheiro [Nome Completo] — CREA-[UF] [Número], 
declara ter revisado e validado os dados de entrada e os resultados do dimensionamento 
normativo acima, assumindo responsabilidade técnica nos termos da Lei 5.194/66 e 
Resolução CONFEA 1.010/05."
```

- Checkbox: "Li e concordo com o termo de responsabilidade técnica" (obrigatório)

**Ações:**
- [Assinar] → POST /api/v1/quotations/{quotation_id}/technical-approvals/
- [Cancelar]

---

### APR-03 — Histórico de Aprovações
**Rota:** Aba em COT-03 ou `/cotacoes/{id}/aprovacoes/`
**Personas:** Engenheiro, Admin
**Sprint:** 5

**Dados exibidos:**
| Aprovador | CREA | ART | Componente | Hash do Snapshot | Aprovado em | Status |
- Status: "Ativo" (verde) | "Revogado em DD/MM/AAAA por [Nome] — Motivo: ..." (vermelho)

**Ações:**
- [Revogar] → modal com campo "Motivo" obrigatório (DELETE lógico)

---

### APR-04 — Validação PVElite (Modal)
**Rota:** Modal em EQP-05
**Personas:** Engenheiro
**Sprint:** 5

**Campos:**
- Espessura PVElite (mm) (obrigatório)
- MAWP PVElite (bar) (obrigatório)
- Notas

**Resultado calculado inline:**
```
Delta Espessura: 0,8% ✓ (dentro da tolerância de 1%)
Delta MAWP:      1,7% ✓
```

**Ações:**
- [Registrar Validação] → POST .../validate-pvélite/ → snapshot marcado como validado

---

### AUD-01 — AccessLog
**Rota:** `/auditoria/`
**Personas:** Admin, Gestor
**Sprint:** 5

**Dados exibidos (tabela):**
ID | Usuário | Ação | Recurso | ID do Recurso | IP | Data/Hora | Detalhes

**Filtros:**
- Usuário (autocomplete)
- Ação (multi-select: view/create/update/delete/export/approve/revoke)
- Tipo de recurso (Cotação/Proposta/Aprovação/Usuário...)
- Período (de/até)

**Ações:**
- [Exportar CSV] → AUD-03
- [Detalhe] → modal com JSONB completo de `details`

---

### AUD-02 — Histórico de Entidade
**Rota:** `/auditoria/{resource_type}/{id}/historico/`
**Personas:** Admin, Gestor
**Sprint:** 5

**Dados exibidos:**
Timeline vertical de todas as alterações de uma entidade específica.
Cada entrada: data/hora, usuário, tipo (Criado/Alterado/Excluído), diff por campo.

**Diff por campo:**
```
Campo: Pressão de Projeto
  Antes: 8,0 bar
  Depois: 10,0 bar
```

---

### AUD-03 — Export CSV de Auditoria
**Rota:** `GET /auditoria/export/?from=&to=&user=&action=`
**Personas:** Admin
**Sprint:** 5

Geração de CSV com todos os campos do AccessLog no período filtrado. Download direto (sem Celery para CSV < 10.000 linhas).

---

### CFG-01 — Configurações do Tenant
**Rota:** `/configuracoes/`
**Personas:** Admin
**Sprint:** 1

**Campos:**
- Razão Social | CNPJ | Endereço | Cidade | UF
- Logo (upload PNG/SVG, max 2MB)
- Regime Tributário (Simples / Lucro Presumido / Lucro Real)
- Moeda padrão | Margem padrão % | Prazo padrão de validade (dias)
- Exigir validação PVElite (toggle)
- Template de proposta padrão (dropdown)

**Ações:**
- [Salvar configurações]

---

### CFG-02 — Usuários e RBAC
**Rota:** `/configuracoes/usuarios/`
**Personas:** Admin
**Sprint:** 1

**Dados exibidos (tabela):**
Nome | Email | Role | CREA | MFA Ativo | Último Login | Ativo | Ações

**Ações:**
- [+ Novo Usuário] → modal com campos: email, nome, role, CREA (se engenheiro), senha temporária
- [Editar] → modal de edição (role, CREA, ativo)
- [Desativar] → modal de confirmação
- [Resetar MFA] → modal de confirmação

**Validações:**
- Role engenheiro sem CREA_NUMBER → "CREA obrigatório para engenheiros"
- Email duplicado → "E-mail já cadastrado"

---

### CFG-03 — Templates de Proposta
**Rota:** `/configuracoes/templates/`
**Personas:** Admin
**Sprint:** 4

**Dados exibidos:**
Nome | Descrição | Padrão? | Ativo | Última atualização | Ações

**Ações:**
- [+ Upload Template] → modal: nome, descrição, arquivo .docx (max 10MB), marcar como padrão
- [Visualizar Preview] → renderiza template com dados de exemplo → PROP-02 em modo preview
- [Definir como Padrão]
- [Desativar]

---

### CFG-04 — Operações e Índices (Rates)
**Rota:** `/configuracoes/operacoes/`
**Personas:** Engenheiro, Admin
**Sprint:** 1

**Layout:** Tabs: Operações | Máquinas | Índices de Produtividade

**Aba Operações:**
Tabela: Código | Nome | Categoria | Unidade | Ativo
[+ Nova Operação]

**Aba Máquinas:**
Tabela: Código | Nome | Custo hora R$ | Setup padrão (h) | Ativo
[+ Nova Máquina]

**Aba Índices de Produtividade:**
Tabela: Operação | Material | Espessura (mm) | Layer | Índice | Unid | Confiança | N amostras | Válido de | Válido até
Filtros: Layer (Padrão Ind. / Tenant / Atual), Operação
[+ Novo Índice Tenant] → sobrescreve padrão da indústria

**Notas:**
- Índices `industry_standard` são somente leitura (editáveis apenas via importação)
- Layer `actual` é gerado automaticamente pelo sistema (H2) — somente leitura

---

## 8. Padrões de Interação

### Erros de Validação
- Exibidos inline abaixo do campo com ícone ⚠ e texto em `--color-danger-600`
- Banner de erro de API (não-validação): faixa vermelha no topo do formulário com `error.message`
- Erros de cálculo (`CalculationError`): painel destacado com código do erro + mensagem em português + link para documentação da norma

### Estados de Loading Assíncrono
- Botões que disparam tarefas: texto muda para "[Calculando...]", ícone spinner, `disabled=true`
- AsyncProgressBar: polling via `hx-trigger="every 2s"`, barra de progresso + mensagem descritiva
- Nunca usar spinner genérico sem texto descritivo do que está acontecendo

### Campos Read-Only por Status
- Cotação aprovada ou posterior: todos os campos de dados e equipamentos ficam `readonly` (com visual diferente — fundo `--color-neutral-100`, sem borda de input)
- Badge "Somente Leitura" visível no topo do formulário de equipamento

### Aprovação Técnica
- ApprovalBanner sempre visível no topo da aba Equipamentos de COT-03
- Componentes com aprovação vigente: ícone ✓ verde na tabela
- Componentes recalculados após aprovação: ícone ⚠ âmbar com tooltip "Aprovação revogada — recalculado em DD/MM/AAAA"

### Confirmações Destrutivas
- Toda ação destrutiva (revogar aprovação, desativar usuário, regenerar BOM, marcar como perdida) abre modal com:
  - Título descritivo da ação
  - Consequências explícitas em 1–2 frases
  - Botão [Cancelar] (esquerda, neutro) + [Confirmar] (direita, vermelho)
  - Nunca auto-confirmar

### Feedback de Sucesso
- Toast no canto superior direito, verde, 3 segundos
- Para ações críticas (assinar cálculo, aprovar cotação): banner persistente no topo da tela até o usuário fechar

---

## Anexo A · CSS Completo do Design System G

Para o dev parceiro: este é o CSS-base pronto para colar em `static/css/design-system-g.css` e importar no template-base do Django. Tudo já está em `:root` para coexistir com Tailwind utilities — você pode usar `bg-[var(--g-orange)]` em classes Tailwind também.

```css
/* ================================================================
   SmartQuotation · Design System G · Refined Bauhaus · v1.0
   ================================================================ */

@import url('https://fonts.googleapis.com/css2?family=Archivo:wght@400;500;600;700;800&family=JetBrains+Mono:wght@400;500;600&display=swap');

:root {
  /* Cores */
  --g-paper:      #f4f1ea;
  --g-paper-2:    #fafaf2;
  --g-white:      #ffffff;
  --g-black:      #16151a;
  --g-orange:     #d94e1f;
  --g-yellow:     #f5c542;
  --g-green:      #2d6a3e;
  --g-red:        #a23a2f;
  --g-blue:       #2950b0;
  --g-amber:      #b8851a;
  --g-gray-1:     #888278;
  --g-gray-2:     #e3dfd2;
  --g-gray-3:     #c8c2b2;

  --g-bg-review:    #fff8e6;
  --g-bg-approved:  #eaf3ea;
  --g-bg-sent:      #e8edf8;
  --g-bg-lost:      #faeae8;

  /* Tipografia */
  --font-display: 'Archivo', sans-serif;
  --font-mono:    'JetBrains Mono', monospace;

  --w-regular: 400;
  --w-medium: 500;
  --w-semibold: 600;
  --w-bold: 700;
  --w-black: 800;

  --ls-display: -0.025em;
  --ls-body: -0.005em;
  --ls-eyebrow: 0.14em;
  --ls-uppercase: 0.10em;

  /* Bordas */
  --border-thin: 1px solid var(--g-gray-2);
  --border-medium: 1px solid var(--g-gray-1);
  --border-strong: 1.5px solid var(--g-black);
}

/* ============= BASE ============= */
* { box-sizing: border-box; margin: 0; padding: 0; }
html, body {
  font-family: var(--font-display);
  color: var(--g-black);
  background: var(--g-paper);
  font-size: 13px;
  line-height: 1.5;
}
body { letter-spacing: var(--ls-body); }

/* Sem border-radius em nenhum lugar (exceto bolinhas decorativas) */
input, button, textarea, select, .card, .container { border-radius: 0; }

/* ============= LAYOUT CANÔNICO ============= */
.g-app {
  height: 100vh;
  display: grid;
  grid-template-columns: 60px 200px 1fr;
}

/* Rail (60px) */
.g-rail {
  background: var(--g-black); color: var(--g-paper);
  display: flex; flex-direction: column; align-items: center;
  padding: 14px 0; gap: 4px;
}
.g-rail .mark {
  width: 36px; height: 36px; background: var(--g-orange); color: #fff;
  display: flex; align-items: center; justify-content: center;
  font-weight: var(--w-black); font-size: 16px; letter-spacing: -0.04em;
  margin-bottom: 12px; position: relative;
}
.g-rail .mark::after {
  content: ''; position: absolute; bottom: -3px; right: -3px;
  width: 7px; height: 7px; background: var(--g-yellow);
}
.g-rail a {
  width: 36px; height: 32px;
  display: flex; align-items: center; justify-content: center;
  color: var(--g-gray-1); text-decoration: none;
  font-weight: var(--w-bold); font-size: 10.5px; letter-spacing: 0.04em;
}
.g-rail a.active {
  background: #d94e1f15; color: var(--g-yellow);
  border-left: 2px solid var(--g-yellow);
}

/* Sidebar Módulo (200px) */
.g-sb {
  background: var(--g-white);
  border-right: var(--border-thin);
  padding: 18px 0;
  display: flex; flex-direction: column;
  overflow-y: auto;
}
.g-sb .head { padding: 0 18px 12px; border-bottom: var(--border-thin); }
.g-sb .head .eyebrow {
  font-family: var(--font-mono); font-size: 9.5px;
  color: var(--g-gray-1); letter-spacing: var(--ls-eyebrow); text-transform: uppercase;
}
.g-sb .head h2 {
  font-weight: var(--w-bold); font-size: 16px; letter-spacing: -0.01em;
  text-transform: uppercase; margin-top: 4px;
}
.g-sb .head h2::after {
  content: ''; display: block; width: 24px; height: 3px;
  background: var(--g-orange); margin-top: 6px;
}
.g-sb .grp {
  padding: 12px 18px 4px;
  font-family: var(--font-mono); font-size: 9.5px;
  color: var(--g-gray-1); letter-spacing: var(--ls-eyebrow); text-transform: uppercase;
}
.g-sb a {
  display: flex; align-items: center; gap: 8px;
  padding: 6px 18px;
  color: var(--g-black); text-decoration: none;
  font-weight: var(--w-semibold); font-size: 12.5px;
}
.g-sb a:hover { background: var(--g-paper); }
.g-sb a.on { background: var(--g-black); color: var(--g-yellow); }
.g-sb a .n {
  margin-left: auto; font-family: var(--font-mono);
  font-size: 10px; color: var(--g-gray-1);
}
.g-sb a.on .n { color: var(--g-orange); }

/* ============= COMPONENTES ============= */

/* Q-Header */
.q-header {
  background: var(--g-white); border-bottom: var(--border-strong);
  padding: 20px 26px 18px; position: sticky; top: 0; z-index: 10;
}
.q-header .row1 {
  display: flex; align-items: start; justify-content: space-between;
  gap: 24px; margin-bottom: 14px;
}
.q-header .id-block .breadcrumb-q {
  font-family: var(--font-mono); font-size: 10.5px;
  color: var(--g-gray-1); letter-spacing: var(--ls-eyebrow); text-transform: uppercase;
  margin-bottom: 6px;
}
.q-header .id-block .number {
  font-weight: var(--w-black); font-size: 28px;
  letter-spacing: var(--ls-display); line-height: 1; text-transform: uppercase;
}
.q-header .id-block .number .rev {
  color: var(--g-orange); font-family: var(--font-mono);
  font-size: 16px; font-weight: var(--w-semibold); letter-spacing: 0;
  margin-left: 10px; text-transform: none; vertical-align: middle;
}
.q-header .id-block .subtitle { margin-top: 6px; font-size: 13.5px; font-weight: var(--w-medium); }
.q-header .id-block .subtitle b { font-weight: var(--w-bold); }
.q-header .id-block .subtitle .equip {
  color: var(--g-gray-1); margin-left: 6px;
  font-family: var(--font-mono); font-size: 11.5px;
}
.q-header .status-block { text-align: right; display: flex; flex-direction: column; align-items: flex-end; gap: 6px; }
.q-header .status-block .meta {
  font-family: var(--font-mono); font-size: 10.5px;
  color: var(--g-gray-1); letter-spacing: 0.06em; line-height: 1.5;
}
.q-header .status-block .meta b { color: var(--g-black); }

/* Status Pill */
.q-status {
  display: inline-flex; align-items: center; gap: 6px;
  padding: 5px 12px;
  font-weight: var(--w-bold); font-size: 11px;
  letter-spacing: var(--ls-uppercase); text-transform: uppercase;
  border: var(--border-strong); color: currentColor;
}
.q-status::before { content: ''; width: 6px; height: 6px; background: currentColor; }
.q-status--review { color: var(--g-amber); background: var(--g-bg-review); }
.q-status--approved { color: var(--g-green); background: var(--g-bg-approved); }
.q-status--draft { color: var(--g-gray-1); }
.q-status--sent { color: var(--g-blue); background: var(--g-bg-sent); }
.q-status--won {
  color: var(--g-paper); background: var(--g-green); border-color: var(--g-green);
}
.q-status--won::before { background: var(--g-yellow); }
.q-status--lost { color: var(--g-red); background: var(--g-bg-lost); }

/* Variante compacta para tabelas */
.comp-status {
  display: inline-flex; align-items: center; gap: 5px;
  padding: 2px 8px;
  font-weight: var(--w-bold); font-size: 10px;
  letter-spacing: 0.08em; text-transform: uppercase;
  border: var(--border-strong); color: currentColor;
}
.comp-status::before { content: ''; width: 5px; height: 5px; background: currentColor; }
.comp-status--calc { color: var(--g-green); background: var(--g-bg-approved); }
.comp-status--pending { color: var(--g-amber); background: var(--g-bg-review); }
.comp-status--imported { color: var(--g-blue); background: var(--g-bg-sent); }
.comp-status--signed { color: var(--g-paper); background: var(--g-green); border-color: var(--g-green); }
.comp-status--signed::before { background: var(--g-yellow); }

/* Botões */
.q-actions, .q-btn-group {
  display: flex; gap: 8px; flex-wrap: wrap;
  border-top: var(--border-thin); padding-top: 14px;
}
.q-btn {
  background: var(--g-white); border: var(--border-strong);
  padding: 7px 14px; font-family: var(--font-display);
  font-weight: var(--w-bold); font-size: 11px;
  letter-spacing: 0.06em; text-transform: uppercase;
  color: var(--g-black); cursor: pointer;
}
.q-btn:hover { background: var(--g-paper); }
.q-btn.primary { background: var(--g-black); color: var(--g-yellow); }
.q-btn.primary::before { content: '▸ '; color: var(--g-orange); }
.q-btn.ghost { border-color: var(--g-gray-2); color: var(--g-gray-1); font-weight: var(--w-semibold); }
.q-btn.danger { border-color: var(--g-red); color: var(--g-red); }
.q-btn[disabled] { opacity: 0.4; cursor: not-allowed; }

.btn-mini {
  background: var(--g-white); border: var(--border-strong);
  padding: 4px 10px; font-weight: var(--w-bold); font-size: 10px;
  letter-spacing: 0.06em; text-transform: uppercase; cursor: pointer;
}
.btn-mini.primary { background: var(--g-black); color: var(--g-yellow); }

/* Approval Banner */
.approval-banner {
  background: var(--g-green); color: var(--g-paper);
  padding: 10px 26px;
  display: flex; align-items: center; justify-content: space-between; gap: 16px;
  border-bottom: var(--border-strong);
  position: sticky; top: 0; z-index: 9;
}
.approval-banner .lt {
  display: flex; align-items: center; gap: 12px;
  font-weight: var(--w-semibold); font-size: 12.5px;
}
.approval-banner .lt .check {
  width: 22px; height: 22px; background: var(--g-yellow); color: var(--g-black);
  display: flex; align-items: center; justify-content: center;
  font-weight: var(--w-black); font-size: 13px;
}
.approval-banner .lt .meta {
  font-family: var(--font-mono); font-size: 10.5px;
  color: #c8e0c8; letter-spacing: 0.04em; font-weight: var(--w-medium);
}
.approval-banner .lt .meta b { color: var(--g-paper); }
.approval-banner .rt {
  font-family: var(--font-mono); font-size: 10.5px;
  color: #c8e0c8; letter-spacing: 0.04em;
}
.approval-banner .rt b { color: var(--g-paper); }

.approval-banner--pending { background: var(--g-amber); }
.approval-banner--revoked { background: var(--g-red); }

/* Section */
.g-section { background: var(--g-white); border: var(--border-thin); margin-bottom: 16px; }
.g-section-head {
  border-bottom: var(--border-strong); padding: 12px 18px;
  display: flex; align-items: center; justify-content: space-between; gap: 16px;
}
.g-section-head h3 {
  font-weight: var(--w-bold); font-size: 13px;
  letter-spacing: 0.10em; text-transform: uppercase;
}
.g-section-head h3::before {
  content: ''; display: inline-block; width: 16px; height: 3px;
  background: var(--g-orange); vertical-align: middle; margin-right: 8px;
}
.g-section-head .actions { display: flex; gap: 6px; }
.g-section-body { padding: 14px 18px; }

/* StatRow */
.stat-row {
  display: grid; grid-template-columns: repeat(4, 1fr);
  background: var(--g-white); border: var(--border-strong); margin-bottom: 16px;
}
.stat { padding: 14px 16px; border-right: var(--border-thin); position: relative; }
.stat:last-child { border-right: none; }
.stat::before {
  content: ''; position: absolute; left: 0; top: 0; width: 24px; height: 3px;
  background: var(--g-orange);
}
.stat:nth-child(2)::before { background: var(--g-yellow); }
.stat:nth-child(3)::before { background: var(--g-green); }
.stat:nth-child(4)::before { background: var(--g-black); }
.stat .lbl {
  font-family: var(--font-mono); font-size: 9.5px;
  color: var(--g-gray-1); letter-spacing: 0.1em; text-transform: uppercase;
  margin-top: 6px;
}
.stat .val {
  font-weight: var(--w-black); font-size: 24px;
  letter-spacing: var(--ls-display); line-height: 1.1; margin-top: 2px;
  font-feature-settings: 'tnum';
}
.stat .val .u { font-size: 12px; color: var(--g-gray-1); font-weight: var(--w-semibold); margin-left: 3px; }
.stat .delta { font-family: var(--font-mono); font-size: 10px; margin-top: 2px; }
.stat .delta.up { color: var(--g-green); }
.stat .delta.dn { color: var(--g-red); }

/* CompCard */
.comp-card {
  background: var(--g-white); border: var(--border-strong);
  padding: 12px 14px; position: relative;
}
.comp-card::before {
  content: ''; position: absolute; left: 0; top: 0; bottom: 0; width: 4px;
  background: var(--g-green);
}
.comp-card.pending::before { background: var(--g-amber); }
.comp-card.imported::before { background: var(--g-blue); }
.comp-card .row1 { display: flex; align-items: center; justify-content: space-between; gap: 8px; }
.comp-card .name {
  font-weight: var(--w-bold); font-size: 13px;
  text-transform: uppercase; letter-spacing: -0.01em;
}
.comp-card .name small {
  display: block; font-family: var(--font-mono);
  font-weight: var(--w-medium); font-size: 10px;
  color: var(--g-gray-1); margin-top: 1px; letter-spacing: 0.06em;
}
.comp-card .results {
  display: grid; grid-template-columns: 1fr 1fr 1fr;
  margin-top: 10px; padding-top: 10px; border-top: var(--border-thin);
}
.comp-card .res { padding-right: 6px; border-right: var(--border-thin); }
.comp-card .res:last-child { border-right: none; padding-left: 6px; }
.comp-card .res .l {
  font-family: var(--font-mono); font-size: 9px;
  color: var(--g-gray-1); letter-spacing: 0.08em; text-transform: uppercase;
}
.comp-card .res .v {
  font-family: var(--font-mono); font-weight: var(--w-semibold); font-size: 12.5px;
  margin-top: 2px; font-feature-settings: 'tnum';
}
.comp-card .res .v .u { color: var(--g-gray-1); font-weight: var(--w-regular); font-size: 10px; margin-left: 2px; }

/* ParamGrid */
.param-grid {
  display: grid; grid-template-columns: repeat(4, 1fr);
  background: var(--g-white); border: var(--border-thin); margin-bottom: 14px;
}
.param { padding: 10px 14px; border-right: var(--border-thin); border-bottom: var(--border-thin); }
.param:nth-child(4n) { border-right: none; }
.param:nth-last-child(-n+4) { border-bottom: none; }
.param .lbl {
  font-family: var(--font-mono); font-size: 9.5px;
  color: var(--g-gray-1); letter-spacing: 0.1em; text-transform: uppercase;
}
.param .val {
  font-family: var(--font-mono); font-weight: var(--w-semibold); font-size: 13.5px;
  margin-top: 3px; font-feature-settings: 'tnum';
}
.param .val .u { color: var(--g-gray-1); font-weight: var(--w-medium); font-size: 11px; margin-left: 2px; }

/* DataTable */
.g-table { width: 100%; border-collapse: collapse; font-size: 12px; }
.g-table thead th {
  text-align: left; padding: 8px 10px;
  background: var(--g-black); color: var(--g-paper);
  font-weight: var(--w-bold); font-size: 10px;
  letter-spacing: var(--ls-uppercase); text-transform: uppercase;
}
.g-table thead th.num { text-align: right; }
.g-table tbody td { padding: 9px 10px; border-bottom: var(--border-thin); }
.g-table tbody tr:hover td { background: var(--g-paper-2); }
.g-table tbody tr:last-child td { border-bottom: none; }
.g-table tbody td.num { text-align: right; font-family: var(--font-mono); font-feature-settings: 'tnum'; }
.g-table tbody td.id {
  font-family: var(--font-mono); font-weight: var(--w-semibold);
  color: var(--g-orange); font-size: 11px;
}
.g-table tbody td.title { font-weight: var(--w-semibold); font-size: 12.5px; }
.g-table tbody td.title small {
  display: block; font-weight: var(--w-regular); font-size: 10.5px;
  color: var(--g-gray-1); margin-top: 1px; font-family: var(--font-mono);
}

/* Linha "Preço de Venda" — assinatura visual canônica */
.g-table tr.price-final td {
  background: var(--g-black); color: var(--g-paper);
  font-weight: var(--w-black); text-transform: uppercase;
}
.g-table tr.price-final td.num { color: var(--g-yellow); font-size: 14px; }

/* Minimap */
.g3-minimap {
  background: var(--g-white); border-left: var(--border-thin);
  padding: 18px 16px;
  position: sticky; top: 0; height: 100vh;
  overflow-y: auto;
}
.g3-minimap h4 {
  font-family: var(--font-mono); font-size: 9.5px;
  color: var(--g-gray-1); letter-spacing: var(--ls-eyebrow); text-transform: uppercase;
  margin-bottom: 10px;
}
.g3-minimap a {
  display: block; padding: 6px 0 6px 14px;
  text-decoration: none; color: var(--g-black);
  font-weight: var(--w-semibold); font-size: 11.5px;
  border-left: 2px solid var(--g-gray-2);
}
.g3-minimap a:hover { border-left-color: var(--g-gray-1); }
.g3-minimap a.on { border-left-color: var(--g-orange); color: var(--g-orange); }
.g3-minimap a .n {
  float: right; font-family: var(--font-mono); font-size: 10px;
  color: var(--g-gray-1); font-weight: var(--w-medium);
}
.g3-minimap a.on .n { color: var(--g-orange); }
.g3-minimap .div { height: 1px; background: var(--g-gray-2); margin: 14px 0 8px; }
.g3-minimap .progress {
  background: var(--g-paper); border: var(--border-thin);
  padding: 10px 12px; margin-top: 14px;
}
.g3-minimap .progress .lbl {
  font-family: var(--font-mono); font-size: 9px;
  color: var(--g-gray-1); letter-spacing: 0.1em; text-transform: uppercase;
}
.g3-minimap .progress .val {
  font-weight: var(--w-black); font-size: 22px; margin-top: 4px;
  letter-spacing: var(--ls-display); font-feature-settings: 'tnum';
}
.g3-minimap .progress .bar {
  height: 6px; background: var(--g-gray-2); margin-top: 8px;
  position: relative;
}
.g3-minimap .progress .bar::after {
  content: ''; position: absolute; left: 0; top: 0; bottom: 0;
  width: var(--progress, 67%); background: var(--g-orange);
}
.g3-minimap .progress .steps {
  font-family: var(--font-mono); font-size: 9.5px;
  color: var(--g-gray-1); margin-top: 6px; letter-spacing: 0.06em;
}

/* AsyncProgressBar */
.async-progress {
  background: var(--g-paper); border: var(--border-strong);
  height: 8px; position: relative; margin-bottom: 8px;
}
.async-progress .progress-bar { background: var(--g-orange); height: 100%; }
.async-progress + .progress-label {
  font-family: var(--font-mono); font-size: 10.5px;
  color: var(--g-gray-1); letter-spacing: 0.06em;
}

/* Inputs */
input[type="text"], input[type="number"], input[type="email"], select, textarea {
  border: var(--border-strong); background: var(--g-white);
  padding: 6px 10px; font-family: var(--font-display);
  font-size: 13px; color: var(--g-black);
}
input:focus, select:focus, textarea:focus {
  outline: 2px solid var(--g-orange); outline-offset: -2px;
}
label {
  font-family: var(--font-mono); font-size: 10px;
  color: var(--g-gray-1); letter-spacing: 0.1em; text-transform: uppercase;
  display: block; margin-bottom: 4px;
}
```

### Configuração Tailwind (opcional)

Para usar tokens G como classes Tailwind:

```js
// tailwind.config.js
module.exports = {
  theme: {
    extend: {
      colors: {
        'g-paper': '#f4f1ea',
        'g-paper-2': '#fafaf2',
        'g-black': '#16151a',
        'g-orange': '#d94e1f',
        'g-yellow': '#f5c542',
        'g-green': '#2d6a3e',
        'g-red': '#a23a2f',
        'g-blue': '#2950b0',
        'g-amber': '#b8851a',
      },
      fontFamily: {
        display: ['Archivo', 'sans-serif'],
        mono: ['JetBrains Mono', 'monospace'],
      },
      borderRadius: {
        DEFAULT: '0',
        none: '0',
      },
    },
  },
  // Desativa border-radius por default
  corePlugins: {
    borderRadius: false,
  },
}
```

---

## Anexo B · Checklist de Aderência ao G

Antes de marcar uma tela como "pronta", verificar:

- [ ] **Zero `border-radius`** em qualquer elemento (exceto bolinhas decorativas de 5–8px)
- [ ] **Zero `box-shadow`** em containers (sem sombras suaves)
- [ ] **Zero gradientes** (nem em backgrounds, nem em botões)
- [ ] **Zero italic** (nem em corpo, nem em títulos, nem em números)
- [ ] **Zero serif** (proibido Fraunces, Instrument Serif, Playfair, etc.)
- [ ] **Todos os números** em `JetBrains Mono` com `font-feature-settings: 'tnum'`
- [ ] **Todos os IDs** (COT-XXXX, V-101, etc.) em `JetBrains Mono` cor `--g-orange`
- [ ] **Header de tabela** preto sólido + texto creme uppercase
- [ ] **Sem zebra striping** em tabelas (linhas alternadas removidas)
- [ ] **CTA primária** sempre preto-com-amarelo + chevron laranja (`▸`)
- [ ] **Status pills** com borda 1.5px + bolinha à esquerda
- [ ] **Stat-row** com faixas verticais laranja/amarelo/verde/preto no topo
- [ ] **Card de componente** com faixa lateral colorida segundo status (verde/amarelo/azul)
- [ ] **Seções** com cabeçalho preto + título uppercase + faixa laranja de 3px antes do título
- [ ] **Eyebrows** em JetBrains Mono uppercase letter-spacing 0.14em
