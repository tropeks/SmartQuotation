# Varredura de sensibilidade do motor de custeio

Harness: `scripts/sensibilidade_motor.py` (Python puro, read-only sobre `pricing_engine/`,
roda em ~5s). Guarda: `tests/test_sensibilidade.py` (27 testes, `python -m
tests.test_sensibilidade` ou `pytest tests/test_sensibilidade.py`). Dados completos desta
rodada: rode `python3 scripts/sensibilidade_motor.py --json out.json --md out.md`.

**Pergunta que este documento responde**: quais campos do data sheet / knobs do motor
merecem a paciência do Wellington, e quais são ruído que ele pode ignorar com segurança?

---

## 1. A conclusão primeiro

**Caveat antes dos números** (detalhado em §6, mas vale ler AQUI, junto com o número mais
carregado do documento): toda elasticidade abaixo mede a ESTRUTURA do modelo — as fórmulas
e proxies geométricos do `pricing_engine` — calibrada a **1 job por designação**. Não é a
física medida da fábrica. Se o modelo estiver sistematicamente errado num ponto (ex.:
solda deveria escalar linear com espessura, não ao quadrado), a magnitude de um número
muda, mas o RANKING relativo entre campos tende a se manter.

### Campos que movem dinheiro de verdade (ordenados por |E_bruta| médio a ±10%)

| # | Campo/knob | E_bruta | Onde mais pesa |
|---|---|---:|---|
| 1 | **markup (`fator_preco`)** | **1,000** | todos os casos — proporcionalidade direta, não é achado, é definição |
| 2 | **metalurgia do feixe** (`preco_por_lado`/`dens_por_lado`) | **0,51** | OF3683 (job em inox — troca de liga é o maior risco de custo que existe) |
| 3 | **fator_correcao_mo** (capacidade/MO) | **0,29 – 0,44** | todos — é a fração de MO em cada caso (28,9% a 53,5%) |
| 4 | **preço/kg de material** (uniforme) | **0,30 – 0,41** | todos — é a fração de material em cada caso |
| 5 | **espessura da virola/casco** (`esp_casco_mm`) | **0,30 – 0,32** | BEU/BEM — bate em material E em duas famílias de solda (∝espessura²) |
| 6 | **diâmetro do casco** (`diametro_casco_mm`) | **0,25 – 0,28** | BEU/BEM — o campo com MAIS drivers físicos dependurados nele (5) |
| 7 | **comprimento do TUBO** (`comprimento_tubo_mm`) | **0,23 – 0,29** | BEU/BEM/FEIXE |
| 8 | **liga metalúrgica** (`liga_por_lado`, horas) | **0,20 – 0,32** | BEU/BEM/OF3683 |
| 9 | **impostos_pct** | **0,05 – 0,19** | move a receita líquida, NUNCA o preço cobrado (achado #5 abaixo) |
|10 | **nº de tubos** (FEIXE) | **0,43** | feixe isolado (~53% MO) — bem mais alto que no permutador |

### Campos que são ruído — pode errar sem custar nada

| Campo | E_bruta | Por quê é zero |
|---|---:|---|
| **setup_frac** (qualquer parâmetro) NO PONTO DE REFERÊNCIA | **exatamente 0,000** | identidade algébrica: `setup + (1−setup)×1,0 = 1,0` p/ qualquer setup |
| **perda_por_familia['espelho']**, no data sheet ATUAL | **exatamente 0,000** | a knob está *fiada para nada* — ver achado #2 |
| **nº de passes** | 0,015 – 0,016 | só afeta rasgos de partição, uma fatia pequena da MO |
| **nº de chicanas**, canal de MATERIAL | **0,000** | material de chicana é FIXO no seed, nunca recomputado |
| **comprimento do CASCO** (`comprimento_casco_mm`), canal de MO | **0,000** | achado #1 — o driver de horas usa o comprimento do TUBO, não do casco |
| **nº de tirantes** | 0,004 | só 1 de 2 operações tem um degrau discreto (<10 → ≥10) |
| **OD do tubo** | 0,10 | só material, nenhum driver de horas depende de OD |

**MO não é 32% do custo — é 38,8% (BEU) e 40,0% (BEM), medido agora.** O handoff
(`docs/HANDOFF_MIGRACAO.md` §4) cita R$ 40.990/R$ 128.160 = 32%, de uma discussão de
2026-07-31. Medindo hoje: `custo_mao_obra=R$ 49.830` / `custo_total=R$ 128.163` = **38,9%**
no BEU (BEM: 40,0%; OF3683, o job em inox, cai para **28,9%** — material domina a 65,5%).
Isso não é erro de medição — é o motor tendo evoluído (refinos v3 do CLAUDE.md: solda
∝espessura², fator de liga por lado, furação de chicana ∝tubos×chicanas) depois daquela
conversa. **A implicação prática não muda de sinal** (10% de erro na capacidade ainda vira
~3-4% no preço final, não 10% — só um pouco pior que os "~3,2%" originais), mas se o
handoff for citado de novo, cite 38-40%, não 32%.

---

## 2. Tabela por caso

Baseline usa uma `TenantCostChain` "vazia" (fator_correcao_mo=1,0), não `cost_chain=None`
— é o caminho que o produto real sempre usa (ver achado #4). δ primário = ±10%; δ de
não-linearidade = ±25%. **`E_calib` do permutador (BEU/BEM/OF3683) é HIPOTÉTICO** — o
back-solve real do produto só existe para o feixe (`apps.cost_discovery.services`); ver
§3. **Avisos de viabilidade geométrica** (`permutador_layout.check_layout`, disparado em
qualquer perturbação de nº de tubos/OD/diâmetro do casco): **0 avisos em toda a rodada**
(todas as combinações testadas, nos 4 casos, ±10% e ±25%, ficaram dentro da folga
feixe↔casco) — checado explicitamente contando `Ponto.avisos` em cada um dos pontos
gerados, não presumido pelo silêncio do JSON.

### BEU (baseline R$ 128.042,69 · referencial R$ 128.160,00 · Δ −0,09% · MO 38,8% · Material 30,8%)

| Entrada | Grupo | E_bruta (+10%/−10%) | E_calib (+10%/−10%) | Assimetria/não-linear? |
|---|---|---|---|---|
| fator_correcao_mo | knob_calibracao | 0,388 / 0,388 | N/A (é o próprio knob) | não — perfeitamente linear (prova de afinidade) |
| fator_preco | markup | 1,000 / 1,000 | N/A (downstream) | não |
| impostos_pct | markup | −0,099 / −0,099 (alvo=preco_sem_impostos) | N/A | não |
| preço/kg material (uniforme) | material | 0,358 / 0,244 | −0,920 / −0,628 | **sim** — +10% quase 50% maior que −10% |
| liga_por_lado[feixe] | metalurgia | 0,296 / 0,296 | −0,229 / −0,229 | não |
| liga_por_lado[casco] | metalurgia | 0,231 / 0,231 | −0,312 / −0,312 | não |
| dens_por_lado[feixe] | metalurgia | 0,169 / 0,169 | −0,433 / −0,433 | não |
| preco_por_lado[feixe] | metalurgia | 0,175 / 0,175 | −0,449 / −0,449 | não |
| setup_frac (todos, no ponto de ref.) | knob_tenant | **0,000 / 0,000** | **0,000 / 0,000** | ver §3 "fora do ponto" |
| perda_por_familia['espelho'] (form atual) | knob_tenant | **0,000 / 0,000** | **0,000 / 0,000** | knob inerte — achado #2 |
| perda_por_familia['espelho'] (se o form editasse) | knob_tenant | −0,005 / 0,011 | 0,012 / −0,029 | **sim**, com clamp visível a +25% (E→0) |
| nº de tubos | dims_form | 0,034 / 0,034 | −0,022 / −0,022 | salta p/ 0,083 a +25% — **não é `faixa()`** (`faixa()` nem existe em `permutador_quote.py`); é o clamp `max(perda_eff,1.0)` — achado #9 |
| comprimento do tubo | dims_form | 0,244 / 0,244 | −0,483 / −0,483 | não |
| OD do tubo | dims_form | 0,102 / 0,102 | −0,261 / −0,261 | não (só material) |
| parede do tubo | dims_form | 0,078 / 0,080 | −0,200 / −0,206 | leve assimetria |
| nº de chicanas | dims_form | 0,024 / 0,024 | 0,000 / 0,000 | não (só MO, material congelado) |
| nº de passes | dims_form | 0,015 / 0,015 | 0,000 / 0,000 | não |
| comprimento do casco/virola | dims_form | 0,044 / 0,044 | −0,113 / −0,113 | não — **só material** (achado #1) |
| diâmetro do casco | dims_form | 0,280 / 0,272 | −0,456 / −0,439 | leve assimetria |
| espessura da virola | dims_form | 0,317 / 0,305 | −0,450 / −0,450 | leve assimetria em E_bruta |

BEM segue o mesmo padrão qualitativo (números completos no JSON) — MO 40,0%, material 33,0%,
mesma ordem relativa de leverage, com `liga_por_lado[feixe]` um pouco mais alto (0,319) e
`preço/kg material` um pouco mais baixo (0,32 vs 0,30 do BEU).

### OF3683 (job custom, inox — R$ 734.612,13 · referencial R$ 733.510,00 · Δ +0,15% · MO 28,9% · Material 65,5%)

**Sem data sheet** (achado #3 — ver abaixo): os campos `dims_form` inteiros (nº de tubos,
comprimentos, diâmetros...) não têm como ser varridos aqui. O que sobra é justamente onde
este job PESA mais: metalurgia e preço de material.

| Entrada | E_bruta (+10%) | E_calib (+10%) |
|---|---:|---:|
| preco_por_lado[feixe] | 0,508 | 1,768 |
| dens_por_lado[feixe] | 0,507 | 1,763 |
| fator_correcao_mo | 0,289 | N/A |
| preco_por_lado[casco] | 0,147 | 0,512 |
| dens_por_lado[casco] | 0,116 | 0,403 |
| impostos_pct (alvo=preco_sem_impostos) | 0,054 | N/A |
| liga_por_lado[feixe] | 0,050 | 0,019 |
| liga_por_lado[casco] | 0,045 | 0,012 |
| preço/kg de material (uniforme) | **PULADO** | — ver achado #6 |
| setup_frac (no ponto de referência) | 0,000 | 0,000 |

`E_calib` de metalurgia no OF3683 é **maior que 1** (1,77): o back-solve, ao tentar
reconciliar o total via `fc`, precisa distorcer a MO muito além do erro original para
compensar um erro que é 100% material — o remédio é pior que a doença (achado #7).

### FEIXE-136 (R$ 34.344,93 · referencial R$ 35.353,00 · Δ −2,85% · MO 53,5%)

| Entrada | E_bruta (+10%/−10%) | E_calib (+10%/−10%) | Nota |
|---|---|---|---|
| fator_correcao_mo | 0,443 / 0,443 | N/A | maior fração de MO dos 4 casos |
| nº de tubos | 0,466 / 0,402 | −0,543 / −0,543 | **campo isolado de maior leverage do feixe** |
| comprimento do tubo | 0,287 / 0,287 | −0,509 / −0,509 | não |
| preço/kg de material | 0,386 – 0,390 | −0,68 a −0,69 | corrigido de colisão (ver achado #6) |
| nº de chicanas | 0,179 / 0,103 | −0,069 / −0,069 | assimétrico — `faixa()` do grupo de chicanas |
| espessura da chicana | 0,099 / 0,067 | −0,062 / −0,062 | assimétrico |
| espessura bruta do espelho | 0,053 / 0,053 | −0,036 / −0,036 | não |
| custo_transporte | 0,047 / 0,047 | ~0,000 | 100% pass-through, não escala com fc |
| nº de tirantes | 0,004 / 0,004 | −0,008 / −0,008 | salta p/ **0,032 a −25%** — cruza o degrau `<10 → ≥10` |
| fator_preco | 1,000 | N/A | |
| impostos_pct | 0,189 | N/A | aqui SIM move `preco_com_impostos` (Cotacao é linear nisso — diferente do permutador!) |

---

## 3. Fora do ponto calibrado

⚠️ **Esta seção é HIPOTÉTICA para o permutador.** O `back_solve()` real
(`apps.cost_discovery.services`) hoje só existe para o FEIXE — importa e opera
exclusivamente sobre `FeixeInputs`/`quote_feixe`; não há grep de nada equivalente para
`quote_completo` em `apps.cost_discovery`, `apps.quotations.adapter` nem
`apps.tema_templates.services`. O `fc≈1,00` do BEU/BEM não saiu de um back-solve rodado em
produção — é o valor EMBUTIDO no seed, ajustado por quem construiu o seed para reproduzir
o referencial (gate 0,0%), não calibrado em runtime. O que esta seção mede é: **SE** o
back-solve do feixe fosse estendido ao permutador (extensão algebricamente trivial — a
mesma prova de afinidade em `fc` vale para os dois motores, ver docstring do harness),
o que aconteceria numa cotação nova, deslocada do job único usado para fixar aquele `fc`
no seed. Peguei esse `fc≈1,00` e apliquei a uma cotação hipotética **50% maior** e
**30% menor** (todos os drivers físicos em bloco), sem recalibrar — porque, mesmo NUM
MUNDO onde o back-solve existisse para o permutador, não HÁ como recalibrar uma cotação
nova contra um referencial que não existe.

| Caso | Bloco | Fator de escala efetivo (MO) | Fator de escala efetivo (total) | E de `setup_frac` no bloco |
|---|---:|---:|---:|---:|
| BEU | 1,5× | **0,866** | 0,801 | −0,024 |
| BEU | 0,7× | **1,172** | 1,255 | +0,020 |
| BEM | 1,5× | 0,865 | 0,797 | −0,024 |
| BEM | 0,7× | 1,173 | 1,261 | +0,020 |
| OF3683 | 1,5× | 0,710 | 0,680 | −0,002 |
| OF3683 | 0,7× | 1,373 | 1,411 | +0,001 |

Leitura: um job **50% maior** custa só **~80% mais** (não 150%) — economia de escala real,
porque os 20% de setup fixo por operação (`_SETUP_FRAC`) diluem. Um job **30% menor** custa
**~25-26% MAIS** que a proporção ingênua — o piso de setup pesa mais em jobs pequenos. E é
exatamente AQUI que `setup_frac` deixa de ser ruído: no ponto de referência sua elasticidade
é EXATAMENTE zero (§1); fora dele, ela aparece (pequena, −0,02 a +0,02, mas não-nula) — é a
prova concreta de que a calibração de 1 job só garante precisão NAQUELE tamanho de job,
não em geral.

---

## 4. Onde o achado fecha o ciclo — a fila do Wellington, por valor

As perguntas vivem em `sq-well/perguntas.seed.json` (w-001..w-013); w-014 só existe no app
vivo, descrita em `docs/discovery/SPRINT_S2_CUSTO_HORA.md` / `docs/BACKLOG.md`.

### Reordenação proposta (por dinheiro movido, não por data de criação)

| Ordem | Pergunta | Move quanto dinheiro (evidência desta varredura) |
|---|---|---|
| **1** | **w-014** — ligar o custo/hora real ao `TenantCostChain` | É o `fator_correcao_mo` — **0,29 a 0,44 de E_bruta em TODOS os 4 casos**, o maior knob controlável depois do markup. Hoje ele fica em 1,0 "porque sim"; sem w-014 o produto nunca sabe se está vendendo hora abaixo do custo. Nenhuma outra pergunta da fila tem impacto tão amplo e tão direto no preço. |
| **2** | **w-002** — 2º orçamento fechado de BEU/BEM (hold-out) | Testa se a economia de escala que medi em §3 (job 50% maior custa 80%, não 150%) é física real ou artefato de um único ponto calibrado. Sem um 2º job, não dá pra saber se o motor generaliza — e essa é a MESMA pergunta que o "fora do ponto calibrado" expõe estruturalmente. |
| **3** | **w-006** — espessura é o único campo "mínimo"? | `esp_casco_mm` é o campo de dims_form de MAIOR leverage single-field (E_bruta 0,30-0,32, empatado com preço de material) — bate em material E em duas famílias de solda (∝espessura²) ao mesmo tempo. A governança de quem pode editar esse campo (M2 do controle de margem) precisa estar certa PRECISAMENTE aqui. |
| **4** | **w-013** — áudio 20-30min narrando uma cotação | Mais barata de responder da fila (uma gravação) e explica o PORQUÊ dos achados #1/#3 abaixo — por que comprimento do casco não move MO (é bug de mapeamento, ou o Wellington sabe algo que o motor não sabe?), por que nº de tubos pesa tão pouco no BEU. Alto valor esperado por baixo custo de resposta. |
| **5** | **w-009** — memorial diverge do estimado, quanto come de margem | Já É quantificável por este harness: as economias/diseconomias de escala de §3 (±15-40% fora do ponto de referência) SÃO o mecanismo do vazamento que w-009 pergunta sobre. Responder isso com um número real (não a estimativa de engenharia) fecha o ciclo do M1-M4 (vazamento de margem). |
| **6** | **w-001** — orçamento fechado de designação NOVA | Não é sobre um campo, é sobre o motor inteiro: hoje só BEU/BEM têm o data sheet paramétrico (achado #3). Sem isso, toda designação fora de BEU/BEM/OF3683 é uma aposta. Estratégico, mas não muda a sensibilidade dos campos JÁ costeáveis — por isso fica depois de w-002/w-006. |
| 7 | w-007 — espessura-limiar de PWHT | Dinheiro real (todo um bloco de operações de tratamento térmico, hoje fixo/binário), mas não mensurável por ESTA varredura (é um flag discreto, não um campo contínuo) — valor real, mas não posso quantificar aqui. |
| 8 | w-003 — hora-máquina por operação além de mandrilar | Achei UM bug concreto no caminho (achado #8: MANDRILAR do BEU/BEM usa rate errado, R$120-240 por job, **0,02-0,09% do total** — pequeno). O verdadeiro valor de w-003 não é esse número pequeno, é o RISCO de que o mesmo tipo de erro exista, sem detecção, nas outras 63-68 operações que eu não testei uma a uma. |
| 9 | w-005 — passo/ângulo de furação | **Zero impacto hoje** — o motor não modela pitch/ângulo em NENHUM lugar (furação escala só por nº de furos). Não é urgente: mesmo que a resposta mude a prática real, o teto de impacto é a fatia "tubos" da MO (~3,7% do BEU). |
| 10 | w-004 — sequência/nomes do roteiro do espelho | Documentacional — não move nenhum R$ na varredura (é ordem/rótulo, não taxa nem driver). Importa para BOM/roteiro futuro (H2), não para preço hoje. |
| 11 | w-008 — governança pós-aprovação | Pura decisão de processo/workflow — fora do que este harness mede (não é campo do motor). Continua importante, só não compete nesta régua. |
| 12-14 | w-010/011/012 — negócio (cliente pagante, funil, preço) | Ortogonais ao motor de custeio — não avaliáveis por sensibilidade de campo. Sigam em paralelo, sem disputar a mesma fila. |

**Onde fui honesto sobre pergunta cara/impacto baixo**: w-005 (passo/ângulo) e w-004
(roteiro do espelho) são as duas que eu rebaixaria mais — não porque a resposta do
Wellington não importe para a fidelidade do motor, mas porque, pela ESTRUTURA atual do
motor, mesmo a resposta "certa" não move o preço em nada mensurável hoje. E onde fui
honesto sobre impacto alto mas resposta difícil: w-002 (2º orçamento fechado) é cara — exige
o Wellington desenterrar um job antigo — mas não tem substituto: é a ÚNICA forma de saber
se a economia de escala de §3 é real.

---

## 5. Achados suspeitos no motor (reportados, NÃO corrigidos — `pricing_engine/` é read-only)

1. **`comprimento_casco_mm` não move nenhuma hora de MO** — o driver físico `"comprimento"`
   (que escala fabricação/solda do CASCO) usa `comprimento_tubo_mm` como proxy
   (`tema_templates/services._physical_params`), não `comprimento_casco_mm` (que só entra
   via `dims_override` da VIROLA, afetando só material). Na prática, tubo e casco costumam
   ter comprimento parecido — mas se um projeto tiver cabeçotes que alonguem o casco além do
   feixe, o campo que o orçamentista preenche para isso (comprimento do casco) **não muda
   nenhuma hora de fabricação**, só o peso da virola. `E_bruta(comprimento_casco)=0,044`
   contra `E_bruta(comprimento_tubo)=0,244` no BEU — 5,5× de diferença.

2. **`perda_por_familia['espelho']` (Config de Engenharia V2/F1 Bloco A) está fiada para
   nada no fluxo real** — `PermutadorDataSheetForm.to_dims_override()` só sobrescreve os
   labels `TUBOS DE TROCA TÉRMICA` e `VIROLA`; o `dims_override` do espelho nunca é
   populado pelo data sheet. Como a leitura de `perda_por_familia` só acontece dentro do
   ramo `if dims_override and m["label"] in dims_override` (`permutador_quote.py`), a knob
   fica **matematicamente inerte** — um tenant pode configurar qualquer valor e o número
   final não muda 1 centavo. Confirmado numérica (E=0,000 nos 3 casos) e por leitura de
   código. Não é bug do motor per se (a knob FUNCIONA quando alcançável — testei isso em
   "SE o form editasse o espelho" e mostrou E_bruta≠0) — é um problema de FIAÇÃO entre o
   data sheet e a feature já entregue.

3. **OF3683 não é alcançável pelo data sheet paramétrico** — os labels do seed do OF3683
   (transcrição literal do manuscrito, ex. "VIROLA / CHAPA CASCO (IT.1)") não batem com os
   labels canônicos que `to_dims_override()`/`_physical_params()` esperam ("VIROLA",
   "TUBOS DE TROCA TÉRMICA"). Resultado: **nenhum campo dims_form pôde ser varrido para
   OF3683** nesta análise (11 de 22 entradas do BEU simplesmente não existem para o
   OF3683). Isso reflete a realidade de produto (é um backtest de job avulso, não uma
   designação TEMA catalogada — `validate_permutador_completo._REFERENCIAS` já trata isso
   diferente), mas vale deixar explícito: **qualquer designação nova (w-001) vai nascer
   com esse mesmo problema**, a menos que alguém padronize os labels do seed.

4. **`quote_completo(designacao)` sem `cost_chain` ≠ `quote_completo(designacao,
   cost_chain=TenantCostChain())`** — mesmo uma `TenantCostChain` totalmente vazia (sem
   NENHUM override) produz um número DIFERENTE do caminho `cost_chain=None`, porque
   operações com `horas`+`rate` no seed passam a usar `horas × cost_chain.hh(...)` em vez
   de `preco_referencial − ajuste`. Isso SÓ importa quando os dois caminhos divergem — e
   divergem, no achado #8. Como o PRODUTO real (`tema_templates.services.tenant_cost_chain()`)
   **sempre** passa uma `TenantCostChain` (nunca `None`), usei esse caminho como baseline
   do harness — é o número que o Wellington realmente vê, MANDRILAR errado incluído. O
   gate `validate_permutador_completo` usa `cost_chain=None`, então o gate está medindo o
   caminho de TESTE, não o de PRODUÇÃO — os dois divergem por R$120 (BEU) / R$240 (BEM),
   pequeno hoje, mas é o tipo de gap que cresce silenciosamente conforme mais seeds ganham
   `horas`+`rate`.

5. **`impostos_pct` nunca move `preco_com_impostos` no permutador** — em `quote_completo`,
   `preco_com_impostos = custo_total × fator_preco` é calculado primeiro (é o preço de
   TABELA, política comercial); só `preco_sem_impostos` é derivado dele por gross-up
   "por dentro" (`gross_up_icms`). Isso É coerente com ICMS por dentro no Brasil (a empresa
   fixa o preço ao cliente e calcula quanto sobra líquido de imposto) — não é bug — mas é
   contra-intuitivo o suficiente para confundir quem olhar a API esperando que
   `impostos_pct` mova o preço cobrado do cliente. No FEIXE (`quote_feixe`/`Cotacao`), a
   fórmula é a OUTRA convenção (`preco_com_impostos = preco_sem_impostos × (1+impostos_pct/100)`)
   — **os dois motores (feixe vs permutador) usam convenções de imposto INVERSAS uma da
   outra**, e nada no código sinaliza isso ao chamador. `test_sensibilidade.py` pinou esse
   comportamento (`test_impostos_pct_nao_move_preco_com_impostos_no_permutador`).

6. **A chave `(material, forma)` da `TenantCostChain.material_price` é MAIS GROSSA que a
   granularidade real do seed** — cada família (disco/chapa_retangular/anel/...) mapeia
   para uma forma via `_FAMILIA_FORMA`, mas o seed tem `price_kgf` DISTINTO por item, mesmo
   dentro do mesmo (material,forma). Achei 3 colisões no BEU/BEM e 3 no OF3683 — a pior é
   **SA-36/chapa no BEU/BEM, razão 19,4× entre o item mais barato (BARRAS DE SELAGEM,
   R$4,50/kg) e o mais caro (ALÇA IÇAMENTO, R$87,44/kg)**. Se um tenant configurar UM preço
   de tenant para "SA-36 chapa" (o fluxo normal do wizard A1-c), ele sobrescreve TODOS os
   itens dessa chave — silenciosamente 19× mais caro ou mais barato para os que não eram o
   alvo. No OF3683 (job transcrito item a item) o problema é maior: A-240 TP316L/chapa tem
   **16 itens** com razão 2,84× entre eles — o desvio de simplesmente tentar um preço
   "uniforme" nessa chave já é de **+15,3% no material** (R$555.046 vs R$481.520) SEM
   nenhuma perturbação intencional, e por isso **excluí a entrada "preço/kg de material" do
   OF3683 da varredura** (guarda automática no harness: `if abs(drift) < 2%`) em vez de
   reportar um número contaminado. O mesmo padrão existe no feixe (`SA-36/barra_chata`,
   razão 2,22×) — corrigido no harness usando o item de MAIOR peso como referência, mas o
   MOTOR em si não tem essa resolução; um tenant real pagaria o mesmo preço por qualquer
   peça que caia nessa chave.

7. **O back-solve (HIPOTÉTICO no permutador — ver §3) pode piorar o diagnóstico, não só
   falhar em melhorá-lo.** Para `dens_por_lado`/`preco_por_lado` no OF3683, `E_calib ≈
   1,77` — MAIOR que 1 em módulo. Isso significa: SE o permutador tivesse o mesmo
   mecanismo de recalibração que o feixe tem hoje, recalibrar `fc` para absorver um erro
   de 10% em densidade/preço de material distorceria o custo de mão-de-obra calibrado em
   **quase 18%** — o "remédio" seria quase 2× pior que o erro original, porque toda a
   correção (que deveria ser 100% material) é forçada inteira dentro do multiplicador de
   MO. É um argumento a favor de fazer w-002 (2º orçamento) ANTES de estender o back-solve
   ao permutador, não depois — um back-solve mal calibrado é pior que nenhum.

8. **`FAB-MANDRILAR-1` no BEU/BEM tem `rate` inconsistente com `preco_referencial`** — o
   seed traz `horas=3,0, rate=80,0` (BEU) mas `preco_referencial=360,0` — que só bate com
   `rate=120,0` (`3,0×120=360`), não `80,0` (`3,0×80=240`). `rates.py::engematex_seed()` já
   usa `120` para MANDRILAR — o `80` no seed de operações é a exceção errada. O gap
   aparece **quando a `TenantCostChain` em uso NÃO tem override de `rate_hh` para
   MANDRILAR** — nesse caso `hh_any()` cai no fallback (`o["rate"]=80`) em vez de
   `preco_referencial`; NÃO é "sempre que uma `TenantCostChain` está presente" (correção
   sobre uma formulação anterior deste relatório). Isolado: sem `cost_chain` (`None`, usa
   `preco_referencial` direto) → R$ 128.162,69; `TenantCostChain()` vazia (sem
   `rate_hh["MANDRILAR"]`) → R$ 128.042,69, **−R$ 120,00** exatos; uma chain com só
   `rate_hh={"MANDRILAR": 120}` (o valor correto) → volta a reproduzir R$ 128.162,69
   **bit-a-bit** — prova de que o gap é 100% isolado nesse rate (pinado em
   `test_mandrilar_gap_beu_e_exatamente_120_reais`). `rates.engematex_seed()` completo
   também corrige o MANDRILAR (tem `rate_hh["MANDRILAR"]=120`), mas dá **R$ 128.423,57**
   — NÃO "o gap some", porque `engematex_seed()` também sobrescreve `material_price` com
   valores que não necessariamente batem com os do seed do BEU, introduzindo uma
   divergência DIFERENTE e maior (R$ 260,88), de causa distinta. Não confunda os dois
   efeitos — a lição de w-003 continua de pé: só MANDRILAR tem `rate_hh` cadastrado por
   padrão, e é onde achei este bug por acidente escaneando 1 driver; não escaneei as outras
   168/147/214 operações uma a uma, nem os preços de material um a um.

9. **O canal de MATERIAL fica 100% INERTE a `nº de tubos`, até um clamp disparar — não é
   um degrau de tabela (`faixa()` nem existe em `permutador_quote.py`, só no motor do
   feixe).** Quando `dims_override` só muda `QUANTIDADE` (mantendo OD/ESP/COMPR no valor
   de referência), `peso_liquido_geom()` sempre chama a fórmula com `qtd=1` — então
   `liq_new == liq_seed` exatamente, e a perda auto-calibrada vira
   `perda_eff = peso_bruto_seed / (liq_seed × qtd_perturbada)`. Fazendo as contas:
   `peso_bruto_novo = liq_seed × qtd_perturbada × max(perda_eff, 1,0)`. Enquanto
   `perda_eff ≥ 1,0` (ou seja, enquanto a razão de tubos não superar a própria perda
   auto-calibrada de referência — no BEU, 1,1001, medido direto do seed:
   `peso_bruto=856,517kg`, `liq_seed=11,45kg`, `qtd_ref=68` → `perda_eff_ref=1,1001`), os
   termos se CANCELAM e `peso_bruto_novo = peso_bruto_seed`, CONSTANTE — o peso do material
   dos tubos fica **totalmente cego a quantos tubos você diga que tem**. O clamp só
   dispara (e o material passa a escalar linearmente) quando `qtd_perturbada >
   qtd_ref × perda_eff_ref` — no BEU isso é `qtd > 74,8`, ou seja, δ > **+10,01%**. É
   exatamente por isso que `E_bruta(nº de tubos)` fica travado em 0,034 em +10%/−10%/−25%
   (dentro da zona inerte ou bem abaixo dela) e salta pra 0,083 só em +25% (68→85,
   claramente além do limiar de 74,8). Mais grave que "elasticidade pequena": é
   "elasticidade ZERO por construção, dentro de uma banda de ±10% que é exatamente onde a
   maioria dos erros de preenchimento cai".

---

## 6. Limitações desta varredura

- **Mede a ESTRUTURA do motor, não a física da fábrica.** Massa/solda/área/volume são
  PROXIES geométricos (`massa∝D²·L`, `solda∝(comprimento+diâmetro)×espessura²`...), não
  medições. As elasticidades que reporto são corretas PARA O MODELO — se o modelo estiver
  errado (ex.: solda realmente escala com espessura¹, não espessura²), o número certo muda,
  mas o RANKING relativo entre campos provavelmente não muda muito.
- **Calibrado a 1 job por designação.** BEU e BEM têm 1 referencial cada; a §3 ("fora do
  ponto calibrado") já mostra que isso PRODUZ elasticidade zero exatamente no ponto
  calibrado — o resto do espaço de cotações é extrapolação, não interpolação.
  Estruturalmente, é a mesma limitação que motiva w-002.
- **`setup_frac` são defaults de engenharia, não medidos** (`_SETUP_FRAC` no código-fonte,
  20% para furação/chicanas, 10-15% para solda/comprimento/diâmetro) — a magnitude exata da
  não-linearidade em §3 depende desses números; o SINAL (economia em jobs grandes,
  penalidade em jobs pequenos) é estrutural e não depende dos valores exatos.
- **A varredura só perturba UMA entrada por vez** (exceto §3, que perturba um bloco
  inteiro). Interações de segunda ordem entre campos (ex.: diâmetro grande + espessura
  grande ao mesmo tempo) não foram medidas — cada `E_bruta`/`E_calib` é uma derivada
  parcial, não uma superfície completa.
- **OF3683 e o feixe não compartilham o mesmo espaço de entradas que BEU/BEM** (achados #3
  e #1) — a comparação entre casos é sobre a MESMA métrica (elasticidade), mas nem toda
  entrada existe em todo caso; a tabela §1 já reflete isso (cada campo lista onde foi
  medido).
- **`E_calib` mede o resíduo no `custo_mão_de_obra`, não no `custo_total`** — por
  construção, o `custo_total` SEMPRE reconcilia depois do back-solve (é a definição do
  mecanismo); o número que importa é o que sobra na composição interna, que é o que
  alimenta o diagnóstico de capacidade (`cost_structure.diagnosticar`). Isso é documentado
  extensamente no docstring do harness — vale reler antes de citar um `E_calib` fora de
  contexto.
