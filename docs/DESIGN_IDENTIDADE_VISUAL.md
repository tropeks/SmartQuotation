# Identidade visual do SmartQuotation

**Decisão (Rômulo, 2026-07-28):** o SmartQuotation adota a **mesma identidade visual do
Vitali** — a pele *Tasy Neumorphic*. Mais agradável e com cara de produto enterprise.

**Quando:** sprint futura, sem pressa. Nada aqui bloqueia o roadmap atual (M1 do controle de
vazamento de margem, fila de perguntas, motor). Este documento existe para a decisão não se
perder e para a migração já nascer com o alvo definido.

---

## 1. O que sai e o que entra

| | Hoje | Alvo |
|---|---|---|
| Nome | Design System G · *Refined Bauhaus* | **Tasy Neumorphic** |
| Superfície | cor blocada, zero sombra, zero gradiente | relevo por sombra (esculpido) |
| Cantos | `--radius: 0` | 6 / 8 / 12 px |
| Paleta | papel `#f4f1ea`, preto `#16151a`, laranja `#d94e1f` | cinzas frios + azul corporativo `#0066A1` |
| Tipografia | Archivo + JetBrains Mono | **Inter** + JetBrains Mono |
| Arquivo | `backend/static/css/design-system-g.css` | reescrita do mesmo arquivo |

O G não é ruim — é uma escolha estética diferente (Bauhaus, seca, alto contraste). A troca é
por **coerência de portfólio** e por leitura de mercado: o comprador de caldeiraria média
reconhece o visual enterprise, não o editorial.

---

## 2. Onde vivem os tokens (fonte da verdade)

No repo do Vitali, **não** aqui — copiar valores, nunca reinventar:

- `~/dev/vitali/frontend/tailwind.config.ts` → cores `neu.*` e sombras `neu-*`
- `~/dev/vitali/frontend/app/globals.css` → classes `.neu-input`, `.neu-btn-*`, `.neu-panel`
- `~/dev/vitali/docs/FRONTEND_GUIDELINES.md` → receitas canônicas de componente
- `~/dev/vitali/DESIGN.md` → princípios (⚠️ a parte *flat* está marcada como superseded
  desde 2026-07-21; o que vale é a Tasy Neumorphic)

### Paleta

| Papel | Hex |
|---|---|
| fundo da aplicação | `#DFE5EB` |
| container externo | `#EBF0F5` |
| painel / conteúdo | `#F4F7FA` |
| painel claro | `#F8FAFC` |
| campo escavado | `#E8EDF2` |
| texto principal | `#24292F` |
| texto secundário | `#57606A` |
| texto desabilitado | `#8C959F` |
| marca | `#0066A1` → `#005282` (gradiente), borda superior `#3385b5` |
| sucesso / atenção / perigo | `#2DA44E` / `#9A6700` / `#CF222E` |

### Sombras — é o que faz a pele existir

```css
--sh-inset:        inset 0 2px 4px rgba(0,0,0,.06);                              /* campos */
--sh-btn:          inset 0 1px 1px rgba(255,255,255,.5), 0 2px 4px rgba(0,0,0,.05);
--sh-btn-primary:  0 3px 10px rgba(0,102,161,.3);
--sh-panel:        inset 0 1px 2px rgba(255,255,255,.8), 0 2px 8px rgba(0,0,0,.03);
--sh-elevated:     0 10px 30px rgba(0,0,0,.1), inset 0 2px 4px rgba(255,255,255,.8);
```

Campo **afunda**, painel **emerge**. É o contraste entre os dois que dá o efeito — sem as
sombras, vira um cartão cinza qualquer.

---

## 3. Implementação de referência já no ar

Os dois formulários construídos em 2026-07-28 **já usam a pele nova** e servem de gabarito
vivo — copiar de lá é mais rápido que reler o Tailwind do Vitali:

- `~/dev/sq-form/templates/base.html` → tokens + botões + campos, em CSS puro (sem Tailwind)
- `~/dev/sq-well/templates/base.html` → idem
- No ar em **form.qtec.me** e **well.qtec.me**

O CSS ali é deliberadamente sem build step: dá para colar direto no `design-system-g.css`.

---

## 4. Escopo da migração (quando a sprint chegar)

1. **Reescrever `design-system-g.css`** com os tokens acima, mantendo os **nomes de classe
   existentes** (`.g-rail`, `.q-btn`, `.q-badge`, `.g-main`, `.command-center-layout`…). Se os
   seletores forem preservados, a maioria dos templates não precisa mudar — é troca de pele,
   não de estrutura.
2. **Aposentar os aliases** `--g-paper`/`--g-orange`/etc. mapeando-os para os novos tokens
   antes de removê-los, para não quebrar templates legados de uma vez.
3. **Fontes:** trocar Archivo por Inter no `base.html` (já vem do Google Fonts).
4. **Revisar caso a caso** o que depende de contraste alto: `.q-badge`, tints de status
   (`--g-bg-review`, `--g-bg-approved`…) e a barra preta do rail.
5. **Decidir sobre tema escuro:** a pele neumórfica é de mundo único (claro) — o relevo morre
   no escuro. O Vitali assume isso. Manter a mesma decisão.

### Riscos conhecidos

- **Densidade:** o Vitali é mais denso (fonte 12–13 px, input de 32 px). O SmartQuotation tem
  telas de EAP com muita coluna — validar que a densidade nova não aperta demais.
- **Regressão visual silenciosa:** não há teste de UI. Vale um passe de `/design-review` ou
  screenshots antes/depois nas telas críticas (data sheet, EAP, proposta).
- **Proposta em PDF/DOCX:** o template da proposta tem estilo próprio; conferir se herda algo
  do design system antes de mexer.

---

*Referência cruzada: `CLAUDE.md` (seção Arquitetura) aponta para o `design-system-g.css`.*
