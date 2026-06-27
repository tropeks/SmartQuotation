"""
Testes do app proposals: template configurável, customização por caso, geração DOCX/PDF.
"""
import os
import shutil
import unittest
from django.contrib.auth.models import User
from django_tenants.test.cases import TenantTestCase

from apps.quotations.models import Customer
from apps.quotations.services import create_feixe_quotation
from apps.proposals.models import Proposal, ProposalTemplate
from apps.proposals import services
from apps.audit.models import AccessLog


def _chrome_ou_weasy() -> bool:
    if any(shutil.which(c) for c in ("google-chrome", "google-chrome-stable", "chromium", "chromium-browser")):
        return True
    try:
        import weasyprint  # noqa
        return True
    except Exception:
        return False


class ProposalTests(TenantTestCase):
    def setUp(self):
        self.tpl = ProposalTemplate.objects.create(name="Padrão", is_default=True)
        self.customer = Customer.objects.create(company_name="Petrobras RPBC")
        self.q = create_feixe_quotation(self.customer, "Feixe 136 tubos")

    def test_template_renderiza_placeholders(self):
        ctx = services.build_context(self.q)
        texts = services.render_template_texts(self.tpl, ctx)
        self.assertIn("Feixe 136 tubos", texts["intro_text"])     # {{ titulo }}
        self.assertIn("136", texts["scope_text"])                  # {{ n_tubos }}
        self.assertIn("8 semanas", texts["terms_text"])            # {{ delivery_weeks }}
        # texto plano: OD 3/4" não pode virar 3/4&quot; (sem autoescape na substituição)
        self.assertIn('3/4"', texts["scope_text"])
        self.assertNotIn("&quot;", texts["scope_text"])

    def test_create_proposal_pre_preenche_textos_editaveis(self):
        p = services.create_proposal(self.q, self.tpl)
        self.assertTrue(p.intro_text)                              # veio do template
        self.assertTrue(p.number.startswith("PROP-"))
        self.assertEqual(p.status, "draft")

    def test_customizacao_por_caso_nao_altera_template(self):
        p = services.create_proposal(self.q, self.tpl)
        p.intro_text = "Texto customizado para ESTE cliente."
        p.save()
        # o template-modelo permanece intacto
        self.tpl.refresh_from_db()
        self.assertIn("{{ titulo }}", self.tpl.intro_template)
        self.assertEqual(Proposal.objects.get(pk=p.pk).intro_text, "Texto customizado para ESTE cliente.")

    def test_generate_docx_cria_arquivo_e_hash(self):
        p = services.create_proposal(self.q, self.tpl)
        path = services.generate_docx(p)
        self.assertTrue(os.path.exists(path))
        self.assertGreater(os.path.getsize(path), 1000)
        self.assertEqual(len(Proposal.sha256(path)), 64)
        os.remove(path)

    @unittest.skipUnless(_chrome_ou_weasy(), "sem backend de PDF (chrome/weasyprint)")
    def test_generate_completo_docx_pdf_hashes(self):
        p = services.create_proposal(self.q, self.tpl)
        services.generate(p)
        self.assertEqual(p.status, "ready")
        self.assertTrue(p.pdf_path and p.docx_path)
        self.assertEqual(len(p.pdf_sha256), 64)
        self.assertEqual(len(p.docx_sha256), 64)

    def test_numeracao_proposta_por_revisao(self):
        p1 = services.create_proposal(self.q, self.tpl)
        p2 = services.create_proposal(self.q, self.tpl)
        self.assertTrue(p1.number.endswith("-A"))
        self.assertTrue(p2.number.endswith("-B"))


class ProposalViewTests(TenantTestCase):
    def setUp(self):
        self.client.defaults["HTTP_HOST"] = self.get_test_tenant_domain()
        self.user = User.objects.create_user(username="orc", password="senha-forte-123")
        from apps.accounts.models import UserProfile
        # Criar/editar/gerar proposta exige papel de escrita (RBAC H2.8: Engenheiro/Admin).
        UserProfile.objects.create(user=self.user, full_name="Orc", role=UserProfile.ROLE_ADMIN)
        self.client.force_login(self.user)
        ProposalTemplate.objects.create(name="Padrão", is_default=True)
        self.q = create_feixe_quotation(Customer.objects.create(company_name="Cli"), "Feixe")

    def test_fluxo_criar_editar(self):
        # criar a partir do template -> redireciona pro editor
        resp = self.client.get(f"/cotacoes/{self.q.pk}/proposta/nova/")
        self.assertEqual(resp.status_code, 302)
        p = Proposal.objects.latest("created_at")
        # editar customizando o texto
        resp = self.client.post(f"/propostas/{p.pk}/editar/", {
            "intro_text": "Intro customizada", "scope_text": "Escopo",
            "terms_text": "Condições", "closing_text": "Fecho", "save": "1"})
        self.assertEqual(resp.status_code, 302)
        p.refresh_from_db()
        self.assertEqual(p.intro_text, "Intro customizada")


    def test_generate_view_registra_access_log(self):
        p = services.create_proposal(self.q)
        resp = self.client.post(f"/propostas/{p.pk}/editar/", {
            "intro_text": "Intro", "scope_text": "Escopo",
            "terms_text": "Condições", "closing_text": "Fecho", "generate": "1"})
        self.assertEqual(resp.status_code, 302)
        self.assertTrue(AccessLog.objects.filter(action="generate", resource_id=str(p.pk)).exists())

    def test_download_registra_access_log(self):
        p = services.create_proposal(self.q)
        p.docx_path = "proposals/test-download.docx"
        from django.conf import settings
        import os
        os.makedirs(os.path.join(settings.MEDIA_ROOT, "proposals"), exist_ok=True)
        with open(os.path.join(settings.MEDIA_ROOT, p.docx_path), "wb") as fp:
            fp.write(b"docx")
        p.save()

        resp = self.client.get(f"/propostas/{p.pk}/download/docx/")

        self.assertEqual(resp.status_code, 200)
        self.assertTrue(AccessLog.objects.filter(action="download", resource_id=str(p.pk)).exists())


    def test_download_formato_invalido_retorna_404(self):
        p = services.create_proposal(self.q)
        resp = self.client.get(f"/propostas/{p.pk}/download/xlsx/")
        self.assertEqual(resp.status_code, 404)

    def test_login_required(self):
        self.client.logout()
        resp = self.client.get(f"/cotacoes/{self.q.pk}/proposta/nova/")
        self.assertEqual(resp.status_code, 302)
        self.assertIn("/login/", resp.url)


class ProposalMemorialTests(TenantTestCase):
    """Memorial ASME embutido na proposta (anexo de certificação no PDF)."""

    def _permutador_q(self):
        from apps.quotations.services import create_permutador_quotation
        from pricing_engine.permutador_quote import quote_completo
        cust = Customer.objects.create(company_name="ACME")
        cleaned = {"classe_casco": "CS", "pressao_projeto_bar": 50, "temperatura_projeto_c": 150,
                   "rt_escopo": "Total", "diametro_casco_mm": 764, "esp_casco_mm": 9.5,
                   "corrosao_mm": 3, "comprimento_casco_mm": 1631}
        return create_permutador_quotation(cust, "BEU", cleaned, quote_completo("BEU"))

    def test_proposal_memorial_para_permutador(self):
        from apps.proposals.services import proposal_memorial
        memo = proposal_memorial(self._permutador_q())
        blob = " ".join(e["item"] for e in memo)
        self.assertIn("UG-27", blob)
        self.assertTrue(any("2025" in (e.get("fonte") or "") for e in memo))

    def test_proposal_memorial_feixe_vazio(self):
        from apps.proposals.services import proposal_memorial
        from apps.quotations.services import create_feixe_quotation
        cust = Customer.objects.create(company_name="X Ltda")
        q = create_feixe_quotation(cust, "Feixe")
        self.assertEqual(proposal_memorial(q), [])

    def test_proposal_pdf_html_inclui_memorial(self):
        from apps.proposals.services import create_proposal, _pdf_context
        from django.template.loader import render_to_string
        prop = create_proposal(self._permutador_q())
        html = render_to_string("proposals/proposal_pdf.html", _pdf_context(prop))
        self.assertIn("Memória de cálculo", html)
        self.assertIn("UG-27", html)
        self.assertIn("2025", html)            # procedência normativa no anexo

    def test_proposal_docx_inclui_memorial(self):
        from apps.proposals.services import create_proposal, generate_docx
        import docx
        prop = create_proposal(self._permutador_q())
        path = generate_docx(prop)
        d = docx.Document(path)
        full = "\n".join(p.text for p in d.paragraphs)
        for t in d.tables:
            for row in t.rows:
                full += "\n" + " ".join(c.text for c in row.cells)
        self.assertIn("Memória de cálculo", full)
        self.assertIn("UG-27", full)
