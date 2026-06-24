import math

from pricing_engine import operations
from pricing_engine import process_params as pp


def test_cnc_process_parameters_confirmados():
    assert pp.get("FURAR_ESPELHO", pp.CNC) == 97.56
    assert pp.get("FURAR_CHICANA", pp.CNC) == 83.34
    try:
        pp.get("ALARGAR_ESPELHO", pp.CNC)
    except KeyError:
        pass
    else:
        raise AssertionError("ALARGAR_ESPELHO não deve existir como etapa CNC")


def test_operacoes_acima_do_limiar_usam_cnc_sem_pendencia():
    assert pp.choose_drill_method(601) == pp.CNC
    assert operations.furar_espelho_horas(601, 44.5) == math.ceil(44.5 / 97.56 / 60 * 601)
    assert operations.furar_chicana_horas(180.0, 601) == math.ceil(180.0 / 83.34 / 60 * 601)
    assert operations.alargar_espelho_horas(601, 44.5) == 0


def test_process_parameter_override_por_material_com_fallback():
    overrides = {
        ("FURAR_ESPELHO", pp.CNC, None): 90.0,
        ("FURAR_ESPELHO", pp.CNC, "AISI316"): 80.0,
    }
    with pp.override(overrides):
        assert pp.get("FURAR_ESPELHO", pp.CNC, "AISI316") == 80.0
        assert pp.get("FURAR_ESPELHO", pp.CNC, "SA-516 GR 70") == 90.0
