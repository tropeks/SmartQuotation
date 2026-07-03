# SmartQuotation

SaaS multi-tenant de cotação técnico-comercial para caldeiraria média/pesada.
MVP: cotação de **feixe tubular** de trocadores de calor. Design partner: ENGEMATEX.

## Arquitetura

```
pricing_engine/        # MOTOR de custeio — Python PURO (zero Django). Não editar p/ web.
  EAP/WBS: Cotacao → Item → {MateriaPrima, Operacao}
  64 operações + 17 componentes paramétricos, fiéis à planilha ENGEMATEX.
  ProcessParameter (física → horas) ≠ Rate (custo → R$). Validado a -2,9% vs gabarito real.
  quote_feixe(FeixeInputs) → Cotacao.   Custo = peso BRUTO (cobra perdas) + bruto/líquido/perda.
  permutador_quote.py → PERMUTADOR COMPLETO GENÉRICO por designação TEMA (BEU, BEM, ...).
  quote_completo(designacao, cost_chain) compõe matéria-prima (peso geométrico×preço; itens
  comerciais=catálogo) + mão-de-obra (FC escala) + serviços. Validado a 0,0% vs gabarito:
  BEU R$ 128.160, BEM R$ 119.295. Seeds {d}_{materiais,operacoes,ground_truth}.json gerados
  por scripts/extract_permutador.py. beu_quote.quote_beu = wrapper compat. beu_geometry.py=pesos
  (ρ por material via materials.density; tampo 2:1 = CALIB 4/π, calibração não fórmula física).
  Parametria v2: dims_override recomputa peso pela geometria; params={parâmetro: razão} escala
  HORAS de MO E serviços por driver físico com setup fixo (horas=horas_ref×(setup+(1-setup)×razão)).
  Parâmetros: tubos·chicanas·comprimento·diametro·solda·massa·area·volume. _param_da_op mapeia
  cada op (tirantes/barras→diametro; RT/UT→solda; TT/consumíveis→massa; hidro→volume; soldas
  long∝comprimento/circ∝diametro). permutador_layout.check_layout avisa geometria inviável
  (feixe não cabe no casco). Razão 1,0 = referência → gate 0,0%. LIMITAÇÃO: massa/solda/area/
  volume são proxies (≈D·L…); setup fractions são defaults; calibração a 1 job. Data sheet em
  apps/tema_templates (inputs: tubos, comprimento, OD, parede, nº chicanas, D casco, esp, liga).
  Refinos v3 (sem domínio): soldas ∝ espessura² (solda_long/circ/NDT); furação chicana ∝
  tubos×chicanas; fator de liga na MO (LIGA_FATOR CS1,0/inox1,3/duplex1,6/níquel2,0, editável);
  folga feixe↔casco por cabeçote TEMA (permutador_layout.FOLGA_POR_CABECOTE).
  Metalurgia POR LADO (feixe|casco): liga_por_lado escala MO do lado, dens_por_lado escala
  peso do material do lado (suporta bimetálico: feixe inox + casco CS). Scrap por família
  (beu_geometry.PERDA_POR_FAMILIA: disco/perfurado 1,25 etc.). Pressão→espessura ASME VIII
  (UG-27/32, Ap.2, UG-21) e flanges implementados; defaults VALIDADOS pelo PE (Wellington, 2026-06-19).

backend/               # Django 5.2 + django-tenants (schema-per-tenant) + session auth (sem JWT)
  apps/tenants/        # Tenant/Domain/Plan (public). provision_tenant cria schema isolado.
  apps/accounts/       # UserProfile + RBAC (regra engenheiro→CREA) + login/logout sessão
  apps/materials/      # Material (423 seed, densidade de norma) + MaterialPrice (cifrado, por forma)
  apps/engineering_params/  # Rate + ProcessParameter (seed ENGEMATEX) + regra furação radial≤600<CNC
  apps/quotations/     # EAP persistida + ADAPTER (único acoplamento Django↔motor) + data sheet UI
  apps/proposals/      # proposta DOCX/PDF (template configurável + editável por caso)
  apps/cost_discovery/ # wizard A1-c: cadeia de custos (seed top-down + back-solve de calibração)
  static/css/design-system-g.css   # Design System G·Refined Bauhaus (UX_SPEC v2)

# Cadeia de custos: o adapter monta TenantCostChain do banco (MaterialPrice por forma,
# fator_correcao_mo, markup, impostos) e injeta no motor. O back-solve calibra o fator de
# MO contra um job real conhecido (erro <0,1% vs realidade da empresa).
```

**Regra de ouro:** `pricing_engine` é lib pura. O único ponto que importa Django↔motor é
`apps/quotations/adapter.py` (`recompute()` monta FeixeInputs, chama `quote_feixe`, persiste a EAP).

## Stack
Python 3.12 · Django 5.2 · django-tenants · DRF · HTMX + Alpine + Tailwind tokens G ·
PostgreSQL 16 · Redis · Celery · WeasyPrint/docxtpl (proposta) · django-encrypted-model-fields.

## Dev (Docker)
```bash
cp backend/.env.example backend/.env       # ajuste se necessário
docker compose up -d db redis              # Postgres 5436, Redis 6380
# backend (venv local ou docker):
cd backend && python -m venv .venv && . .venv/bin/activate
pip install -r requirements/development.txt
export POSTGRES_PORT=5436 POSTGRES_HOST=localhost POSTGRES_USER=sq POSTGRES_PASSWORD=sq POSTGRES_DB=smartquotation
python manage.py migrate_schemas --shared
python manage.py provision_tenant --name "ENGEMATEX" --schema engematex --domain engematex.localhost
python manage.py migrate_schemas --tenant
python manage.py tenant_command seed_materials --schema=engematex
python manage.py tenant_command seed_engineering_params --schema=engematex
python manage.py tenant_command seed_ligas --schema=engematex          # ligas metalúrgicas (S 2025)
python manage.py tenant_command seed_proposal_template --schema=engematex
python manage.py tenant_command seed_tema_catalog --schema=engematex    # partes TEMA (dropdowns Compor Trocador) — SEM isto o /tema/compor/ fica vazio
python manage.py runserver 0.0.0.0:8000     # acessar via engematex.localhost:8000
# PDF da proposta: WeasyPrint (Docker) ou google-chrome --print-to-pdf (fallback). DOCX: python-docx.
```

## Testes
```bash
python -m tests.validate_feixe_completo      # gate do FEIXE (falha se regredir >10%)
python -m tests.validate_permutador_completo # gate do PERMUTADOR completo BEU+BEM (±10% + geometria)
cd backend && python manage.py test apps     # 73 testes (django-tenants TenantTestCase)
```

## CI
`.github/workflows/ci.yml`: gates do motor feixe + permutador (BEU+BEM, ±10%) + Django check + makemigrations --check.

## Docs de domínio
`~/.gstack/projects/tropeks-SmartQuotation/`: design doc (Approach C), spec do motor de custeio,
análise da planilha. `PROJECT_MAP.md`: índice anti-token. Grafo: `graphify explain "X"`.

## Decisões de domínio (ENGEMATEX)
- Custo = peso BRUTO (Opção A — cobra perdas de material). Bruto/líquido/perda exibidos.
- Chicana: TEMA RCB-4, corte = altura restante (hc = OD − corte).
- ProcessParameter editável por (operação × máquina); furação ≤600 furos → radial, >600 → CNC.
- Cotação = snapshot (deep-copy), não referência viva ao template.
