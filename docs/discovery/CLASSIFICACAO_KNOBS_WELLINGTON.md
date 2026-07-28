# Quem pode mudar cada parâmetro? — para validação do Wellington

**Contexto (2 min de leitura).** No SmartQuotation, vários números que antes eram fixos no
sistema agora são **configuráveis por empresa** ("knobs"). A pergunta que você levantou é a
certa: **quem deve ter permissão de mudar o VALOR PADRÃO de cada um?**

Sua tese: o **orçamentista** deve ter liberdade nas variáveis de produção; só devem exigir
**engenheiro** os números que, se errados, podem causar **acidente** (falha estrutural). O
preço/margem é outro tipo de risco — comercial, não de segurança.

Concordamos, com um ajuste: um erro de preço não é risco de segurança, mas também não deveria
ser 100% livre — o dono natural dele é o **gestor comercial**, não o engenheiro. Então
propomos **três baldes**, não dois:

| Balde | Quem edita | Precisa de aprovação? |
|---|---|---|
| 🔴 **Segurança** | só **Engenheiro** (CREA) | não — o engenheiro é o responsável legal; edita direto |
| 🟡 **Comercial** | Orçamentista **propõe** → **Gestor comercial** aprova | sim (proposta + aprovação) |
| 🟢 **Livre** | **Orçamentista** edita direto | não (mas fica registrado no histórico) |

> **Importante — o que NÃO muda:** toda cotação convertida em Ordem de Fabricação continua
> exigindo **sua assinatura técnica (CREA/ART) sobre aquela cotação específica**. Esta tabela é
> só sobre os **valores-padrão da empresa** (a régua), não sobre o resultado de cada cotação —
> esse você continua assinando caso a caso.

Além disso, os knobs de segurança terão **limites de norma travados no sistema** (faixa TEMA do
corte de chicana, raio mínimo de curva por diâmetro, espessura mínima ASME): nem o engenheiro
consegue salvar um valor fora da norma. Norma não é opinião da empresa.

---

## A tabela — marque a coluna "Sua decisão"

### 🔴 Proposta: SEGURANÇA (só engenheiro edita)

| Parâmetro | O que é, em campo | Por que segurança | Sua decisão |
|---|---|---|---|
| **Corte de chicana (%)** | % de corte do baffle (padrão 25%) | Chicana é suporte de tubo; corte errado muda o vão livre → vibração e fadiga do feixe | ☐ concordo ☐ mudar p/ ____ |
| **Raio mínimo de curva em U** | Fator do raio mínimo do tubo em U (padrão 1,5×) | Raio pequeno afina a parede na curva → ponto fraco sob pressão | ☐ concordo ☐ mudar p/ ____ |
| **Modo de compatibilidade TEMA** | Rigor da conformidade TEMA aplicada | Relaxar conformidade é decisão técnica de norma | ☐ concordo ☐ mudar p/ ____ |
| **Defaults de pressão→espessura (ASME)** | Espessura mínima por pressão (você validou em 19/06) | Núcleo da integridade sob pressão | ☐ concordo ☐ mudar p/ ____ |

### 🟡 Proposta: COMERCIAL (orçamentista propõe, gestor comercial aprova)

| Parâmetro | O que é, em campo | Por que comercial | Sua decisão |
|---|---|---|---|
| **Rates (R$/hora homem e máquina)** | Custo-hora de mão-de-obra e de máquina | Erro = preço errado, não acidente | ☐ concordo ☐ mudar |
| **Preço de material (R$/kg por forma)** | Tabela de preço da matéria-prima | Erro = preço errado | ☐ concordo ☐ mudar |
| **Markup (margem)** | Margem aplicada sobre o custo | Puro comercial | ☐ concordo ☐ mudar |
| **Impostos** | Carga tributária na formação de preço | Puro comercial | ☐ concordo ☐ mudar |
| **Fator de calibração da MO** | Ajuste fino do tempo de MO contra job real conhecido | É a "verdade calibrada" do sistema; mexer nele reprecifica tudo | ☐ concordo ☐ mudar |

### 🟢 Proposta: LIVRE (orçamentista edita direto)

| Parâmetro | O que é, em campo | Por que livre | Sua decisão |
|---|---|---|---|
| **Comprimentos comerciais de tubo** | Lista de comprimentos de tubo disponíveis (6 m, 12 m…) | Logística de compra, sem efeito estrutural | ☐ concordo ☐ mudar |
| **Limiar de furação (radial vs CNC)** | Nº de furos a partir do qual usa CNC (padrão 600) | Escolha de método/processo; muda tempo, não segurança | ☐ concordo ☐ mudar |

---

## ⚠️ Dois pontos onde precisamos da sua decisão explícita

**1. Fração de setup (`setup_frac`) e perda/scrap por família (`perda_por_familia`).**
São o "tempo fixo de preparação" por operação e a % de perda de material por tipo de peça.
Você tende a vê-los como **variável de produção** (→ livre para o orçamentista). Nosso receio
técnico: como eles entram direto no **custo final**, deixá-los 100% livres deixa o orçamentista
mexer no preço **sem passar pela aprovação comercial** (mexe no "tempo/perda" em vez do markup).
O ajuste caso-a-caso do job já é possível dentro da própria cotação; o que está aqui é o
**valor-padrão da empresa**, que é calibração.

- ☐ Concordo: são **comerciais** (orçamentista propõe, gestor aprova)
- ☐ Não: são **livres** de produção (orçamentista edita direto)
- ☐ Meio-termo: livres **dentro de uma faixa**, fora da faixa vira proposta — faixa: ____

**2. Parâmetros de processo (física→horas — ex.: tempo por furo, taxa de solda).**
Hoje são valores versionados que convertem física em horas. Um erro muda o **tempo estimado**
(→ custo), não a integridade da peça.

- ☐ São **comerciais** (afetam custo → orçamentista propõe, gestor aprova)
- ☐ São **livres de produção** (orçamentista, chão de fábrica, edita direto)
- ☐ Alguns são segurança? Quais: ____

---

*Qualquer linha que você mudar, a gente reclassifica no sistema. A classificação é sua — o
sistema só executa. Obrigado, Wellington.*
