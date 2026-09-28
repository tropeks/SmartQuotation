"""
Tests: scripts/ci/suite_local_pg.sh — Postgres efêmero (ordem 009) + `manage.py test apps`
local contra uma major específica, espelhando o job django-test do ci.yml.

Docker FALSO (tests/_ops_fakes.py) para o Postgres efêmero (run/exec/rm — pg_isready e psql
respondem via ctr_bin/). `manage.py test apps` roda um PYTHON FALSO próprio (o fake docker
não entende Django): registra os args recebidos e sai com FAKE_TEST_EXIT.
"""
import subprocess
import sys
import tempfile
from pathlib import Path

from tests._ops_fakes import SCRIPTS, FakeEnv, _write_exec, run_tests

_FAKE_TEST_PYTHON = r"""#!/usr/bin/env bash
printf '%s\n' "$*" >> "${FAKE_TEST_ARGV_LOG:-/dev/null}"
exit "${FAKE_TEST_EXIT:-0}"
"""

SCRIPT = SCRIPTS / "ci" / "suite_local_pg.sh"


class Case:
    def __init__(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.base = Path(self._tmp.name)
        self.fk = FakeEnv(self.base)
        self.pyfake = self.base / "fake_python.sh"
        _write_exec(self.pyfake, _FAKE_TEST_PYTHON)
        self.argv_log = self.base / "test_argv.log"
        self.backend_dir = self.base / "backend"
        self.backend_dir.mkdir()
        self.fk.env.update({
            "PYTHON": str(self.pyfake),
            "BACKEND_DIR": str(self.backend_dir),
            "FAKE_TEST_ARGV_LOG": str(self.argv_log),
            "PG_POLL_INTERVAL": "0",
            "PG_WAIT_SECONDS": "3",
        })

    def run(self, args, extra_env=None, timeout=30) -> subprocess.CompletedProcess:
        env = dict(self.fk.env)
        env.update(extra_env or {})
        return subprocess.run(
            ["bash", str(SCRIPT), *args], env=env, capture_output=True, text=True, timeout=timeout
        )

    def docker_calls(self):
        return self.fk.docker_calls()

    def container_name(self):
        runs = [c for c in self.docker_calls() if c.startswith("run ")]
        assert len(runs) == 1, runs
        parts = runs[0].split()
        return runs[0], parts[parts.index("--name") + 1]

    def assert_removed(self):
        run, name = self.container_name()
        rms = [c for c in self.docker_calls() if c.startswith("rm ")]
        assert rms and rms[-1] == f"rm -fv {name}", f"container {name} não foi removido com -v: {rms}"

    def __enter__(self):
        return self

    def __exit__(self, *a):
        self._tmp.cleanup()


def test_success_runs_django_tests_against_ephemeral_postgres_15_and_removes_container():
    with Case() as c:
        r = c.run(["15"])
        assert r.returncode == 0, r.stdout + r.stderr
        run, name = c.container_name()
        assert name.startswith("sq-ci-pg-15-"), name
        for flag in ("--rm", "127.0.0.1:", "postgres:15"):
            assert flag in run, f"{flag!r} ausente em: {run}"
        assert "0.0.0.0" not in run, "porta nunca pode ir para 0.0.0.0"
        c.assert_removed()
        assert "manage.py test apps" in c.argv_log.read_text(), c.argv_log.read_text()


def test_major_outside_15_17_is_refused_before_touching_docker():
    with Case() as c:
        for major in ("14", "18", "abc", ""):
            r = c.run([major] if major else [])
            assert r.returncode != 0, (major, r.stdout + r.stderr)
            assert "15, 16 ou 17" in r.stderr, (major, r.stderr)
        assert c.docker_calls() == [], "nenhuma chamada docker antes da validação da major"


def test_extra_args_pass_through_to_manage_py_test():
    with Case() as c:
        r = c.run(["16", "-v2", "apps.quotations"])
        assert r.returncode == 0, r.stdout + r.stderr
        assert "manage.py test apps -v2 apps.quotations" in c.argv_log.read_text()
        run, _ = c.container_name()
        assert "postgres:16" in run, run


def test_container_is_removed_with_dash_v_even_when_django_tests_fail():
    with Case() as c:
        r = c.run(["15"], {"FAKE_TEST_EXIT": "1"})
        assert r.returncode != 0, r.stdout + r.stderr
        c.assert_removed()


def test_container_name_colliding_with_production_is_refused():
    with Case() as c:
        r = c.run(["15"], {"DB_CONTAINER": "sq-prod-db"})
        assert r.returncode != 0 and "PRODUÇÃO" in r.stderr, r.stderr
        assert c.docker_calls() == []


def test_production_volume_name_is_refused():
    with Case() as c:
        r = c.run(["15"], {"POSTGRES_VOLUME": "smartquotation_sq_postgres_data"})
        assert r.returncode != 0 and "volume" in r.stderr.lower(), r.stderr
        assert c.docker_calls() == []
        assert " -v " not in " ".join(c.docker_calls()), "nunca monta volume nomeado"


def test_explicit_postgres_port_is_honored_and_published_only_on_loopback():
    with Case() as c:
        r = c.run(["15"], {"POSTGRES_PORT": "55123"})
        assert r.returncode == 0, r.stdout + r.stderr
        run, _ = c.container_name()
        assert "127.0.0.1:55123:5432" in run, run


def test_postgres_never_ready_fails_and_container_is_removed():
    with Case() as c:
        r = c.run(["15"], {"FAKE_PG_READY_EXIT": "1"})
        assert r.returncode != 0 and "não ficou pronto" in r.stderr, r.stderr
        c.assert_removed()


TESTS = [
    test_success_runs_django_tests_against_ephemeral_postgres_15_and_removes_container,
    test_major_outside_15_17_is_refused_before_touching_docker,
    test_extra_args_pass_through_to_manage_py_test,
    test_container_is_removed_with_dash_v_even_when_django_tests_fail,
    test_container_name_colliding_with_production_is_refused,
    test_production_volume_name_is_refused,
    test_explicit_postgres_port_is_honored_and_published_only_on_loopback,
    test_postgres_never_ready_fails_and_container_is_removed,
]

if __name__ == "__main__":
    n = run_tests(TESTS)
    print()
    if n:
        print(f"FAILED: {n}/{len(TESTS)} tests failed")
        sys.exit(1)
    print(f"OK: all {len(TESTS)} tests passed")
