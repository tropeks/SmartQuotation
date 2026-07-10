from decimal import Decimal
from django_tenants.test.cases import TenantTestCase

from apps.quotations.models import CalculationSnapshot, Quotation, Customer
from apps.quotations.services import create_feixe_quotation
from apps.quotations.templatetags.money import brl

class FeatureViewsTests(TenantTestCase):
    def setUp(self):
        from django.contrib.auth.models import User
        self.client.defaults["HTTP_HOST"] = self.get_test_tenant_domain()
        self.user = User.objects.create_user(username="orc2", password="123")
        from apps.accounts.models import UserProfile
        UserProfile.objects.create(user=self.user, full_name="Orc2", role=UserProfile.ROLE_ORCAMENTISTA)
        self.client.force_login(self.user)
        self.customer = Customer.objects.create(company_name="Cliente Teste")

    def test_edit_opens_prefilled_and_creates_revision_with_changed_inputs(self):
        """Tier A: 'Revisar' abre form editável pré-preenchido; salvar cria nova
        revisão com os inputs alterados e recalcula a EAP."""
        from django.urls import reverse
        from apps.quotations.forms import FeixeDataSheetForm
        q = create_feixe_quotation(self.customer, "Feixe Edit", created_by=self.user)
        orig_tubos = int((q.inputs or {}).get("n_tubos", 136))

        # GET: form de edição pré-preenchido com os inputs da cotação
        resp = self.client.get(reverse("quotations:edit", args=[q.pk]))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Feixe Edit")
        self.assertContains(resp, str(orig_tubos))

        # POST: muda nº de tubos → nova revisão recalculada
        data = FeixeDataSheetForm.initial_from_quotation(q)
        data = {k: ("" if v is None else v) for k, v in data.items()}
        data["n_tubos"] = orig_tubos + 10
        n_before = Quotation.objects.count()
        self.client.post(reverse("quotations:edit", args=[q.pk]), data)

        self.assertEqual(Quotation.objects.count(), n_before + 1)
        new = Quotation.objects.exclude(pk=q.pk).order_by("-id").first()
        self.assertEqual(new.revision, q.revision + 1)
        self.assertEqual(int(new.inputs["n_tubos"]), orig_tubos + 10)
        self.assertTrue(new.itens.exists())          # motor recalculou a EAP
        self.assertNotEqual(new.custo_total, 0)
        # original permanece intacto
        q.refresh_from_db()
        self.assertEqual(int(q.inputs["n_tubos"]), orig_tubos)

    def test_list_quotations(self):
        q = create_feixe_quotation(self.customer, "Feixe A")
        q.status = "sent"
        q.save()
        resp = self.client.get("/cotacoes/")
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Feixe A")
        self.assertContains(resp, "Cliente Teste")
        self.assertContains(resp, q.number)
        self.assertContains(resp, "Enviada")
        self.assertContains(resp, brl(q.preco_com_impostos))  # pt-BR: separador de milhar
        
    def test_quotation_detail(self):
        q = create_feixe_quotation(self.customer, "Feixe A")
        resp = self.client.get(f"/cotacoes/{q.pk}/")
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Feixe A")
        self.assertContains(resp, q.number)
        self.assertContains(resp, "Estrutura Analítica")
        self.assertContains(resp, "COT-03")
        self.assertContains(resp, "g-breadcrumb")
        self.assertContains(resp, "g-tabs")
        self.assertContains(resp, 'role="tab"')
        self.assertContains(resp, 'id="sec-preco"')
        self.assertContains(resp, "§1")
        self.assertContains(resp, "§6")
        
    def test_quotation_revise_feixe(self):
        q = create_feixe_quotation(self.customer, "Feixe A")
        old_pk = q.pk
        old_num = q.number
        old_rev = q.revision
        resp = self.client.post(f"/cotacoes/{old_pk}/revisar/")
        self.assertEqual(resp.status_code, 302)

        q2 = Quotation.objects.get(pk=resp.url.split("/")[-2])
        self.assertNotEqual(q2.number, old_num)
        self.assertEqual(q2.revision, old_rev + 1)
        self.assertEqual(q2.customer, self.customer)
        self.assertEqual(q2.scope, "tube_bundle")
        self.assertEqual(q2.status, "draft")
        self.assertEqual(q2.title, "Feixe A")
        self.assertEqual(CalculationSnapshot.objects.filter(quotation=q).count(), 1)
        self.assertEqual(CalculationSnapshot.objects.filter(quotation=q2).count(), 1)

    def test_quotation_revise_permutador(self):
        from apps.quotations.services import create_permutador_quotation
        from pricing_engine.permutador_quote import quote_completo
        resultado = quote_completo("BEU")
        q = create_permutador_quotation(self.customer, "BEU", {"designacao": "BEU", "n_tubos": 68}, resultado, title="BEU Test")

        resp = self.client.post(f"/cotacoes/{q.pk}/revisar/")
        self.assertEqual(resp.status_code, 302)

        q2 = Quotation.objects.get(pk=resp.url.split("/")[-2])
        self.assertNotEqual(q2.number, q.number)
        self.assertEqual(q2.revision, q.revision + 1)
        self.assertEqual(q2.customer, self.customer)
        self.assertEqual(q2.scope, "complete")
        self.assertEqual(q2.status, "draft")
        self.assertEqual(CalculationSnapshot.objects.filter(quotation=q).count(), 1)
        self.assertEqual(CalculationSnapshot.objects.filter(quotation=q2).count(), 1)

    def test_revise_permutador_reproduz_custo_original(self):
        """REGRESSÃO: revisar deve recomputar com as DIMENSÕES da cotação original, não o seed."""
        from apps.tema_templates.services import estimate_from_inputs
        from apps.quotations.services import create_permutador_quotation
        # dims customizadas (casco bem maior que o gabarito) → custo != seed
        cleaned = {"designacao": "BEU", "n_tubos": 68, "comprimento_tubo_mm": 13000,
                   "od_tubo_mm": 19.05, "esp_tubo_mm": 2.108, "n_chicanas": 18,
                   "comprimento_casco_mm": 3000, "diametro_casco_mm": 1200, "esp_casco_mm": 16,
                   "n_passes_tubos": 2, "rt_escopo": "Total", "classe_feixe": "INOX",
                   "classe_casco": "CS", "fluido_corrosivo": "Tubos", "fator_correcao_mo": 1.0}
        resultado = estimate_from_inputs("BEU", cleaned)
        q = create_permutador_quotation(self.customer, "BEU", cleaned, resultado, title="BEU custom")
        resp = self.client.post(f"/cotacoes/{q.pk}/revisar/")
        q2 = Quotation.objects.get(pk=resp.url.split("/")[-2])
        # a revisão deve ter o MESMO preço (mesmas dims), não o preço do seed
        self.assertAlmostEqual(float(q2.preco_com_impostos), float(q.preco_com_impostos), delta=1.0)

    # ---- Tela 05 item 4: edição INLINE de metadados (sem motor, sem nova revisão) ----
    def test_update_meta_saves_title_without_revision_or_recompute(self):
        """update_meta persiste metadados comerciais da cotação ATUAL: NÃO cria nova
        revisão e NÃO recomputa pelo motor (distingue-se de quotation_edit/revise)."""
        from django.urls import reverse
        q = create_feixe_quotation(self.customer, "Título Antigo", created_by=self.user)
        q.refresh_from_db()                    # valores como estão persistidos (arredondados)
        n_before = Quotation.objects.count()
        custo_before = q.custo_total
        rev_before = q.revision
        computed_before = q.computed_at

        resp = self.client.post(reverse("quotations:update_meta", args=[q.pk]),
                                {"title": "Título Novo"})
        self.assertEqual(resp.status_code, 200)
        self.assertJSONEqual(resp.content.decode(),
                             {"ok": True, "title": "Título Novo", "updated": ["title"]})

        q.refresh_from_db()
        self.assertEqual(q.title, "Título Novo")           # metadado salvo
        self.assertEqual(Quotation.objects.count(), n_before)  # nenhuma nova revisão
        self.assertEqual(q.revision, rev_before)
        self.assertEqual(q.custo_total, custo_before)      # motor não rodou
        self.assertEqual(q.computed_at, computed_before)   # sem recompute

    def test_update_meta_rejects_blank_title(self):
        from django.urls import reverse
        q = create_feixe_quotation(self.customer, "Mantém", created_by=self.user)
        resp = self.client.post(reverse("quotations:update_meta", args=[q.pk]),
                                {"title": "   "})
        self.assertEqual(resp.status_code, 400)
        q.refresh_from_db()
        self.assertEqual(q.title, "Mantém")                # não sobrescreveu

    def test_update_meta_denies_user_without_write_permission(self):
        """Guardrail RBAC: um usuário sem permissão de escrita no tenant é BARRADO
        (não-membro → 302 login pelo middleware; membro sem papel de escrita → 403
        pelo @require_role). Em ambos os casos NÃO grava e nunca retorna 200."""
        from django.contrib.auth.models import User
        from django.urls import reverse
        q = create_feixe_quotation(self.customer, "T", created_by=self.user)
        norole = User.objects.create_user(username="norole", password="123")
        self.client.force_login(norole)
        resp = self.client.post(reverse("quotations:update_meta", args=[q.pk]),
                                {"title": "Hack"})
        self.assertIn(resp.status_code, (302, 403))
        self.assertNotEqual(resp.status_code, 200)
        q.refresh_from_db()
        self.assertEqual(q.title, "T")            # não gravou

    def test_detail_has_inline_edit_scaffolding(self):
        """Detalhe expõe o modo de edição inline (Alpine isEditing + endpoint meta)."""
        from django.urls import reverse
        q = create_feixe_quotation(self.customer, "Feixe X", created_by=self.user)
        resp = self.client.get(reverse("quotations:detail", args=[q.pk]))
        self.assertContains(resp, "isEditing")
        self.assertContains(resp, reverse("quotations:update_meta", args=[q.pk]))
        self.assertContains(resp, "Salvar Alterações")
        self.assertContains(resp, "Cancelar Revisão")

    # ---- Tela 07 item 1: trava do CONVERTER EM OF refletida no front ----
    def test_detail_convert_button_reflects_convertibility(self):
        """O contexto marca is_convertible pela MESMA regra do POST
        (production.services._assert_convertible): sem aprovação técnica ativa
        casando com o snapshot atual → False e botão desabilitado; com aprovação
        válida → True e botão habilitado (form de POST presente)."""
        from django.urls import reverse
        from django.contrib.auth.models import User
        from apps.accounts.models import UserProfile
        from apps.audit.services import approve_quotation
        from apps.production.services import is_convertible

        q = create_feixe_quotation(self.customer, "Feixe Conv", created_by=self.user)

        # Sem aprovação → não convertível (coerente com _assert_convertible)
        self.assertFalse(is_convertible(q))
        resp = self.client.get(reverse("quotations:detail", args=[q.pk]))
        self.assertFalse(resp.context["is_convertible"])
        self.assertContains(resp, "disabled")
        self.assertContains(resp, "Aguardando aprovação")

        # Aprova tecnicamente com engenheiro (CREA)
        eng_user = User.objects.create_user(username="eng-conv")
        engineer = UserProfile.objects.create(
            user=eng_user, full_name="Eng Conv", role=UserProfile.ROLE_ENGENHEIRO,
            crea_number="CREA-999", crea_state="SP",
        )
        approve_quotation(q, engineer)

        # Com aprovação válida → convertível e botão habilitado
        self.assertTrue(is_convertible(q))
        resp = self.client.get(reverse("quotations:detail", args=[q.pk]))
        self.assertTrue(resp.context["is_convertible"])
        self.assertContains(resp, reverse("production:convert", args=[q.pk]))

    def test_detail_expoe_acoes_de_aprovacao_e_polling_do_gate_de_conversao(self):
        """Tela 07 itens 2+3: o detalhe mostra as ações de solicitação/aprovação
        e o bloco do gate consulta periodicamente o backend para destravar sem reload."""
        from django.urls import reverse
        q = create_feixe_quotation(self.customer, "Feixe Gate", created_by=self.user)

        resp = self.client.get(reverse("quotations:detail", args=[q.pk]))

        self.assertContains(resp, "Solicitar Aprovação (Remoto)")
        self.assertContains(resp, "Aprovar Agora (Presencial)")
        self.assertContains(resp, reverse("audit:request_remote", args=[q.pk]))
        self.assertContains(resp, reverse("audit:approve_presencial", args=[q.pk]))
        self.assertContains(resp, reverse("audit:convertibility_panel", args=[q.pk]))
        self.assertContains(resp, 'hx-trigger="load, every 5s"')

    # ---- Tela 05 item 4 (parte B): drawer de detalhe da linha da EAP (N2) ----
    def _item_with_material(self, q):
        item = q.itens.filter(materiais__isnull=False).first()
        self.assertIsNotNone(item, "cotação de feixe deve ter item com material")
        return item

    def _item_with_operation(self, q):
        item = q.itens.filter(operacoes__isnull=False).first()
        self.assertIsNotNone(item, "cotação de feixe deve ter item com operação")
        return item

    def test_detail_eap_rows_are_clickable_drawer_triggers(self):
        """Linhas da §2 EAP viram gatilhos do drawer (clicáveis + endpoint drawer)."""
        from django.urls import reverse
        q = create_feixe_quotation(self.customer, "Feixe Drawer", created_by=self.user)
        item = self._item_with_material(q)
        resp = self.client.get(reverse("quotations:detail", args=[q.pk]))
        self.assertEqual(resp.status_code, 200)
        # gatilho HTMX aponta pro endpoint do drawer daquele item
        self.assertContains(resp, reverse("quotations:eap_item_drawer", args=[item.pk]))
        self.assertContains(resp, "drawer-panel")       # CSS novo do slide-over
        self.assertContains(resp, "eap-row")            # linha clicável marcada

    def test_eap_item_drawer_loads_materials_and_operations(self):
        """GET drawer devolve o parcial com materiais + operações daquele item."""
        from django.urls import reverse
        q = create_feixe_quotation(self.customer, "Feixe Drawer", created_by=self.user)
        item = self._item_with_material(q)
        mat = item.materiais.first()
        resp = self.client.get(reverse("quotations:eap_item_drawer", args=[item.pk]))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, mat.descricao)                       # material listado
        self.assertContains(resp, reverse("quotations:eap_item_save", args=[item.pk]))
        self.assertContains(resp, f"material_custo_{mat.pk}")          # campo editável

    def test_eap_item_save_persists_override_and_updates_rollup_without_engine(self):
        """POST persiste os overrides DIRETO nas rows e recalcula só os roll-ups
        (item + cotação) por SOMA — sem chamar o motor e sem criar revisão."""
        from decimal import Decimal
        from django.urls import reverse
        q = create_feixe_quotation(self.customer, "Feixe Save", created_by=self.user)
        item = self._item_with_material(q)
        mat = item.materiais.first()
        q.refresh_from_db()
        computed_before = q.computed_at
        rev_before = q.revision
        n_before = Quotation.objects.count()

        novo_custo = mat.custo + Decimal("1000.00")
        resp = self.client.post(
            reverse("quotations:eap_item_save", args=[item.pk]),
            {f"material_custo_{mat.pk}": str(novo_custo)},
        )
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Override salvo")

        mat.refresh_from_db()
        self.assertEqual(mat.custo, novo_custo)                        # override persistido na row

        item.refresh_from_db()
        soma_mat = sum((m.custo for m in item.materiais.all()), Decimal("0"))
        self.assertEqual(item.custo_material, soma_mat)                # roll-up do item = soma
        self.assertContains(resp, brl(item.custo_material))
        self.assertContains(resp, brl(item.custo_total))

        q.refresh_from_db()
        soma_q_mat = sum((i.custo_material for i in q.itens.all()), Decimal("0"))
        soma_q_mo = sum((i.custo_mo for i in q.itens.all()), Decimal("0"))
        self.assertEqual(q.custo_material, soma_q_mat)                 # roll-up da cotação = soma
        self.assertEqual(q.custo_mo, soma_q_mo)
        self.assertEqual(q.custo_total, q.custo_material + q.custo_mo)
        # guardrails: motor NÃO rodou e NÃO houve nova revisão
        self.assertEqual(q.computed_at, computed_before)
        self.assertEqual(q.revision, rev_before)
        self.assertEqual(Quotation.objects.count(), n_before)

    def test_eap_item_save_updates_rendered_total_when_operation_cost_changes(self):
        """O parcial re-renderizado precisa refletir o novo total também quando o
        override vem de mão de obra, não só de material."""
        from decimal import Decimal
        from django.urls import reverse
        q = create_feixe_quotation(self.customer, "Feixe Save OP", created_by=self.user)
        item = self._item_with_operation(q)
        op = item.operacoes.first()
        self.assertIsNotNone(op, "cotação de feixe deve ter operação")

        novo_custo = op.custo + Decimal("250.00")
        resp = self.client.post(
            reverse("quotations:eap_item_save", args=[item.pk]),
            {f"op_custo_{op.pk}": str(novo_custo)},
        )
        self.assertEqual(resp.status_code, 200)

        op.refresh_from_db()
        item.refresh_from_db()
        self.assertEqual(op.custo, novo_custo)
        self.assertEqual(
            item.custo_mo,
            sum((o.custo for o in item.operacoes.all() if o.aplicavel), Decimal("0")),
        )
        self.assertContains(resp, brl(item.custo_mo))
        self.assertContains(resp, brl(item.custo_total))

    def test_eap_item_drawer_denies_user_without_role(self):
        """Guardrail RBAC: usuário sem papel no tenant é barrado no drawer (leitura)."""
        from django.contrib.auth.models import User
        from django.urls import reverse
        q = create_feixe_quotation(self.customer, "Feixe Sec", created_by=self.user)
        item = self._item_with_material(q)
        norole = User.objects.create_user(username="norole_drawer", password="123")
        self.client.force_login(norole)
        resp = self.client.get(reverse("quotations:eap_item_drawer", args=[item.pk]))
        self.assertIn(resp.status_code, (302, 403))
        self.assertNotEqual(resp.status_code, 200)
