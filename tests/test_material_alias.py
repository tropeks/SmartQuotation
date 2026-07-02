import pytest

from pricing_engine.materials import density


@pytest.mark.parametrize(
    ("alias", "expected"),
    [
        ("B.3003H14", 2.7475e-6),
        ("b 3003 h14", 2.7475e-6),
        ("B.5052F", 2.7475e-6),
        ("b 5052 f", 2.7475e-6),
        ("B.5052-0", 2.7475e-6),
        ("b 5052 0", 2.7475e-6),
        ("B.6351T6", 2.7475e-6),
        ("b 6351 t 6", 2.7475e-6),
        ("A-266", 7.85e-6),
        ("a 266", 7.85e-6),
        ("A-516.60", 7.85e-6),
        ("a 516 60", 7.85e-6),
    ],
)
def test_density_resolves_material_aliases(alias: str, expected: float) -> None:
    assert density(alias) == pytest.approx(expected)
