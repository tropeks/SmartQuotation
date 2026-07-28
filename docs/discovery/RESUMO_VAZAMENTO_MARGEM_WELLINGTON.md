# Controle de vazamento de margem — para validação do Wellington

**Contexto (2 min).** Levamos a sua ideia de "quem pode editar depende do tipo de cotação" para
uma análise de arquitetura profunda (dois revisores independentes). Ela evoluiu para algo mais
forte e mais alinhado ao objetivo comercial do produto: **impedir que a margem vaze** numa
cotação sem que a pessoa certa reveja. Precisamos do seu aval em 4 pontos.

---

## 1. Onde a margem vaza (confirme se bate com a realidade)

Uma cotação pode perder margem por 4 caminhos. Marque se algum está errado ou faltando:

| Vetor | Exemplo | Dono natural da revisão |
|---|---|---|
| **Comercial** | baixar markup, rate (R$/h) ou preço de material | Gestor comercial |
| **Produção** | mexer no tempo de setup ou na % de perda/scrap | Engenharia (know-how de fabricação) |
| **Engenharia** | mudar corte de chicana, espessura, folga → muda peso e horas | Engenharia |
| **Ajuste manual na EAP** | sobrescrever direto um custo/hora de uma linha, "no braço" | (hoje ninguém revisa) |

☐ Os 4 batem. ☐ Falta um: __________ ☐ Um está errado: __________

---

## 2. A mudança mais importante: controle na ASSINATURA, não no teclado

Você tinha dito "em projeto novo, só o engenheiro edita os parâmetros de engenharia". A análise
mostrou um risco nesse formato de **travar o teclado**: numa firma com um engenheiro só (você), se
você viaja, o orçamentista não consegue nem rascunhar — e a saída dele seria compartilhar seu
login ou marcar tudo como "reposição" pra destravar. Isso **destrói** a rastreabilidade que a
gente quer criar.

Proposta (modelo "verificação suave"):
- O orçamentista **pode digitar** valores de engenharia numa cotação (agiliza o trabalho dele).
- Mas esses valores ficam marcados como **"não verificados"**, e a cotação **não converte em
  Ordem de Fabricação** enquanto você não revisar e **assinar**.
- Ou seja: o bloqueio vive na **sua assinatura técnica (CREA/ART)**, exatamente onde já está a
  responsabilidade legal — não numa trava de digitação.

**Pergunta:** isso te protege igual ou melhor que travar a edição? Ou você quer, além disso, que
em projeto novo o campo de engenharia fique **realmente bloqueado** pro orçamentista (mesmo com o
custo de você virar gargalo quando estiver fora)?

☐ Verificação suave (assinatura é o controle) me atende
☐ Quero bloqueio duro em projeto novo, mesmo sendo gargalo
☐ Depende (explico)

---

## 3. Sua assinatura vira "consciente de mudanças"

Hoje, quando você assina uma cotação, assina um retrato dela. Proposta: se **depois** da sua
assinatura alguém mexer num campo de engenharia, o sistema mostra pra você exatamente **o que
mudou** (campo, de→para, quem, quando, impacto na margem) e **exige re-assinatura** antes de virar
OF. Você nunca assina "às cegas" uma cotação que mudou.

☐ Isso me protege, quero. ☐ Ajustar: __________

---

## 4. "Reposição/parte" continua liberando o orçamentista

Quando a cotação é **transcrição de um projeto assinado do cliente** (reposição/parte), o
orçamentista mexer nos valores de engenharia é **fidelidade ao documento do cliente**, não
vazamento. Nesse caso ele edita livre, e o sistema **registra a fonte** (nº do desenho, revisão,
data) — que pode sair na proposta como "dados conforme documento do cliente X rev.Y".

☐ Correto. ☐ Ajustar: __________

---

## ⚠️ Um alerta que a análise levantou (independe da feature)

Hoje, no sistema atual, é possível: aprovar/assinar uma cotação → depois **baixar um custo pelo
ajuste manual da EAP** → e converter em OF **sem que a assinatura perceba a mudança**. É um furo
real de margem já aberto. A primeira entrega (M1) tampa exatamente isso.

---

*A classificação de quem revisa o quê é decisão sua — o sistema só executa. Obrigado, Wellington.*
