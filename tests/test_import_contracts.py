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

Além do positivo (os contratos passam hoje), há testes NEGATIVOS: plantam uma violação real
(módulo `_tmp_prova004_*` de nome único, removido no finally) e confirmam que o
import-linter reprova E aponta o contrato certo — sem isso, um `.importlinter` com typo
(root_package errado, allowlist mal escrita) vira um contrato vazio, sempre verde.

ESTE TESTE AINDA NÃO TEM STEP DEDICADO NO CI (`docs/patches/004-ci-import-linter.patch`
adiciona um quando o Capitão tocar `.github/workflows/ci.yml`). Até lá, ele roda
DEPENDURADO em `tests/test_requirements_lock.py` (que o job `ops-tests` já chama via
`python -m tests.test_requirements_lock`) — é o único módulo já registrado no CI capaz de
carregar este, sem editar o workflow. Ver `test_requirements_lock.test_import_linter_...`.
"""
import subprocess
import sys
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CONFIG = ROOT / ".importlinter"
WRAPPER = ROOT / "scripts" / "lint_imports.py"
# Diretório qualquer de `apps` sem relação com pricing_engine — só para plantar o módulo de
# prova das violações de C2 (materials não importa o motor, então nenhum arquivo real vizinho
# se confunde com o `_tmp_*` de prova).
APPS_PROVA_DIR = ROOT / "backend" / "apps" / "materials"
PRICING_ENGINE_DIR = ROOT / "pricing_engine"


def _run_lint_imports() -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(WRAPPER), "--no-cache"],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )


def _run_with_temp_module(directory: Path, tag: str, content: str) -> tuple[str, subprocess.CompletedProcess]:
    """Planta um módulo `.py` de nome único em `directory`, roda o import-linter, e remove
    o arquivo no finally — nada sobra no repo, nem em caso de falha do teste."""
    name = f"_tmp_prova004_{tag}_{uuid.uuid4().hex[:8]}"
    path = directory / f"{name}.py"
    path.write_text(content, encoding="utf-8")
    try:
        result = _run_lint_imports()
    finally:
        path.unlink(missing_ok=True)
    return name, result


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


# --- Testes NEGATIVOS: sem eles, um .importlinter com typo (root_package errado, nome de
# contrato duplicado, allowlist mal escrita) vira um contrato VAZIO — sempre verde, sem
# proteger nada. Cada teste abaixo PLANTA uma violação real, roda o import-linter, confirma
# que ele reprova (returncode != 0) E que o nome do contrato quebrado aparece na saída — e
# remove o arquivo plantado no finally, mesmo se a asserção falhar.

def test_pega_import_direto_de_funcao_que_computa_cotacao():
    """C2: um módulo novo em `apps` importando `quote_feixe` direto (fora do adapter e da
    allowlist) tem que reprovar o contrato "só o adapter persiste"."""
    name, result = _run_with_temp_module(
        APPS_PROVA_DIR, "c2_direto",
        "# prova negativa (ordem 004): violação de C2 -- import direto da função de compute\n"
        "from pricing_engine.feixe_quote import quote_feixe\n",
    )
    assert result.returncode != 0, (
        "import-linter deveria reprovar um módulo novo em apps importando quote_feixe "
        f"direto; saiu 0. Saída:\n{result.stdout}"
    )
    assert "só apps.quotations.adapter persiste" in result.stdout, (
        f"nome do contrato C2 não apareceu na saída (contrato errado reprovou?):\n{result.stdout}"
    )
    assert f"apps.materials.{name}" in result.stdout, (
        f"a cadeia da violação plantada não apareceu na saída:\n{result.stdout}"
    )


def test_pega_bypass_pelo_pacote_pricing_engine():
    """C2 pelo BYPASS do pacote: `pricing_engine/__init__.py` importa `beu_quote` e
    `permutador_quote` (ver `pricing_engine/__init__.py`), então `import pricing_engine` (ou
    `from pricing_engine import quote_completo`, que grimp trata como o mesmo import do
    pacote) tem que quebrar o contrato pela cadeia INDIRETA apps.X -> pricing_engine ->
    pricing_engine.permutador_quote/beu_quote. Se isto passasse, seria um furo: quem quisesse
    contornar a allowlist bastaria importar o pacote inteiro em vez do submódulo."""
    name, result = _run_with_temp_module(
        APPS_PROVA_DIR, "c2_bypass_pacote",
        "# prova negativa (ordem 004): bypass da allowlist via `import pricing_engine`\n"
        "import pricing_engine\n",
    )
    assert result.returncode != 0, (
        "FURO: import-linter deveria reprovar `import pricing_engine` de dentro de apps "
        f"(bypass pelo pacote), mas saiu 0. Saída:\n{result.stdout}"
    )
    assert "só apps.quotations.adapter persiste" in result.stdout, (
        f"nome do contrato C2 não apareceu na saída:\n{result.stdout}"
    )
    assert f"apps.materials.{name}" in result.stdout, (
        f"a cadeia da violação plantada não apareceu na saída:\n{result.stdout}"
    )


def test_pega_django_dentro_do_pricing_engine():
    """C1: um módulo novo DENTRO de pricing_engine importando django tem que reprovar o
    contrato "pricing_engine é lib pura"."""
    name, result = _run_with_temp_module(
        PRICING_ENGINE_DIR, "c1",
        "# prova negativa (ordem 004): violação de C1 -- pricing_engine importando Django\n"
        "import django\n",
    )
    assert result.returncode != 0, (
        "import-linter deveria reprovar pricing_engine importando django; saiu 0. "
        f"Saída:\n{result.stdout}"
    )
    assert "pricing_engine é lib pura" in result.stdout, (
        f"nome do contrato C1 não apareceu na saída (contrato errado reprovou?):\n{result.stdout}"
    )
    assert f"pricing_engine.{name}" in result.stdout, (
        f"a cadeia da violação plantada não apareceu na saída:\n{result.stdout}"
    )


if __name__ == "__main__":
    tests = [
        test_importlinter_config_exists,
        test_importlinter_wrapper_exists,
        test_import_contracts_pass,
        test_pega_import_direto_de_funcao_que_computa_cotacao,
        test_pega_bypass_pelo_pacote_pricing_engine,
        test_pega_django_dentro_do_pricing_engine,
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
