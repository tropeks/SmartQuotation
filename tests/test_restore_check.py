"""
Tests: scripts/restore_check.sh — drill de restore num Postgres efêmero (ordem 002).

Docker FALSO (tests/_ops_fakes.py): `docker run` só registra, `docker exec ... psql` é um psql
falso que consome o dump e responde às consultas por FAKE_SCHEMA_PRESENT/FAKE_TABLES/FAKE_QCOUNT.
Prova: sucesso grava restore_last_success; schema/tabela/cotações ausentes falham; o container
efêmero é SEMPRE removido (rm -f com o mesmo nome do run), inclusive no erro; saída sem conteúdo.
"""
import gzip
import sys
import tempfile
from pathlib import Path

from tests._ops_fakes import FakeEnv, run_tests, synthetic_dump, write_gz, write_media_tar


class Case:
    def __init__(self, *, media=True, dump=True):
        self._tmp = tempfile.TemporaryDirectory()
        self.base = Path(self._tmp.name)
        self.fk = FakeEnv(self.base)
        self.bdir = self.base / "backups"
        self.bdir.mkdir()
        self.sink = self.base / "restored.sql"
        self.fk.env.update({
            "BACKUP_DIR": str(self.bdir),
            "FAKE_RESTORE_SINK": str(self.sink),
            "RESTORE_POLL_INTERVAL": "0",
            "RESTORE_WAIT_SECONDS": "3",
        })
        if dump:
            write_gz(self.bdir / "sq_20260920_030000.sql.gz", "velho\n")
            write_gz(self.bdir / "sq_20260927_030000.sql.gz", synthetic_dump())
        if media:
            write_media_tar(self.bdir / "media_20260927_030000.tar.gz", {"p/COT-SINT-0001.pdf": b"%PDF"})

    def run(self, extra=None):
        return self.fk.run("restore_check.sh", extra)

    def container_name(self):
        runs = [c for c in self.fk.docker_calls() if c.startswith("run ")]
        assert len(runs) == 1, runs
        parts = runs[0].split()
        return runs[0], parts[parts.index("--name") + 1]

    def assert_removed(self):
        run, name = self.container_name()
        rms = [c for c in self.fk.docker_calls() if c.startswith("rm ")]
        assert rms and rms[-1] == f"rm -f {name}", f"container {name} não foi removido: {rms}"
        last_rm = max(i for i, c in enumerate(self.fk.docker_calls()) if c.startswith("rm "))
        last_exec = max((i for i, c in enumerate(self.fk.docker_calls()) if c.startswith("exec ")), default=-1)
        assert last_rm > last_exec, "rm tem que vir depois do último exec"

    def __enter__(self):
        return self

    def __exit__(self, *a):
        self._tmp.cleanup()


def test_success_restores_newest_dump_in_isolated_ephemeral_container():
    with Case() as c:
        r = c.run()
        assert r.returncode == 0, r.stderr
        run, name = c.container_name()
        assert name.startswith("sq-restore-check-"), name
        for flag in ("--network none", "--rm", "postgres:15"):
            assert flag in run, f"{flag!r} ausente em: {run}"
        assert "POSTGRES_PASSWORD" not in run, "nenhum segredo em argv do run"
        c.assert_removed()
        # o que foi aplicado é o dump MAIS RECENTE, inteiro
        newest = gzip.decompress((c.bdir / "sq_20260927_030000.sql.gz").read_bytes()).decode()
        assert c.sink.read_text() == newest
        status = dict(ln.split("=", 1) for ln in (c.bdir / "restore_last_success").read_text().splitlines())
        assert status["dump"] == "sq_20260927_030000.sql.gz" and status["schema"] == "engematex"
        assert status["quotations"] == "3" and status["media_entries"] == "1", status
        assert "materials_materialprice" in status["tables"], status


def test_output_has_only_counts_and_table_names_never_content():
    with Case() as c:
        r = c.run()
        assert r.returncode == 0, r.stderr
        out = r.stdout + r.stderr
        for leak in ("COT-SINT", "linha sintética", "already exists", "CREATE"):
            assert leak not in out, f"conteúdo do dump/psql vazou na saída: {leak!r}"
        assert "quotations_quotation: 3 linha(s)" in out, out


def test_missing_schema_fails_and_container_is_removed():
    with Case() as c:
        r = c.run({"FAKE_SCHEMA_PRESENT": "0"})
        assert r.returncode != 0 and "schema engematex ausente" in r.stderr, r.stderr
        c.assert_removed()
        assert not (c.bdir / "restore_last_success").exists()


def test_missing_key_table_fails_and_container_is_removed():
    with Case() as c:
        r = c.run({"FAKE_TABLES": "quotations_quotation materials_material"})
        assert r.returncode != 0 and "materials_materialprice ausente" in r.stderr, r.stderr
        c.assert_removed()
        assert not (c.bdir / "restore_last_success").exists()


def test_quotations_below_threshold_fails():
    with Case() as c:
        r = c.run({"FAKE_QCOUNT": "0"})
        assert r.returncode != 0, r.stderr
        c.assert_removed()
        r2 = Case()
        with r2:
            r = r2.run({"FAKE_QCOUNT": "3", "RESTORE_MIN_QUOTATIONS": "10"})
            assert r.returncode != 0
            r2.assert_removed()


def test_postgres_never_ready_fails_and_container_is_removed():
    with Case() as c:
        r = c.run({"FAKE_PG_READY_EXIT": "1"})
        assert r.returncode != 0 and "não ficou pronto" in r.stderr, r.stderr
        c.assert_removed()


def test_corrupt_media_fails_and_container_is_removed():
    with Case() as c:
        (c.bdir / "media_20260927_040000.tar.gz").write_bytes(b"lixo")
        r = c.run()
        assert r.returncode != 0 and "media" in r.stderr, r.stderr
        c.assert_removed()
        assert not (c.bdir / "restore_last_success").exists()


def test_no_dump_fails_before_starting_any_container():
    with Case(dump=False) as c:
        r = c.run()
        assert r.returncode != 0 and "nenhum dump" in r.stderr, r.stderr
        assert not [x for x in c.fk.docker_calls() if x.startswith("run ")]


def test_injection_in_identifiers_is_refused():
    with Case() as c:
        r = c.run({"RESTORE_SCHEMA": "engematex'; DROP SCHEMA x; --"})
        assert r.returncode != 0 and "inválido" in r.stderr
        assert c.fk.docker_calls() == []


TESTS = [
    test_success_restores_newest_dump_in_isolated_ephemeral_container,
    test_output_has_only_counts_and_table_names_never_content,
    test_missing_schema_fails_and_container_is_removed,
    test_missing_key_table_fails_and_container_is_removed,
    test_quotations_below_threshold_fails,
    test_postgres_never_ready_fails_and_container_is_removed,
    test_corrupt_media_fails_and_container_is_removed,
    test_no_dump_fails_before_starting_any_container,
    test_injection_in_identifiers_is_refused,
]

if __name__ == "__main__":
    n = run_tests(TESTS)
    print()
    if n:
        print(f"FAILED: {n}/{len(TESTS)} tests failed")
        sys.exit(1)
    print(f"OK: all {len(TESTS)} tests passed")
