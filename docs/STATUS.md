# SmartQuotation — Status do Projeto

> Documento vivo. Última revisão: ciclo de design mecânico (colaboração com @WellToMcAt).
> Métricas atuais: **18 PRs mergeados · 95 testes Django · gates feixe −2,9% / permutador BEU+BEM 0,0%.**

---

## 1. Visão geral

Motor de custeio **paramétrico** para permutadores de calor casco-tubo (caldeiraria média/pesada), design partner **ENGEMATEX**. Reproduz os gabaritos reais e responde às dimensões/materiais do projeto.

| Equipamento | Motor | Gabarito | Erro |
|---|---:|---:|:--:|
| Feixe tubular (136 tubos) | — | venda R$ 44.192 | −2,9% |
| **BEU** (bonnet + casco 1 passe + feixe-U) | R$ 128.160 | R$ 128.160 | **0,0%** |
| **BEM** (espelho fixo, tubos retos) | R$ 119.295 | R$ 119.295 | **0,0%** |

---

## 2. O que o motor calcula hoje (paramétrico e validado)

- **Matéria-prima** — peso recomputado pela geometria de cada peça: tubo, virola, **espelho**, **chicana**, tampo 2:1, anel, pescoço de bocal e **flange WN (tabela ASME)**.
- **Mão de obra** — horas escalam pelo driver físico de cada operação, **com parcela de setup fixo**: furação ∝ nº de tubos; furação de chicana ∝ nº tubos × nº chicanas; soldas ∝ comprimento (longitudinal) e diâmetro (circunferencial) **× espessura²**; rasgos ∝ (nº passes − 1); **bocais ∝ peso do flange**.
- **Ensaios/serviços** — raio-X e ultrassom ∝ metros de solda; tratamento térmico e consumíveis ∝ massa; teste hidrostático ∝ volume.
- **Metalurgia bimetálica** — feixe e casco com ligas diferentes; afeta **horas (liga), densidade e preço/kg** por lado.
- **Layout** — alerta se o feixe não couber no casco (regra de pitch TEMA, folga por tipo de cabeçote).

Tudo cotável na tela **"Permutador"**. Cada aproximação está marcada na própria interface.

---

## 3. Roadmap de design mecânico (respostas do @WellToMcAt)

Ordem de prioridade definida por ele: **A3 → A2 → A1**.

| Item | Descrição | Status |
|---|---|:--:|
| **A3 — Flanges** | Peso real do flange WN por Ø × rating × schedule (tabela ASME); horas de solda do bocal escalam com o flange | ✅ **concluído** (PR #15, #16) |
| **A2 — Fluido corrosivo** | Campo Tubos/Casco/Ambos; se Tubos, metalurgia dos tubos espelha p/ cabeçote + espelhos | ✅ **concluído** |
| **A1 — Espessura ASME** | UG-27 calcula espessura mínima do casco em background + **alerta crítico** se entrada < norma (espelho UHX fica manual) | ⏳ **aguardando tabelas de tensão admissível (S) do Wellington** |

### Calibrações (confirmadas pelo Wellington)
| Item | Decisão | Status |
|---|---|:--:|
| Scrap espelho/chicana | **40%** (tampo 20%, tubo/chapa 10%) | 🔄 a aplicar |
| Radiografia | dropdown de escopo (100%/10%/Isento) multiplica metros de solda | 🔄 a aplicar |
| ICMS | fórmula real por dentro: Preço = Custo/(1 − alíquota) | 🔄 a aplicar |
| Fatores de liga (MO e preço) | defaults OK p/ MVP; futuro = integração ERP | ✅ default |

---

## 4. Refinos de precisão no roadmap (apontados pela revisão adversarial)

Cada PR passa por um **revisor adversarial cruzado** (Google Antigravity / Gemini). Itens menores em aberto, sem impacto no MVP:
- Solda do bocal por Σ(D · t² · q) em vez de peso (mais preciso em Ø extremos); SO vs WN; faces RTJ; série ASME B16.47 (A/B) para >24".
- Acoplar flange ↔ pescoço no que-if; geometria do espelho/chicana no override (já ativa).

---

## 5. Limitações honestas (declaradas na UI e no código)

1. Os fatores de **setup, liga, preço por liga e scrap** são *defaults de engenharia* — editáveis, não medidos (serão refinados com dados reais da ENGEMATEX / ERP).
2. A escala é **calibrada a 1 job real** por designação (sem 2º gabarito para validar a linearidade fora do ponto de referência).
3. **Pressão → espessura** (A1) e **tabela de flanges** (A3) dependem das tabelas de norma do Wellington para sair do provisório.

---

## 6. Como rodar / testar

```bash
python -m tests.validate_feixe_completo          # gate do feixe (±10%)
python -m tests.validate_permutador_completo     # gate BEU+BEM (±10% + geometria)
cd backend && python manage.py test apps         # 95 testes (django-tenants)
```

Arquitetura, decisões e seeds: ver `CLAUDE.md` e `pricing_engine/`.
