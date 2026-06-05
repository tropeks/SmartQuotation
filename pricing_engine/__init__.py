"""
pricing_engine — motor de custeio puro (zero Django), fiel à planilha ENGEMATEX.

Espinha dorsal: Estrutura Analítica (EAP/WBS) — ver wbs.py.
Separação: ProcessParameter (física → horas) ≠ Rate (custo → R$).
Spec: ~/.gstack/projects/tropeks-SmartQuotation/rcosta00-main-costing-engine-spec.md
"""
from . import dimensions, materials, process_params, rates, wbs, operations  # noqa: F401
from . import beu_geometry, beu_quote  # noqa: F401

__all__ = ["dimensions", "materials", "process_params", "rates", "wbs", "operations",
           "beu_geometry", "beu_quote"]
