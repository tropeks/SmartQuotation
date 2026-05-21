# CHANGELOG · UX_SPEC.md

## v2.0 — 2026-05-16

### 🎨 Design system

**ANTES (v1.0):** paleta navy + âmbar com Inter como fonte base — visual SaaS corporativo genérico ("cara de vibe-code").

**AGORA (v2.0):** **G · Refined Bauhaus** — paleta papel-cru + preto + laranja-segurança + amarelo, tipografia Archivo (uppercase forte) + JetBrains Mono (números), geometria 100% reta (zero `border-radius`), zero `box-shadow`, zero gradiente, zero italic, zero serif. Identidade industrial pesada com refinamento contemporâneo.

### 🏗 Padrão arquitetural

**ANTES (v1.0):** COT-03 e telas-hub usavam abas horizontais (`Dados Gerais | Equipamentos | BOM | Preço | Aprovação | Proposta`).

**AGORA (v2.0):** **Command Center** — coluna única scrollável com seções verticais (`§1` a `§6`) e **minimap navegável à direita** com scroll-spy + indicador de progresso da cotação. Q-Header e Minimap são sticky.

### 📋 Componentes renomeados / reescritos

| Antes (v1) | Agora (v2) | O que mudou |
|---|---|---|
| StatusBadge | **StatusPill** (`q-status`) | Borda 1.5px + bolinha à esquerda + uppercase Archivo 700; variante `won` com fundo verde + bolinha amarela |
| (header inline) | **QHeader** (`q-header`) | Componente formal com eyebrow + número + revisão + cliente + equipamento + status + actions contextuais |
| ApprovalBanner | **ApprovalBanner** | Mantido conceitualmente, agora visualmente: faixa verde sólida com check amarelo + meta em mono |
| (não existia) | **StatRow** | Barra de 4 KPIs com faixas verticais coloridas categorizadas (laranja/amarelo/verde/preto) |
| (não existia) | **CompCard** | Card de componente com faixa lateral colorida indicando status (verde/âmbar/azul) |
| (não existia) | **ParamGrid** | Grid 4-colunas para data sheet em modo visualização |
| (não existia) | **Minimap** | Navegação lateral com scroll-spy + indicador de progresso |
| CalculationResultBlock | (substituído por CompCard) | Granularidade movida para componentes individuais |
| FormSection colapsável | **Section** (não-colapsável por padrão) | Em telas-hub do Command Center, seções ficam abertas; colapsável vira exceção |

### ➕ Adicionados

- **§3.5 — Padrão arquitetural Command Center** com layout canônico (3 colunas), comportamentos obrigatórios, e quando NÃO usar.
- **§3.6 — Matriz de Ações por Status × Role** consolidada em tabela única para o vibe-coding.
- **Anexo A — CSS completo do design system G** (~400 linhas) pronto para colar em `static/css/design-system-g.css`.
- **Anexo B — Checklist de aderência ao G** (15 itens) para revisão de tela antes de marcar como pronta.

### ⚠ Telas que precisam ser revistas (próximos passos)

Toda especificação por tela em §7 ainda referencia a v1 do design system. As próximas etapas são:

1. **Reescrever COT-01, COT-02** com componentes G (StatusPill, QBtn, DataTable G).
2. **Reescrever EQP-01, EQP-02** (data sheets) — usar ParamGrid em modo visualização + form tradicional em modo edição.
3. **Reescrever EQP-03** (resultado de cálculo) — virar grid de CompCard com AsyncProgressBar G.
4. **Reescrever CST-03, CST-04** (formação de preço) — aplicar pattern "linha Preço de Venda em preto+amarelo" como assinatura visual canônica.
5. **Reescrever APR-02** (modal de assinatura) — usar QHeader + StatusPill + componentes G.
6. **Avaliar DASH-01** — candidato natural a virar Command Center modo executivo.
