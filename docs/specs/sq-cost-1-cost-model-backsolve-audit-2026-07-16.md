# SQ-COST-1 — Spec: modelo de estrutura de custos + auditoria de contaminação do back-solve

**Data:** 2026-07-16
**Tipo:** design/spec (nenhuma migration, nenhum código de app, nenhuma mudança de engine)
**Branch:** `sdk/sq-cost-1-backsolve-audit-20260716-194322`
**Depende de:** SQ-COST-0 (reconciliação de docs)
**Insumos:** `docs/discovery/wellington-costing-eto-sprints-2026-07-16.md`, `/tmp/sq_wellington_cost_opus_probe.md`,
`.legatus/sprints/2026-07-16-sq-cost-1-sdk-spec-backsolve.md`
**Stop condition:** `AWAIT_PMO_REVIEW`

---

## 1. Recomendação executiva

O ganho do ciclo Wellington não é "adicionar um módulo de custos" — é **rotular o que já existe** antes de
estender qualquer coisa. Três achados do probe Opus, confirmados por leitura direta do código nesta sessão,
mudam a ordem de prioridade:

1. **Não existe overhead/custo fixo em lugar nenhum do sistema.** `TenantCostChain`
   (`pricing_engine/rates.py:24-37`) só carrega `rate_hh`, `rate_hm`, `material_price`,
   `process_params`, `fator_correcao_mo`, `fator_preco`, `impostos_pct`. Overhead hoje está
   **implicitamente diluído** dentro de `rate_hh` e `fator_preco`, sem forma de inspecionar ou defender
   esse valor. Este é o gap real de Wellington — não duplica nada existente.
2. **A contaminação que Wellington teme já está implementada e rodando.** `back_solve`
   (`backend/apps/cost_discovery/services.py:64-100`) faz bisseção em `fator_correcao_mo` até o motor
   **reproduzir um preço histórico conhecido**, e grava esse fator via `_apply_fator_mo()` em
   `TenantParamConfig` (singleton, sem versionamento). Um `error_pct ≈ 0` mede fidelidade ao preço do Mané,
   não cobertura da operação. Ver Seção 3.
3. **`OperacaoExecutada.custo_fixo` (`pricing_engine/wbs.py:47`) é um falso amigo.** Significa "serviço de
   valor fixo" (TT, transporte, LP) — **não** overhead estrutural. Reaproveitar esse nome para o novo
   conceito corrompe leitura futura e pode confundir os gates de regressão. Ver Seção 7.

**Recomendação:** aprovar a extensão do modelo de custos como um novo model `CostStructure`
**tenant-scoped e versionado**, plugado no fluxo existente de `apps/cost_discovery` (não um wizard
paralelo), com overhead como **linha separada e inspecionável** (não absorvida em `rate_hh`). A auditoria
de contaminação (Seção 3) deve ser lida e aceita **antes** de qualquer nova calibração back-solve ser
vendida como "custo validado". Este sprint não implementa nada — apenas especifica e audita.

---

## 2. Mapa de conceitos existentes

Cada conceito do discovery Wellington, mapeado ao campo/model atual — ou marcado `AUSENTE`.

| Conceito (Wellington) | Existe hoje? | Campo/model | Observação |
|---|---|---|---|
| Preço de matéria-prima por forma | ✅ Existe | `apps.materials.models.MaterialPrice` (por `material × forma`, cifrado, `valid_from/valid_until`) | Alimenta `TenantCostChain.material_price` via `build_chain_from_db` / `build_cost_chain` |
| Custo de mão de obra por operação (R$/h) | ✅ Existe | `apps.engineering_params.models.Rate` (`rate_hh`, `rate_hm`, versionado `valid_from/valid_until`) | |
| Física → horas (avanço/tempo/taxa) | ✅ Existe | `apps.engineering_params.models.ProcessParameter` (por operação×método×material, versionado) | Arquitetura travada: ProcessParameter ≠ Rate (`PROJECT_MAP.md:65`) |
| Fator de correção de MO (calibração) | ✅ Existe | `TenantParamConfig.fator_correcao_mo` — **singleton** (`get_solo()`), não versionado | Multiplica TODAS as horas; alvo do back-solve |
| Markup / margem de venda | ⚠️ Parcialmente | `Quotation.fator_preco` / `TenantCostChain.fator_preco` | É **markup sobre custo**, não margem de contribuição. `fator_preco=1,20` não responde "isso cobre a operação?" |
| Impostos | ✅ Existe | `Quotation.impostos_pct` / `TenantCostChain.impostos_pct` | |
| Wizard de descoberta de cadeia de custos | ✅ Existe | `apps.cost_discovery.models.CostDiscoverySession` + `services.py` (`top_down`, `back_solve`, `apply_top_down`) | Ponto de extensão obrigatório (não criar rival) |
| Custo fixo mensal (despesa fixa da empresa) | ❌ AUSENTE | — | Núcleo do gap de Wellington |
| Capacidade produtiva (horas/mês) | ❌ AUSENTE | — | Núcleo do gap de Wellington |
| Custo fixo por hora produtiva (rateio) | ❌ AUSENTE | — | Depende dos dois anteriores |
| Margem de contribuição (meta / mínima) | ❌ AUSENTE | — | `fator_preco` não é substituto |
| Preço mínimo saudável | ❌ AUSENTE | — | Nada compara preço de venda a um piso de custo |
| Provenance do preço (`referencial` vs `validado por custo`) | ❌ AUSENTE | — | `grep -rn "pricing_basis\|referencial\|validado_custo" backend/apps` → zero hits. Nenhum campo distingue preço calibrado por back-solve de preço com cadeia de custo completa |
| Horas orçadas (estimadas) | ✅ Existe (fluxo completo) | `wbs.OperacaoExecutada.horas_hh` → `adapter.py:165` → `ItemOperation.horas_hh` → `production/services.py:130` (deep-copy) → `OFOperation.horas_hh` | Contradiz a alegação obsoleta de `STATUS.md`/`ROADMAP.md` de que horas estimadas não estavam expostas — corrigida em SQ-COST-0 |
| Horas reais (apontadas) | ✅ Existe | `ProductionEntry.hours_hh/hours_hm` → agregadas em `OFOperation.actual_hh` | |
| Comparação horas orçadas vs horas reais | ❌ AUSENTE | — | `production/services.py:317-325` compara **custo**, nunca horas — ver Seção 6 |
| Aprendizado de índice (orçado→realizado) | ✅ Existe, mas conflacionado | `ActualRate` (Welford, R$/h observado) → `RateSuggestion` (N≥20, conf≥70%) | O sinal mistura erro de `Rate` com erro de `ProcessParameter` (Finding C) |
| Custo de "serviço de valor fixo" (TT, transporte, LP) | ✅ Existe — **nome colidente** | `pricing_engine.wbs.OperacaoExecutada.custo_fixo` | **Não é overhead estrutural.** Ver Seção 7 |
| Canal de aviso/alerta não-bloqueante | ✅ Existe | `Quotation.avisos` (JSON list `{nivel, codigo, mensagem}`, `nivel ∈ {warning, block}`), populado por `apps.quotations.validators.validate_metalurgia` | Reusar para alertas de preço mínimo/margem (Seção 8, SQ-COST-5 futuro) |
| Trilha de auditoria para mudança de campo sensível | ✅ Existe | `apps.audit.services.log_access(request, action, resource, metadata)` → `AccessLog` | Reusar para mudança de provenance/overhead, não inventar novo log |
| Centro de custo / rateio por centro | ❌ AUSENTE (não-goal deste ciclo) | — | Ver Seção 8 |

---

## 3. Auditoria de contaminação do back-solve

### 3.1 Caminho de código exato

```
apps/cost_discovery/services.py

back_solve(reference_inputs, known_price, fator_preco=1.01377, impostos_pct=23.303,
           lo=0.05, hi=10.0, tol=0.0005, iters=60)
  → _inputs(reference_inputs)                       # monta FeixeInputs a partir do job de referência
  → bisseção em `fator_correcao_mo` (0,05 .. 10,0)
      cada iteração chama _price_at(inputs, mid, fator_preco, impostos_pct)
        → build_chain_from_db(mid, ...)              # monta TenantCostChain com o mid testado
        → quote_feixe(inputs, cost_chain=chain).preco_com_impostos
  → converge quando |price - known| / known <= tol (0,05%)
  → retorna {"fator": mid, "achieved": price, "error_pct": (price-known)/known*100}

run_back_solve(session)
  → chama back_solve(...)
  → grava session.solved_fator_mo / achieved_price / error_pct
  → _apply_fator_mo(fator)
      → TenantParamConfig.get_solo()
      → cfg.fator_correcao_mo = fator      # SINGLETON — sobrescreve o valor global do tenant
      → cfg.save()
```

A partir daí, **toda cotação futura do tenant** herda esse `fator_correcao_mo` via
`adapter.build_cost_chain()` (linha 98-99: `chain.fator_correcao_mo = float(cfg.fator_correcao_mo)`).
Não há distinção, em nenhuma cotação subsequente, entre "este fator veio de back-solve" e "este fator veio
de um levantamento de custo real".

### 3.2 O que `error_pct` significa

`error_pct` é a **distância residual entre o preço que o motor produz com o `fator_correcao_mo` encontrado
e o preço histórico informado como alvo** (`known_price`). É uma medida de **convergência da bisseção**
— o algoritmo para quando `|preço_motor - preço_conhecido| / preço_conhecido <= tol` (0,05% por padrão) ou
esgota `iters` (60). Os gates de CI (`tests/validate_feixe_completo.py`, `tests/validate_permutador_completo.py`)
reportam esse mesmo tipo de métrica para os casos BEU (0,0%) e BEM (0,0%): eles confirmam que **o motor
reproduz a planilha ENGEMATEX byte a byte**, dado o fator calibrado.

### 3.3 O que `error_pct` NÃO significa

- **Não mede se o preço histórico (`known_price`) cobre o custo real da operação.** Se o Mané subprecificou
  a mão de obra na proposta original, o back-solve encontra um `fator_correcao_mo` que faz o motor
  reproduzir esse preço subprecificado — e reporta `error_pct: 0,0%` como se fosse sucesso.
- **Não mede margem de contribuição, cobertura de custo fixo, nem lucratividade.** Nenhum desses conceitos
  entra na função objetivo da bisseção; ela só minimiza a distância a `known_price`.
- **Não distingue erro de horas (`ProcessParameter`) de erro de custo/hora (`Rate`).** O único grau de
  liberdade que a bisseção ajusta é um multiplicador escalar sobre TODAS as horas
  (`fator_correcao_mo` — comentário no código: "multiplica TODAS as horas (B31 na planilha)"). Se o erro
  real estivesse em uma única operação (ex.: solda subestimada), o back-solve ainda "resolve" via um fator
  global, escondendo onde o desvio realmente está.
- **Não é uma segunda fonte de verdade independente.** O único dado de entrada é o preço final que o
  próprio orçamentista (Mané) definiu — exatamente a fonte que a Áudio 2 do discovery identifica como "meio
  que chutada por benchmark... nunca aferida".

### 3.4 Risco atual de produto

- Toda cotação ENGEMATEX calculada hoje herda `TenantParamConfig.fator_correcao_mo`, que — se a sessão de
  calibração ativa foi `method="back_solve"` — foi ajustado para reproduzir preços históricos, não para
  refletir o custo real de mão de obra da empresa. **Não há como hoje, olhando uma cotação, saber se seu
  preço é confiável (calibrado por custo real) ou apenas fiel ao histórico.**
- O gap é agravado pelo singleton: `TenantParamConfig` não guarda histórico de qual sessão gerou o fator
  vigente, nem quando foi aplicado. Uma auditoria retroativa (“que fator estava ativo quando a cotação X foi
  calculada?”) não é possível hoje sem olhar o `CalculationSnapshot` da cotação — que grava os *outputs*, mas
  não necessariamente amarra explicitamente à `CostDiscoverySession` de origem.
- Toda `CostDiscoverySession` com `method="back_solve"` já registrada no banco (produção ou staging) deve
  ser tratada, a partir deste spec, como **fonte de calibração benchmark-derivada** — nunca como prova de
  que o preço cobre a operação. Isso vale mesmo com `error_pct` baixo.
- **Remediação proposta (não implementada neste sprint):** SQ-COST-2 rotula toda cotação cuja cadeia
  deriva de uma sessão `back_solve` como `pricing_basis = referencial`, derivado automaticamente de
  `CostDiscoverySession.method` — nunca setado à mão pelo usuário (ver Seção 5).

---

## 4. Proposta de extensão do modelo de custos

### 4.1 Decisão de posicionamento: extensão, não wizard rival

`docs/discovery/...md §8` e o probe Opus (`Warning list #2`) já sinalizam o risco: a redação literal do
discovery ("modelar `TenantCostStructure`") colidiria com `CostDiscoverySession` + `TenantParamConfig` +
`Rate` se implementada como um fluxo paralelo. Decisão deste spec:

- **Novo model, `CostStructure`**, justificado porque nenhum model existente pode carregar o conceito:
  - `TenantParamConfig` é **singleton** (`get_solo()`, `pk=1` forçado) — não tem histórico/vigência, e
    misturar "custo fixo mensal" ali quebraria a natureza de "knobs de engenharia" do model.
  - `CostDiscoverySession` é um **log de eventos de calibração** (um registro por rodada de seed/back-solve),
    não um cadastro de valores vigentes.
  - `Rate`/`ProcessParameter`/`MaterialPrice` já têm semântica própria (custo de operação, física, preço de
    material) — custo fixo estrutural não é nenhum desses três.
- **Mas `CostStructure` não vira um wizard novo.** Ele é criado e editado **dentro do fluxo existente de
  `apps.cost_discovery`**, como um passo adicional do wizard A1-c (ao lado de `top_down`/`back_solve`), e
  referenciado por `CostDiscoverySession` quando aplicável. Nenhuma nova app Django, nenhuma nova rota
  de topo independente do cost_discovery.

### 4.2 Modelo proposto (nível de design — sem migration)

```python
# apps/cost_discovery/models.py (extensão, mesma app)

class CostStructure(models.Model):
    """Estrutura de custo fixo/capacidade do tenant — versionada, como Rate/MaterialPrice.
    NÃO afeta o preço calculado até SQ-COST-4/5 explicitamente ligarem isso à cadeia de custos."""

    custo_fixo_mensal = models.DecimalField(max_digits=14, decimal_places=2)
    horas_produtivas_mensais = models.DecimalField(max_digits=10, decimal_places=2)
    margem_contribuicao_alvo_pct = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    notes = models.TextField(blank=True)

    valid_from = models.DateField(default=date.today)
    valid_until = models.DateField(null=True, blank=True)

    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True,
                                    on_delete=models.SET_NULL)
    created_at = models.DateTimeField(auto_now_add=True)

    # rastreabilidade: de onde vieram os números (não é cálculo, é proveniência)
    source_session = models.ForeignKey(
        "cost_discovery.CostDiscoverySession", null=True, blank=True,
        on_delete=models.SET_NULL, related_name="cost_structures")

    class Meta:
        ordering = ["-valid_from"]

    @property
    def custo_fixo_hora(self) -> Decimal:
        if not self.horas_produtivas_mensais:
            return Decimal("0")
        return (self.custo_fixo_mensal / self.horas_produtivas_mensais).quantize(Decimal("0.01"))
```

Idioma de vigência (`valid_from`/`valid_until`) espelha `Rate` e `MaterialPrice` — não o singleton de
`TenantParamConfig` — porque custo fixo muda por período contábil (mês/trimestre) e o tenant precisa
auditar retroativamente "qual era o custo fixo/hora quando esta cotação foi feita?" da mesma forma que já
faz para `Rate`.

### 4.3 Onde overhead entra na cadeia (decisão de design, não implementada)

**Decisão travada por este spec: overhead é linha separada, nunca absorvida em `rate_hh`.**

Justificativa:
1. Absorver overhead em `rate_hh` recria exatamente a invisibilidade que motivou o discovery Wellington —
   ninguém consegue inspecionar quanto do R$/h é mão de obra pura vs estrutura.
2. `ActualRate`/`RateSuggestion` (H2.3) assumem que `Rate.rate_hh` é o **custo comprável de uma hora de
   trabalho**. Se overhead fosse somado ali, o loop de aprendizado (Welford sobre `custo/horas reais`)
   começaria a "aprender" overhead junto com produtividade real, corrompendo a calibração já auditada
   (`aa3127c`, 7 achados corrigidos).
3. Overhead como linha separada permite `preco_minimo` explícito (`custo_total_sem_overhead + overhead_rateado`)
   sem tocar em nenhum dos campos já validados pelos gates BEU/BEM.

Extensão futura de `TenantCostChain` (SQ-COST-4/5, não neste sprint):

```python
@dataclass
class TenantCostChain:
    ...
    overhead_hora: float = 0.0     # ⚠️ NUNCA "custo_fixo" — ver Seção 7
```

Com `overhead_hora=0.0` como default, todo golden case existente (feixe −2,9%, BEU/BEM 0,0%) permanece
bit-idêntico até um tenant optar explicitamente por ligar overhead na cotação.

---

## 5. Modelo de proveniência de preço: `referencial` vs `validado por custo`

### 5.1 Definições

- **`referencial`** — o preço foi formado por markup (`fator_preco`) e/ou por um `fator_correcao_mo`
  calibrado via `back_solve` contra um preço histórico. Serve como benchmark de formato e ordem de
  grandeza, **não** como prova de que a operação está coberta.
- **`validado_custo`** — a cotação usa uma `CostStructure` vigente (custo fixo + capacidade + margem alvo)
  e o preço de venda foi comparado a um `preco_minimo` derivado dela. Só é possível a partir de SQ-COST-4/5.

### 5.2 Regras de derivação (não é campo editável à mão)

1. `Quotation.pricing_basis` é **derivado**, nunca setado diretamente pelo usuário em formulário livre —
   evita o mesmo problema que estamos corrigindo (usuário "marca" algo como validado sem que seja).
2. Regra de derivação proposta:
   - Se a `TenantCostChain` da cotação usa um `fator_correcao_mo` cuja origem rastreável é uma
     `CostDiscoverySession(method="back_solve")` **e** não há `CostStructure` vigente aplicada à cotação
     ⇒ `referencial`.
   - Se existe `CostStructure` vigente **e** a cotação expõe `preco_minimo` comparável ao preço de venda
     (SQ-COST-5) ⇒ elegível a `validado_custo`.
   - Qualquer cotação sem nenhuma sessão de calibração rastreável (seed default) ⇒ `referencial` por
     definição — nunca o default oposto.
3. Toda cotação que hoje já existe deve ser **back-filled para `referencial`** — é o que ela é, mesmo sem
   o novo enum existir ainda.

### 5.3 Estratégia de migração/backfill (nível de design)

- Migration aditiva: `Quotation.pricing_basis` enum (`referencial` default, `validado_custo`), nullable=False,
  default `referencial`. Sem dado a recalcular — todo registro existente já é `referencial` pela regra 5.2.3.
- Migration de dados (data migration, não schema) para popular `CostDiscoverySession` → `pricing_basis`
  cross-reference, se decidirmos amarrar explicitamente cotação↔sessão (campo opcional
  `Quotation.cost_discovery_session` FK null=True — a definir em SQ-COST-2, fora do escopo deste sprint).
- Nenhuma migration é criada nesta sprint. Este é o desenho para SQ-COST-2 executar.
- Regressão obrigatória no momento da implementação: gates BEU/BEM devem permanecer 0,0% — o campo é
  metadado, não deve mover nenhum valor calculado.

---

## 6. Implicação para decomposição de horas (SQ-COST-3)

O probe Opus identificou (Finding C) que o loop orçado→realizado hoje conflaciona dois erros independentes:

```
production/services.py:317-325 (_close_out_observations)
  observed_rate = Decimal(op.custo) / Decimal(actual_hh)
  ProductionObservation.objects.create(..., estimated_custo=op.custo, actual_hh=actual_hh,
                                        observed_rate=observed_rate)
  _update_actual_rate(op.codigo_op, observed_rate)   # Welford sobre observed_rate
```

`op.custo` é o custo **estimado** (`OFOperation.custo`, snapshot do orçamento). `actual_hh` é a soma real
apontada em `ProductionEntry`. `observed_rate = custo_orçado / horas_reais` mistura:

- erro de **horas estimadas** (`ProcessParameter` errado — a física está errada, ex. furação levou mais
  tempo que o previsto por driver físico mal calibrado);
- erro de **R$/hora** (`Rate` errado — a física estava certa, mas o preço da hora não cobre o custo real).

Hoje `RateSuggestion` (H2.3, N≥20, confiança≥70%) "corrige" `Rate.rate_hh` para compensar **qualquer** um
dos dois — inclusive quando o problema real está em `ProcessParameter`. O rate droga para absorver erro de
estimativa de horas, e a confiança (`ActualRate.confidence`) sobe mesmo que o número esteja compensando o
erro errado.

**Separação exigida para SQ-COST-3** (nível de design, para o próximo sprint):

1. `ProductionObservation` ganha campo aditivo `estimated_hh` (de `OFOperation.horas_hh`, já disponível —
   dado já flui, não é preciso novo cálculo de motor).
2. `delta_horas_pct = (actual_hh − estimated_hh) / estimated_hh`, com guarda para `estimated_hh = 0`
   (operações de serviço fixo — `wbs.py:47` `custo_fixo` — legitimamente têm zero horas).
3. Roteamento do sinal:
   - `delta_horas_pct` fora da banda esperada ⇒ aponta para `ProcessParameter` da operação (reportar,
     **não** auto-sugerir mudança de parâmetro físico neste ciclo — risco de regressão nos golden cases).
   - Delta residual em `observed_rate` **depois de controlar por horas reais corretas** ⇒ aponta para
     `Rate`, e é isso que `RateSuggestion` deveria consumir.
4. Não alterar o agregador Welford (`_update_actual_rate`) nesta sprint nem na próxima sem re-auditar —
   é código já auditado (`aa3127c`, 7 achados). SQ-COST-3 deve ser aditivo, não um refactor do agregador.

Este spec **não implementa** SQ-COST-3 — apenas define o contrato de dados e o roteamento de sinal que o
próximo sprint deve seguir, para não repetir a conflação atual.

---

## 7. Restrição de nomenclatura (obrigatória, vale para todo sprint futuro)

**Proibido nomear overhead estrutural como `custo_fixo`.**

- `pricing_engine/wbs.py:47` — `OperacaoExecutada.custo_fixo` já existe e significa **"serviço de valor
  fixo"** (tratamento térmico, transporte, LP — qualquer operação cobrada como valor fechado, não
  horas×rate). É parte do roll-up de `custo_mo` de um item hoje (`Item.custo_mo` soma `op.custo`, que inclui
  `custo_fixo` quando a operação não tem horas).
- Reaproveitar `custo_fixo` para "despesa fixa mensal / overhead estrutural" faria duas coisas
  semanticamente diferentes compartilharem um nome idêntico no mesmo módulo — silenciosamente corrompendo
  a leitura dos golden cases (`tests/validate_feixe_completo.py`, `tests/validate_permutador_completo.py`)
  e confundindo qualquer engenheiro futuro que grep por `custo_fixo`.
- **Nomenclatura obrigatória para o novo conceito:** prefixo `overhead_*` ou `custo_estrutura_*`.
  Exemplos aprovados: `overhead_hora`, `overhead_mensal`, `custo_estrutura_mensal`,
  `CostStructure.custo_fixo_mensal` é uma **exceção aceitável** porque vive num model isolado
  (`apps.cost_discovery.models.CostStructure`), não dentro do `pricing_engine`, e o nome ali descreve o
  campo de entrada do usuário (que é, de fato, "custo fixo mensal" no sentido contábil) — mas qualquer campo
  que cruze para dentro de `TenantCostChain`/`pricing_engine` **deve** usar `overhead_*` para não colidir
  com `wbs.custo_fixo`.
- Esta restrição é uma condição de aceite explícita para SQ-COST-4/5 (Seção 10).

---

## 8. Não-objetivos e guardrails deste ciclo

Confirmando os limites já acordados no discovery e no probe — este spec não abre exceção a nenhum deles:

- **Sem centros de custo.** Um custo fixo/hora global por tenant, não por centro de custo/máquina/setor.
  Centros de custo multiplicam o modelo por N e exigem dados de rateio que a ENGEMATEX (e PMEs em geral)
  não têm hoje — é a mesma razão pela qual elas não conseguem fazer isso em Excel.
- **Sem analytics competitivo** ("vitória perigosa", 2º colocado, etc. — SQ-COST-5 do discovery original /
  deferred do probe). Depende de dado que a ENGEMATEX pode não ter, e é inútil sem o modelo de custo
  validado por baixo primeiro.
- **Sem alerta de preço bloqueante no primeiro ciclo.** Qualquer alerta de "preço abaixo do mínimo" é
  **advisory**, no canal já existente `Quotation.avisos` (mesmo padrão dos alertas ASME,
  `nivel: warning|block` — usar `warning`, nunca `block`, para preço mínimo neste ciclo). Calibração a 1
  job/tenant não sustenta bloqueio de preço.
- **Sem mudança de valor calculado neste sprint.** SQ-COST-1 é spec pura; nenhum golden case pode se mover.
- **Sem novo app Django, sem nova rota de topo.** `CostStructure` vive em `apps.cost_discovery`.
- **Sem alterar o agregador Welford de `ActualRate`** nem o contrato de `RateSuggestion` nesta ou na
  próxima sprint sem re-auditoria completa.

---

## 9. Contratos propostos para os próximos sprints

### SQ-COST-2 — Proveniência `referencial` vs `validado por custo`
- **Escopo:** `Quotation.pricing_basis` (enum), derivação automática (Seção 5.2), badge UI (Design System
  G), `AccessLog` em mudança de proveniência, back-fill de cotações existentes para `referencial`.
- **Não-escopo:** nenhuma matemática de overhead, nenhum bloqueio, zero mudança de valor calculado.
- **Aceite:** toda cotação existente lê `referencial`; usuário não confunde um preço com o outro; gates
  BEU/BEM inalterados.

### SQ-COST-3 — Decomposição de horas orçado vs realizado
- **Escopo:** `ProductionObservation.estimated_hh` (aditivo), `delta_horas_pct`, guarda de
  `estimated_hh=0`, roteamento do sinal (erro de horas → `ProcessParameter`; erro de rate → `Rate`), view
  somente-leitura de operações com maior desvio.
- **Não-escopo:** nenhuma auto-sugestão de `ProcessParameter`; nenhum refactor do agregador Welford.
- **Aceite:** para uma OF concluída, o sistema mostra quais operações estouraram em horas; `RateSuggestion`
  deixa de absorver erro de estimativa de horas.
- **Independência:** SQ-COST-3 não depende de SQ-COST-1/2 — pode rodar em paralelo, os dados já existem.

(SQ-COST-4 — estrutura de custo fixo/capacidade — e SQ-COST-5 — margem/preço mínimo — seguem descritos no
probe Opus e no discovery original; este spec não os reabre, apenas confirma que `CostStructure` conforme
Seção 4 é a base que eles devem consumir.)

---

## 10. Critérios de aceite e checklist de evidência

**Aceite deste spec:**
- [x] Todo conceito do discovery Wellington mapeado a campo/model existente ou marcado `AUSENTE` (Seção 2).
- [x] Auditoria de contaminação do back-solve concreta, amarrada a código real (`cost_discovery/services.py:64-100`,
      `production/services.py:317-325`) (Seção 3).
- [x] Proposta de novo model (`CostStructure`) justificada como extensão plugada em `cost_discovery`, não
      wizard rival (Seção 4.1).
- [x] Overhead decidido como linha separada, não absorvido em `rate_hh` (Seção 4.3).
- [x] Nomenclatura `overhead_*`/`custo_estrutura_*` fixada; colisão com `wbs.custo_fixo` documentada como
      proibida (Seção 7).
- [x] Próximos sprints (SQ-COST-2, SQ-COST-3) descritos com contrato suficiente para não exigir
      re-discovery.

**Checklist de evidência (a rodar por este worker, não testes de app):**
- `git diff --check`
- `git status --short`
- confirmar que nenhum arquivo `.py`/migration mudou no diff

**Fora do escopo de evidência desta sprint:** `manage.py test`, gates de engine (`validate_feixe_completo`,
`validate_permutador_completo`) — nenhum código foi tocado.

---

## 11. Perguntas em aberto para Wellington/Romulo

Reincidentes do discovery original (`docs/discovery/...md §6`), ainda não respondidas — bloqueantes para
SQ-COST-4, não para SQ-COST-1/2/3:

1. Qual o custo fixo mensal aproximado da ENGEMATEX para popular o primeiro `CostStructure` real?
2. Quantas horas produtivas/mês são realistas (capacidade instalada vs capacidade efetiva)?
3. Confirma-se **um custo fixo/hora global por tenant** para o primeiro ciclo (vs. centro de custo)? Este
   spec assume que sim (Seção 8) — pendente de confirmação explícita.
4. Existem sessões `CostDiscoverySession(method="back_solve")` já aplicadas em produção/staging hoje? Se
   sim, listar quais cotações herdam esse fator, para priorizar o back-fill de `pricing_basis` em SQ-COST-2.
5. O primeiro piloto de alerta de preço mínimo deve ser puramente informativo (`avisos`, nível `warning`) —
   confirma-se que não deve bloquear em nenhuma hipótese neste ciclo?
6. Overhead separado (`overhead_hora`) vs embutido em `rate_hh`: este spec recomenda separado (Seção 4.3) —
   pedir sign-off explícito, porque a decisão trava o desenho de SQ-COST-4/5.

---

AWAIT_PMO_REVIEW
