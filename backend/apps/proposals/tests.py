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

    def test_login_required(self):
        self.client.logout()
        resp = self.client.get(f"/cotacoes/{self.q.pk}/proposta/nova/")
        self.assertEqual(resp.status_code, 302)
        self.assertIn("/login/", resp.url)
