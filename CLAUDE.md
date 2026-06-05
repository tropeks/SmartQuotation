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

backend/               # Django 5.2 + django-tenants (schema-per-tenant) + session auth (sem JWT)
  apps/tenants/        # Tenant/Domain/Plan (public). provision_tenant cria schema isolado.
  apps/accounts/       # UserProfile + RBAC (regra engenheiro→CREA) + login/logout sessão
  apps/materials/      # Material (423 seed, densidade de norma) + MaterialPrice (cifrado, por forma)
  apps/engineering_params/  # Rate + ProcessParameter (seed ENGEMATEX) + regra furação radial≤600<CNC
  apps/quotations/     # EAP persistida + ADAPTER (único acoplamento Django↔motor) + data sheet UI
  static/css/design-system-g.css   # Design System G·Refined Bauhaus (UX_SPEC v2)
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
python manage.py tenant_command seed_proposal_template --schema=engematex
python manage.py runserver 0.0.0.0:8000     # acessar via engematex.localhost:8000
# PDF da proposta: WeasyPrint (Docker) ou google-chrome --print-to-pdf (fallback). DOCX: python-docx.
```

## Testes
```bash
python -m tests.validate_feixe_completo      # gate do motor (falha se regredir >10%)
cd backend && python manage.py test apps     # 37 testes (django-tenants TenantTestCase)
```

## CI
`.github/workflows/ci.yml`: gate do motor (±10%) + Django check + makemigrations --check.

## Docs de domínio
`~/.gstack/projects/tropeks-SmartQuotation/`: design doc (Approach C), spec do motor de custeio,
análise da planilha. `PROJECT_MAP.md`: índice anti-token. Grafo: `graphify explain "X"`.

## Decisões de domínio (ENGEMATEX)
- Custo = peso BRUTO (Opção A — cobra perdas de material). Bruto/líquido/perda exibidos.
- Chicana: TEMA RCB-4, corte = altura restante (hc = OD − corte).
- ProcessParameter editável por (operação × máquina); furação ≤600 furos → radial, >600 → CNC.
- Cotação = snapshot (deep-copy), não referência viva ao template.
