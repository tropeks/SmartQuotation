"""Carimbo, selo e proveniência da tela de detalhe (DESIGN_PRANCHA §5.1/§5.2/§5.3).

O que estes testes travam:
  * o SELO tem três estados e o do meio — `divergente`, "o cálculo mudou depois da
    assinatura" — é o que o produto existe para denunciar. Ele não tinha forma na
    tela e não tinha teste; passa a ter os dois.
  * o CARIMBO degrada com "—" nos campos que o sistema NÃO captura (TAG do
    equipamento, origem do projeto) em vez de inventar valor.
  * a marca de PROVENIÊNCIA sobe da operação (N2) para a linha da EAP (N1) pela
    regra "basta uma operação manual para o item ser manual".
"""
from django.contrib.auth.models import User
from django.urls import reverse
from django_tenants.test.cases import TenantTestCase as TestCase

from apps.accounts.models import UserProfile
from apps.access.matrix import seed_access_matrix
from apps.audit.services import approve_quotation
from apps.quotations.models import Customer
from apps.quotations.services import create_calculation_snapshot, create_feixe_quotation


class PranchaDetailTests(TestCase):
    def setUp(self):
        # sem o host do tenant o client cai no schema PUBLIC (onde as tabelas de
        # tenant não existem) — mesmo contrato dos demais testes de view do app.
        self.client.defaults["HTTP_HOST"] = self.get_test_tenant_domain()
        seed_access_matrix()
        self.customer = Customer.objects.create(company_name="ENGEMATEX")
        self.user = User.objects.create_user(username="orc", password="x-senha-123")
        UserProfile.objects.create(user=self.user, full_name="Orç",
                                   role=UserProfile.ROLE_ORCAMENTISTA)
        self.client.force_login(self.user)
        self.q = create_feixe_quotation(self.customer, "Feixe Prancha", created_by=self.user)

    def _engineer(self):
        user = User.objects.create_user(username="eng-prancha", password="x-senha-123")
        return UserProfile.objects.create(
            user=user, full_name="Eng Prancha", role=UserProfile.ROLE_ENGENHEIRO,
            crea_number="123456", crea_state="SP")

    def _detail(self):
        return self.client.get(reverse("quotations:detail", args=[self.q.pk]))

    # ---- §5.3 selo ------------------------------------------------------
    def test_selo_sem_aprovacao(self):
        resp = self._detail()
        self.assertEqual(resp.context["selo"]["estado"], "sem-aprovacao")
        self.assertContains(resp, "q-selo--sem-aprovacao")

    def test_selo_ok_quando_assinatura_cobre_o_snapshot_vigente(self):
        approve_quotation(self.q, self._engineer())
        resp = self._detail()
        self.assertEqual(resp.context["selo"]["estado"], "ok")
        self.assertContains(resp, "q-selo--ok")

    def test_selo_divergente_quando_o_calculo_muda_depois_da_assinatura(self):
        """Recalcular depois de assinar produz um snapshot novo: a assinatura
        continua ATIVA mas não cobre mais estes números — e a conversão trava."""
        from apps.production.services import is_convertible

        approve_quotation(self.q, self._engineer())
        self.q.custo_total = self.q.custo_total + 1     # muda o cálculo…
        self.q.save(update_fields=["custo_total"])
        create_calculation_snapshot(self.q)             # …e gera novo hash

        resp = self._detail()
        selo = resp.context["selo"]
        self.assertEqual(selo["estado"], "divergente")
        self.assertContains(resp, "q-selo--divergente")
        self.assertNotEqual(selo["hash_assinado"], selo["hash_vigente"])
        # o selo conta a MESMA verdade do gate de conversão
        self.assertFalse(is_convertible(self.q))

    # ---- §5.1 carimbo ---------------------------------------------------
    def test_carimbo_traz_o_que_existe_e_degrada_o_que_nao_existe(self):
        resp = self._detail()
        carimbo = resp.context["carimbo"]
        self.assertEqual(carimbo["cliente"], "ENGEMATEX")
        self.assertEqual(carimbo["equipamento"], "Feixe Prancha")
        # campos sem fonte no sistema: vazios (o template renderiza "—" com o rótulo)
        self.assertEqual(carimbo["tag"], "")
        self.assertEqual(carimbo["origem_projeto"], "")
        # feixe não tem designação TEMA nem condições de projeto (só o permutador)
        self.assertEqual(carimbo["designacao"], "")
        self.assertEqual(carimbo["pressao_temperatura"], "")
        self.assertContains(resp, "q-carimbo-grid")
        self.assertContains(resp, "TAG do equipamento")

    def test_carimbo_responsavel_tecnico_vem_de_quem_assinou(self):
        self.assertEqual(self._detail().context["carimbo"]["responsavel"], "")
        approve_quotation(self.q, self._engineer())
        self.assertIn("Eng Prancha", self._detail().context["carimbo"]["responsavel"])
        self.assertIn("CREA SP/123456", self._detail().context["carimbo"]["responsavel"])

    def test_carimbo_permutador_traz_designacao_pressao_e_norma(self):
        from apps.tema_templates.services import estimate_from_inputs
        from apps.quotations.services import create_permutador_quotation

        cleaned = {
            "designacao": "BEU", "n_tubos": 136, "comprimento_tubo_mm": 6000,
            "od_tubo_mm": 19.05, "esp_tubo_mm": 2.11, "n_chicanas": 12,
            "n_passes_tubos": 2, "rt_escopo": "Total",
            "comprimento_casco_mm": 6000, "diametro_casco_mm": 600, "esp_casco_mm": 12.7,
            "pressao_projeto_bar": 10.0, "temperatura_projeto_c": 150.0,
            "corrosao_mm": 3.0, "densidade_fluido_kg_m3": 1000,
            "classe_feixe": "CS", "classe_casco": "CS", "fluido_corrosivo": "Tubos",
            "fator_correcao_mo": 1.0,
        }
        resultado = estimate_from_inputs("BEU", cleaned)
        self.assertIsNotNone(resultado, "data sheet do permutador deve custear")
        q = create_permutador_quotation(self.customer, "BEU", cleaned, resultado,
                                        created_by=self.user, title="Permutador BEU")
        carimbo = self.client.get(
            reverse("quotations:detail", args=[q.pk])).context["carimbo"]
        self.assertEqual(carimbo["designacao"], "BEU")
        self.assertEqual(carimbo["pressao_temperatura"], "10 bar · 150 °C")
        # norma vem do memorial ASME gravado em CalculationSnapshot.standard_refs
        self.assertIn("ASME", carimbo["norma"])
        self.assertNotIn("UG-", carimbo["norma"])   # o carimbo nomeia o código, não a cláusula

    # ---- §5.2 proveniência ---------------------------------------------
    def test_item_vira_manual_se_qualquer_operacao_for_manual(self):
        item = self.q.itens.filter(operacoes__custo_direto=False).first()
        self.assertIsNotNone(item)

        resp = self._detail()
        linha = next(i for i in resp.context["itens"] if i.pk == item.pk)
        self.assertEqual(linha.pv, "motor")

        op = item.operacoes.filter(custo_direto=False).first()
        op.origem = "manual"
        op.save(update_fields=["origem"])

        resp = self._detail()
        linha = next(i for i in resp.context["itens"] if i.pk == item.pk)
        self.assertEqual(linha.pv, "manual")
        self.assertContains(resp, "eap-row--manual")
        self.assertContains(resp, "pv--manual")

    def test_item_sem_operacao_e_catalogo(self):
        item = self.q.itens.filter(operacoes__isnull=True).first()
        if item is None:
            item = self.q.itens.first()
            item.operacoes.all().delete()
        linha = next(i for i in self._detail().context["itens"] if i.pk == item.pk)
        self.assertEqual(linha.pv, "catalogo")

    def test_drawer_marca_a_origem_de_cada_operacao(self):
        item = self.q.itens.filter(operacoes__custo_direto=False).first()
        op = item.operacoes.filter(custo_direto=False).first()
        op.origem = "manual"
        op.save(update_fields=["origem"])
        resp = self.client.get(reverse("quotations:eap_item_drawer", args=[item.pk]))
        self.assertContains(resp, "pv--manual")
        self.assertContains(resp, "eap-row--manual")
