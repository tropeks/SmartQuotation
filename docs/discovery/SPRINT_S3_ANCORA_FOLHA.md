# Sprint S3 — tirar a calibração do benchmark contaminado

**Contrato.** Gate Legatus: SEARCH → PLAN → RED → GREEN → VERIFY → REVIEW → EVIDENCE.

## O problema, na frase do Wellington

> *"O custo é meio que chutado por benchmark, então ele nunca é aferido no sentido de
> saber se aquilo está cobrindo as despesas da empresa. A parte de matéria-prima está
> ok, agora a parte de mão de obra não vai estar ok."* — áudio de 2026-07-16

O `back_solve` que existe hoje (`apps/cost_discovery/services.py:64`) faz bisseção no
`fator_correcao_mo` até o motor **reproduzir o preço** de um job de referência. A âncora
é o preço da proposta.

Se o preço vem de benchmark e a parte de mão de obra "não vai estar ok", então o fator
encontrado **absorve o erro do preço**. Calibramos o motor para errar igual — com
precisão de 0,1%.

## A troca

Mesma mecânica, âncora diferente: em vez de *"qual fator reproduz o preço cobrado"*,
perguntar *"qual fator reproduz as horas que a fábrica realmente pagou"*.

```
fator = horas efetivamente pagas no período  ÷  horas estimadas para as OFs do período
```

O dado (1) sai da folha/cartão de ponto e (2) o sistema já tem, somando a EAP. Nenhum
apontamento de chão de fábrica é necessário — é a maior alavanca disponível hoje.

### Uma descoberta que simplifica

O `back_solve` atual precisa de **bisseção** porque o preço passa por markup e impostos:
a relação fator→preço não é trivial de inverter.

Ancorado em horas, não precisa. O `fator_correcao_mo` é um **multiplicador escalar
linear das horas** (`pricing_engine/operations_registry.py:47`, `FC(i)`), então:

```
horas_reais = horas_estimadas × fator   →   fator = horas_reais ÷ horas_estimadas
```

Divisão direta. Sem bisseção, sem tolerância, sem iteração — e exato em vez de
convergente. A troca de âncora não é só mais honesta: é mais simples.

## PLAN

| # | Entrega |
|---|---|
| 1 | Somar as horas estimadas das OFs/cotações de um período (da EAP persistida) |
| 2 | `fator_por_folha(horas_pagas, horas_estimadas)` → fator + diagnóstico |
| 3 | Comando que roda a conciliação e mostra o resultado, com `--simular` |
| 4 | Testes: a conta, o período vazio, o caso degenerado (estimadas = 0) |

**Não aplica automaticamente.** Mudar `fator_correcao_mo` reprecifica todas as cotações
do tenant. Mesma natureza da w-014 — o comando mostra e só aplica com `--aplicar`
explícito, e a decisão de adotar é do dono da margem.

## Limites honestos (a registrar no resultado, não esconder)

- Dá o **viés agregado**, não diz qual operação estoura. Isso só o apontamento resolve.
- Exige período razoavelmente fechado: OF que começou antes ou terminou depois distorce.
- Assume que a fábrica estava trabalhando naquelas OFs. Retrabalho, serviço avulso e
  ociosidade entram no bolo e inflam o fator.

O terceiro limite é o mais sério e **é informação, não defeito**: a diferença entre
horas pagas e horas produtivas é exatamente a capacidade ociosa que o Nível 0 (S2)
mede pelo outro lado. Os dois números conversam.

---

## GREEN

`apps/cost_discovery/reconciliacao.py` + comando `conciliar_horas`, **17 testes verdes**.

- `horas_estimadas_de(cotações)` soma HH+HM da EAP persistida, **ignorando operação não
  aplicável** — o que está marcado como não aplicável não consome hora da fábrica.
- `reconciliar(pagas, estimadas)` devolve fator, desvio % e diagnóstico. Divisão direta,
  sem bisseção. Tolerância de 5%: abaixo disso é ruído de arredondamento e de fronteira
  de período, não viés de estimativa — reagir a ele seria perseguir o próprio erro de
  medição.
- `limites_conhecidos()` sai **junto** do número, sempre. Um fator de correção sem os
  limites vira verdade absoluta na cabeça de quem lê, e a próxima decisão é tomada sobre
  uma medida que não suporta o peso.
- O comando só grava com `--aplicar` explícito. Mudar `fator_correcao_mo` reprecifica o
  tenant inteiro; isso não pode ser efeito colateral de uma consulta.

## VERIFY

- `apps.cost_discovery` + `apps.materials.tests_vigencia`: **29 OK**
- `apps.materials` + `apps.cost_structure` + guard-rails da EAP: **76 OK**
- Gates do motor: feixe −2,9% · permutador BEU/BEM 0,00% — OK
- `makemigrations --check`: sem pendência

## Backlog

- **S3.1** o período usa `Quotation.created_at`; o correto é a data de ENTREGA da OF.
  Depende de a OF ter data de conclusão confiável — verificar em `apps/production`.
- **S3.2** cruzar o fator da folha com a capacidade ociosa do Nível 0: a diferença entre
  horas pagas e horas produtivas é a mesma grandeza medida por dois caminhos, e os dois
  números têm de fechar.
