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

import os
import time

from tests._offsite_fakes import OffsiteCase
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
        # -v: sem ele o volume anônimo do postgres:15, com a cópia do banco, fica para trás
        assert rms and rms[-1] == f"rm -fv {name}", f"container {name} não foi removido com -v: {rms}"
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
        # major de origem do dump (default do fixture: 15.8) e a imagem efetivamente usada.
        assert status["source_major"] == "15" and status["image"] == "postgres:15", status


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


def test_partial_restore_with_failed_copy_fails():
    """Um COPY que falha no meio é restore parcial: só 'role já existe' é tolerado."""
    with Case() as c:
        err = ('ERROR:  invalid input syntax for type bigint: "x"\n'
               'CONTEXT:  COPY quotations_quotation, line 7: "7\tCOT-SINT-0007"')
        r = c.run({"FAKE_PSQL_EXTRA_ERR": err})
        assert r.returncode != 0 and "restore parcial" in r.stderr, r.stderr
        assert "COT-SINT" not in r.stdout + r.stderr, "mensagem do psql (com dado) vazou"
        assert not (c.bdir / "restore_last_success").exists()
        c.assert_removed()


def test_only_role_already_exists_is_tolerated():
    with Case() as c:
        r = c.run({"FAKE_PSQL_EXTRA_ERR": 'ERROR:  role "postgres" already exists'})
        assert r.returncode == 0, r.stderr
        assert "2 erro(s) do psql, 0 inesperado(s)" in r.stdout, r.stdout


def test_stale_newest_dump_fails_before_starting_container():
    with Case() as c:
        t = time.time() - 30 * 3600
        for p in c.bdir.glob("sq_*.sql.gz"):
            os.utime(p, (t, t))
        r = c.run()
        assert r.returncode != 0 and "mais de 26h" in r.stderr, r.stderr
        assert not [x for x in c.fk.docker_calls() if x.startswith("run ")]
        r = c.run({"RESTORE_MAX_AGE_HOURS": "48"})
        assert r.returncode == 0, r.stderr


def test_restore_dump_file_points_to_a_specific_offsite_download():
    """Drill trimestral a partir do off-site: o arquivo indicado, velho ou não, é o restaurado,
    e o status do drill semanal não é tocado."""
    with Case() as c:
        drill = c.base / "drill"
        drill.mkdir()
        dump = drill / "sq_20260601_030000.sql.gz"
        write_gz(dump, synthetic_dump(quotations=5))
        media = drill / "media_20260601_030000.tar.gz"
        write_media_tar(media, {"a.pdf": b"%PDF", "b.pdf": b"%PDF"})
        t = time.time() - 120 * 24 * 3600
        os.utime(dump, (t, t))
        r = c.run({"RESTORE_DUMP_FILE": str(dump), "RESTORE_MEDIA_FILE": str(media)})
        assert r.returncode == 0, r.stderr
        assert c.sink.read_bytes() == gzip.decompress(dump.read_bytes()), "não restaurou o arquivo indicado"
        st = dict(ln.split("=", 1) for ln in (c.bdir / "restore_file_last_success").read_text().splitlines())
        assert st["dump"] == dump.name and st["media"] == media.name and st["media_entries"] == "2", st
        assert not (c.bdir / "restore_last_success").exists(), "drill do off-site não vira o semanal"
        c.assert_removed()


def test_restore_dump_file_missing_fails_before_starting_container():
    with Case() as c:
        r = c.run({"RESTORE_DUMP_FILE": str(c.base / "nao_existe.sql.gz")})
        assert r.returncode != 0 and "RESTORE_DUMP_FILE" in r.stderr, r.stderr
        r = c.run({"RESTORE_MEDIA_FILE": str(c.base / "nao_existe.tar.gz")})
        assert r.returncode != 0 and "RESTORE_MEDIA_FILE" in r.stderr, r.stderr
        assert not [x for x in c.fk.docker_calls() if x.startswith("run ")]


def test_restore_file_is_refused_inside_backup_units_or_inside_backup_dir():
    with Case() as c:
        outside = c.base / "drill.sql.gz"
        write_gz(outside, synthetic_dump())
        r = c.run({"RESTORE_DUMP_FILE": str(outside), "SQ_BACKUP_UNIT": "1"})
        assert r.returncode == 1 and "SQ_BACKUP_UNIT=1" in r.stderr, r.stderr
        media_out = c.base / "drill_media.tar.gz"
        write_media_tar(media_out, {"a.pdf": b"%PDF"})
        r = c.run({"RESTORE_MEDIA_FILE": str(media_out), "SQ_BACKUP_UNIT": "1"})
        assert r.returncode == 1 and "SQ_BACKUP_UNIT=1" in r.stderr, r.stderr
        r = c.run({"RESTORE_DUMP_FILE": str(c.bdir / "sq_20260927_030000.sql.gz")})
        assert r.returncode == 1 and "dentro do BACKUP_DIR" in r.stderr, r.stderr
        r = c.run({"RESTORE_MEDIA_FILE": str(c.bdir / "media_20260927_030000.tar.gz")})
        assert r.returncode == 1 and "dentro do BACKUP_DIR" in r.stderr, r.stderr
        assert not [x for x in c.fk.docker_calls() if x.startswith("run ")]
    with Case() as c:  # INVOCATION_ID sozinho (terminal sob systemd, runner de CI) NÃO é o marcador
        outside = c.base / "drill.sql.gz"
        write_gz(outside, synthetic_dump())
        r = c.run({"RESTORE_DUMP_FILE": str(outside), "INVOCATION_ID": "abc123"})
        assert r.returncode == 0, r.stderr


def _offsite_restore(oc, extra=None):
    env = {"FAKE_RESTORE_SINK": str(oc.base / "restored.sql"), "RESTORE_POLL_INTERVAL": "0",
           "RESTORE_WAIT_SECONDS": "3"}
    env.update(extra or {})
    return oc.fk.run("restore_check.sh", env)


def test_weekly_drill_confirms_newest_offsite_dump_by_hash_without_download():
    with OffsiteCase() as oc:
        assert oc.push().returncode == 0
        n = len(oc.rclone_calls())
        r = _offsite_restore(oc)
        assert r.returncode == 0, r.stderr
        calls = oc.rclone_calls()[n:]
        assert len(calls) == 1 and calls[0].startswith("hashsum ") and "sq_20260927_030000" in calls[0], calls
        st = dict(ln.split("=", 1) for ln in (oc.bdir / "restore_last_success").read_text().splitlines())
        assert st["offsite_dump"] == "sq_20260927_030000.sql.gz.age", st


def test_weekly_drill_fails_when_offsite_is_missing_changed_or_unreachable():
    with OffsiteCase() as oc:
        assert oc.push().returncode == 0
        r = _offsite_restore(oc, {"FAKE_RCLONE_FAIL": "hashsum"})
        assert r.returncode == 1 and "não respondeu" in r.stderr, r.stderr
        obj = oc.dump_bucket / "sq_20260927_030000.sql.gz.age"
        obj.write_bytes(b"adulterado")
        r = _offsite_restore(oc)
        assert r.returncode == 1 and "hash diferente" in r.stderr, r.stderr
        obj.unlink()
        r = _offsite_restore(oc)
        assert r.returncode == 1 and "ausente" in r.stderr, r.stderr
        assert not (oc.bdir / "restore_last_success").exists()
        assert not [x for x in oc.fk.docker_calls() if x.startswith("run ")], "falha antes do container"
    with OffsiteCase() as oc:  # off-site configurado, mas nada confirmado
        r = _offsite_restore(oc)
        assert r.returncode == 1 and "nenhum dump confirmado" in r.stderr, r.stderr


def test_weekly_drill_fails_when_offsite_confirmed_is_not_the_newest_local_or_is_stale():
    with OffsiteCase() as oc:
        assert oc.push().returncode == 0
        write_gz(oc.bdir / "sq_20260928_030000.sql.gz", synthetic_dump())  # novo, não enviado
        r = _offsite_restore(oc)
        assert r.returncode == 1 and "não é o dump local mais novo" in r.stderr, r.stderr
        (oc.bdir / "sq_20260928_030000.sql.gz").unlink()
        old = time.time() - 30 * 3600
        for p in oc.bdir.glob("sq_*.sql.gz"):
            os.utime(p, (old, old))
        r = _offsite_restore(oc, {"RESTORE_MAX_AGE_HOURS": "0"})
        assert r.returncode == 1 and "mais de 26h" in r.stderr, r.stderr
        r = _offsite_restore(oc, {"RESTORE_MAX_AGE_HOURS": "0", "OFFSITE_MAX_AGE_HOURS": "48"})
        assert r.returncode == 0, r.stderr


def test_weekly_drill_never_downloads_when_provider_has_no_hash():
    with OffsiteCase() as oc:
        assert oc.push().returncode == 0
        n = len(oc.rclone_calls())
        r = _offsite_restore(oc, {"OFFSITE_HASH_DOWNLOAD": "1"})
        assert r.returncode == 0, r.stderr
        calls = oc.rclone_calls()[n:]
        assert len(calls) == 1 and calls[0].startswith("lsjson "), calls  # nem hashsum --download
        assert "hash indisponível sem download" in r.stderr, r.stderr
        st = dict(ln.split("=", 1) for ln in (oc.bdir / "restore_last_success").read_text().splitlines())
        assert st["offsite_check"] == "tamanho", st
        obj = oc.dump_bucket / "sq_20260927_030000.sql.gz.age"
        obj.write_bytes(obj.read_bytes() + b"X")
        r = _offsite_restore(oc, {"OFFSITE_HASH_DOWNLOAD": "1"})
        assert r.returncode == 1 and "tamanho diferente" in r.stderr, r.stderr
        obj.unlink()
        r = _offsite_restore(oc, {"OFFSITE_HASH_DOWNLOAD": "1"})
        assert r.returncode == 1 and "ausente" in r.stderr, r.stderr


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
    test_partial_restore_with_failed_copy_fails,
    test_only_role_already_exists_is_tolerated,
    test_stale_newest_dump_fails_before_starting_container,
    test_restore_dump_file_points_to_a_specific_offsite_download,
    test_restore_dump_file_missing_fails_before_starting_container,
    test_restore_file_is_refused_inside_backup_units_or_inside_backup_dir,
    test_weekly_drill_fails_when_offsite_confirmed_is_not_the_newest_local_or_is_stale,
    test_weekly_drill_never_downloads_when_provider_has_no_hash,
    test_weekly_drill_confirms_newest_offsite_dump_by_hash_without_download,
    test_weekly_drill_fails_when_offsite_is_missing_changed_or_unreachable,
]

if __name__ == "__main__":
    n = run_tests(TESTS)
    print()
    if n:
        print(f"FAILED: {n}/{len(TESTS)} tests failed")
        sys.exit(1)
    print(f"OK: all {len(TESTS)} tests passed")
