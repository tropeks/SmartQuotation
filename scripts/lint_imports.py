#!/usr/bin/env python3
"""
Wrapper do import-linter (ordem 004 — INTENT v3 §Limites, trava mecânica: "o único
caminho que PERSISTE resultado do motor é apps/quotations/adapter.py").

`pricing_engine` vive na raiz do repo; `apps` vive em `backend/`. São duas raízes de
import diferentes, e o import-linter (grimp) resolve os `root_packages` do
`.importlinter` a partir do `sys.path` do PROCESSO em que roda — não há como declarar
duas raízes no arquivo de config. Este wrapper injeta as duas em PYTHONPATH antes de
chamar `lint-imports`, em vez de depender de quem invoca lembrar disso.

Uso:
    python scripts/lint_imports.py [args extras do lint-imports, ex.: --verbose]

Não precisa de Django: grimp analisa por AST (imports estáticos), não executa
`apps.*` nem `pricing_engine.*`. Rode com o Python de qualquer venv que tenha
`import-linter` instalado (ci.lock, development.txt ou ops.lock — ver
backend/requirements/README.md).

Contratos em `.importlinter` (raiz do repo). Gate programático em
`tests/test_import_contracts.py` — hoje dependurado em `tests/test_requirements_lock.py`
(chamado pelo job `ops-tests` do CI); `docs/patches/004-ci-import-linter.patch` adiciona
um step dedicado quando o Capitão tocar `.github/workflows/ci.yml`.
"""
import os
import subprocess
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BACKEND = os.path.join(REPO_ROOT, "backend")
CONFIG = os.path.join(REPO_ROOT, ".importlinter")


def _lint_imports_executable() -> str:
    """`lint-imports` no mesmo bin/ do Python corrente (mesmo venv); cai para o PATH se
    não existir ali (ex.: instalação sem venv dedicado)."""
    candidate = os.path.join(os.path.dirname(sys.executable), "lint-imports")
    return candidate if os.path.exists(candidate) else "lint-imports"


def run(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    env = os.environ.copy()
    existing = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = os.pathsep.join(
        p for p in (BACKEND, REPO_ROOT, existing) if p
    )
    cmd = [_lint_imports_executable(), "--config", CONFIG, "--no-logo", *argv]
    result = subprocess.run(cmd, cwd=REPO_ROOT, env=env)
    return result.returncode


if __name__ == "__main__":
    sys.exit(run())
