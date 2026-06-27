"""Guard tests for pricing_engine.components — fail loud on misconfiguration.

DB-free: importa apenas a lib pura (zero Django). Roda da raiz do repo.
"""
import pytest

from pricing_engine.components import CompSpec, peso_componente


def test_peso_componente_levanta_para_forma_desconhecida():
    """Forma desconhecida deve LEVANTAR ValueError (não retornar custo zerado).

    Antes: retornava (0.0, "PENDENTE: forma ...") → custo zerado silencioso.
    """
    c = CompSpec(
        codigo="X", descricao="comp inexistente", material="SA-36",
        forma="forma_que_nao_existe", qtd=1, od_mm=100, esp_mm=10,
    )
    with pytest.raises(ValueError, match="forma_que_nao_existe"):
        peso_componente(c)


def test_peso_componente_forma_valida_continua_ok():
    """Sanidade: forma conhecida segue retornando (peso>0, 'ok')."""
    c = CompSpec(
        codigo="D", descricao="disco", material="SA-36",
        forma="disco", qtd=1, od_mm=475, esp_mm=44.5,
    )
    peso, status = peso_componente(c)
    assert status == "ok"
    assert peso > 0
