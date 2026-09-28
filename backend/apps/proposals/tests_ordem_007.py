"""
Ordem 007 — a revisão de cotação MANTÉM o número (`Quotation.number`), então o
número/storage da PROPOSTA precisam distinguir a revisão (P5), e só a revisão vigente
pode ENVIAR proposta (P2).
"""
from django.core.files.storage import default_storage
from django_tenants.test.cases import TenantTestCase

from apps.quotations.models import Customer
from apps.quotations.services import create_feixe_quotation
from apps.proposals.models import ProposalTemplate
from apps.proposals import services


class ProposalOrdem007Tests(TenantTestCase):
    def setUp(self):
        self.tpl = ProposalTemplate.objects.create(name="Padrão", is_default=True)
        self.customer = Customer.objects.create(company_name="ACME Prop 007")
        self.q = create_feixe_quotation(self.customer, "Feixe Prop 007")

    def test_numero_da_proposta_na_rev0_nao_muda(self):
        """P5: `PROP-AAAA-NNN-A` na Rev.0 — sem sufixo de revisão (sem mudança de formato)."""
        p = services.create_proposal(self.q, self.tpl)
        self.assertEqual(p.number, f"PROP-{self.q.number.replace('COT-', '')}-A")
        self.assertNotIn("-R", p.number)

    def test_numero_da_proposta_na_revisao_leva_sufixo_r(self):
        """P5: `PROP-AAAA-NNN-R{n}-A` a partir da Rev.N (n>0) — sem o sufixo, a proposta
        da Rev.1 teria o MESMO número da proposta da Rev.0 (a revisão mantém o `number`
        da cotação desde a ordem 007), colidindo no storage."""
        from apps.quotations.adapter import revise_feixe

        revisada = revise_feixe(self.q, created_by=None)
        self.assertEqual(revisada.number, self.q.number)   # ordem 007: mantém o número
        self.assertEqual(revisada.revision, 1)

        p0 = services.create_proposal(self.q, self.tpl)
        p1 = services.create_proposal(revisada, self.tpl)
        self.assertEqual(p0.number, f"PROP-{self.q.number.replace('COT-', '')}-A")
        self.assertEqual(p1.number, f"PROP-{self.q.number.replace('COT-', '')}-R1-A")
        self.assertNotEqual(p0.number, p1.number)

    def test_storage_name_por_pk_sobrevive_a_colisao_de_number(self):
        """A chave do storage é `pk`, não `proposal.number` — mesmo se dois registros
        tivessem (por qualquer razão futura) o MESMO `number`, um `generate()` não
        apagaria o arquivo do outro no delete-then-save de `_save_to_storage`."""
        p1 = services.create_proposal(self.q, self.tpl)
        p2 = services.create_proposal(self.q, self.tpl)
        p2.number = p1.number  # força a colisão histórica de propósito
        p2.save(update_fields=["number"])
        self.assertNotEqual(
            services._proposal_storage_name(p1, "pdf"),
            services._proposal_storage_name(p2, "pdf"),
        )

    def test_pdf_da_rev0_sobrevive_ao_gerar_pdf_da_rev1(self):
        """P5 — prova de ponta a ponta (sem depender de chrome/weasyprint): o PDF já salvo
        da Rev.0 continua existindo no storage depois que a Rev.1 gera o seu próprio."""
        import os
        import tempfile
        from apps.quotations.adapter import revise_feixe

        p0 = services.create_proposal(self.q, self.tpl)
        fd, tmp0 = tempfile.mkstemp()
        os.close(fd)
        with open(tmp0, "w") as fh:
            fh.write("PDF-REV0")
        p0.pdf_path = services._save_to_storage(tmp0, services._proposal_storage_name(p0, "pdf"))
        p0.save(update_fields=["pdf_path"])
        os.unlink(tmp0)

        revisada = revise_feixe(self.q, created_by=None)
        p1 = services.create_proposal(revisada, self.tpl)
        fd, tmp1 = tempfile.mkstemp()
        os.close(fd)
        with open(tmp1, "w") as fh:
            fh.write("PDF-REV1")
        p1.pdf_path = services._save_to_storage(tmp1, services._proposal_storage_name(p1, "pdf"))
        p1.save(update_fields=["pdf_path"])
        os.unlink(tmp1)

        self.assertNotEqual(p0.pdf_path, p1.pdf_path)
        self.assertTrue(default_storage.exists(p0.pdf_path), "PDF da Rev.0 foi apagado pela Rev.1")
        with default_storage.open(p0.pdf_path) as fh:
            self.assertEqual(fh.read(), b"PDF-REV0")
        default_storage.delete(p0.pdf_path)
        default_storage.delete(p1.pdf_path)

    def test_send_email_bloqueado_se_nao_for_a_revisao_vigente(self):
        """P2: a Rev.0 (superada pela Rev.1) não pode ENVIAR proposta."""
        from apps.quotations.adapter import revise_feixe
        from apps.quotations.services import NotCurrentRevisionError

        revise_feixe(self.q, created_by=None)  # cria a Rev.1 -> self.q deixa de ser vigente
        p0 = services.create_proposal(self.q, self.tpl)
        p0.pdf_path = "proposals/test/fake.pdf"  # não precisa existir: o guard corre antes
        p0.save(update_fields=["pdf_path"])
        with self.assertRaises(NotCurrentRevisionError):
            services.send_email(p0, to_email="cliente@exemplo.com", body="oi")
