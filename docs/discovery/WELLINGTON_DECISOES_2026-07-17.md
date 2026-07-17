# Decisões que preciso do Wellington — features 17/07/2026

> **De:** Claude (arquiteto/dev) · **Para:** Wellington (PE, co-autor)
> **Contexto:** análise dos 9 áudios (`SmartQuotation_Features_Wellington_2026-07-17.md`) confirmada contra o código.
> **Como usar:** cada item traz meu **default proposto**. Se concordar, responda só "ok no item X". Onde discordar, me diga o valor/regra correta. **Só os itens abaixo bloqueiam entrega** — todo o resto já está sendo implementado em paralelo (sprints F1, F4/F6, F8a).

---

## Resumo do que NÃO precisa de você (já em execução)
- **F1** (hora-máquina no cálculo): bug confirmado — a HM está na fórmula, mas a *taxa* de hora-máquina chega zero em quase toda operação e não há campo para editá-la. Estou expondo taxa HH e HM editáveis no drawer, com default do cadastro de Rate. **Só preciso de você no item Q1 abaixo** (política de default da taxa HM).
- **F4/F5/F6** (completo × partes): decisão de arquiteto tomada — adotar agora, reusando o campo `scope` que já existe. **Preciso só do aval do item Q6.**
- **F8a** (campos do feixe que já existem no motor: fixo/flutuante, espaçadores, união tubo-espelho): em execução. **Ângulo de furação depende do item Q3.**
- **F3** (layout roteiro separado × aninhado): você delegou ao UI/UX — decidido, sem bloqueio.

---

## Decisões que preciso de você

### Q1 — F1: default da taxa de hora-máquina
Hoje o motor só atribui taxa de hora-máquina (R$/h-máquina) à operação **OP-MANDRILAR** (~R$80/h); todas as outras vêm com taxa HM = 0. Vou expor o campo editável no drawer com default vindo do cadastro.
**Default proposto:** manter default 0 para operações sem taxa-máquina cadastrada (o usuário preenche caso a caso, como você descreveu no áudio), e semear a taxa HM das operações que **têm** recurso-máquina a partir do cadastro de Rate (RateHM).
**Preciso saber:** quais operações, além da mandrilar, têm hora-máquina relevante (ex.: furação CNC, corte a laser, calandragem)? Se tiver uma tabela de R$/h-máquina por recurso, me manda que eu semeio. Se não, fica 0-default + edição manual.

### Q2 — F1/F2: nomes e ordem das operações do roteiro do espelho
No áudio F2 você citou "usinar, cortar, [expandir], traçar furos". A transcrição ficou dúbia em "expandir/espicionar".
**Preciso saber:** a sequência e os nomes corretos do roteiro do **espelho** (tubesheet). Ex.: traçar furos → furar → mandrilar (expandir tubo no espelho) — confirma os termos que a ENGEMATEX usa.

### Q3 — F8: ângulo de disposição da furação (30/45/60/90)
O motor hoje só conhece layout "triangular/quadrado" e **não** usa ângulo (30/45/60/90) no custo. Expor o ângulo é fácil; a questão é o efeito no custo.
**Preciso saber:** o ângulo do layout **muda o custo/horas** (via passo → nº de furos/área do espelho), ou por ora é só informação documental na cotação?
**Default proposto:** por ora tratar como campo documental (não altera custo). Se você quiser que dirija o custo, me diga a relação passo↔ângulo que usam.

### Q4 — F8: recorte da chicana (baffle cut)
Hoje o sistema guarda o corte como **"altura restante" (mm)**. Você disse "recorte da chicana".
**Default proposto:** manter altura restante (mm), que é o que o motor usa (TEMA RCB-4, hc = OD − corte).
**Preciso saber:** prefere que o orçamentista informe o corte em **% (padrão TEMA, ex. 25%)** e o sistema converta para mm? (dá pra oferecer os dois.)

### Q5 — F9: tubo em U desenvolvido + emenda
Para calcular o tubo reto desenvolvido a partir do U, preciso fixar duas convenções.
**Default proposto:**
- Comprimentos padrão de mercado = **6,95 m** e **12 m** (configuráveis).
- Comprimento reto desenvolvido = 2 × perna reta + comprimento desenvolvido da curva (π × raio de curvatura). Raio mínimo de curvatura = **1,5 × OD do tubo** (TEMA RCB).
**Preciso saber:** confirma 6,95 m e 12 m? E o raio de curvatura que vocês usam (1,5×OD? outro?). Emenda sinalizada quando desenvolvido > comprimento padrão.

### Q6 — F5/F6: escopo da Fase 1 (aval do faseamento)
Como arquiteto, minha recomendação é adotar já a separação **"equipamento completo × partes"** (o dado já existe no banco). Fase 1 oferece **apenas**: *equipamento completo* e *feixe tubular* (reto/U). Partes avulsas (só cabeçote, só casco, tampa…) ficam para a **Fase 2**, e cada nova designação TEMA custeável exige um job real de calibração (ver Q7).
**Preciso saber:** confirma o escopo da Fase 1 = {completo, feixe} só?

### Q7 — F7: designações TEMA custeáveis
Hoje só **BEU** e **BEM** têm custeio validado (a 0,0% vs gabarito). Qualquer outra designação (ex.: **AES**) precisa de um **job real fechado** para gerar o seed de calibração — não dá para "carregar da norma" sozinho, porque os pesos/horas vêm do gabarito.
**Preciso saber:** quais designações você precisa a seguir (AES? outras?) e você consegue me passar um orçamento fechado real de cada uma para eu gerar o seed?

---

### Q8 — F10: orçamentista pode converter cotação em OF?
O Rom pediu para tornar isso **configurável** (toggle por tenant), o que resolve a pendência que estava em aberto com você. A mecânica entrega o toggle; o **default** fica conservador.
**Default proposto:** orçamentista **NÃO** converte (= comportamento atual: só engenheiro/gestor_comercial/admin). O admin liga o toggle se, no fluxo real da ENGEMATEX, o orçamentista converte.
**Preciso saber:** no fluxo real, o orçamentista converte cotação em OF? Se sim, deixo o default já ligado.

### Q9 — F10: quem edita a página de permissões/aprovações?
**Default proposto:** só **admin** edita os níveis de acesso e o fluxo de aprovações.
**Preciso saber:** o **gestor_comercial** também deve poder editar essa config, ou fica só admin?

### Q10 — F10: fluxo de aprovações
Hoje a conversão cotação→OF exige aprovação técnica (engenheiro com CREA) antes de liberar — isso é compliance e fica como estágio **fixo** (não desligável).
**Preciso saber:** existe algum outro estágio de aprovação no processo real (ex.: aprovação comercial/gestor antes de virar OF)? Se sim, quem aprova e é obrigatório?

---

## Itens que já resolvi por default (só reverta se discordar)
- **F3:** decisão de UI/UX (roteiro aninhado no item vs. lista separada) — você já aceitou o que o UI/UX definir.
- **F8 "âmbito de tubo"** = bitola/OD do tubo — já existe no form (`tubo_od_spec` + parede BWG). ✔
- **Feixe reto × U** — o motor já distingue de forma robusta (`is_u`, `OP-CURVAR-U` etc.). ✔
