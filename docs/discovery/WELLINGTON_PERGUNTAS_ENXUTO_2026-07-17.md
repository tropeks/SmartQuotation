# Wellington — o que preciso de você (versão enxuta)

Wellington, revisei tudo e a maioria das dúvidas eu consigo resolver sozinho no sistema
(viram campos configuráveis com um valor padrão que você troca depois). **Sobrou só o que
depende do chão de fábrica da ENGEMATEX** — número que só existe num equipamento real e que
o sistema não tem como adivinhar. São 3 coisas.

---

## 1. Orçamento real de designação TEMA nova (o pedido principal)

Hoje o motor custeia **BEU** e **BEM** batendo 0,0% com o gabarito real. Para custear qualquer
**outra** designação (AES, NEN, BEP…) com a mesma precisão, eu preciso de **um orçamento real
já fechado** dessa designação — porque as horas de solda, usinagem e o peso vêm do trabalho
real, não da norma. Sem um job real, eu só chutaria.

**Preciso de você:**
- Quais designações você quer custear a seguir? (AES? outra?)
- Para **cada uma**, um **orçamento fechado real** (mesmo formato do BEU/BEM que você já me
  passou) — é o que eu uso pra calibrar o motor a 0%.

---

## 2. Operações com hora-máquina (pra eu preencher os padrões)

O motor só tem taxa de hora-máquina cadastrada na **mandrilar** (~R$80/h). Todas as outras
entram com hora-máquina = 0, e o usuário preenche à mão. Isso funciona, mas se você me der os
valores eu já deixo **pré-preenchido** — o usuário não começa do zero.

**Preciso de você (opcional, só melhora o padrão):**
- Quais operações além da mandrilar têm hora-máquina relevante? (furação CNC, corte a laser,
  calandragem…)
- Se tiver uma tabela de **R$/hora-máquina por recurso**, me manda que eu semeio. Se não tiver,
  fica 0 + edição manual (sem problema).

---

## 3. Roteiro do espelho (tubesheet) — confirmar a sequência

No áudio você citou "usinar, cortar, [expandir], traçar furos", mas a transcrição ficou dúbia
no "expandir/espicionar". O roteiro é editável no sistema, mas se o **padrão** já sair certo,
ninguém precisa corrigir.

**Preciso de você:**
- Confirma a **sequência e os nomes** que a ENGEMATEX usa no espelho. Ex.: traçar furos →
  furar → mandrilar (expandir tubo no espelho) — é isso? Corrige os termos.

---

## O que **NÃO** precisa de você (já resolvi por padrão configurável)

Tudo abaixo virou campo ajustável no sistema, com um valor padrão pesquisado. **Só me avise se
discordar de algum default** — não precisa responder um por um:

| Assunto | Como ficou (default) |
|---|---|
| Recorte da chicana (baffle cut) | campo em **% do diâmetro** (padrão **25%**), converte pra mm sozinho |
| Comprimento de tubo padrão | **6,10 m e 12 m** configuráveis (o "6,95 m" do áudio era erro de transcrição — não usei) |
| Raio mínimo da curva em U | **1,5 × diâmetro do tubo** (norma TEMA) |
| Ângulo/passo da furação | campo exposto, padrão TEMA (passo mín. **1,25 × OD**) |
| Orçamentista converte cotação em OF | **liga/desliga por empresa** (padrão: não converte — você liga se quiser) |
| Quem edita permissões e fluxo de aprovação | **configurável** (padrão: só admin) |
| Estágios de aprovação (ex.: comercial após a técnica) | a empresa **monta o próprio fluxo** na tela — a técnica com CREA fica fixa (compliance) |

---

*Resumo: os 3 pedidos de cima são o que trava a precisão do motor. O resto roda sozinho com os
padrões — é só ajustar na tela se a ENGEMATEX fizer diferente.*
