"""
Custo real da hora: a conta, a vigência e a importação do formulário externo.

A régua que este app constrói é diferente da que o motor já tem. O motor bate 0,0%
contra o orçamento fechado da empresa — isso mede FIDELIDADE ao preço que ela cobraria.
Aqui se mede se esse preço cobre a operação.
"""
import json
import tempfile
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

from django.core.exceptions import ValidationError
from django.core.management import call_command
from django_tenants.test.cases import TenantTestCase

from apps.cost_structure.models import CostStructure
from apps.cost_structure.services import (abrir_vigencia, da_resposta_do_formulario,
                                          diagnosticar, parse_num)


def _estrutura(**over):
    """Fábrica com números redondos: 100.000/mês ÷ 1.000 h = R$ 100/h."""
    campos = {
        "custo_pessoal_direto": Decimal("60000"),
        "custo_pessoal_indireto": Decimal("15000"),
        "custo_galpao": Decimal("12000"),
        "custo_maquinas": Decimal("5000"),
        "custo_estrutura": Decimal("8000"),
        "pessoas_produtivas": Decimal("10"),
        "jornada_semanal_h": Decimal("40"),
        "semanas_mes": Decimal("5"),
        "fator_pratico_pct": Decimal("50"),   # 10 × 40 × 5 × 50% = 1.000 h
        "horas_extras_mes": Decimal("0"),
    }
    campos.update(over)
    return CostStructure(**campos)


class ParseNumTests(TenantTestCase):
    def test_ponto_com_tres_digitos_e_milhar(self):
        """'8.000' é oito mil. Ler como 8,00 erraria o custo por mil vezes."""
        self.assertEqual(parse_num("R$ 8.000"), Decimal("8000"))
        self.assertEqual(parse_num("1.234.567"), Decimal("1234567"))

    def test_virgula_manda_quando_presente(self):
        self.assertEqual(parse_num("1.234,56"), Decimal("1234.56"))

    def test_ponto_decimal_continua_valendo(self):
        self.assertEqual(parse_num("1234.56"), Decimal("1234.56"))
        self.assertEqual(parse_num("7.5"), Decimal("7.5"))

    def test_vazio_e_lixo_viram_zero(self):
        for entrada in ("", None, "abc", "   "):
            self.assertEqual(parse_num(entrada), Decimal("0"))


class ContaTests(TenantTestCase):
    def test_custo_hora_e_capacidade_dividindo_o_custo(self):
        e = _estrutura()
        self.assertEqual(e.custo_mensal, Decimal("100000"))
        self.assertEqual(e.horas_mes, Decimal("1000.00"))
        self.assertEqual(e.custo_hora, Decimal("100.0000"))

    def test_indiretos_custam_mas_nao_vendem_hora(self):
        """O encarregado entra no numerador e não no denominador — é o que dilui."""
        com = _estrutura()
        sem = _estrutura(custo_pessoal_indireto=Decimal("0"))
        self.assertEqual(com.horas_mes, sem.horas_mes)
        self.assertGreater(com.custo_hora, sem.custo_hora)

    def test_fator_pratico_encarece_a_hora(self):
        """Ninguém produz 100% da jornada; assumir que sim subestima o custo."""
        realista = _estrutura(fator_pratico_pct=Decimal("50"))
        ingenuo = _estrutura(fator_pratico_pct=Decimal("100"))
        self.assertEqual(ingenuo.custo_hora * 2, realista.custo_hora)

    def test_horas_extras_entram_na_capacidade(self):
        e = _estrutura(horas_extras_mes=Decimal("1000"))
        self.assertEqual(e.horas_mes, Decimal("2000.00"))

    def test_sem_capacidade_nao_ha_custo_hora(self):
        self.assertIsNone(_estrutura(pessoas_produtivas=Decimal("0")).custo_hora)

    def test_ponto_de_equilibrio(self):
        e = _estrutura(rate_praticado=Decimal("200"))
        self.assertEqual(e.ponto_equilibrio_horas, Decimal("500.00"))

    def test_ponto_de_equilibrio_exige_rate(self):
        self.assertIsNone(_estrutura().ponto_equilibrio_horas)


class DiagnosticoTests(TenantTestCase):
    def test_cobrar_abaixo_do_custo_e_prejuizo(self):
        d = diagnosticar(_estrutura(rate_praticado=Decimal("80")))
        self.assertEqual(d["nivel"], "prejuizo")
        self.assertLess(d["delta"], 0)

    def test_folga_pequena_e_limite(self):
        d = diagnosticar(_estrutura(rate_praticado=Decimal("110")))
        self.assertEqual(d["nivel"], "limite")

    def test_folga_confortavel_e_saudavel(self):
        d = diagnosticar(_estrutura(rate_praticado=Decimal("150")))
        self.assertEqual(d["nivel"], "saudavel")
        self.assertEqual(d["pct"], Decimal("50.0"))

    def test_sem_rate_diz_o_custo_mesmo_assim(self):
        self.assertEqual(diagnosticar(_estrutura())["nivel"], "sem_rate")

    def test_sem_capacidade_nao_diagnostica(self):
        d = diagnosticar(_estrutura(pessoas_produtivas=Decimal("0")))
        self.assertEqual(d["nivel"], "sem_dados")


class VigenciaTests(TenantTestCase):
    def test_vigente_devolve_a_regua_da_data(self):
        antiga = _estrutura(valid_from=date(2026, 1, 1))
        abrir_vigencia(antiga)
        nova = _estrutura(custo_galpao=Decimal("30000"), valid_from=date(2026, 6, 1))
        abrir_vigencia(nova)

        self.assertEqual(CostStructure.objects.vigente(date(2026, 3, 1)).pk, antiga.pk)
        self.assertEqual(CostStructure.objects.vigente(date(2026, 7, 1)).pk, nova.pk)

    def test_abrir_vigencia_fecha_a_anterior_na_vespera(self):
        """Trocar de galpão não pode reescrever o custo/hora de março."""
        antiga = abrir_vigencia(_estrutura(valid_from=date(2026, 1, 1)))
        abrir_vigencia(_estrutura(valid_from=date(2026, 6, 1)))

        antiga.refresh_from_db()
        self.assertEqual(antiga.valid_until, date(2026, 5, 31))
        self.assertEqual(CostStructure.objects.count(), 2, "a antiga é preservada")

    def test_antes_da_primeira_vigencia_nao_ha_regua(self):
        abrir_vigencia(_estrutura(valid_from=date(2026, 6, 1)))
        self.assertIsNone(CostStructure.objects.vigente(date(2026, 1, 1)))

    def test_duas_vigencias_no_mesmo_dia_sao_recusadas(self):
        abrir_vigencia(_estrutura(valid_from=date(2026, 6, 1)))
        with self.assertRaises(ValueError):
            abrir_vigencia(_estrutura(valid_from=date(2026, 6, 1)))

    def test_vigencia_que_termina_antes_de_comecar_e_invalida(self):
        e = _estrutura(valid_from=date(2026, 6, 1), valid_until=date(2026, 5, 1))
        with self.assertRaises(ValidationError):
            e.full_clean()

    def test_fator_pratico_fora_da_faixa_e_invalido(self):
        with self.assertRaises(ValidationError):
            _estrutura(fator_pratico_pct=Decimal("130")).full_clean()


RESPOSTA = {
    "empresa": "ENGEMATEX", "respondente": "Wellington", "mes_referencia": "2026-06",
    "linhas": {
        "diretos": [{"nome": "Caldeireiro", "qtd": 4, "custo": 7000},
                    {"nome": "Soldador", "qtd": 6, "custo": 8000}],
        "indiretos": [{"nome": "Encarregado", "qtd": 1, "custo": 9000}],
        "galpao": [{"nome": "Aluguel", "valor": 12000}],
        "maquinas": [{"nome": "Depreciação", "valor": 5000}],
        "estrutura": [{"nome": "Pró-labore", "valor": 20000}],
    },
    "escalares": {
        "rateio_pct": "50", "jornada_semanal": "40", "semanas_mes": "5",
        "fator_pratico_pct": "50", "horas_extras": "0", "rate_atual": "80",
        "observacoes": "Mês típico.",
    },
}


class ImportacaoTests(TenantTestCase):
    def test_traduz_as_listas_do_formulario(self):
        e = da_resposta_do_formulario(RESPOSTA)
        self.assertEqual(e.custo_pessoal_direto, Decimal("76000"))   # 4×7000 + 6×8000
        self.assertEqual(e.custo_pessoal_indireto, Decimal("9000"))
        self.assertEqual(e.pessoas_produtivas, Decimal("10"), "cabeças vêm das linhas")
        self.assertEqual(e.origem, "formulario")

    def test_rateio_reduz_a_estrutura(self):
        e = da_resposta_do_formulario(RESPOSTA)
        self.assertEqual(e.custo_estrutura, Decimal("10000"), "20.000 a 50%")

    def test_custo_hora_da_resposta_importada(self):
        e = da_resposta_do_formulario(RESPOSTA)
        self.assertEqual(e.custo_mensal, Decimal("112000"))
        self.assertEqual(e.horas_mes, Decimal("1000.00"))
        self.assertEqual(e.custo_hora, Decimal("112.0000"))
        self.assertEqual(diagnosticar(e)["nivel"], "prejuizo",
                         "cobra 80 e a hora custa 112")

    def test_payload_cru_e_preservado_para_recomputar(self):
        e = da_resposta_do_formulario(RESPOSTA)
        self.assertEqual(e.payload, RESPOSTA)

    def test_resposta_vazia_nao_quebra(self):
        e = da_resposta_do_formulario({})
        self.assertEqual(e.custo_mensal, Decimal("0"))
        self.assertIsNone(e.custo_hora)

    def test_comando_importa_e_abre_vigencia(self):
        with tempfile.TemporaryDirectory() as tmp:
            caminho = Path(tmp) / "resposta.json"
            caminho.write_text(json.dumps(RESPOSTA), encoding="utf-8")
            call_command("importar_estrutura_custo", arquivo=str(caminho),
                         vigencia="2026-07-01", verbosity=0)

        vigente = CostStructure.objects.vigente(date(2026, 7, 15))
        self.assertIsNotNone(vigente)
        self.assertEqual(vigente.empresa, "ENGEMATEX")
        self.assertEqual(vigente.custo_hora, Decimal("112.0000"))

    def test_comando_simular_nao_grava(self):
        with tempfile.TemporaryDirectory() as tmp:
            caminho = Path(tmp) / "resposta.json"
            caminho.write_text(json.dumps(RESPOSTA), encoding="utf-8")
            call_command("importar_estrutura_custo", arquivo=str(caminho),
                         simular=True, verbosity=0)
        self.assertEqual(CostStructure.objects.count(), 0)
