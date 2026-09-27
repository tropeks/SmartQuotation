"""
Tests: endurecimento do scripts/backup_db.sh (ordem 002, achados da revisão do PR #114).

Tudo com docker FALSO (tests/_ops_fakes.py) — nenhum docker real, nenhuma produção.
Roda sozinho (`python -m tests.test_backup_db_hardening`) e também pelo
`python -m tests.test_backup_script`, que o job ops-tests do CI já chama.
"""
import os
import stat
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from tests._ops_fakes import FOOTER_DB, SCRIPTS, FakeEnv, run_tests, synthetic_dump

SCRIPT = SCRIPTS / "backup_db.sh"
LIB = SCRIPTS / "lib" / "backup_common.sh"


def _mode(p: Path) -> int:
    return stat.S_IMODE(p.stat().st_mode)


def _fresh():
    tmp = tempfile.TemporaryDirectory()
    base = Path(tmp.name)
    fk = FakeEnv(base)
    bdir = base / "backups" / "sq"
    fk.env["BACKUP_DIR"] = str(bdir)
    fk.env["POSTGRES_USER"] = "sq"
    fk.env["POSTGRES_DB"] = "smartquotation"
    return tmp, fk, bdir


def _dumps(bdir: Path):
    return sorted(bdir.glob("sq_*.sql.gz")) if bdir.exists() else []


# --- (a) umask 077: dump 0600, diretório 0700 --------------------------------------------

def test_umask_is_set_before_any_mkdir():
    text = SCRIPT.read_text()
    assert "umask 077" in text, "backup_db.sh precisa de 'umask 077'"
    assert text.index("umask 077") < text.index("mkdir -p"), (
        "umask 077 tem que vir ANTES do mkdir: senão o diretório nasce 0755"
    )


def test_final_dump_and_status_are_0600_and_dir_0700():
    tmp, fk, bdir = _fresh()
    with tmp:
        fk.set_dump(synthetic_dump())
        r = fk.run("backup_db.sh")
        assert r.returncode == 0, r.stderr
        dumps = _dumps(bdir)
        assert len(dumps) == 1, dumps
        assert _mode(dumps[0]) == 0o600, oct(_mode(dumps[0]))
        assert _mode(bdir) == 0o700, oct(_mode(bdir))
        assert _mode(bdir / "last_success") == 0o600, oct(_mode(bdir / "last_success"))


# --- (b) rodapé obrigatório: dump truncado grande é rejeitado ----------------------------

def test_large_dump_without_footer_is_rejected_and_leaves_nothing():
    tmp, fk, bdir = _fresh()
    with tmp:
        # Milhares de linhas, com "engematex": passa tamanho/linhas/schema. Só o rodapé pega.
        text = "\n".join(f"INSERT INTO engematex.t VALUES ({i});" for i in range(5000)) + "\n"
        fk.set_dump(text)
        r = fk.run("backup_db.sh")
        assert r.returncode != 0, "dump sem rodapé tem que falhar"
        assert "rodapé" in r.stderr, r.stderr
        assert list(bdir.iterdir()) == [], f"nada pode sobrar: {list(bdir.iterdir())}"


def test_cluster_dump_truncated_before_cluster_footer_is_rejected():
    tmp, fk, bdir = _fresh()
    with tmp:
        # Tem o rodapé de UM banco, mas não o do cluster: o pg_dumpall parou no meio.
        fk.set_dump(synthetic_dump(lines=3000, footer=None))
        r = fk.run("backup_db.sh")
        assert r.returncode != 0, r.stderr
        assert not _dumps(bdir)


def test_compose_mode_requires_pg_dump_footer():
    tmp, fk, bdir = _fresh()
    with tmp:
        fk.env["FAKE_STATE"] = "absent"
        body = "\n".join(f"-- linha {i} engematex" for i in range(300)) + "\n"
        fk.set_dump(body)
        r = fk.run("backup_db.sh")
        assert r.returncode != 0 and not _dumps(bdir), r.stderr
        fk.set_dump(body + "--\n" + FOOTER_DB + "\n--\n")
        r = fk.run("backup_db.sh")
        assert r.returncode == 0, r.stderr
        assert len(_dumps(bdir)) == 1


# --- (c) injeção: nada do host é re-parseado pelo sh do container ------------------------

def test_container_dump_passes_user_host_port_as_positional_argv():
    tmp, fk, bdir = _fresh()
    with tmp:
        fk.set_dump(synthetic_dump())
        r = fk.run("backup_db.sh", {"POSTGRES_USER": "sq_admin"})
        assert r.returncode == 0, r.stderr
        argv = Path(fk.env["FAKE_DUMP_ARGV"]).read_text().splitlines()
        assert argv == ["-U", "sq_admin", "-h", "127.0.0.1", "-p", "5436"], argv
        exec_calls = [c for c in fk.docker_calls() if c.startswith("exec ")]
        assert exec_calls and exec_calls[0].endswith(" sh sq_admin 127.0.0.1 5436"), exec_calls


def test_malicious_values_are_refused_before_touching_docker():
    for var, value in [
        ("POSTGRES_USER", 'sq"; touch MARKER; echo "'),
        ("POSTGRES_USER", "sq$(touch MARKER)"),
        ("DB_CONTAINER_HOST", "127.0.0.1; touch MARKER"),
        ("DB_CONTAINER_PORT", "5436 -f /tmp/x"),
    ]:
        tmp, fk, bdir = _fresh()
        with tmp:
            fk.set_dump(synthetic_dump())
            marker = Path(tmp.name) / "MARKER"
            env = {var: value.replace("MARKER", str(marker))}
            r = subprocess.run(
                ["bash", str(SCRIPT)], env={**fk.env, **env}, capture_output=True, text=True,
                cwd=tmp.name,
            )
            assert r.returncode != 0, f"{var}={value!r} tinha que ser recusado"
            assert "inválido" in r.stderr, r.stderr
            assert not marker.exists(), f"{var}={value!r} executou comando injetado"
            assert fk.docker_calls() == [], f"docker não pode ser chamado: {fk.docker_calls()}"
            assert not _dumps(bdir)


# --- (e) container parado não conta ------------------------------------------------------

def test_stopped_container_fails_instead_of_falling_back_to_compose():
    tmp, fk, bdir = _fresh()
    with tmp:
        fk.env["FAKE_STATE"] = "false"
        fk.set_dump(synthetic_dump())
        r = fk.run("backup_db.sh")
        assert r.returncode != 0, r.stderr
        assert "PARADO" in r.stderr, r.stderr
        calls = fk.docker_calls()
        assert any("{{.State.Running}}" in c for c in calls), calls
        assert not any(c.startswith(("compose", "exec")) for c in calls), calls
        assert not _dumps(bdir)


# --- (f) retenção ------------------------------------------------------------------------

def _old(p: Path, days: float) -> None:
    t = time.time() - days * 86400
    os.utime(p, (t, t))


def test_retention_prunes_old_dumps_only_after_a_new_valid_one():
    tmp, fk, bdir = _fresh()
    with tmp:
        bdir.mkdir(parents=True)
        old = bdir / "sq_20200101_030000.sql.gz"
        recent = bdir / "sq_20260920_030000.sql.gz"
        other = bdir / "media_20200101_030000.tar.gz"
        for p in (old, recent, other):
            p.write_bytes(b"x")
        _old(old, 30)
        _old(recent, 3)
        _old(other, 30)

        # Backup que FALHA não poda nada.
        fk.set_dump("x" * 20)
        r = fk.run("backup_db.sh")
        assert r.returncode != 0
        assert old.exists() and recent.exists(), "falha não pode podar"

        fk.set_dump(synthetic_dump())
        r = fk.run("backup_db.sh", {"BACKUP_RETENTION_DAYS": "14"})
        assert r.returncode == 0, r.stderr
        assert not old.exists(), "dump de 30 dias tinha que ser podado (retenção 14)"
        assert recent.exists(), "dump de 3 dias fica"
        assert other.exists(), "backup_db.sh só poda sq_*.sql.gz"
        assert len(_dumps(bdir)) == 2  # recent + novo


def test_retention_zero_disables_pruning_and_garbage_is_refused():
    tmp, fk, bdir = _fresh()
    with tmp:
        bdir.mkdir(parents=True)
        old = bdir / "sq_20200101_030000.sql.gz"
        old.write_bytes(b"x")
        _old(old, 400)
        fk.set_dump(synthetic_dump())
        r = fk.run("backup_db.sh", {"BACKUP_RETENTION_DAYS": "0"})
        assert r.returncode == 0, r.stderr
        assert old.exists()
        r = fk.run("backup_db.sh", {"BACKUP_RETENTION_DAYS": "14; rm -rf /"})
        assert r.returncode != 0 and "BACKUP_RETENTION_DAYS" in r.stderr


def test_prune_never_removes_the_last_valid_even_if_old():
    """Relógio torto / mtime antigo: o arquivo recém-validado nunca é podado."""
    with tempfile.TemporaryDirectory() as d:
        d = Path(d)
        keep = d / "sq_1.sql.gz"
        gone = d / "sq_0.sql.gz"
        for p in (keep, gone):
            p.write_bytes(b"x")
            _old(p, 100)
        r = subprocess.run(
            ["bash", "-c", f'set -euo pipefail; SQ_SCRIPT=t; . "{LIB}"; '
             f'sq_prune "{d}" "sq_*.sql.gz" 14 "{keep}"'],
            capture_output=True, text=True,
        )
        assert r.returncode == 0, r.stderr
        assert keep.exists() and not gone.exists()


# --- (g) last_success só no sucesso ------------------------------------------------------

def test_last_success_records_timestamp_file_and_bytes_only_on_success():
    tmp, fk, bdir = _fresh()
    with tmp:
        fk.set_dump(synthetic_dump())
        r = fk.run("backup_db.sh")
        assert r.returncode == 0, r.stderr
        status = dict(
            line.split("=", 1) for line in (bdir / "last_success").read_text().splitlines()
        )
        assert set(status) == {"timestamp", "file", "bytes"}, status
        assert status["timestamp"][:4].isdigit() and "T" in status["timestamp"], status
        dump = bdir / status["file"]
        assert dump.exists(), status
        assert int(status["bytes"]) == dump.stat().st_size

        before = (bdir / "last_success").read_text()
        fk.set_dump("x" * 20)
        r = fk.run("backup_db.sh")
        assert r.returncode != 0
        assert (bdir / "last_success").read_text() == before, "falha não pode tocar last_success"


# --- (h) POSTGRES_USER ausente: erro claro, não "unbound variable" ------------------------

def test_compose_mode_without_postgres_user_gives_clear_error():
    tmp, fk, bdir = _fresh()
    with tmp:
        fk.env["FAKE_STATE"] = "absent"
        del fk.env["POSTGRES_USER"]
        fk.set_dump(synthetic_dump())
        r = fk.run("backup_db.sh")
        assert r.returncode != 0
        assert "POSTGRES_USER" in r.stderr and "unbound" not in r.stderr, r.stderr
        assert not _dumps(bdir)


def test_container_mode_without_postgres_user_uses_the_containers_own():
    tmp, fk, bdir = _fresh()
    with tmp:
        del fk.env["POSTGRES_USER"]
        del fk.env["POSTGRES_DB"]
        fk.env["FAKE_CTR_ENV"] = "POSTGRES_USER=usuario_do_container"
        fk.set_dump(synthetic_dump())
        r = fk.run("backup_db.sh")
        assert r.returncode == 0, r.stderr
        argv = Path(fk.env["FAKE_DUMP_ARGV"]).read_text().splitlines()
        assert argv[:2] == ["-U", "usuario_do_container"], argv


TESTS = [
    test_umask_is_set_before_any_mkdir,
    test_final_dump_and_status_are_0600_and_dir_0700,
    test_large_dump_without_footer_is_rejected_and_leaves_nothing,
    test_cluster_dump_truncated_before_cluster_footer_is_rejected,
    test_compose_mode_requires_pg_dump_footer,
    test_container_dump_passes_user_host_port_as_positional_argv,
    test_malicious_values_are_refused_before_touching_docker,
    test_stopped_container_fails_instead_of_falling_back_to_compose,
    test_retention_prunes_old_dumps_only_after_a_new_valid_one,
    test_retention_zero_disables_pruning_and_garbage_is_refused,
    test_prune_never_removes_the_last_valid_even_if_old,
    test_last_success_records_timestamp_file_and_bytes_only_on_success,
    test_compose_mode_without_postgres_user_gives_clear_error,
    test_container_mode_without_postgres_user_uses_the_containers_own,
]

if __name__ == "__main__":
    n = run_tests(TESTS)
    print()
    if n:
        print(f"FAILED: {n}/{len(TESTS)} tests failed")
        sys.exit(1)
    print(f"OK: all {len(TESTS)} tests passed")
