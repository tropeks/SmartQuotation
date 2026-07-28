"""
A Ordem de Fabricação nasce do que foi ASSINADO (M1.1).

`convert_quotation_to_of` copiava custo, horas, taxas e pesos dos objetos VIVOS do banco,
não do JSON congelado em `CalculationSnapshot` — o mesmo snapshot cujo hash a assinatura
técnica valida. As duas coisas coincidem enquanto nada altera a EAP fora do caminho que
emite snapshot.

Depois do M1 esse caminho existe e emite. Mas a garantia é por CONSEQUÊNCIA, não por
construção: basta um fluxo novo gravar custo sem emitir snapshot para a OF voltar a nascer
diferente do que o engenheiro assinou, com a ART casando.

Estes testes fixam a garantia no lugar certo — a OF lê do snapshot. Aí não importa quem
mexeu no banco depois: o que vai para o chão de fábrica é o que foi aprovado.
"""
from decimal import Decimal

from django.contrib.auth.models import User
from django_tenants.test.cases import TenantTestCase

from apps.accounts.models import UserProfile
from apps.audit.services import approve_quotation
from apps.production.models import OFMaterial, OFOperation
from apps.production.services import convert_quotation_to_of
from apps.quotations.models import Customer, ItemMaterial, ItemOperation
from apps.quotations.services import create_feixe_quotation

SENHA = "x123456789"


class OFNasceDoSnapshotTests(TenantTestCase):
    def setUp(self):
        self.engenheiro = User.objects.create_user(username="eng_of", password=SENHA)
        self.perfil = UserProfile.objects.create(
            user=self.engenheiro, full_name="Engenheiro OF",
            role=UserProfile.ROLE_ENGENHEIRO, crea_number="CREA-OF-1/SP", crea_state="SP")
        self.customer = Customer.objects.create(company_name="Cliente OF")
        self.quotation = create_feixe_quotation(self.customer, "Feixe OF",
                                                created_by=self.engenheiro)

    def _adulterar_direto_no_banco(self):
        """Simula um caminho que grava custo SEM emitir snapshot.

        Hoje não existe um assim entre as views da EAP — o M1 fechou os dois que havia.
        Mas o admin do Django ainda permite (M1.2), e qualquer código novo pode
        reintroduzir. É contra isso que a leitura pelo snapshot protege.
        """
        op = ItemOperation.objects.filter(
            item__quotation=self.quotation, custo_direto=False, aplicavel=True).first()
        ItemOperation.objects.filter(pk=op.pk).update(
            horas_hh=Decimal("0.01"), custo=Decimal("1.00"))
        mat = ItemMaterial.objects.filter(
            item__quotation=self.quotation, peso_bruto_kg__gt=0).first()
        ItemMaterial.objects.filter(pk=mat.pk).update(
            peso_bruto_kg=Decimal("0.001"), custo=Decimal("1.00"))
        return op, mat

    def test_of_leva_as_horas_assinadas_e_nao_as_adulteradas(self):
        op = ItemOperation.objects.filter(
            item__quotation=self.quotation, custo_direto=False, aplicavel=True).first()
        horas_assinadas = op.horas_hh
        approve_quotation(self.quotation, self.perfil, art_number="ART-OF")

        self._adulterar_direto_no_banco()
        of = convert_quotation_to_of(self.quotation, created_by=self.engenheiro)

        na_of = OFOperation.objects.get(item__ordem=of, codigo_op=op.codigo_op)
        self.assertEqual(
            na_of.horas_hh, horas_assinadas,
            "a fábrica tem de receber a hora que o engenheiro assinou")

    def test_of_leva_o_peso_assinado(self):
        mat = ItemMaterial.objects.filter(
            item__quotation=self.quotation, peso_bruto_kg__gt=0).first()
        peso_assinado = mat.peso_bruto_kg
        approve_quotation(self.quotation, self.perfil, art_number="ART-OF")

        self._adulterar_direto_no_banco()
        of = convert_quotation_to_of(self.quotation, created_by=self.engenheiro)

        na_of = OFMaterial.objects.get(item__ordem=of, codigo_mp=mat.codigo_mp)
        self.assertEqual(na_of.peso_bruto_kg, peso_assinado)

    def test_totais_da_of_sao_os_do_snapshot(self):
        self.quotation.refresh_from_db()          # o valor em memória tem mais casas
        custo_assinado = self.quotation.custo_total
        approve_quotation(self.quotation, self.perfil, art_number="ART-OF")

        self._adulterar_direto_no_banco()
        of = convert_quotation_to_of(self.quotation, created_by=self.engenheiro)

        self.assertEqual(of.custo_total, custo_assinado,
                         "o total da OF é o total aprovado, não o do banco corrente")

    def test_sem_adulteracao_a_of_continua_igual_ao_banco(self):
        """O caminho normal não pode mudar de comportamento."""
        approve_quotation(self.quotation, self.perfil, art_number="ART-OF")
        of = convert_quotation_to_of(self.quotation, created_by=self.engenheiro)

        self.quotation.refresh_from_db()
        self.assertEqual(of.custo_total, self.quotation.custo_total)
        self.assertEqual(of.peso_bruto_kg, self.quotation.peso_bruto_kg)
        self.assertEqual(
            OFOperation.objects.filter(item__ordem=of).count(),
            ItemOperation.objects.filter(item__quotation=self.quotation).count(),
            "todas as operações são copiadas")
        self.assertEqual(
            OFMaterial.objects.filter(item__ordem=of).count(),
            ItemMaterial.objects.filter(item__quotation=self.quotation).count())
