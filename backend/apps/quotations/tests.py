"""
Testes do app quotations + adapter pricing_engine.
Teste-chave: uma cotação persistida reproduz o gabarito ENGEMATEX (caso 136 tubos).
"""
from decimal import Decimal
from django.conf import settings
from django.core.management import call_command
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase
from django_tenants.test.cases import TenantTestCase
from django_tenants.utils import get_public_schema_name, get_tenant_domain_model, get_tenant_model

from apps.quotations.models import CalculationSnapshot, Quotation, Customer, QuotationItem, ItemMaterial, ItemOperation
from apps.quotations.adapter import build_cost_chain, recompute, default_inputs, to_feixe_inputs
from apps.quotations.services import create_feixe_quotation, next_number


class TenantMigrationTestCase(TransactionTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        call_command("migrate_schemas", schema_name=get_public_schema_name(), interactive=False, verbosity=0)

        tenant_domain = cls.get_test_tenant_domain()
        if tenant_domain not in settings.ALLOWED_HOSTS:
            settings.ALLOWED_HOSTS += [tenant_domain]

        cls.tenant = get_tenant_model()(schema_name=cls.get_test_schema_name())
        cls.tenant.save(verbosity=0)
        cls.domain = get_tenant_domain_model()(tenant=cls.tenant, domain=tenant_domain)
        cls.domain.save()
        connection.set_tenant(cls.tenant)

    @classmethod
    def tearDownClass(cls):
        connection.set_schema_to_public()
        cls.domain.delete()
        cls.tenant.delete(force_drop=True)

        tenant_domain = cls.get_test_tenant_domain()
        if tenant_domain in settings.ALLOWED_HOSTS:
            settings.ALLOWED_HOSTS.remove(tenant_domain)
        super().tearDownClass()

    @classmethod
    def get_test_tenant_domain(cls):
        return "tenant.test.com"

    @classmethod
    def get_test_schema_name(cls):
        return "test"


class FeixeQuotationTests(TenantTestCase):
    def setUp(self):
        self.customer = Customer.objects.create(company_name="Petrobras RPBC")

    def test_item_operation_recalc_custo_derivado(self):
        q = create_feixe_quotation(self.customer, "Feixe 136 tubos")
        item = QuotationItem.objects.filter(quotation=q).first()
        op = ItemOperation.objects.create(
            item=item,
            codigo_op="OP-TEST-HH",
            descricao="Operacao derivada",
            custo_direto=False,
            horas_hh=Decimal("10.00"),
            horas_hm=Decimal("0.00"),
            taxa_hora=Decimal("110.00"),
            taxa_hora_hm=Decimal("0.00"),
            custo=Decimal("0.00"),
        )

        returned = op.recalc_custo()
        op.refresh_from_db()

        self.assertEqual(returned, Decimal("1100.00"))
        self.assertEqual(op.custo, Decimal("1100.00"))

    def test_item_operation_recalc_custo_direto_preserva_valor(self):
        q = create_feixe_quotation(self.customer, "Feixe 136 tubos")
        item = QuotationItem.objects.filter(quotation=q).first()
        op = ItemOperation.objects.create(
            item=item,
            codigo_op="OP-TEST-DIR",
            descricao="Operacao direta",
            custo_direto=True,
            horas_hh=Decimal("0.00"),
            horas_hm=Decimal("0.00"),
            taxa_hora=Decimal("0.00"),
            taxa_hora_hm=Decimal("0.00"),
            custo=Decimal("200.00"),
        )

        returned = op.recalc_custo()
        op.refresh_from_db()

        self.assertEqual(returned, Decimal("200.00"))
        self.assertEqual(op.custo, Decimal("200.00"))
    def test_cotacao_persistida_reproduz_gabarito(self):
        q = create_feixe_quotation(self.customer, "Feixe 136 tubos")
        # gabarito real ENGEMATEX: custo 35.353, preço c/imp 44.192 (gate ±10%)
        self.assertAlmostEqual(float(q.custo_total), 35353, delta=35353 * 0.10)
        self.assertAlmostEqual(float(q.preco_com_impostos), 44192, delta=44192 * 0.10)
        # custo = material + MO
        self.assertAlmostEqual(
            float(q.custo_total), float(q.custo_material + q.custo_mo), delta=1.0)

    def test_eap_persistida_com_roll_up(self):
        q = create_feixe_quotation(self.customer, "Feixe 136 tubos")
        itens = QuotationItem.objects.filter(quotation=q)
        self.assertGreaterEqual(itens.count(), 8)        # tubos, espelhos, chicanas, montagem...
        # roll-up: soma dos itens == custo_total
        soma = sum((i.custo_total for i in itens), Decimal("0"))
        self.assertAlmostEqual(float(soma), float(q.custo_total), delta=1.0)
        # tubos têm matéria-prima persistida
        self.assertTrue(ItemMaterial.objects.filter(item__quotation=q, codigo_mp="TUB-01").exists())
        # furação tem operação persistida
        self.assertTrue(ItemOperation.objects.filter(item__quotation=q, codigo_op="OP-ESP-FURAR").exists())

    def test_peso_bruto_maior_que_liquido(self):
        q = create_feixe_quotation(self.customer, "Feixe 136 tubos")
        self.assertGreater(q.peso_bruto_kg, q.peso_liquido_kg)   # refugo > 0
        self.assertGreater(q.perda_kg, 0)

    def test_parametrico_mais_tubos_aumenta_preco(self):
        q1 = create_feixe_quotation(self.customer, "136 tubos")
        inp = default_inputs(); inp["n_tubos"] = 200
        q2 = create_feixe_quotation(self.customer, "200 tubos", inputs=inp)
        self.assertGreater(q2.preco_com_impostos, q1.preco_com_impostos)

    def test_process_parameter_material_do_tenant_altera_custo_da_furacao(self):
        from apps.engineering_params.models import ProcessParameter

        ProcessParameter.objects.create(
            operacao="FURAR_ESPELHO",
            metodo="radial",
            material="SA-516 GR 70",
            valor=Decimal("1.0000"),
            unidade="mm/min",
            descricao="mock lento para validar lookup por material",
        )
        q = create_feixe_quotation(self.customer, "Feixe com parametro por material")
        op = ItemOperation.objects.get(item__quotation=q, codigo_op="OP-ESP-FURAR")
        self.assertGreater(op.custo, Decimal("10000"))

    def test_recompute_idempotente_nao_duplica_eap(self):
        q = create_feixe_quotation(self.customer, "Feixe")
        n1 = QuotationItem.objects.filter(quotation=q).count()
        recompute(q)                                     # recomputa
        n2 = QuotationItem.objects.filter(quotation=q).count()
        self.assertEqual(n1, n2)                          # snapshot substituído, não duplicado

    def test_recompute_persiste_campos_editaveis_sem_mudar_totais_no_fluxo_real(self):
        baseline = create_feixe_quotation(self.customer, "Feixe baseline", inputs=default_inputs())
        q = Quotation.objects.create(
            number=next_number(),
            customer=self.customer,
            title="Feixe editable ops",
            scope="tube_bundle",
            inputs=default_inputs(),
        )
        recompute(q)

        hourly = ItemOperation.objects.get(item__quotation=q, codigo_op="OP-MANDRILAR")
        fixed = ItemOperation.objects.get(item__quotation=q, codigo_op="OP-TRANSP-ENT")
        q.refresh_from_db()
        baseline.refresh_from_db()

        self.assertGreater(hourly.horas_hh, Decimal("0"))
        self.assertGreater(hourly.taxa_hora, Decimal("0"))
        self.assertFalse(hourly.custo_direto)
        self.assertAlmostEqual(
            float(hourly.custo),
            float((hourly.horas_hh * hourly.taxa_hora) + (hourly.horas_hm * hourly.taxa_hora_hm)),
            delta=0.01,
        )
        self.assertTrue(fixed.custo_direto)
        self.assertEqual(fixed.horas_hh, Decimal("0.00"))
        self.assertEqual(q.custo_mo, baseline.custo_mo)
        self.assertEqual(q.custo_total, baseline.custo_total)

    def test_numeracao_sequencial(self):
        q1 = create_feixe_quotation(self.customer, "A")
        q2 = create_feixe_quotation(self.customer, "B")
        self.assertTrue(q1.number.startswith("COT-"))
        self.assertNotEqual(q1.number, q2.number)
        self.assertEqual(int(q2.number.split("-")[-1]), int(q1.number.split("-")[-1]) + 1)

    def test_calculation_snapshot_criada_para_feixe(self):
        q = create_feixe_quotation(self.customer, "Feixe 136 tubos")
        snaps = CalculationSnapshot.objects.filter(quotation=q)
        self.assertEqual(snaps.count(), 1)
        snap = snaps.get()
        self.assertEqual(snap.engine_version, "calc-snapshot-v1")
        self.assertEqual(snap.inputs["quotation"]["number"], q.number)
        self.assertIn("totals", snap.outputs)
        self.assertEqual(snap.outputs["totals"]["custo_total"], str(q.custo_total))

    def test_hash_muda_quando_inputs_mudam(self):
        q1 = create_feixe_quotation(self.customer, "Feixe 136 tubos")
        inp = default_inputs(); inp["n_tubos"] = 200
        q2 = create_feixe_quotation(self.customer, "Feixe 200 tubos", inputs=inp)
        h1 = q1.snapshots.first().snapshot_hash
        h2 = q2.snapshots.first().snapshot_hash
        self.assertNotEqual(h1, h2)


    def test_snapshot_hash_deterministico_independe_ordem_relacionados(self):
        from apps.quotations.services import build_snapshot_payload
        q = create_feixe_quotation(self.customer, "Feixe hash")
        h1 = q.snapshots.first().snapshot_hash
        h2 = build_snapshot_payload(q)["snapshot_hash"]
        self.assertEqual(h1, h2)

    def test_snapshot_permutador_com_memorial_e_standard_refs(self):
        from apps.quotations.services import create_permutador_quotation
        from pricing_engine.permutador_quote import quote_completo
        cust = Customer.objects.create(company_name="ACME Memo")
        cleaned = {"designacao": "BEU", "classe_casco": "CS", "pressao_projeto_bar": 50,
                   "temperatura_projeto_c": 150, "rt_escopo": "Total", "diametro_casco_mm": 764,
                   "esp_casco_mm": 9.5, "corrosao_mm": 3, "comprimento_casco_mm": 1631}
        q = create_permutador_quotation(cust, "BEU", cleaned, quote_completo("BEU"))
        snap = q.snapshots.first()
        self.assertIn("memorial", snap.outputs)
        self.assertTrue(snap.standard_refs)
        self.assertTrue(any("ASME" in ref.get("norma", "") for ref in snap.standard_refs))


    def test_snapshot_permutador_pressurizado_exige_memorial(self):
        from unittest.mock import patch
        from apps.quotations.services import create_permutador_quotation
        from pricing_engine.permutador_quote import quote_completo
        cust = Customer.objects.create(company_name="ACME Empty Memo")
        cleaned = {"designacao": "BEU", "pressao_projeto_bar": 50}
        with patch("apps.tema_templates.services.memorial_asme", return_value=[]):
            with self.assertRaises(RuntimeError):
                create_permutador_quotation(cust, "BEU", cleaned, quote_completo("BEU"))

    def test_snapshot_permutador_propaga_falha_do_memorial(self):
        from unittest.mock import patch
        from apps.quotations.services import create_permutador_quotation
        from pricing_engine.permutador_quote import quote_completo
        cust = Customer.objects.create(company_name="ACME Fail")
        cleaned = {"designacao": "BEU", "pressao_projeto_bar": 50}
        with patch("apps.tema_templates.services.memorial_asme", side_effect=RuntimeError("boom")):
            with self.assertRaises(RuntimeError):
                create_permutador_quotation(cust, "BEU", cleaned, quote_completo("BEU"))

    def test_to_feixe_inputs_merge_defaults(self):
        q = Quotation(inputs={"n_tubos": 99}, customer=self.customer)
        inp = to_feixe_inputs(q)
        self.assertEqual(inp.n_tubos, 99)
        self.assertEqual(inp.tubo_material, "SA-179")    # default preservado


class PricingBasisTests(TenantTestCase):
    """SQ-COST-2: proveniência do preço (`referencial` vs `validado_custo`).

    Não é um campo editável à mão (ver spec SQ-COST-1 §5.2) — este ciclo só garante
    o default/backfill `referencial` e a exposição do rótulo humano. `validado_custo`
    só passa a ser atingível quando `CostStructure`/preço mínimo existirem (SQ-COST-4/5).
    """

    def setUp(self):
        self.customer = Customer.objects.create(company_name="Cliente Provenance")

    def test_nova_cotacao_default_referencial(self):
        q = create_feixe_quotation(self.customer, "Feixe provenance")
        self.assertEqual(q.pricing_basis, "referencial")

    def test_label_humano_provenance(self):
        q = create_feixe_quotation(self.customer, "Feixe provenance label")
        self.assertEqual(q.get_pricing_basis_display(), "Referencial")

    def test_pricing_basis_nao_e_campo_do_form_data_sheet(self):
        """Guardrail do spec: usuário não pode marcar `validado_custo` à mão via form comum."""
        from apps.quotations.forms import FeixeDataSheetForm
        self.assertNotIn("pricing_basis", FeixeDataSheetForm.base_fields)

    def test_recompute_nao_altera_totais_calculados(self):
        """Regressão: adicionar provenance não move nenhum total já validado pelos gates."""
        baseline = create_feixe_quotation(self.customer, "Feixe baseline pricing basis", inputs=default_inputs())
        q = create_feixe_quotation(self.customer, "Feixe com provenance", inputs=default_inputs())

        self.assertEqual(q.pricing_basis, baseline.pricing_basis)
        self.assertEqual(q.custo_material, baseline.custo_material)
        self.assertEqual(q.custo_mo, baseline.custo_mo)
        self.assertEqual(q.custo_total, baseline.custo_total)
        self.assertEqual(q.preco_sem_impostos, baseline.preco_sem_impostos)
        self.assertEqual(q.preco_com_impostos, baseline.preco_com_impostos)


class PricingBasisMigrationTests(TenantMigrationTestCase):
    migrate_from = ("quotations", "0007_quotation_avisos")
    migrate_to = ("quotations", "0008_quotation_pricing_basis")

    def setUp(self):
        super().setUp()
        self.executor = MigrationExecutor(connection)
        self.executor.loader.build_graph()
        self.executor.migrate([self.migrate_from])

        old_apps = self.executor.loader.project_state([self.migrate_from]).apps
        customer = old_apps.get_model("quotations", "Customer").objects.create(
            company_name="Cliente legado provenance"
        )
        old_apps.get_model("quotations", "Quotation").objects.create(
            number="COT-LEGACY-PB-0001",
            customer=customer,
            title="Cotacao legado provenance",
        )

        self.executor = MigrationExecutor(connection)
        self.executor.loader.build_graph()
        self.executor.migrate([self.migrate_to])
        self.apps = self.executor.loader.project_state([self.migrate_to]).apps

    def tearDown(self):
        executor = MigrationExecutor(connection)
        executor.loader.build_graph()
        executor.migrate([self.migrate_to])
        super().tearDown()

    def test_migration_backfill_pricing_basis_referencial(self):
        quotation = self.apps.get_model("quotations", "Quotation").objects.get(
            number="COT-LEGACY-PB-0001"
        )
        self.assertEqual(quotation.pricing_basis, "referencial")


class ItemOperationMigrationTests(TenantMigrationTestCase):
    migrate_from = ("quotations", "0003_customer_phone")
    migrate_to = ("quotations", "0004_itemoperation_custo_direto_itemoperation_horas_hh_and_more")

    def setUp(self):
        super().setUp()
        self.executor = MigrationExecutor(connection)
        self.executor.loader.build_graph()
        self.executor.migrate([self.migrate_from])

        old_apps = self.executor.loader.project_state([self.migrate_from]).apps
        customer = old_apps.get_model("quotations", "Customer").objects.create(
            company_name="Cliente legado"
        )
        quotation = old_apps.get_model("quotations", "Quotation").objects.create(
            number="COT-LEGACY-0001",
            customer=customer,
            title="Cotacao legado",
        )
        item = old_apps.get_model("quotations", "QuotationItem").objects.create(
            quotation=quotation,
            codigo_item="ITEM-LEGACY",
            descricao="Item legado",
        )
        old_apps.get_model("quotations", "ItemOperation").objects.create(
            item=item,
            codigo_op="OP-LEGACY",
            descricao="Operacao legado",
            custo=Decimal("321.00"),
        )

        self.executor = MigrationExecutor(connection)
        self.executor.loader.build_graph()
        self.executor.migrate([self.migrate_to])
        self.apps = self.executor.loader.project_state([self.migrate_to]).apps

    def tearDown(self):
        executor = MigrationExecutor(connection)
        executor.loader.build_graph()
        executor.migrate([self.migrate_to])
        super().tearDown()

    def test_migration_backfill_define_campos_editaveis(self):
        operation = self.apps.get_model("quotations", "ItemOperation").objects.get(
            codigo_op="OP-LEGACY"
        )

        self.assertTrue(operation.custo_direto)
        self.assertEqual(operation.horas_hh, Decimal("0.00"))
        self.assertEqual(operation.horas_hm, Decimal("0.00"))
        self.assertEqual(operation.taxa_hora, Decimal("0.00"))
        self.assertEqual(operation.taxa_hora_hm, Decimal("0.00"))
        self.assertEqual(operation.custo, Decimal("321.00"))


class QuotationPartTests(TenantTestCase):
    """Task 3: composição por partes avulsas + scope 'parts'."""

    def setUp(self):
        from apps.tema_templates.models import ComponentTemplate
        self.customer = Customer.objects.create(company_name="Cliente Reposição")
        self.casco = ComponentTemplate.objects.create(
            tema_part="shell", tema_letter="E", name="Casco E")
        self.cabecote = ComponentTemplate.objects.create(
            tema_part="front_head", tema_letter="A", name="Cabeçote A")

    def test_scope_parts_disponivel(self):
        self.assertIn("parts", dict(Quotation.SCOPE))

    def test_cria_partes_com_ordenacao_e_related_name(self):
        from apps.quotations.models import QuotationPart
        q = Quotation.objects.create(
            number="COT-PARTS-1", customer=self.customer, title="Reposição", scope="parts")
        QuotationPart.objects.create(quotation=q, template=self.cabecote, tema_letter="A",
                                     material_sigla="SA-105", incluso=False, sort_order=2)
        QuotationPart.objects.create(quotation=q, template=self.casco, tema_letter="E",
                                     material_sigla="SA-516 GR 70", incluso=True, sort_order=1)
        partes = list(q.parts.all())                 # related_name 'parts'
        self.assertEqual(len(partes), 2)
        self.assertEqual(partes[0].template, self.casco)   # sort_order=1 primeiro
        self.assertEqual(q.parts.filter(incluso=True).count(), 1)


class CosturaARecomputeTests(TenantTestCase):
    """Task 4: recompute() ramifica por scope — foco no custeio de PARTES avulsas."""

    def setUp(self):
        from datetime import date
        from apps.tema_templates.models import ComponentTemplate, ComponentOperation
        from apps.engineering_params.models import ProcessParameter, Rate
        from apps.materials.models import Material, MaterialPrice
        self.customer = Customer.objects.create(company_name="Cliente Reposição")
        mat = Material.objects.create(sigla="SA-516 GR 70", tipo="AÇO CARBONO")
        MaterialPrice.objects.create(material=mat, forma="chapa",
                                     preco_brl_kg="20.00", valid_from=date(2020, 1, 1))
        self.casco = ComponentTemplate.objects.create(
            tema_part="shell", tema_letter="E", name="Casco E")
        ComponentOperation.objects.create(
            template=self.casco, codigo_op="OP-CORTE", descricao="Corte de chapa",
            operacao="CORTE_CHAPA", metodo="manual", driver="massa", setup_fixo=Decimal("2"))
        ProcessParameter.objects.create(
            operacao="CORTE_CHAPA", metodo="manual", valor=Decimal("0.01"),
            unidade="fator", valid_from=date(2020, 1, 1))
        Rate.objects.create(operacao="CORTE_CHAPA", rate_hh=Decimal("100.00"),
                            valid_from=date(2020, 1, 1))

    def test_parts_custeia_material_e_mo_com_origem_template(self):
        from apps.quotations.models import QuotationPart
        q = Quotation.objects.create(number="COT-P1", customer=self.customer,
                                     title="Casco reposição", scope="parts")
        QuotationPart.objects.create(quotation=q, template=self.casco, tema_letter="E",
                                     material_sigla="SA-516 GR 70",
                                     params={"massa": 500}, incluso=True)
        recompute(q)
        q.refresh_from_db()
        self.assertEqual(q.custo_material, Decimal("10000.00"))   # 500kg × R$20
        self.assertGreater(q.custo_mo, 0)
        op = ItemOperation.objects.get(item__quotation=q, codigo_op="OP-CORTE")
        self.assertEqual(op.origem, "template")
        self.assertFalse(op.custo_direto)
        self.assertEqual(op.horas_hh, Decimal("7.00"))           # 500×0.01 + setup 2
        self.assertEqual(op.custo, Decimal("700.00"))            # 7h × R$100 × FC 1.0
        self.assertEqual(op.horas_hh_sugerida, Decimal("7.00"))

    def test_parts_ignora_peca_nao_inclusa(self):
        from apps.quotations.models import QuotationPart
        q = Quotation.objects.create(number="COT-P2", customer=self.customer,
                                     title="Casco off", scope="parts")
        QuotationPart.objects.create(quotation=q, template=self.casco,
                                     material_sigla="SA-516 GR 70",
                                     params={"massa": 500}, incluso=False)
        recompute(q)
        q.refresh_from_db()
        self.assertEqual(q.itens.count(), 0)
        self.assertEqual(q.custo_total, Decimal("0.00"))


class DatabookServiceTests(TenantTestCase):
    """Task 5: Databook de Suprimentos (ASTM por componente, consome MaterialStandard)."""

    def setUp(self):
        from django.core.management import call_command
        from apps.tema_templates.models import ComponentTemplate
        call_command("seed_material_standards")
        self.customer = Customer.objects.create(company_name="Cliente Reposição")
        self.casco = ComponentTemplate.objects.create(
            tema_part="shell", tema_letter="E", name="Casco E")
        self.cabecote = ComponentTemplate.objects.create(
            tema_part="front_head", tema_letter="A", name="Cabeçote A")

    def _databook_casco_inox_cabecote(self):
        from apps.quotations.models import QuotationPart
        from apps.quotations.databook import build_databook
        q = Quotation.objects.create(number="COT-DB1", customer=self.customer,
                                     title="Reposição", scope="parts")
        QuotationPart.objects.create(quotation=q, template=self.casco, tema_letter="E",
                                     material_sigla="ASTM A240 Tp 316L", incluso=True, sort_order=1)
        QuotationPart.objects.create(quotation=q, template=self.cabecote, tema_letter="A",
                                     material_sigla="SA-516 GR 70", incluso=True, sort_order=2)
        return build_databook(q)

    def test_casco_inox_resolve_norma_316L(self):
        rows = self._databook_casco_inox_cabecote()
        chapa_inox = [r for r in rows if "316L" in r["norma_astm"]]
        self.assertTrue(chapa_inox, "esperava chapa de pressão inox 316L")
        self.assertEqual(chapa_inox[0]["certificacao"], "EN 10204 3.1")

    def test_cabecote_puxa_junta_e_prisioneiros(self):
        rows = self._databook_casco_inox_cabecote()
        normas = " | ".join(r["norma_astm"] for r in rows)
        self.assertIn("Double Jacketed", normas)     # junta de cabeçote
        self.assertIn("A193 Gr. B7", normas)          # prisioneiros
        self.assertIn("A194", normas)                 # porcas


class ComposePartsTests(TenantTestCase):
    """Task 9: UI compor — montar TEMA ou só partes."""

    def setUp(self):
        from django.contrib.auth.models import User
        from apps.accounts.models import UserProfile
        from apps.tema_templates.models import ComponentTemplate
        self.client.defaults["HTTP_HOST"] = self.get_test_tenant_domain()
        self.user = User.objects.create_user(username="orc", password="senha-forte-123")
        UserProfile.objects.create(user=self.user, full_name="Orc",
                                   role=UserProfile.ROLE_ORCAMENTISTA)
        self.client.force_login(self.user)
        self.casco = ComponentTemplate.objects.create(
            tema_part="shell", tema_letter="E", name="Casco E")

    def test_form_carrega(self):
        self.assertEqual(self.client.get("/cotacoes/nova/partes/").status_code, 200)

    def test_cria_cotacao_de_partes(self):
        from apps.quotations.models import QuotationPart
        resp = self.client.post("/cotacoes/nova/partes/criar/", {
            "customer_name": "Cliente X", "title": "Reposição casco",
            "template_id": str(self.casco.pk),
            f"material_{self.casco.pk}": "SA-516 GR 70",
            f"massa_{self.casco.pk}": "500",
        })
        self.assertEqual(resp.status_code, 302)
        q = Quotation.objects.get(title="Reposição casco")
        self.assertEqual(q.scope, "parts")
        self.assertEqual(q.parts.count(), 1)
        self.assertEqual(q.parts.first().material_sigla, "SA-516 GR 70")

    def test_compat_check_avisa_incompativel(self):
        resp = self.client.get("/cotacoes/partes/compat/", {"front": "N", "shell": "E", "rear": "M"})
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "N")   # aviso sobre cabeçote frontal N


class FolgaRcb43Tests(TenantTestCase):
    """Task 8: folga periférica shell-to-bundle (TEMA RCB-4.3) do feixe de reposição."""

    def setUp(self):
        from apps.tema_templates.models import ComponentTemplate
        from apps.quotations.validators import validate_folga_feixe
        self.validate = validate_folga_feixe
        self.customer = Customer.objects.create(company_name="Cliente")
        self.feixe_tmpl = ComponentTemplate.objects.create(
            tema_part="tube_bundle", name="Feixe reto")

    def _q_feixe(self, d_casco):
        from apps.quotations.models import QuotationPart
        q = Quotation.objects.create(number=f"COT-F{Quotation.objects.count()}",
                                     customer=self.customer, title="Feixe", scope="parts")
        QuotationPart.objects.create(
            quotation=q, template=self.feixe_tmpl, incluso=True,
            params={"n_tubos": 100, "od_tubo_mm": 19.05, "d_casco_mm": d_casco, "cabecote": "M"})
        return q

    def test_folga_suficiente_sem_aviso(self):
        self.assertEqual(self.validate(self._q_feixe(400)), [])   # feixe ≈274mm, folga >> 12

    def test_folga_apertada_warning_rcb43(self):
        avisos = self.validate(self._q_feixe(280))   # feixe ≈274mm → folga ~6mm < 12
        self.assertTrue(avisos)
        self.assertEqual(avisos[0]["nivel"], "warning")
        self.assertIn("RCB-4.3", avisos[0]["mensagem"])

    def test_folga_negativa_block(self):
        avisos = self.validate(self._q_feixe(250))   # feixe ≈274mm > casco → não entra
        self.assertTrue(avisos)
        self.assertEqual(avisos[0]["nivel"], "block")
        self.assertEqual(avisos[0]["codigo"], "FOLGA_RCB43_NEGATIVA")


class MetalurgiaValidatorTests(TenantTestCase):
    """Task 7: validador metalúrgico/térmico → Quotation.avisos."""

    def setUp(self):
        from apps.quotations.validators import validate_metalurgia
        self.validate = validate_metalurgia
        self.customer = Customer.objects.create(company_name="Cliente")

    def _q(self, **inputs):
        return Quotation.objects.create(
            number=f"COT-V{Quotation.objects.count()}", customer=self.customer,
            title="V", scope="tube_bundle", inputs=inputs)

    def test_warning_inox_feixe_casco_cs_espelho_fixo(self):
        q = self._q(tubo_material="ASTM A213 Tp 316L", casco_material="ASTM A516 Gr 70",
                    designacao="AEM", temperatura_projeto_c=200)   # rear M = espelho fixo
        avisos = self.validate(q)
        codes = [a["codigo"] for a in avisos]
        self.assertIn("THERM_EXPANSAO_FIXO", codes)
        msg = next(a["mensagem"] for a in avisos if a["codigo"] == "THERM_EXPANSAO_FIXO")
        self.assertIn("junta de expansão", msg)
        self.assertTrue("TEMA U" in msg or " S " in msg)

    def test_block_chicana_a36_tubos_inox_corrosivo(self):
        q = self._q(tubo_material="ASTM A249 Tp 304L", chicana_material="ASTM A36",
                    servico_corrosivo=True)
        avisos = self.validate(q)
        blocks = [a for a in avisos if a["nivel"] == "block"]
        self.assertTrue(blocks)
        self.assertEqual(blocks[0]["codigo"], "GALVANICA_CHICANA")

    def test_compativel_sem_block(self):
        q = self._q(tubo_material="SA-179", casco_material="SA-516 GR 70", designacao="AEM")
        avisos = self.validate(q)
        self.assertFalse([a for a in avisos if a["nivel"] == "block"])
        self.assertNotIn("THERM_EXPANSAO_FIXO", [a["codigo"] for a in avisos])

    def test_recompute_persiste_avisos(self):
        from apps.tema_templates.models import ComponentTemplate
        from apps.quotations.models import QuotationPart
        feixe = ComponentTemplate.objects.create(tema_part="tube_bundle", name="Feixe")
        casco = ComponentTemplate.objects.create(tema_part="shell", name="Casco")
        rear = ComponentTemplate.objects.create(tema_part="rear_head", tema_letter="M", name="Cab M")
        q = Quotation.objects.create(number="COT-VR", customer=self.customer,
                                     title="VR", scope="parts")
        QuotationPart.objects.create(quotation=q, template=feixe, material_sigla="ASTM A213 Tp 316L",
                                     params={"delta_t": 180}, incluso=True)
        QuotationPart.objects.create(quotation=q, template=casco, material_sigla="ASTM A516 Gr 70",
                                     incluso=True)
        QuotationPart.objects.create(quotation=q, template=rear, tema_letter="M", incluso=True)
        recompute(q)
        q.refresh_from_db()
        self.assertIn("THERM_EXPANSAO_FIXO", [a["codigo"] for a in q.avisos])


class DatabookViewTests(TenantTestCase):
    """Task 6: view + CSV do Databook."""

    def setUp(self):
        from django.contrib.auth.models import User
        from django.core.management import call_command
        from apps.accounts.models import UserProfile
        from apps.tema_templates.models import ComponentTemplate
        from apps.quotations.models import QuotationPart
        call_command("seed_material_standards")
        self.client.defaults["HTTP_HOST"] = self.get_test_tenant_domain()
        self.user = User.objects.create_user(username="orc", password="senha-forte-123")
        UserProfile.objects.create(user=self.user, full_name="Orc",
                                   role=UserProfile.ROLE_ORCAMENTISTA)
        self.client.force_login(self.user)
        customer = Customer.objects.create(company_name="Cliente")
        casco = ComponentTemplate.objects.create(tema_part="shell", tema_letter="E", name="Casco E")
        self.q = Quotation.objects.create(number="COT-DBV", customer=customer,
                                          title="Reposição", scope="parts")
        QuotationPart.objects.create(quotation=self.q, template=casco,
                                     material_sigla="ASTM A240 Tp 316L", incluso=True)

    def test_databook_view_200(self):
        resp = self.client.get(f"/cotacoes/{self.q.pk}/databook/")
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "316L")

    def test_databook_csv(self):
        resp = self.client.get(f"/cotacoes/{self.q.pk}/databook.csv")
        self.assertEqual(resp.status_code, 200)
        self.assertIn("text/csv", resp["Content-Type"])
        self.assertIn("316L", resp.content.decode("utf-8"))


class ItemOperationProvenanceTests(TenantTestCase):
    """Task 2: override NÃO-DESTRUTIVO — origem + horas sugeridas + restaurar."""

    def setUp(self):
        from django.contrib.auth.models import User
        from apps.accounts.models import UserProfile
        self.client.defaults["HTTP_HOST"] = self.get_test_tenant_domain()
        self.customer = Customer.objects.create(company_name="Petrobras RPBC")
        self.user = User.objects.create_user(username="orc", password="senha-forte-123")
        UserProfile.objects.create(user=self.user, full_name="Orc",
                                   role=UserProfile.ROLE_ORCAMENTISTA)
        self.client.force_login(self.user)

    def _op_horaria(self):
        """Uma cotação de feixe custeada → devolve uma ItemOperation horária (custo_direto=False)."""
        q = create_feixe_quotation(self.customer, "Feixe 136 tubos")
        op = (ItemOperation.objects.filter(item__quotation=q, custo_direto=False)
              .exclude(horas_hh=0).first())
        self.assertIsNotNone(op, "esperava ao menos uma operação horária no feixe")
        return q, op

    def test_recompute_grava_sugeridas_e_origem_seed(self):
        _q, op = self._op_horaria()
        self.assertEqual(op.origem, "seed")
        self.assertEqual(op.horas_hh_sugerida, op.horas_hh)
        self.assertEqual(op.horas_hm_sugerida, op.horas_hm)

    def test_override_marca_manual_e_mantem_sugerida(self):
        _q, op = self._op_horaria()
        sugerida = op.horas_hh_sugerida
        nova = (sugerida or Decimal("0")) + Decimal("7.00")
        resp = self.client.post(
            f"/cotacoes/eap/item/{op.item.pk}/salvar/",
            {f"op_horas_hh_{op.pk}": str(nova)})
        self.assertEqual(resp.status_code, 200)
        op.refresh_from_db()
        self.assertEqual(op.origem, "manual")
        self.assertEqual(op.horas_hh, nova)
        self.assertEqual(op.horas_hh_sugerida, sugerida)   # sugestão preservada

    def test_drawer_mostra_input_aberto_e_chip_origem(self):
        _q, op = self._op_horaria()
        resp = self.client.get(f"/cotacoes/eap/item/{op.item.pk}/drawer/")
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, f"op_horas_hh_{op.pk}")   # input aberto, prefillado
        self.assertContains(resp, "sugerido (motor)")        # chip de origem seed

    def test_restore_volta_sugerida_e_recalcula(self):
        _q, op = self._op_horaria()
        sugerida = op.horas_hh_sugerida
        self.client.post(f"/cotacoes/eap/item/{op.item.pk}/salvar/",
                         {f"op_horas_hh_{op.pk}": str((sugerida or Decimal("0")) + Decimal("9"))})
        resp = self.client.post(f"/cotacoes/eap/op/{op.pk}/restaurar/")
        self.assertEqual(resp.status_code, 200)
        op.refresh_from_db()
        self.assertEqual(op.horas_hh, sugerida)
        self.assertEqual(op.origem, "seed")
        self.assertEqual(op.custo, (op.horas_hh * op.taxa_hora
                                    + op.horas_hm * op.taxa_hora_hm))


class ItemOperationTaxaEditavelTests(TenantTestCase):
    """F1: o VALOR da hora-homem (taxa_hora) e da hora-máquina (taxa_hora_hm) é
    editável no drawer da EAP, além das quantidades. Sem isso, editar horas-HM
    dava horas_hm×0 = 0 e o total não mudava (taxa_hora_hm chega zero na maioria
    das operações)."""

    def setUp(self):
        from django.contrib.auth.models import User
        from apps.accounts.models import UserProfile
        self.client.defaults["HTTP_HOST"] = self.get_test_tenant_domain()
        self.customer = Customer.objects.create(company_name="Petrobras RPBC")
        self.user = User.objects.create_user(username="orc", password="senha-forte-123")
        UserProfile.objects.create(user=self.user, full_name="Orc",
                                   role=UserProfile.ROLE_ORCAMENTISTA)
        self.client.force_login(self.user)

    def _op_horaria(self):
        q = create_feixe_quotation(self.customer, "Feixe 136 tubos")
        op = (ItemOperation.objects.filter(item__quotation=q, custo_direto=False)
              .exclude(horas_hh=0).first())
        self.assertIsNotNone(op, "esperava ao menos uma operação horária no feixe")
        return q, op

    def test_edita_taxa_hora_homem_muda_op_item_e_total(self):
        q, op = self._op_horaria()
        item = op.item
        antes_custo = op.custo
        antes_item_mo = item.custo_mo
        antes_total = q.custo_total
        nova_taxa = op.taxa_hora + Decimal("50.00")
        esperado_op = (op.horas_hh * nova_taxa) + (op.horas_hm * op.taxa_hora_hm)
        delta = esperado_op - antes_custo
        self.assertGreater(delta, Decimal("0"))

        resp = self.client.post(
            f"/cotacoes/eap/item/{item.pk}/salvar/",
            {f"op_taxa_hh_{op.pk}": str(nova_taxa)})
        self.assertEqual(resp.status_code, 200)

        op.refresh_from_db(); item.refresh_from_db(); q.refresh_from_db()
        self.assertEqual(op.taxa_hora, nova_taxa)
        self.assertEqual(op.custo, esperado_op)
        self.assertEqual(item.custo_mo, antes_item_mo + delta)
        # custo_total é campo de dinheiro (quantizado a centavos no roll-up); o delta
        # pode ter mais casas, então comparo a 2 decimais.
        self.assertAlmostEqual(q.custo_total, antes_total + delta, places=2)

    def test_edita_taxa_hora_maquina_muda_op_item_e_total(self):
        q, op = self._op_horaria()
        item = op.item
        antes_custo = op.custo
        antes_item_mo = item.custo_mo
        antes_total = q.custo_total
        # dá horas de máquina + valor da hora-máquina (que chegava zero): agora o
        # produto horas_hm×taxa_hora_hm passa a contar no custo derivado.
        novas_horas_hm = Decimal("4.00")
        nova_taxa_hm = Decimal("90.00")
        esperado_op = (op.horas_hh * op.taxa_hora) + (novas_horas_hm * nova_taxa_hm)
        delta = esperado_op - antes_custo
        self.assertNotEqual(delta, Decimal("0"))

        resp = self.client.post(
            f"/cotacoes/eap/item/{item.pk}/salvar/",
            {f"op_horas_hm_{op.pk}": str(novas_horas_hm),
             f"op_taxa_hm_{op.pk}": str(nova_taxa_hm)})
        self.assertEqual(resp.status_code, 200)

        op.refresh_from_db(); item.refresh_from_db(); q.refresh_from_db()
        self.assertEqual(op.taxa_hora_hm, nova_taxa_hm)
        self.assertEqual(op.horas_hm, novas_horas_hm)
        self.assertEqual(op.custo, esperado_op)
        self.assertEqual(item.custo_mo, antes_item_mo + delta)
        # custo_total é campo de dinheiro (quantizado a centavos no roll-up).
        self.assertAlmostEqual(q.custo_total, antes_total + delta, places=2)

    def test_drawer_expoe_inputs_de_taxa(self):
        q, op = self._op_horaria()
        resp = self.client.get(f"/cotacoes/eap/item/{op.item.pk}/drawer/")
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, f"op_taxa_hh_{op.pk}")
        self.assertContains(resp, f"op_taxa_hm_{op.pk}")


class DataSheetViewTests(TenantTestCase):
    """Slice end-to-end via HTTP: login -> data sheet -> recompute -> criar -> detalhe."""

    def setUp(self):
        from django.contrib.auth.models import User
        self.client.defaults["HTTP_HOST"] = self.get_test_tenant_domain()
        self.user = User.objects.create_user(username="orc", password="senha-forte-123")
        from apps.accounts.models import UserProfile
        UserProfile.objects.create(user=self.user, full_name="Orc", role=UserProfile.ROLE_ORCAMENTISTA)
        self.client.force_login(self.user)

    def _form_data(self, **over):
        data = {
            "title": "Feixe 136 tubos", "customer_name": "Petrobras RPBC", "tipo": "TUBO RETO",
            "n_tubos": 136, "tubo_material": "SA-179", "tubo_od_spec": '3/4"',
            "tubo_wall_spec": "BWG 14", "tubo_comp_mm": 6096,
            "espelho_material": "SA-516 GR 70", "espelho_od_mm": 475,
            "espelho_flutuante_od_mm": 412, "espelho_esp_bruta_mm": 44.5,
            "chicana_qty": 18, "chicana_od_mm": 416.8, "chicana_esp_mm": 12.5,
            "chicana_cut_remaining_mm": 300, "tirante_qty": 12,
        }
        data.update(over)
        return data

    def test_data_sheet_carrega(self):
        resp = self.client.get("/cotacoes/nova/feixe/")
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Preço de Venda")
        self.assertContains(resp, "design-system-g.css")

    def test_recompute_htmx_retorna_preco(self):
        resp = self.client.post("/cotacoes/recompute/", self._form_data())
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Preço de Venda")
        self.assertContains(resp, "price-line")

    def test_recompute_responde_a_mais_tubos(self):
        r136 = self.client.post("/cotacoes/recompute/", self._form_data(n_tubos=136))
        r200 = self.client.post("/cotacoes/recompute/", self._form_data(n_tubos=200))
        # extrai o preço grosso do HTML (presença de valores distintos)
        self.assertNotEqual(r136.content, r200.content)

    def test_criar_persiste_e_redireciona_pro_detalhe(self):
        resp = self.client.post("/cotacoes/criar/", self._form_data())
        self.assertEqual(resp.status_code, 302)
        q = Quotation.objects.latest("created_at")
        self.assertGreater(q.preco_com_impostos, 0)
        # detalhe renderiza a EAP + preço
        detalhe = self.client.get(resp.url)
        self.assertEqual(detalhe.status_code, 200)
        self.assertContains(detalhe, q.number)
        self.assertContains(detalhe, "Estrutura Analítica")

    def test_espelho_fixo_espelha_od_do_flutuante_no_od_do_fixo(self):
        """F8a: espelho_tipo='FIXO' desabilita espelho_flutuante_od_mm no front (o campo
        não chega no POST, como um <input disabled>) — o form deve completar o OD do
        flutuante com o OD do fixo (não há cabeçote flutuante distinto nessa construção)."""
        data = self._form_data(espelho_tipo="FIXO", espelho_od_mm=500)
        data.pop("espelho_flutuante_od_mm", None)
        resp = self.client.post("/cotacoes/criar/", data)
        self.assertEqual(resp.status_code, 302)
        q = Quotation.objects.latest("created_at")
        self.assertEqual(q.inputs["espelho_tipo"], "FIXO")
        self.assertEqual(q.inputs["espelho_flutuante_od_mm"], 500.0)

    def test_espelho_flutuante_default_quando_tipo_omitido(self):
        """Sem espelho_tipo no POST (form legado/JS desabilitado), cai no default
        'FLUTUANTE' e preserva o OD flutuante enviado."""
        data = self._form_data()
        data.pop("espelho_tipo", None)
        resp = self.client.post("/cotacoes/criar/", data)
        self.assertEqual(resp.status_code, 302)
        q = Quotation.objects.latest("created_at")
        self.assertEqual(q.inputs["espelho_tipo"], "FLUTUANTE")
        self.assertEqual(q.inputs["espelho_flutuante_od_mm"], 412.0)

    def test_espacadores_aceitos_e_alteram_o_recompute(self):
        """F8a: espacador_qty/material/comp_mm são aceitos pelo form e realmente
        alteram o custo (ESC-6a em pricing_engine/components.py usa esses inputs)."""
        poucos = self.client.post(
            "/cotacoes/recompute/", self._form_data(espacador_qty=2, espacador_comp_mm=6096)
        )
        muitos = self.client.post(
            "/cotacoes/recompute/", self._form_data(espacador_qty=60, espacador_comp_mm=6096)
        )
        self.assertEqual(poucos.status_code, 200)
        self.assertEqual(muitos.status_code, 200)
        self.assertNotEqual(poucos.content, muitos.content)

    def test_login_required(self):
        self.client.logout()
        resp = self.client.get("/cotacoes/nova/feixe/")
        self.assertEqual(resp.status_code, 302)
        self.assertIn("/login/", resp.url)


class QuotationRBACTests(TenantTestCase):
    """RBAC do app quotations (espelha o padrão require_role de production/engineering_params).

    Regra: qualquer membro autenticado pode VER/listar; só papéis com permissão de
    escrita podem CRIAR, recomputar/precificar ou revisar.

    Nota de modelagem: orçamentista é o autor das cotações (papel default; exigido pelos
    testes legados de revisão em test_feature.py), e os papéis que editam
    engineering_params/production (engenheiro, gestor_comercial, admin) também escrevem —
    ou seja, TODO papel de tenant é autor. O principal que NÃO tem papel de escrita no
    tenant é um superusuário de plataforma (passa o TenantMembershipMiddleware pelo atalho
    is_superuser, mas não possui UserProfile/role) → deve receber 403 na escrita/preço.
    """

    def setUp(self):
        from django.contrib.auth.models import User
        from apps.accounts.models import UserProfile
        self.client.defaults["HTTP_HOST"] = self.get_test_tenant_domain()
        self.customer = Customer.objects.create(company_name="RBAC Cliente")
        # principal SEM papel de escrita no tenant (superuser de plataforma, sem UserProfile → role None)
        self.user_sem_papel = User.objects.create_superuser(
            username="platops", password="x123456789", email="ops@x.com")
        # usuário com papel autorizado (orçamentista = autor de cotações; default e exigido por testes legados)
        self.user_autorizado = User.objects.create_user(username="orcok", password="x123456789")
        UserProfile.objects.create(
            user=self.user_autorizado, full_name="Orc OK", role=UserProfile.ROLE_ORCAMENTISTA)

    def _form_data(self, **over):
        data = {
            "title": "Feixe 136 tubos", "customer_name": "RBAC Cliente", "tipo": "TUBO RETO",
            "n_tubos": 136, "tubo_material": "SA-179", "tubo_od_spec": '3/4"',
            "tubo_wall_spec": "BWG 14", "tubo_comp_mm": 6096,
            "espelho_material": "SA-516 GR 70", "espelho_od_mm": 475,
            "espelho_flutuante_od_mm": 412, "espelho_esp_bruta_mm": 44.5,
            "chicana_qty": 18, "chicana_od_mm": 416.8, "chicana_esp_mm": 12.5,
            "chicana_cut_remaining_mm": 300, "tirante_qty": 12,
        }
        data.update(over)
        return data

    def test_criar_negado_para_usuario_sem_papel(self):
        self.client.force_login(self.user_sem_papel)
        resp = self.client.post("/cotacoes/criar/", self._form_data())
        self.assertEqual(resp.status_code, 403)

    def test_recompute_negado_para_usuario_sem_papel(self):
        self.client.force_login(self.user_sem_papel)
        resp = self.client.post("/cotacoes/recompute/", self._form_data())
        self.assertEqual(resp.status_code, 403)

    def test_data_sheet_negado_para_usuario_sem_papel(self):
        self.client.force_login(self.user_sem_papel)
        resp = self.client.get("/cotacoes/nova/feixe/")
        self.assertEqual(resp.status_code, 403)

    def test_revisar_negado_para_usuario_sem_papel(self):
        q = create_feixe_quotation(self.customer, "Feixe RBAC")
        self.client.force_login(self.user_sem_papel)
        resp = self.client.post(f"/cotacoes/{q.pk}/revisar/")
        self.assertEqual(resp.status_code, 403)

    def test_listar_permitido_para_membro_autenticado(self):
        # VER/listar continua liberado para qualquer membro autenticado do tenant
        self.client.force_login(self.user_autorizado)
        resp = self.client.get("/cotacoes/")
        self.assertEqual(resp.status_code, 200)

    def test_criar_permitido_para_papel_autorizado(self):
        self.client.force_login(self.user_autorizado)
        resp = self.client.post("/cotacoes/criar/", self._form_data())
        self.assertEqual(resp.status_code, 302)

    def test_detalhe_permitido_para_operador_staff_sem_perfil(self):
        # Operador de plataforma (is_superuser, sem UserProfile) passa o
        # TenantMembershipMiddleware pelo atalho de has_tenant_membership; o
        # detalhe (LEITURA) deve continuar acessível a ele, como antes de
        # quotation_detail trocar @login_required por @require_role(*_READ_ROLES).
        q = create_feixe_quotation(self.customer, "Feixe RBAC Detalhe")
        self.client.force_login(self.user_sem_papel)
        resp = self.client.get(f"/cotacoes/{q.pk}/")
        self.assertEqual(resp.status_code, 200)

    def test_recompute_permitido_para_papel_autorizado(self):
        self.client.force_login(self.user_autorizado)
        resp = self.client.post("/cotacoes/recompute/", self._form_data())
        self.assertEqual(resp.status_code, 200)


class QuotationSetStatusTests(TenantTestCase):
    def setUp(self):
        from django.contrib.auth.models import User
        from apps.accounts.models import UserProfile

        self.client.defaults["HTTP_HOST"] = self.get_test_tenant_domain()
        self.customer = Customer.objects.create(company_name="Status Cliente")
        self.quotation = create_feixe_quotation(self.customer, "Feixe Status")
        self.user_autorizado = User.objects.create_user(username="status-orc", password="x123456789")
        UserProfile.objects.create(
            user=self.user_autorizado,
            full_name="Status Orc",
            role=UserProfile.ROLE_ORCAMENTISTA,
        )
        self.user_sem_papel = User.objects.create_superuser(
            username="status-ops",
            password="x123456789",
            email="status-ops@example.com",
        )
        self.url = f"/cotacoes/{self.quotation.pk}/status/"

    def test_post_valido_muda_status_e_persiste(self):
        self.client.force_login(self.user_autorizado)

        resp = self.client.post(self.url, {"status": "approved"})

        self.assertEqual(resp.status_code, 200)
        self.quotation.refresh_from_db()
        self.assertEqual(self.quotation.status, "approved")
        self.assertContains(resp, "Aprovada")
        self.assertContains(resp, "q-status--approved")

    def test_status_invalido_retorna_400_e_nao_persiste(self):
        self.client.force_login(self.user_autorizado)

        resp = self.client.post(self.url, {"status": "cancelled"})

        self.assertEqual(resp.status_code, 400)
        self.quotation.refresh_from_db()
        self.assertEqual(self.quotation.status, "draft")

    def test_sem_permissao_bloqueado(self):
        self.client.force_login(self.user_sem_papel)

        resp = self.client.post(self.url, {"status": "approved"})

        self.assertEqual(resp.status_code, 403)
        self.quotation.refresh_from_db()
        self.assertEqual(self.quotation.status, "draft")


class QuotationEntryFlowTests(TenantTestCase):
    def setUp(self):
        from django.contrib.auth.models import User
        from apps.accounts.models import UserProfile

        self.client.defaults["HTTP_HOST"] = self.get_test_tenant_domain()
        self.user = User.objects.create_user(username="orc-entry", password="senha-forte-123")
        UserProfile.objects.create(
            user=self.user,
            full_name="Orc Entry",
            role=UserProfile.ROLE_ORCAMENTISTA,
        )

        self.engineer_user = User.objects.create_user(username="eng-entry", password="senha-forte-123")
        self.engineer_profile = UserProfile.objects.create(
            user=self.engineer_user,
            full_name="Eng Entry",
            role=UserProfile.ROLE_ENGENHEIRO,
            crea_number="12345",
            crea_state="SP",
        )

        self.customer_a = Customer.objects.create(company_name="Cliente Alpha")
        self.customer_b = Customer.objects.create(company_name="Cliente Beta")
        self.client.force_login(self.user)

    def _new_quotation_payload(self, **overrides):
        data = {
            "customer": self.customer_a.pk,
            "title": "Nova Cotacao Alpha",
            "description": "Descricao livre",
            "valid_until": "2026-08-01",
            "delivery_weeks": "6",
            "payment_terms": "30 dias",
            "engineer_responsavel": self.engineer_profile.pk,
        }
        data.update(overrides)
        return data

    def test_lista_cotacoes_exibe_statuspill_filtros_e_botao_nova(self):
        q_draft = create_feixe_quotation(self.customer_a, "Feixe Alpha", created_by=self.user)
        q_draft.status = "lost"
        q_draft.save(update_fields=["status"])
        create_feixe_quotation(self.customer_b, "Feixe Beta", created_by=self.user)

        resp = self.client.get("/cotacoes/")

        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "+ Nova Cotação")
        self.assertContains(resp, "q-status")
        self.assertContains(resp, "Rev. A")
        self.assertContains(resp, "Cliente Alpha")
        self.assertContains(resp, "font-style: italic")

        filtered = self.client.get("/cotacoes/", {"status": ["lost"], "customer": self.customer_a.pk, "q": "Alpha"})
        self.assertEqual(filtered.status_code, 200)
        self.assertContains(filtered, "Feixe Alpha")
        self.assertNotContains(filtered, "Feixe Beta")

    def test_cotacao_nova_carrega_campos_chave(self):
        resp = self.client.get("/cotacoes/nova/")

        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "COT · Nova")
        self.assertContains(resp, "Cliente")
        self.assertContains(resp, "Título")
        self.assertContains(resp, "Descrição")
        self.assertContains(resp, "Válido até")
        self.assertContains(resp, "Prazo de entrega")
        self.assertContains(resp, "Condições de pagamento")
        self.assertContains(resp, "Engenheiro responsável")
        self.assertContains(resp, "Salvar e continuar")
        self.assertContains(resp, "Cancelar")

    def test_cotacao_nova_post_valido_cria_rascunho_e_redireciona(self):
        resp = self.client.post("/cotacoes/nova/", self._new_quotation_payload())

        self.assertEqual(resp.status_code, 302)
        q = Quotation.objects.latest("created_at")
        self.assertEqual(q.status, "draft")
        self.assertEqual(q.customer, self.customer_a)
        self.assertEqual(q.title, "Nova Cotacao Alpha")
        self.assertEqual(q.created_by, self.user)
        detalhe = self.client.get(resp.url)
        self.assertEqual(detalhe.status_code, 200)
        self.assertContains(detalhe, q.number)


class PermutadorQuotationTests(TenantTestCase):
    """Ciclo cotação→proposta: persistir a cotação do permutador a partir do motor."""

    def test_persiste_totais_do_permutador(self):
        from apps.quotations.services import create_permutador_quotation
        from pricing_engine.permutador_quote import quote_completo
        cust = Customer.objects.create(company_name="ACME Ltda")
        resultado = quote_completo("BEU")
        q = create_permutador_quotation(cust, "BEU", {"designacao": "BEU", "n_tubos": 68},
                                        resultado)
        self.assertEqual(q.scope, "complete")
        self.assertEqual(q.inputs.get("designacao"), "BEU")
        self.assertAlmostEqual(float(q.preco_com_impostos),
                               round(resultado["preco_com_impostos"], 2), places=2)
        self.assertAlmostEqual(float(q.custo_material),
                               round(resultado["custo_material"], 2), places=2)
        # custo_mo da Quotation = mão de obra + serviços do permutador
        self.assertAlmostEqual(
            float(q.custo_mo),
            round(resultado["custo_mao_obra"] + resultado["custo_servicos"], 2), places=2)
        self.assertEqual(q.snapshots.count(), 1)

    def test_cria_itens_por_secao(self):
        from apps.quotations.services import create_permutador_quotation
        from pricing_engine.permutador_quote import quote_completo
        cust = Customer.objects.create(company_name="ACME")
        resultado = quote_completo("BEU")
        q = create_permutador_quotation(cust, "BEU", {}, resultado)
        itens = q.itens.all()
        self.assertEqual(itens.count(), len(resultado["por_secao"]))
        soma = sum(float(i.custo_material) + float(i.custo_mo) for i in itens)
        self.assertAlmostEqual(soma, sum(resultado["por_secao"].values()), places=1)
        self.assertEqual(q.snapshots.count(), 1)

    def test_loop_fecha_gera_proposta(self):
        """Prova o ciclo: cotação do permutador → proposta com o preço correto."""
        from apps.quotations.services import create_permutador_quotation
        from apps.proposals.services import create_proposal, build_context
        from pricing_engine.permutador_quote import quote_completo
        cust = Customer.objects.create(company_name="ACME")
        resultado = quote_completo("BEU")
        q = create_permutador_quotation(cust, "BEU", {"n_tubos": 68}, resultado)
        prop = create_proposal(q)
        self.assertEqual(prop.quotation_id, q.id)
        ctx = build_context(q)
        self.assertEqual(ctx["preco_com_impostos"], q.preco_com_impostos)
        self.assertEqual(ctx["cliente"], "ACME")


class CustomerQuickCreateTests(TenantTestCase):
    """Endpoint JSON do modal de cadastro rápido de cliente (Nova Cotação)."""

    def setUp(self):
        from django.contrib.auth.models import User
        from apps.accounts.models import UserProfile
        self.client.defaults["HTTP_HOST"] = self.get_test_tenant_domain()
        self.user = User.objects.create_user(username="orc2", password="senha-forte-123")
        UserProfile.objects.create(user=self.user, full_name="Orc2", role=UserProfile.ROLE_ORCAMENTISTA)
        self.client.force_login(self.user)
        self.url = "/cotacoes/clientes/criar/"

    def test_cria_cliente_e_retorna_json(self):
        resp = self.client.post(self.url, {
            "company_name": "Nova Petro S.A.", "cnpj": "12.345.678/0001-90",
            "contact_name": "Fulano", "email": "fulano@nova.com", "phone": "(11) 98888-7777",
        })
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data["ok"])
        c = Customer.objects.get(pk=data["id"])
        self.assertEqual(c.company_name, "Nova Petro S.A.")
        self.assertEqual(c.phone, "(11) 98888-7777")
        self.assertEqual(data["company_name"], "Nova Petro S.A.")

    def test_campos_obrigatorios_faltando_retorna_400(self):
        resp = self.client.post(self.url, {"cnpj": "", "phone": ""})
        self.assertEqual(resp.status_code, 400)
        data = resp.json()
        self.assertFalse(data["ok"])
        self.assertIn("company_name", data["errors"])
        self.assertIn("contact_name", data["errors"])
        self.assertIn("email", data["errors"])
        self.assertEqual(Customer.objects.count(), 0)

    def test_cnpj_e_telefone_sao_opcionais(self):
        resp = self.client.post(self.url, {
            "company_name": "Sem CNPJ Ltda", "contact_name": "Beltrano", "email": "b@x.com",
        })
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.json()["ok"])

    def test_get_nao_permitido(self):
        resp = self.client.get(self.url)
        self.assertEqual(resp.status_code, 405)


class TemaEntryRoutingTests(TenantTestCase):
    """F4 — tela de entrada TEMA unificada (completo × feixe reto/U).

    Cobre o ROTEAMENTO das duas escolhas da Fase 1: 'Equipamento completo'
    (fluxo tema_templates) e 'Feixe tubular' com reto × U repassado ao data sheet.
    Não custeia nada — só verifica navegação/estado.
    """

    def setUp(self):
        from django.contrib.auth.models import User
        from apps.accounts.models import UserProfile
        self.client.defaults["HTTP_HOST"] = self.get_test_tenant_domain()
        self.user = User.objects.create_user(username="orc", password="senha-forte-123")
        UserProfile.objects.create(user=self.user, full_name="Orc",
                                   role=UserProfile.ROLE_ORCAMENTISTA)
        self.client.force_login(self.user)

    def test_entrada_oferece_completo_e_feixe(self):
        r = self.client.get("/cotacoes/nova/tema/")
        self.assertEqual(r.status_code, 200)
        # Opção A: link para o fluxo de equipamento completo (tema_templates).
        self.assertContains(r, "/tema/compor/")
        # Opção B: escolha reto × U aponta para o data sheet do feixe com ?tipo=.
        self.assertContains(r, "/cotacoes/nova/feixe/?tipo=TUBO%20RETO")
        self.assertContains(r, "/cotacoes/nova/feixe/?tipo=TUBO%20U")

    def test_feixe_reto_pre_seleciona_tipo(self):
        r = self.client.get("/cotacoes/nova/feixe/", {"tipo": "TUBO RETO"})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.context["form"].initial.get("tipo"), "TUBO RETO")

    def test_feixe_u_pre_seleciona_tipo(self):
        r = self.client.get("/cotacoes/nova/feixe/", {"tipo": "TUBO U"})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.context["form"].initial.get("tipo"), "TUBO U")

    def test_tipo_invalido_e_ignorado(self):
        r = self.client.get("/cotacoes/nova/feixe/", {"tipo": "XPTO"})
        self.assertEqual(r.status_code, 200)
        self.assertNotEqual(r.context["form"].initial.get("tipo"), "XPTO")
