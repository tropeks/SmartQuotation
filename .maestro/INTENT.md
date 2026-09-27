<!-- maestro-intent v1
version: 3
ts: 2026-09-27T17:16:54-03:00
head: 74d8149bf6fb3df9aaa681b2b8cbc7f230bac480
author_session: d125f612-fe58-44f9-9789-3bae25d86d02
hash: be9e1bc4
-->
# Direção — SmartQuotation

> **Carimbada pelo Capitão em 27/09/2026** (decisão 01M3J59NS40AM6SHH0198B311E do app,
> DP-52), aprovada como redigida. `maestro intent --bump` sobe a versão só com o carimbo
> dele. Redigida pelo Conformador a partir de `docs/PRODUCT_VISION.md`,
> `docs/PROJECT_BRIEF.md`, `docs/ROADMAP.md`, `docs/RESUMO_WELLINGTON.md`,
> `docs/ARCHITECTURE.md`, `docs/BACKLOG.md` e de `cognitive-core/docs/VISAO.md` e `FASES.md`
> (Fase 1). Onde as fontes divergem, vale a PRODUCT_VISION (10/07) sobre o PROJECT_BRIEF
> (2025), e a FASES v0.3 (26/09) para o que é do Core. Incorpora as respostas técnicas do
> Diretor de 27/09. Histórico: v1 foi o template vazio; v2 é a primeira versão carimbada;
> **v3** (27/09, decisão 01M3J7RNGCM5Y22RHHZSFWJPGR do Capitão) troca, em §Limites, "o adapter
> é o único acoplamento" por "o único caminho que PERSISTE resultado do motor é o adapter",
> travado por import-linter.
>
> **Pendências** (não são limites nem resultado ainda):
> - Candidatas e prazo da beta multi-empresa: com o Capitão.
> - Retenção de cotações e cálculos por 15 anos (NR-13, do `PROJECT_BRIEF`): espera a DP-27
>   (jurídico, J-27).

## Problema
Fabricante brasileiro de equipamento sob encomenda (caldeiraria média e pesada, trocadores
de calor, vasos) orça em planilha artesanal ou em ERP genérico que não entende EAP
paramétrica, ASME nem TEMA. O orçamento leva dias, depende de uma ou duas pessoas que
guardam o conhecimento, não é rastreável e não se liga à fabricação: a OF é redigitada, e
ninguém sabe se o preço cobre o custo fixo e a margem. Software de cálculo de vaso
(PVElite, Compress) é caro e não forma preço. O custo de errar é concreto: cotação abaixo
do custo ganha o pedido e perde dinheiro na fábrica.

## Público
**Primário:** PME brasileira de caldeiraria sob encomenda (job shop ETO). Quem usa, e a dor
que decide a feature: **orçamentista** (monta a cotação a partir da folha de dados, hoje em
dias), **engenheiro habilitado** (confere e assina sob CREA; responde pelo cálculo),
**gestor comercial / dono** (preço, margem, aprovação da proposta), **PCP e produção**
(recebem a OF com lista de material e roteiro sem redigitar).
**Design partner:** ENGEMATEX, com o engenheiro de domínio (PE) validando as regras
normativas. **Beta:** 1 a 2 caldeirarias além dela antes de vender.
**Consumidor de plataforma:** o Quantum Cognitive Core, do qual o SmartQuotation é a
primeira vertical (F1). O Core usa as capabilities do produto; o produto mantém a
autoridade sobre o próprio negócio (VISAO §6).

## Resultado
"A melhor cotação técnica do Brasil industrial": um pedido com folha de dados vira cotação
calculada pelo motor, com EAP editável (materiais e horas de MO), conferida e assinada pelo
engenheiro, aprovada, transformada em proposta e **enviada uma vez**, e, quando ganha,
convertida em OF que segue para o ERP do cliente sem redigitação.

Sucesso verificável, nesta ordem:
1. **Fidelidade do motor:** gates do feixe (−2,9%) e do permutador BEU/BEM (0,0%) intactos,
   e cada novo tenant calibrado por 2 a 3 jobs históricos (golden cases como contrato).
2. **Prova da F1 do Core** (FASES §4), com o design partner: ≥ 50 itens reais em 3 semanas;
   50 envios concorrentes com a mesma chave → 1 despacho; queda simulada → 0 reenvio sem
   conciliação; 0 envio fora do cadastro de destinatários; responsável e plano de operação
   aprovados antes da primeira sugestão; linha de base da métrica norte (horas humanas por
   proposta emitida) fechada.
3. **Beta multi-empresa:** 1 a 2 caldeirarias além da ENGEMATEX operando o ciclo
   cotação → OF sem suporte do dev e sem o Django admin.

## Prioridades
1. **Número certo e rastreável acima de feature.** Toda mudança que toca o motor, o adapter
   ou a cadeia de custo passa pelos gates; custo é derivado (motor ou roll-up), nunca
   digitado; cada valor carrega a origem, e o preço é rotulado `referencial`
   (benchmark, back-solve, histórico) ou `validado por custo` (cadeia de custo, capacidade e
   margem rastreáveis).
2. **A assinatura vale o que assina.** Snapshot de cálculo com hash, aprovação técnica com
   CREA, OF montada a partir do snapshot assinado, trilha de quem mudou o quê. Nenhum
   caminho (admin, API, Core) altera número assinado sem invalidar a assinatura.
3. **F1 do Core: envio seguro.** Capabilities com token delegado por escopo, `proposal.send`
   com idempotência, reserva prévia no ledger, conciliação após queda, destinatário e
   provedor fechados em lista. As garantias de envio são pré-condição do primeiro envio real,
   não melhoria posterior.
4. **Inteligência de custo e margem.** Custo fixo e overhead como linha separada e
   inspecionável, horas orçadas contra realizadas por operação, alerta de preço mínimo que
   avisa e não bloqueia. Ligar o custo/hora aferido ao motor (S2.2) é decisão do dono da
   margem, não do código.
5. **Reduzir o bus factor do domínio.** Os 7 itens provisórios de norma só viram "valor de
   norma" com a chancela do PE; o conhecimento dele vira parâmetro auditável e editável por
   tenant (calibração na UI), não comentário no código.

## Limites
Django 5.2 + DRF + Celery + PostgreSQL, schema-per-tenant (django-tenants), sessão auth,
templates + HTMX; PT-BR na interface. `pricing_engine` é Python puro, sem Django, e o único
caminho que **persiste** resultado do motor é `apps/quotations/adapter.py` (outros módulos
podem chamar o motor para simular ou exibir, nunca gravar o resultado), travado por
import-linter no CI. Custo = peso **bruto** (cobra perdas), com bruto,
líquido e perda exibidos; cotação é snapshot, não referência viva ao template. Gates do motor
(feixe e permutador) nunca regridem; o CI não relaxa gate sem ordem. Número de norma
provisório aparece marcado como estimativa na tela, no código e na memória de cálculo até
a chancela do PE. Contrato de doc canônico mudou, o doc emenda no mesmo changeset.
Nenhum dado real de cliente (preços, jobs, cadastros da ENGEMATEX ou de outro tenant) sai
do repositório nem da instância dele; fixtures e reproduções usam dado sintético ou
referencial já versionado.
Com o Core: modelo sugere, ordena e sinaliza, nunca decide sozinho; regra determinística
(recálculo pelo motor, hash do payload aprovado, destinatário, limites) antes de todo efeito
externo; humano no irreversível; engenheiro habilitado assina o que é dele; dado externo
(e-mail, PDF, planilha do cliente) é dado, não instrução. O Core roda em sombra e depois em
`act_with_approval`, nunca além, na F1.
Autorização do envio com passkey e step-up (F1-32) antes do primeiro envio real; papel
privilegiado não opera efeito externo só com senha.
Fiscal e financeiro entram por integração com o ERP do cliente, nunca reconstruídos. O ERP
prioritário é o **Nomus** (decisão de 10/07); Protheus, Omie, SAP B1 e Bling já existem no
código como conectores. UI nova nasce na
identidade Prancha (`docs/DESIGN_PRANCHA.md`, vigente). Nada em produção real sem gate ship.

## Fora de escopo
Reconstruir fiscal (NF-e, NFS-e, SPED) ou financeiro próprio; competir com ERP genérico em
back-office agora. Portal do cliente e app mobile. Expansão normativa além de trocadores e
vasos (tanques API 650/620, tubulações B31.x, estruturas) antes da beta multi-empresa.
Multi-moeda e PED/exportação. PVElite como gate de CI enquanto não houver casos de
regressão dele no repo. A pele Tasy Neumorphic (superada pela Prancha). Autonomia do Core
além de `act_with_approval` e qualquer promoção automática de classe de ação.
