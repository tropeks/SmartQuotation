"""
Tests: scripts/ci/suite_receipt.sh — prova de suíte verde do HEAD (ordem 009: aceita o job
"Testes Django (multi-tenant)" exato (formato antigo) OU o grupo da matriz Postgres 15/16
introduzida por docs/patches/009-ci-postgres-matrix.patch, cada job nomeado
"Testes Django (multi-tenant) — Postgres <major>".

`git` e `gh` FALSOS num diretório próprio, na frente do PATH: nenhum teste toca a rede nem o
git real do worktree. O fake `git` responde a status/fetch/rev-parse/branch; o fake `gh`
serve os JSONs de `run list` e `run view` a partir de arquivos fixture escritos pelo teste.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "scripts" / "ci" / "suite_receipt.sh"

SHA = "a" * 40

DJANGO_OLD = "Testes Django (multi-tenant)"
DJANGO_15 = "Testes Django (multi-tenant) — Postgres 15"
DJANGO_16 = "Testes Django (multi-tenant) — Postgres 16"

_FAKE_GIT = r"""#!/usr/bin/env bash
case "$1" in
  status)
    [ "${FAKE_GIT_DIRTY:-0}" = "1" ] && echo " M some/file.py"
    exit 0 ;;
  fetch)
    if [ "${FAKE_GIT_FETCH_FAIL:-0}" = "1" ]; then
      echo "fatal: could not read from remote repository." >&2
      exit 1
    fi
    exit 0 ;;
  rev-parse)
    printf '%s\n' "${FAKE_HEAD_SHA}"
    exit 0 ;;
  branch)
    if [ "${FAKE_GIT_NOT_REACHABLE:-0}" = "1" ]; then
      exit 0
    fi
    echo "  origin/main"
    exit 0 ;;
esac
exit 1
"""

_FAKE_GH = r"""#!/usr/bin/env bash
case "$1 $2" in
  "run list")
    cat "${FAKE_GH_RUN_LIST_JSON}"
    exit "${FAKE_GH_RUN_LIST_EXIT:-0}" ;;
  "run view")
    cat "${FAKE_GH_RUN_VIEW_JSON}"
    exit "${FAKE_GH_RUN_VIEW_EXIT:-0}" ;;
esac
exit 1
"""


def _write_exec(path: Path, text: str) -> None:
    path.write_text(text)
    path.chmod(0o755)


def _base_jobs() -> list[dict]:
    """Os 4 jobs obrigatórios que não são o Django (sempre verdes, salvo o teste dizer o
    contrário) — mantém o foco dos testes no comportamento novo (Django old/matrix)."""
    return [
        {"name": "Motor de custeio (gate -10%)", "conclusion": "success", "status": "completed"},
        {"name": "Testes de ops/infra (backup + media volume)", "conclusion": "success", "status": "completed"},
        {"name": "pip-audit (CVEs nos locks)", "conclusion": "success", "status": "completed"},
        {"name": "Django check + migrations", "conclusion": "success", "status": "completed"},
    ]


class Case:
    def __init__(self, jobs: list[dict], *, sha: str = SHA, git_dirty=False, fetch_fail=False,
                 not_reachable=False, run_status="completed", run_conclusion="success"):
        self._tmp = tempfile.TemporaryDirectory()
        self.base = Path(self._tmp.name)
        self.bin = self.base / "bin"
        self.bin.mkdir()
        _write_exec(self.bin / "git", _FAKE_GIT)
        _write_exec(self.bin / "gh", _FAKE_GH)

        run_list = [{
            "databaseId": 1, "status": run_status, "conclusion": run_conclusion,
            "headSha": sha, "createdAt": "2026-01-01T00:00:00Z",
        }]
        run_view = {
            "databaseId": 1, "conclusion": run_conclusion, "status": run_status,
            "headSha": sha, "url": "https://example.invalid/run/1", "jobs": jobs,
        }
        self.run_list_path = self.base / "run_list.json"
        self.run_view_path = self.base / "run_view.json"
        self.run_list_path.write_text(json.dumps(run_list))
        self.run_view_path.write_text(json.dumps(run_view))

        self.env = {
            "PATH": f"{self.bin}:{os.environ.get('PATH', '')}",
            "HOME": os.environ.get("HOME", str(self.base)),
            "FAKE_HEAD_SHA": sha,
            "FAKE_GIT_DIRTY": "1" if git_dirty else "0",
            "FAKE_GIT_FETCH_FAIL": "1" if fetch_fail else "0",
            "FAKE_GIT_NOT_REACHABLE": "1" if not_reachable else "0",
            "FAKE_GH_RUN_LIST_JSON": str(self.run_list_path),
            "FAKE_GH_RUN_VIEW_JSON": str(self.run_view_path),
        }

    def run(self, extra_env: dict | None = None) -> subprocess.CompletedProcess:
        env = dict(self.env)
        env.update(extra_env or {})
        return subprocess.run(
            ["bash", str(SCRIPT)], cwd=str(self.base), env=env,
            capture_output=True, text=True, timeout=30,
        )

    def __enter__(self):
        return self

    def __exit__(self, *a):
        self._tmp.cleanup()


def test_old_single_job_format_green_is_approved():
    with Case(_base_jobs() + [{"name": DJANGO_OLD, "conclusion": "success", "status": "completed"}]) as c:
        r = c.run()
        assert r.returncode == 0, r.stdout + r.stderr
        assert "APROVADO" in r.stdout, r.stdout


def test_matrix_format_both_majors_green_is_approved():
    with Case(_base_jobs() + [
        {"name": DJANGO_15, "conclusion": "success", "status": "completed"},
        {"name": DJANGO_16, "conclusion": "success", "status": "completed"},
    ]) as c:
        r = c.run()
        assert r.returncode == 0, r.stdout + r.stderr
        assert "APROVADO" in r.stdout, r.stdout


def test_matrix_format_postgres_15_failing_is_refused():
    with Case(_base_jobs() + [
        {"name": DJANGO_15, "conclusion": "failure", "status": "completed"},
        {"name": DJANGO_16, "conclusion": "success", "status": "completed"},
    ]) as c:
        r = c.run()
        assert r.returncode != 0, r.stdout + r.stderr
        assert "REPROVADO" in r.stdout, r.stdout
        assert DJANGO_15 in r.stdout and "failure" in r.stdout, r.stdout


def test_matrix_format_missing_postgres_15_is_incomplete_matrix():
    with Case(_base_jobs() + [
        {"name": DJANGO_16, "conclusion": "success", "status": "completed"},
    ]) as c:
        r = c.run()
        assert r.returncode != 0, r.stdout + r.stderr
        assert "matriz" in r.stdout and "incompleta" in r.stdout, r.stdout
        assert DJANGO_15 in r.stdout, r.stdout


def test_django_job_absent_in_either_format_is_refused():
    with Case(_base_jobs()) as c:
        r = c.run()
        assert r.returncode != 0, r.stdout + r.stderr
        assert "REPROVADO" in r.stdout, r.stdout
        assert DJANGO_OLD in r.stdout and "formato antigo" in r.stdout, r.stdout
        assert "formato novo" in r.stdout, r.stdout


def test_both_formats_present_all_must_be_success():
    """Situação de migração: o job antigo e o grupo da matriz aparecem juntos (ex.: run
    disparado antes do patch da matriz mesclar). Todos, de ambos os formatos, têm que estar
    success — um antigo falhando reprova mesmo com a matriz nova inteira verde."""
    with Case(_base_jobs() + [
        {"name": DJANGO_OLD, "conclusion": "failure", "status": "completed"},
        {"name": DJANGO_15, "conclusion": "success", "status": "completed"},
        {"name": DJANGO_16, "conclusion": "success", "status": "completed"},
    ]) as c:
        r = c.run()
        assert r.returncode != 0, r.stdout + r.stderr
        assert DJANGO_OLD in r.stdout and "failure" in r.stdout, r.stdout


def test_dirty_tree_is_refused_before_any_gh_call():
    with Case(_base_jobs() + [{"name": DJANGO_OLD, "conclusion": "success", "status": "completed"}],
              git_dirty=True) as c:
        r = c.run()
        assert r.returncode != 0 and "suja" in r.stderr, r.stderr


def test_head_not_reachable_from_remote_is_refused():
    with Case(_base_jobs() + [{"name": DJANGO_OLD, "conclusion": "success", "status": "completed"}],
              not_reachable=True) as c:
        r = c.run()
        assert r.returncode != 0 and "alcançável" in r.stderr, r.stderr


def test_run_still_in_progress_is_refused_without_waiting():
    with Case(_base_jobs() + [{"name": DJANGO_OLD, "conclusion": None, "status": "in_progress"}],
              run_status="in_progress", run_conclusion=None) as c:
        r = c.run()
        assert r.returncode != 0, r.stdout + r.stderr
        assert "ainda não terminou" in r.stdout, r.stdout


TESTS = [
    test_old_single_job_format_green_is_approved,
    test_matrix_format_both_majors_green_is_approved,
    test_matrix_format_postgres_15_failing_is_refused,
    test_matrix_format_missing_postgres_15_is_incomplete_matrix,
    test_django_job_absent_in_either_format_is_refused,
    test_both_formats_present_all_must_be_success,
    test_dirty_tree_is_refused_before_any_gh_call,
    test_head_not_reachable_from_remote_is_refused,
    test_run_still_in_progress_is_refused_without_waiting,
]


def run_tests(tests) -> int:
    failed = []
    for t in tests:
        try:
            t()
            print(f"  PASS  {t.__name__}")
        except AssertionError as e:
            print(f"  FAIL  {t.__name__}: {e}")
            failed.append(t.__name__)
    return len(failed)


if __name__ == "__main__":
    n = run_tests(TESTS)
    print()
    if n:
        print(f"FAILED: {n}/{len(TESTS)} tests failed")
        sys.exit(1)
    print(f"OK: all {len(TESTS)} tests passed")
