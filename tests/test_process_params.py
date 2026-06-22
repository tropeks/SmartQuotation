import math

from pricing_engine import operations
from pricing_engine import process_params as pp


def test_cnc_process_parameters_confirmados():
    assert pp.get("FURAR_ESPELHO", pp.CNC) == 97.56
    assert pp.get("FURAR_CHICANA", pp.CNC) == 83.34
    assert pp.get("ALARGAR_ESPELHO", pp.CNC) == 70


def test_operacoes_acima_do_limiar_usam_cnc_sem_pendencia():
    assert pp.choose_drill_method(601) == pp.CNC
    assert operations.furar_espelho_horas(601, 44.5) == math.ceil(44.5 / 97.56 / 60 * 601)
    assert operations.furar_chicana_horas(180.0, 601) == math.ceil(180.0 / 83.34 / 60 * 601)
    assert operations.alargar_espelho_horas(601, 44.5) == math.ceil(44.5 / 70 / 60 * 601)
