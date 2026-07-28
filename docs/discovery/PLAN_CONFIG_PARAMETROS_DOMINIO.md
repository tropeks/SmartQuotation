# Plano — Parâmetros de domínio configuráveis (itens 🟢/🟡 do Wellington)

> Companheiro do `PLAN_RBAC_V2_0_IMPL.md` (RBAC), mas **domínio separado**: aqui é
> engenharia/custeio, não permissões. Cobre o que dissemos ao Wellington que "vira config com
> default" — os itens que **não** dependem dele.
>
> **Âncora existente:** `engineering_params.TenantParamConfig` (singleton por tenant, já tem
> `fator_correcao_mo`, `drill_method_threshold_holes`, `tema_compat_mode`). A maioria dos knobs
> novos entra **como campo aqui** — não inventar modelo novo.
>
> **Regra de ouro do repo:** `pricing_engine` é lib pura (zero Django). Todo valor configurável
> flui **do banco → `apps/quotations/adapter.py` → FeixeInputs/cost_chain → motor**. Nenhum knob
> é lido direto pelo motor. **Cada item tem back-end E front-end — o front-end é onde o valor
> vira usável; não pode ser esquecido.**

Onde o front-end mora:
- **Config global do tenant:** página de parâmetros de engenharia (evolui a área que já edita
  `TenantParamConfig`/Rate). Gate de capability existente (`params.manage` / equivalente).
- **Por cotação:** `apps/quotations/forms.py` (data sheet do feixe) + template do data sheet.

---

## C1 — Baffle cut em % (default 25%)  ·  **front-end-heavy**

**Hoje:** `forms.py:55` `chicana_cut_remaining_mm` — guarda "altura restante (mm)" crua. O motor
já consome mm (TEMA RCB-4, `hc = OD − corte`).

- **Back-end:** manter o armazenamento em **mm** (motor não muda). Adicionar
  `TenantParamConfig.baffle_cut_default_pct = 25.0`. Conversão `% → mm` = `pct/100 × D_interno_casco`.
  Validação: faixa 15–45% (aviso fora de 20–35%, boa prática).
- **Front-end (o trabalho real):**
  - Trocar o input do data sheet para **% do diâmetro interno do casco** (default vindo do
    TenantParamConfig), com o **mm calculado exibido ao lado** ("25% → 148 mm") via Alpine —
    reusa o padrão HTMX/Alpine do data sheet.
  - Campo espelhado read-only em mm pra quem pensa em mm; recalcula ao vivo com o D do casco.
  - Config global: campo "corte de chicana padrão (%)" na página de parâmetros.
- **Default / esforço:** 25% · **M** (back-end P, front-end M).
- **Gotcha:** o D interno do casco precisa estar preenchido antes do %→mm; se ainda não estiver,
  cair para input em mm com aviso.

---

## C2 — Comprimentos de tubo padrão (6,10 m e 12 m)  ·  back+front

**Hoje:** `forms.py:37` `tubo_comp_mm` é float livre. O "6,95 m" do áudio era erro de
transcrição — **não** entra.

- **Back-end:** `TenantParamConfig.tube_standard_lengths_mm` (JSON/CSV, default `[6100, 12000]`).
  Regra de emenda: quando `desenvolvido > maior padrão`, sinalizar emenda (já previsto no F9).
- **Front-end:**
  - Dropdown "comprimento padrão" (lista do tenant) **+ opção "outro (livre)"** que revela o
    campo mm atual — não remover a entrada livre, só dar atalho.
  - Aviso inline "vai precisar de emenda" quando o desenvolvido do U passar do padrão.
  - Config global: editor da lista de comprimentos padrão (add/remove).
- **Default / esforço:** [6,10 m, 12 m] · **P/M**.

---

## C3 — Raio mínimo da curva em U (1,5 × OD)  ·  back-end + validação no front

**Hoje:** F9 usa raio ≥ 1,5×OD (TEMA RCB-2.3) implícito.

- **Back-end:** `TenantParamConfig.u_bend_min_radius_factor = 1.5`. `validators.py` passa a ler o
  fator do config em vez de constante.
- **Front-end:** validação no data sheet (feixe em U) — se o raio informado < fator×OD, erro
  inline com o mínimo calculado. Config global: campo "raio mínimo de curva (× OD)".
- **Default / esforço:** 1,5 · **P**.

---

## C4 — Ângulo/passo (pitch) de furação  ·  **BLOQUEADO no motor — decisão primeiro**

**Hoje:** `forms.py:23` diz explicitamente *"BLOQUEADO por ora: o motor (pricing_engine) não
modela o ângulo de passo/furação"*. Ou seja, **não é só expor um campo** — o motor não usa.

Dois caminhos (escolher com o Rom/Wellington):
- **(a) Documental agora (barato):** campo de pitch/ângulo no data sheet **sem efeito no custo**
  (só registra na proposta). Front-end: input + nota "não afeta custo nesta versão". Esforço **P**.
- **(b) Custo real (caro):** motor passa a derivar nº de furos/área do espelho do pitch×ângulo →
  dirige horas de furação. Exige mudança no `pricing_engine` + recalibração + gate. Esforço **GG**.
- **Recomendação:** (a) já; (b) só depois do referencial do Wellington (Q3 do doc enxuto).

---

## C5 — Semear hora-máquina por operação (RateHM)  ·  back + front de cadastro

**Hoje:** `Rate.rate_hm` **já existe** (`engineering_params/models.py`), e há
`simulation.simulate_rate_change(rate_hh, rate_hm)`. Só a **mandrilar** tem valor; resto = 0.

- **Back-end:** seed opcional de `rate_hm` para as operações com recurso-máquina (quando o
  Wellington mandar a tabela — Q2 do doc enxuto). Sem tabela: fica 0 + edição manual (já funciona).
- **Front-end:** o cadastro de Rate já expõe `rate_hm`; garantir a coluna visível/editável na UI
  de parâmetros (não só no admin). Mostrar quais operações estão com HM=0 (nudge de preenchimento).
- **Default / esforço:** 0 + manual · **P** (mecânica pronta; é seed + polish de UI).

---

## C6 — Editor do roteiro do espelho (tubesheet)  ·  **front-end-heavy**

**Hoje:** roteiro de operações do espelho é fixo no seed. Wellington precisa confirmar a
sequência real (Q3 do doc enxuto) — mas a **edição** pode ser config.

- **Back-end:** permitir reordenar/renomear/ativar operações do roteiro por template de item
  (já há `ItemOperation`/`codigo_op`). Snapshot na cotação preservado (cotação = snapshot).
- **Front-end:** editor de lista ordenada (drag → ordem) das operações do espelho, reusando o
  padrão de UI do builder de fluxos da V2 (mesma mecânica de lista ordenável). Default = roteiro
  confirmado pelo Wellington.
- **Default / esforço:** roteiro atual · **M/GG** (o editor é o custo).

---

## Ordem sugerida e resumo

| Item | Back-end | Front-end | Esforço | Bloqueio |
|---|---|---|---|---|
| C1 baffle cut % | campo TenantParamConfig + conversão | input % + mm ao vivo | **M** | — |
| C2 comprimentos padrão | campo (lista) + regra emenda | dropdown + aviso emenda | P/M | — |
| C3 raio mín. U | campo (fator) | validação inline | **P** | — |
| C4 pitch/ângulo | **decisão (a)/(b)** | input (documental) | P ou GG | motor não modela |
| C5 RateHM seed | seed (espera tabela) | coluna editável + nudge | **P** | tabela do Wellington (melhora) |
| C6 roteiro espelho | reordenar ItemOperation | editor drag | M/GG | sequência do Wellington |

**Recomendação de fatiamento:** um PR "config de engenharia v1" com **C1+C2+C3** (todos sem
bloqueio, back-end pequeno, front-end é o valor entregue) → destrava a experiência de config sem
depender do Wellington. C4(a) junto se quiser o campo documental. C5/C6 quando o Wellington
mandar tabela/roteiro.

**Não esquecer (transversal a todos):**
- Toda leitura de knob passa pelo **adapter**, nunca pelo motor (regra de ouro).
- Cada knob novo em `TenantParamConfig` precisa de **migração** + **default no `provision_tenant`/
  seed** + **teste** de que tenant novo mantém o comportamento validado (feixe/permutador a 0%).
- Cada campo de front-end precisa de **empty/erro state** e recalcular ao vivo (padrão HTMX+Alpine
  do data sheet) — o front-end **é** a entrega, não um detalhe.
