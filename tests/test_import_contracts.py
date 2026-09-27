"""
Contrato do import-linter (INTENT v3 §Limites, ordem 004): "pricing_engine é Python puro,
sem Django, e o único caminho que PERSISTE resultado do motor é
apps/quotations/adapter.py (outros módulos podem chamar o motor para simular ou exibir,
nunca gravar o resultado), travado por import-linter no CI."

Contratos em `.importlinter` (raiz do repo); wrapper em `scripts/lint_imports.py` (junta
`pricing_engine`, na raiz, e `apps`, em `backend/`, no mesmo PYTHONPATH — raízes de import
diferentes que o `.importlinter` sozinho não resolve).

Roda via subprocess `lint-imports` (por `scripts/lint_imports.py`), stdlib puro — NÃO
precisa de Django: grimp analisa o grafo de imports por AST, sem executar `apps.*` nem
`pricing_engine.*`. Confira rodando este módulo com um Python que só tenha import-linter
instalado (ex.: o venv de ops, sem Django) e comparando com o venv de CI (com Django): o
resultado deve ser o mesmo.

ESTE TESTE AINDA NÃO TEM STEP DEDICADO NO CI (`docs/patches/004-ci-import-linter.patch`
adiciona um quando o Capitão tocar `.github/workflows/ci.yml`). Até lá, ele roda
DEPENDURADO em `tests/test_requirements_lock.py` (que o job `ops-tests` já chama via
`python -m tests.test_requirements_lock`) — é o único módulo já registrado no CI capaz de
carregar este, sem editar o workflow. Ver `test_requirements_lock.test_import_linter_...`.
"""
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CONFIG = ROOT / ".importlinter"
WRAPPER = ROOT / "scripts" / "lint_imports.py"


def _run_lint_imports() -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(WRAPPER), "--no-cache"],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )


def test_importlinter_config_exists():
    assert CONFIG.exists(), (
        f"{CONFIG} não existe — contrato mecânico do INTENT v3 §Limites removido."
    )


def test_importlinter_wrapper_exists():
    assert WRAPPER.exists(), f"{WRAPPER} não existe (junta pricing_engine e apps no PYTHONPATH)."


def test_import_contracts_pass():
    """pricing_engine é lib pura + só o adapter persiste (allowlist nomeada). Se isto
    reprovar, alguém importou quote_feixe/quote_completo/quote_beu de dentro de `apps` fora
    do adapter e da allowlist em `.importlinter` — ou pricing_engine passou a importar
    Django/DRF/Celery/apps."""
    result = _run_lint_imports()
    assert result.returncode == 0, (
        "import-linter reprovou os contratos de .importlinter "
        f"(saída abaixo). Rode `python scripts/lint_imports.py` para o detalhe:\n\n"
        f"{result.stdout}\n{result.stderr}"
    )


if __name__ == "__main__":
    tests = [
        test_importlinter_config_exists,
        test_importlinter_wrapper_exists,
        test_import_contracts_pass,
    ]
    _REGISTERED = tests
    failed = []
    for t in tests:
        try:
            t()
            print(f"  PASS  {t.__name__}")
        except AssertionError as e:
            print(f"  FAIL  {t.__name__}: {e}")
            failed.append(t.__name__)
    print()
    if failed:
        print(f"FAILED: {len(failed)}/{len(tests)} tests failed")
        sys.exit(1)
    else:
        print(f"OK: all {len(tests)} tests passed")
