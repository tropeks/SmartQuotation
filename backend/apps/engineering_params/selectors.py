"""
Selectors — lógica de leitura derivada dos parâmetros de engenharia.

choose_drill_method replica pricing_engine.process_params.choose_drill_method, mas lê o
limiar do TenantParamConfig do schema atual (editável por tenant).
"""
from apps.engineering_params.models import ProcessParameter, TenantParamConfig

RADIAL = "radial"
CNC = "cnc"


def choose_drill_method(num_holes, override=None, threshold=600):
    """Escolhe radial/CNC pelo nº de furos. Override manual vence.

    <= threshold → radial ; > threshold → cnc. Passe threshold=None para ler o
    limiar do TenantParamConfig do schema atual (editável por tenant).
    """
    if override:
        return override
    if threshold is None:
        threshold = TenantParamConfig.get_solo().drill_method_threshold_holes
    return RADIAL if num_holes <= threshold else CNC


def threshold_do_tenant():
    """Limiar radial→CNC corrente do tenant (TenantParamConfig)."""
    return TenantParamConfig.get_solo().drill_method_threshold_holes


def get_process_parameter(operacao, metodo, material=None, on_date=None):
    """Atalho para ProcessParameter.objects.vigente com fallback por material."""
    return ProcessParameter.objects.vigente(
        operacao=operacao,
        metodo=metodo,
        material=material,
        on_date=on_date,
    )
