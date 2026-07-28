"""
Guard-rail do vazamento de margem pela EAP (sprint M1).

O furo que estes testes fecham: aprovar uma cotação → baixar custo/horas no drawer da
EAP → o hash do snapshot NÃO mudava → a assinatura técnica continuava casando → a
cotação convertia em Ordem de Fabricação com a margem já vazada, sem que ninguém
revisse.

`_case_is_stale` (audit/approvals.py) e `_technical_approval_satisfied`
(production/services.py) comparam contra `latest_snapshot_for()`, que devolve o ÚLTIMO
snapshot GRAVADO — não um recálculo. Sem um snapshot novo depois do override, nada
percebe a mudança.

Nota de projeto: `computed_at` continua intocado de propósito (views.py:580 — sinaliza
"o motor não rodou"). São coisas diferentes: `computed_at` = o motor rodou;
`CalculationSnapshot` = o estado mudou. A correção emite o segundo sem mexer no primeiro.
"""
from decimal import Decimal

from django.contrib.auth.models import User
from django.core import mail
from django.urls import reverse
from django_tenants.test.cases import TenantTestCase

from apps.access.enforcement import invalidate_matrix_cache
from apps.access.models import RolePermission
from apps.accounts.models import UserProfile
from apps.audit.models import AccessLog, TechnicalApproval
from apps.audit.services import approve_quotation
from apps.production.services import is_convertible
from apps.quotations.models import CalculationSnapshot, Customer, ItemOperation, QuotationItem
from apps.quotations.services import create_feixe_quotation

SENHA = "x123456789"
MOTIVO = "Cliente renegociou o escopo de solda; ajuste combinado em ata."


class EapGuardRailTests(TenantTestCase):
    """Override manual na EAP tem de invalidar a assinatura e avisar o comercial."""

    def setUp(self):
        self.client.defaults["HTTP_HOST"] = self.get_test_tenant_domain()

        self.orcamentista = User.objects.create_user(username="orc_eap", password=SENHA)
        UserProfile.objects.create(user=self.orcamentista, full_name="Orçamentista EAP",
                                   role=UserProfile.ROLE_ORCAMENTISTA)

        self.engenheiro = User.objects.create_user(username="eng_eap", password=SENHA,
                                                   email="eng@tenant.com")
        self.perfil_eng = UserProfile.objects.create(
            user=self.engenheiro, full_name="Engenheiro EAP",
            role=UserProfile.ROLE_ENGENHEIRO, crea_number="CREA-M1-001/SP", crea_state="SP")

        # Destinatário da notificação: quem tem a capability comercial.
        self.gestor = User.objects.create_user(username="gestor_eap", password=SENHA,
                                               email="gestor@tenant.com")
        UserProfile.objects.create(user=self.gestor, full_name="Gestor Comercial",
                                   role=UserProfile.ROLE_GESTOR_COMERCIAL)
        invalidate_matrix_cache()

        self.customer = Customer.objects.create(company_name="Cliente M1")
        self.quotation = create_feixe_quotation(self.customer, "Feixe M1",
                                                created_by=self.orcamentista)
        # A EAP do feixe tem vários itens e nem todos têm operação horária
        # (`custo_direto=False` só quando o motor atribuiu horas). Pegamos o item que
        # de fato dá para editar no drawer.
        op = ItemOperation.objects.filter(
            item__quotation=self.quotation, custo_direto=False, aplicavel=True
        ).select_related("item").first()
        self.assertIsNotNone(op, "a fixture do feixe precisa de ao menos uma operação horária")
        self.op = op
        self.item = op.item
        self.client.force_login(self.orcamentista)

    # ── helpers ────────────────────────────────────────────────────────────────
    def _aprovar(self):
        return approve_quotation(self.quotation, self.perfil_eng, art_number="ART-M1")

    def _operacao_horaria(self):
        return self.op

    def _post_override(self, op, horas="1.00", motivo=MOTIVO):
        dados = {f"op_horas_hh_{op.pk}": horas}
        if motivo is not None:
            dados["motivo"] = motivo
        # A notificação vai por transaction.on_commit (para não segurar o lock da
        # cotação no round-trip SMTP). Dentro de TestCase a transação é revertida e o
        # callback nunca roda — captureOnCommitCallbacks o executa de propósito.
        with self.captureOnCommitCallbacks(execute=True):
            return self.client.post(
                reverse("quotations:eap_item_save", args=[self.item.pk]), dados)

    # ── o furo ─────────────────────────────────────────────────────────────────
    def test_override_na_eap_invalida_a_aprovacao_tecnica(self):
        """O exploit: aprovar, baixar horas no drawer, converter em OF assim mesmo."""
        self._aprovar()
        self.assertTrue(is_convertible(self.quotation),
                        "pré-condição: aprovada e convertível antes do override")

        op = self._operacao_horaria()
        self._post_override(op, horas="0.10")

        self.quotation.refresh_from_db()
        self.assertFalse(
            is_convertible(self.quotation),
            "baixar custo depois de aprovada NÃO pode continuar convertível — é o vazamento",
        )

    def test_override_emite_novo_snapshot(self):
        self._aprovar()
        antes = CalculationSnapshot.objects.filter(quotation=self.quotation).count()
        hash_antes = self.quotation.snapshots.order_by("-created_at").first().snapshot_hash

        self._post_override(self._operacao_horaria(), horas="0.25")

        depois = CalculationSnapshot.objects.filter(quotation=self.quotation).count()
        self.assertEqual(depois, antes + 1, "override precisa registrar o novo estado")
        hash_depois = self.quotation.snapshots.order_by("-created_at").first().snapshot_hash
        self.assertNotEqual(hash_antes, hash_depois,
                            "o hash tem de mudar — é ele que a assinatura compara")

    def test_restore_da_operacao_tambem_invalida(self):
        """Restaurar a sugestão do motor também muda o custo — mesmo tratamento."""
        op = self._operacao_horaria()
        op.horas_hh_sugerida = Decimal("9.99")
        op.save(update_fields=["horas_hh_sugerida"])
        self._aprovar()
        self.assertTrue(is_convertible(self.quotation))

        self.client.post(reverse("quotations:eap_op_restore", args=[op.pk]), {"motivo": MOTIVO})

        self.assertFalse(is_convertible(self.quotation))

    # ── justificativa ──────────────────────────────────────────────────────────
    def test_override_sem_justificativa_e_recusado(self):
        op = self._operacao_horaria()
        horas_antes = op.horas_hh

        resp = self._post_override(op, horas="0.10", motivo=None)

        self.assertEqual(resp.status_code, 400)
        op.refresh_from_db()
        self.assertEqual(op.horas_hh, horas_antes, "nada pode ser gravado sem motivo")

    def test_justificativa_em_branco_tambem_e_recusada(self):
        resp = self._post_override(self._operacao_horaria(), horas="0.10", motivo="   ")
        self.assertEqual(resp.status_code, 400)

    def test_justificativa_fica_na_trilha_de_auditoria(self):
        self._post_override(self._operacao_horaria(), horas="0.30")

        registros = AccessLog.objects.filter(action="edit")
        self.assertTrue(registros.exists())
        self.assertTrue(
            any(MOTIVO in str(r.metadata.get("motivo", "")) for r in registros),
            "o motivo digitado tem de ficar gravado junto do antes/depois",
        )

    # ── notificação ────────────────────────────────────────────────────────────
    def test_override_em_cotacao_aprovada_notifica_o_gestor(self):
        self._aprovar()
        mail.outbox = []

        self._post_override(self._operacao_horaria(), horas="0.10")

        self.assertEqual(len(mail.outbox), 1, "o dono da margem precisa saber")
        self.assertIn("gestor@tenant.com", mail.outbox[0].to)
        self.assertIn(self.quotation.number, mail.outbox[0].subject)

    def test_override_em_rascunho_nao_notifica(self):
        """Sem aprovação vigente não há margem aprovada para vazar — não spamar."""
        mail.outbox = []
        self._post_override(self._operacao_horaria(), horas="0.10")
        self.assertEqual(len(mail.outbox), 0)

    # ── o hash tem de cobrir o que a OF carrega ────────────────────────────────
    def test_mover_horas_mantendo_o_custo_tambem_invalida(self):
        """Lavagem de horas: custo = horas × taxa, então dá para halvar as horas e
        dobrar a taxa sem mexer no custo. Se o hash só olhasse o custo, a assinatura
        continuaria casando — e a OF, que copia as HORAS, iria para o chão de fábrica
        com metade do que o engenheiro assinou."""
        op = self._operacao_horaria()
        op.horas_hh = Decimal("100.00")
        op.taxa_hora = Decimal("50.00")
        op.save(update_fields=["horas_hh", "taxa_hora"])
        op.recalc_custo()
        op.refresh_from_db()
        custo_assinado = op.custo
        self._aprovar()
        self.assertTrue(is_convertible(self.quotation))

        self.client.post(reverse("quotations:eap_item_save", args=[self.item.pk]), {
            "motivo": MOTIVO,
            f"op_horas_hh_{op.pk}": "50.00",
            f"op_taxa_hh_{op.pk}": "100.00",
        })

        op.refresh_from_db()
        self.assertEqual(op.horas_hh, Decimal("50.00"), "as horas mudaram de fato")
        self.assertEqual(op.custo, custo_assinado, "e o custo ficou idêntico — é o truque")
        self.assertFalse(
            is_convertible(self.quotation),
            "o hash precisa cobrir horas e taxas, não só o custo",
        )

    # ── a tela precisa conseguir salvar ────────────────────────────────────────
    def test_o_drawer_renderiza_o_campo_de_motivo(self):
        """Exigir motivo sem oferecer o campo quebraria todo save real da tela.
        Este teste parte do HTML renderizado — POST montado à mão não pega isso."""
        resp = self.client.get(reverse("quotations:eap_item_drawer", args=[self.item.pk]))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'name="motivo"')

    def test_post_sem_alteracao_nao_vira_snapshot_nem_email(self):
        """Sem isso, qualquer detentor de quotation.write gera e-mail e linha de
        snapshot em laço, até o gestor aprender a ignorar o alerta.

        O PRIMEIRO POST vazio ainda registra: o roll-up por soma reconcilia o total
        das linhas com o total que o motor gravou, e essa diferença de arredondamento
        é mudança de estado de verdade. Do segundo em diante não há mais o que
        reconciliar — e é aí que o laço tem de parar.
        """
        self.client.post(reverse("quotations:eap_item_save", args=[self.item.pk]),
                         {"motivo": MOTIVO})          # absorve a reconciliação
        self._aprovar()
        antes = CalculationSnapshot.objects.filter(quotation=self.quotation).count()
        mail.outbox = []

        for _ in range(3):
            with self.captureOnCommitCallbacks(execute=True):
                self.client.post(reverse("quotations:eap_item_save", args=[self.item.pk]),
                                 {"motivo": MOTIVO})

        self.assertEqual(CalculationSnapshot.objects.filter(quotation=self.quotation).count(),
                         antes, "hash idêntico não pode virar snapshot novo")
        self.assertEqual(len(mail.outbox), 0, "nem e-mail")
        self.assertTrue(is_convertible(self.quotation), "e a aprovação segue válida")

    def test_engenheiro_que_assinou_tambem_e_avisado(self):
        self._aprovar()
        mail.outbox = []

        self._post_override(self._operacao_horaria(), horas="0.10")

        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("eng@tenant.com", mail.outbox[0].to)

    def test_motivo_gigante_e_truncado(self):
        """O motivo é copiado uma vez por campo alterado — sem limite, amplifica na
        própria tabela de auditoria que serve de prova deste controle."""
        self._post_override(self._operacao_horaria(), horas="0.20", motivo="x" * 5000)

        registro = AccessLog.objects.filter(action="edit").first()
        self.assertLessEqual(len(registro.metadata.get("motivo", "")), 500)

    # ── o guard-rail que já existia não pode quebrar ───────────────────────────
    def test_computed_at_continua_intocado(self):
        """`computed_at` sinaliza 'o motor rodou' — override manual não é o motor."""
        computed_antes = self.quotation.computed_at

        self._post_override(self._operacao_horaria(), horas="0.40")

        self.quotation.refresh_from_db()
        self.assertEqual(self.quotation.computed_at, computed_antes)

    def test_rollup_continua_correto_apos_override(self):
        """A correção não pode alterar o resultado do roll-up por soma."""
        op = self._operacao_horaria()
        self._post_override(op, horas="2.00")

        self.item.refresh_from_db()
        esperado = sum((o.custo for o in self.item.operacoes.all() if o.aplicavel), Decimal("0"))
        self.assertEqual(self.item.custo_mo, esperado)
