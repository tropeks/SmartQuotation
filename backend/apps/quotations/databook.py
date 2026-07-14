"""
Databook de Suprimentos: dado o escopo/partes cotados, emite a Lista de Compras com a
norma ASTM exata exigida por componente (Pedido de Compra). Consome MaterialStandard
(dicionário família×componente — PE Wellington). Service PURO de regra (lê models,
sem acoplar ao pricing_engine, sem UI).
"""
from apps.materials.models import MaterialStandard

# Parte TEMA (ComponentTemplate.tema_part) → componente do dicionário de normas.
_COMPONENTE_POR_PARTE = {
    "shell": "chapas_pressao", "front_head": "chapas_pressao", "rear_head": "chapas_pressao",
    "tubesheet": "chapas_pressao", "tube_bundle": "tubos_troca", "nozzle": "tubos_bocais",
    "flange": "forjados_flanges", "baffle": "barras_chicanas", "tie_rod": "barras_chicanas",
}
_CABECOTES = ("front_head", "rear_head")


def _familia_de_material(sigla: str) -> str:
    """Sigla de material → família metalúrgica do dicionário. Default = aço carbono
    (padrão da caldeiraria ENGEMATEX)."""
    s = (sigla or "").upper()
    if "316" in s:
        return "inox_316L"
    if "304" in s:
        return "inox_304L"
    return "aco_carbono"


def _row(familia: str, componente: str, default_norma: str = "") -> dict | None:
    std = (MaterialStandard.objects
           .filter(familia=familia, componente=componente, is_active=True).first())
    if std:
        return {"componente": std.get_componente_display(), "familia": std.get_familia_display(),
                "norma_astm": std.norma_astm, "condicao": std.condicao,
                "certificacao": std.certificacao, "notas": std.notas}
    if default_norma:
        return {"componente": componente, "familia": familia, "norma_astm": default_norma,
                "condicao": "", "certificacao": "EN 10204 3.1", "notas": ""}
    return None


def build_databook(quotation) -> list[dict]:
    """Lista de Compras (ASTM por componente). Para scope='parts' percorre as
    QuotationParts inclusas; para feixe/completo deriva o conjunto TEMA dos inputs.
    Cabeçote sempre puxa junta Double Jacketed + prisioneiros A193 B7 + porcas A194."""
    rows: list[dict] = []
    seen: set = set()

    def add(familia, componente, default_norma=""):
        key = (familia, componente)
        if key in seen:
            return
        seen.add(key)
        r = _row(familia, componente, default_norma)
        if r:
            rows.append(r)

    parts = (list(quotation.parts.filter(incluso=True).select_related("template"))
             if quotation.scope == "parts" else [])
    if parts:
        for part in parts:
            fam = _familia_de_material(part.material_sigla)
            comp = _COMPONENTE_POR_PARTE.get(part.template.tema_part, "chapas_pressao")
            add(fam, comp)
            if part.template.tema_part in _CABECOTES:
                add("geral", "junta_cabecote", "Dupla Jaqueta (Double Jacketed)")
                add("geral", "estojos_prisioneiros", "ASTM A193 Gr. B7")
                add("geral", "porcas", "ASTM A194 Gr. 2H")
    else:
        inputs = quotation.inputs or {}
        add(_familia_de_material(inputs.get("tubo_material")), "tubos_troca")
        add(_familia_de_material(inputs.get("espelho_material")), "chapas_pressao")
        add("aco_carbono", "barras_chicanas")

    return rows
