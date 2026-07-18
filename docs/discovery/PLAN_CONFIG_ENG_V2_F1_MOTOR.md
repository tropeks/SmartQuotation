# Plano — F1/Bloco A: estender o contrato do motor p/ knobs injetáveis

> Pré-condição (bug `_recompute_complete`) resolvida no PR #97. Este plano é o **trabalho de
> motor** do F1: tornar as constantes de módulo do `pricing_engine` **injetáveis** pelo tenant,
> sem quebrar os gates 0,0% do permutador (BEU/BEM). Mantém a lib PURA.

## 1. Decisão de contrato — estender `TenantCostChain` (não novos kwargs)

O contrato de injeção já existe e é `pricing_engine/rates.py:TenantCostChain` — é o que o adapter
monta do banco e injeta no motor. Os knobs entram COMO CAMPOS NOVOS na chain (dicts de override,
vazio = usa os defaults de módulo), não como novos kwargs de `quote_completo` (a assinatura já é
larga demais e o spec manda "injetar via o contrato estendido").

```python
@dataclass
class TenantCostChain:
    ...                       # campos atuais intactos
    perda_por_familia: dict[str, float] = field(default_factory=dict)   # familia -> fator bruto/liq
    setup_frac: dict[str, float]        = field(default_factory=dict)   # param  -> fração de setup

    def perda(self, familia: str) -> float:
        return self.perda_por_familia.get(familia) or perda_familia(familia)   # fallback módulo
    def setup(self, param: str) -> float:
        v = self.setup_frac.get(param)
        return v if v is not None else _SETUP_FRAC.get(param, 0.15)
```

Compatível pra trás: os 4 sítios que constroem a chain (`rates.engematex_seed`, `adapter.build_cost_chain`,
`tema_templates.tenant_cost_chain`, `cost_discovery.services`) não mudam — os campos nascem vazios.

## 2. Fiação no motor (`permutador_quote.py`) — 2 pontos

- **perda** (`:259` e `:266`): trocar `perda_familia(m["familia"])` por
  `(cost_chain.perda(m["familia"]) if cost_chain else perda_familia(m["familia"]))`.
- **setup** (`_escala_op`, `:111`/`:286`): passar a chain — `_escala_op(o, params_eff, chain)` e dentro
  usar `setup = chain.setup(p) if chain else _SETUP_FRAC.get(p, 0.15)`.

Nada mais muda. `beu_geometry.perda_familia` e `_SETUP_FRAC` continuam existindo como DEFAULTS.

## 3. Por que o gate 0,0% NÃO quebra (prova, não fé)

O gate (`tests.validate_permutador_completo`) roda `quote_completo(desig)` **pelado** —
`dims_override=None`, `params=None`, `cost_chain=None`:

- **perda**: o ramo `perda_familia` só executa dentro de `if dims_override and m["label"] in dims_override`
  (`:244`). Sem override, o material usa `m["peso_bruto"]` do seed direto → knob de perda **nunca é
  lido** no gate. Só afeta o caminho do data sheet (override).
- **setup**: `_escala_op` com `params=None` → `razao = 1.0` → `setup + (1-setup)*1.0 = 1.0` para
  QUALQUER valor de setup. A fração de setup **se cancela** na referência → knob de setup é gate-safe
  por construção.

→ Ambos os knobs "BONS" do spec são seguros. O override de perda respeita a exigência do spec
("não substitui a auto-calibração na referência"): a auto-calibração (`bruto_seed/liq_seed`, `:263`)
segue intacta para as famílias que a usam; o knob só substitui a `perda_familia()` das famílias
espelho/perfurado/disco, e só no caminho override.

## 4. Primeiro knob a subir: `perda_por_familia` (scrap por família)

Escolha: **perda antes de setup**. É um número do próprio Wellington (40%/20%… scrap real),
dimensão limpa (família), e exercita o caminho de material. Setup vem no 2º incremento (é "chute
nosso" — alto valor de config, mas tem o hazard de UI: coexiste com `ComponentOperation.setup_fixo`
scope `parts`; nomear distinto — "scrap de corte" vs "setup de operação").

## 5. Armazenamento no banco (F1 mínimo)

`TenantParamConfig` (singleton) ganha 1 `JSONField` — segue o padrão de `tube_standard_lengths_mm`:

```python
perda_por_familia = models.JSONField(default=_default_perda_por_familia)  # semeia PERDA_POR_FAMILIA
```

`adapter.build_cost_chain` e `tema_templates.tenant_cost_chain` passam a copiar
`cfg.perda_por_familia` → `chain.perda_por_familia`. (Migration + backfill do default no seed.)
Versionamento por vigência (§8 do spec) é dívida consciente adiada — F1 fica no singleton + AccessLog.

## 6. Guard-rails F1 (mínimos, modo warn)

- **Faixa**: cada família com min/max provisório (±50% do default) — fora da faixa = **aviso**, não
  bloqueio (F1 é warn; bloqueio/aprovação é F2).
- **AccessLog**: gravar `param_change` com diff (o padrão de diff do M6 já existe) a cada edição.
- **Falha de leitura VISÍVEL** (§5): o `except Exception: pass` de `build_cost_chain` engole erro de
  leitura de knob → cotação sai com default silencioso. Para o knob sensível, logar/avisar em vez de
  engolir. (Correção pontual no bloco de leitura, não refactor do adapter.)

## 7. Gate de CI novo (§8 do spec)

O CI hoje roda a lib pura com defaults de módulo → um template que altera knob calibrado nunca é
exercitado. Adicionar teste:

1. `quote_completo(desig, cost_chain=chain_vazia)` == `quote_completo(desig)` (chain sem overrides
   reproduz os defaults → 0,0%).
2. Override de perda numa família (ex.: espelho 1,40→1,60) **no caminho override** move o custo de
   material na direção esperada; **sem** override não move (gate intacto).

## 8. UI (estende a página Config de Engenharia)

Tabela família × fator, com default/unidade/faixa/ajuda, gate `engineering_param.write`. Reusa o
padrão da Config Eng v1. (Detalhe de template — depois da fiação do motor + model.)

## 9. Sequência de PRs

1. **PR-A (motor)**: campos na `TenantCostChain` + fiação nos 2 pontos + gate de CI (§7). Sem Django.
   Fecha o contrato. Verde nos gates.
2. **PR-B (model+adapter)**: `JSONField` em `TenantParamConfig` + migration + seed + cópia p/ chain
   nos 2 builders + AccessLog + leitura visível.
3. **PR-C (UI+guard-rails)**: página + faixa min/max warn.

Cada PR é independentemente verde e reversível. PR-A não muda comportamento (defaults idênticos) —
é puro enabling. O valor pro usuário aparece no PR-C.

## Riscos / decisões abertas

- **Setup 2º**: confirmar naming na UI (scrap ≠ setup de operação) antes de subir o 2º knob.
- **Vigência**: F1 usa singleton (sobrescreve, sem histórico além do AccessLog). Se Wellington quiser
  reverter para um valor anterior, precisa de vigência (§8) — provável F1.1 ou junto do F2 (staging).
- **`_FAMILIA_FORMA` vs `perda_por_familia`**: são dicts família-keyed diferentes (forma de preço vs
  scrap). Não confundir na UI nem no model.
