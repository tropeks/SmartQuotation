# Plano — F3 / Bloco C: export/import de golden template dos knobs

> F1 (knobs) + F2 (aprovação SoD) completos. F3 fecha o loop: o Wellington **configura → valida
> rodando cotações → exporta** a "config de ouro" (golden template), em vez de nos pedir números.
> Import **sempre** pela aprovação do F2 (nada aplica em massa sem 2ª assinatura).

## 1. Escopo (DECISÃO Rom 2026-07-18: incluir camada comercial)

**F3 = golden config COMPLETA que reproduz uma cotação** — knobs + horas + rates + preços +
calibração. Camada comercial **incluída** (Rom): o design partner exporta a própria config p/
semear tenants novos; a ressalva de confidencialidade (§5) vira aviso, não bloqueio (prod=eval).

| Camada | Fonte | Import |
|---|---|---|
| **Física — sensível** | `TenantParamConfig`: `perda_por_familia`, `setup_frac`, `drill_method_threshold_holes` | via **proposta+aprovação (F2)** |
| **Física — livre** | `TenantParamConfig`: `tema_compat_mode`, `baffle_cut_default_pct`, `tube_standard_lengths_mm`, `u_bend_min_radius_factor` | aplica direto |
| **Física — horas** | `ProcessParameter` (valor por operação×método×material, versionado) | **nova vigência** (não muta) |
| **Comercial** | `fator_correcao_mo` + `Rate` (rate_hh/hm) + `MaterialPrice` (**descriptografado no export**) | fator_mo=sensível→proposta; Rate/preço=**nova vigência** |

`ProcessParameter`/`Rate`/`MaterialPrice` são VERSIONADOS por vigência → import cria linha nova
com `valid_from=hoje` (fecha a anterior), nunca sobrescreve histórico.

## 2. Formato do template (JSON versionado)

```json
{
  "template_schema_version": 1,
  "kind": "smartquotation.engineering_knobs",
  "exported_at": "<ISO>",
  "source_tenant": "engematex",
  "knob_registry": ["perda_por_familia","setup_frac","drill_method_threshold_holes",
                    "tema_compat_mode","baffle_cut_default_pct","tube_standard_lengths_mm",
                    "u_bend_min_radius_factor"],
  "physical": { "perda_por_familia": {...}, "setup_frac": {...}, "drill_method_threshold_holes": 600, ... },
  "commercial": null
}
```

- `template_schema_version` (constante nova `TEMPLATE_SCHEMA_VERSION` em código) — versiona o FORMATO.
- `knob_registry` = os campos que o motor CONHECE no momento do export → o import detecta chave
  **desconhecida** (knob removido/renomeado) e **avisa/ignora**, nunca aplica às cegas (§spec Bloco C).
- `commercial` fica `null` por default (confidencialidade — §5).

## 3. F3/A — EXPORT

- Botão "Exportar template" na página de knobs → view `knobs/exportar/` devolve o JSON (download,
  `Content-Disposition: attachment`). Só camada **física** por default. Gate: `rate.edit` (quem
  edita knobs exporta).
- Serviço `knob_template.export_template(include_commercial=False)` — monta o dict. `include_commercial`
  é opt-in explícito (§5), com aviso; em F3/A pode nem ser exposto na UI (defende por default).

## 4. F3/B — IMPORT (sempre com diff-preview + aprovação)

- Botão "Importar template" → upload JSON → `knob_template.parse_template(file)` valida:
  - `kind`/`template_schema_version` compatíveis? (major diferente → **bloqueia**; igual → segue com aviso.)
  - chaves em `physical` fora do `knob_registry` atual → **ignora + avisa** (knob removido/renomeado).
- **Diff-preview** (reusa o padrão de/para do F2/M6): mostra, por knob, vigente → do template.
- **Aplicação:**
  - **sensíveis** (perda/setup/drill) → cria **`KnobChangeProposal`** (F2!) com o `after` do template
    → segue a dupla validação SoD. Import NÃO aplica sensível direto.
  - **livres** → aplica direto ao `TenantParamConfig` (com `log_access`), pois não são sensíveis.
- **Semântica/migração** (§spec): se um knob mudou de SENTIDO entre versões (caso real do projeto:
  baffle cut % de corte vs % restante — ver [[baffle-cut-pct-semantica-restante]]), o
  `template_schema_version` é o guarda: import de versão antiga → regra explícita (converter ou avisar).

## 5. Confidencialidade & calibração (por que comercial fica de fora)

- `MaterialPrice` é **cifrado** por decisão de produto; `Rate`/`fator_correcao_mo` são a **estrutura de
  custo da ENGEMATEX**. Exportar = tirar da fronteira de cripto e criar arquivo que circula; template
  cross-tenant com isso = **semear concorrente com o custo do design partner**. → **camada comercial
  NUNCA sai por default**; só com flag explícita + aviso, e cross-tenant só com acordo formal (§7.3).
- `fator_correcao_mo` foi **back-solved** contra os knobs; importar template que altera os knobs
  **invalida a calibração** → aviso forte no import ("revalide o fator de MO / re-back-solve").

## 6. Faseamento (3 PRs — camada comercial cresceu o escopo)

- **F3/A — export** (`knob_template.export_template(include_commercial=True)` + view/rota + botão +
  testes). Serializa TODAS as camadas (física+horas+comercial descriptografado). Read-only, não
  muda custeio. Marca o JSON como confidencial quando inclui comercial.
- **F3/B — import dos KNOBS** (parse+validação de versão/kind + chave desconhecida + diff-preview +
  aplica: sensível→proposta F2, livre→direto). Reusa F2. Não toca modelos versionados ainda.
- **F3/C — import dos VERSIONADOS** (ProcessParameter/Rate/MaterialPrice como novas vigências +
  fator_correcao_mo→proposta + aviso de invalidação de calibração + gate de CI §7). O pedaço pesado.

## 7. Gate de CI (§8 do spec — dívida do F1)

Adicionar um gate que rode o **golden template pelo caminho completo do adapter** (export → import →
recompute de uma cotação) — hoje o CI só roda a lib pura com defaults de módulo; um template que
altera knob calibrado nunca é exercitado. Fecha a lacuna apontada no spec.

## 8. Decisões (com recomendação) — ⚠️ CONFIRMAR

1. **Escopo** → **só knobs do TenantParamConfig** em F3; ProcessParameter/Rate = F3.1. **Rec.: sim.**
2. **Camada comercial** → **fora por default** (nem expor o opt-in em F3/A); tratar quando houver
   demanda real de cross-tenant + acordo. **Rec.: física-only no F3.**
3. **Import sensível** → **via proposta F2** (não aplica direto). **Rec.: sim (reuso limpo).**
4. **Import livre** → aplica direto. **Rec.: sim.**
5. **Chave desconhecida / versão major diferente** → ignora+avisa / bloqueia. **Rec.: sim.**
