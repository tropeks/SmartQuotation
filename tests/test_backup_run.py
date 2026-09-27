"""
Tests: scripts/backup_run.sh — o runner da sq-backup.service (ordem 003, revisão).

Roda TODAS as etapas em ordem (db, media, key, key-offsite, offsite), SEGUE depois de falha,
registra quais falharam em backup_run_last e sai != 0 no fim se alguma falhou. O runner real
é copiado para um diretório temporário com etapas FALSAS (cada uma registra que rodou e sai
com FAKE_RC_<etapa>).
"""
import os
import shutil
import signal
import stat
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from tests._ops_fakes import ROOT, run_tests

ORDER = ["backup_db", "backup_media", "backup_key", "offsite_key_push", "offsite_push"]
_STEP = ('#!/usr/bin/env bash\necho "$(basename "$0" .sh)" >> "$STEP_LOG"\n'
         '[ "${FAKE_SLOW_%s:-0}" = 1 ] && exec sleep 30\n'
         'exit "${FAKE_RC_%s:-0}"\n')


class RunCase:
    def __init__(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.base = Path(self._tmp.name)
        scripts = self.base / "scripts"
        (scripts / "lib").mkdir(parents=True)
        shutil.copy(ROOT / "scripts" / "backup_run.sh", scripts)
        shutil.copy(ROOT / "scripts" / "lib" / "backup_common.sh", scripts / "lib")
        for step in ORDER:
            p = scripts / f"{step}.sh"
            p.write_text(_STEP % (step.upper(), step.upper()))
            p.chmod(0o755)
        self.runner = scripts / "backup_run.sh"
        self.bdir = self.base / "backups"
        self.log = self.base / "steps.log"

    def env(self, **rcs):
        env = {k: v for k, v in os.environ.items() if not k.startswith(("FAKE_", "BACKUP_"))}
        env.update({"BACKUP_DIR": str(self.bdir), "STEP_LOG": str(self.log)})
        env.update({f"FAKE_RC_{k.upper()}": str(v) for k, v in rcs.items()})
        return env

    def run(self, **rcs):
        cmd = ["bash", str(self.runner)]
        return subprocess.run(cmd, env=self.env(**rcs), capture_output=True, text=True, timeout=30)

    def steps(self):
        return self.log.read_text().split() if self.log.exists() else []

    def status(self):
        return dict(ln.split("=", 1) for ln in (self.bdir / "backup_run_last").read_text().splitlines())

    def __enter__(self):
        return self

    def __exit__(self, *a):
        self._tmp.cleanup()


def test_all_green_runs_every_step_in_order():
    with RunCase() as c:
        r = c.run()
        assert r.returncode == 0, r.stderr
        assert c.steps() == ORDER, c.steps()
        st = c.status()
        assert st["failed"] == "-" and all(st[s] == "0" for s in ORDER), st
        assert stat.S_IMODE((c.bdir / "backup_run_last").stat().st_mode) == 0o600


def test_key_offsite_failure_still_ships_the_dump_and_fails_at_the_end():
    with RunCase() as c:
        r = c.run(offsite_key_push=1)
        assert c.steps() == ORDER, "o offsite do dump tem de rodar mesmo com a chave falhando"
        assert r.returncode != 0, "a unit tem de ficar failed"
        st = c.status()
        assert st["offsite_key_push"] == "1" and st["offsite_push"] == "0", st
        assert st["failed"] == "offsite_key_push", st
        assert "offsite_key_push" in r.stderr and "FALHA" in r.stderr, r.stderr


def test_db_failure_still_runs_offsite_over_what_exists():
    with RunCase() as c:
        r = c.run(backup_db=1, backup_key=2)
        assert c.steps() == ORDER and r.returncode != 0
        assert c.status()["failed"] == "backup_db,backup_key", c.status()


def test_sigterm_during_a_step_stops_everything_with_143():
    """systemctl stop / TimeoutStartSec: a etapa em curso morre, as seguintes NÃO rodam."""
    with RunCase() as c:
        env = c.env()
        env["FAKE_SLOW_BACKUP_MEDIA"] = "1"
        pipes = {"stdout": subprocess.PIPE, "stderr": subprocess.PIPE, "text": True}
        p = subprocess.Popen(["bash", str(c.runner)], env=env, **pipes)
        deadline = time.time() + 10
        while "backup_media" not in c.steps():
            assert time.time() < deadline and p.poll() is None, "a etapa lenta não começou"
            time.sleep(0.05)
        time.sleep(0.2)
        start = time.time()
        p.send_signal(signal.SIGTERM)
        _out, err = p.communicate(timeout=10)
        assert p.returncode == 143, (p.returncode, err)
        assert time.time() - start < 5, "o sinal tem de ser atendido na hora, sem esperar a etapa"
        assert c.steps() == ["backup_db", "backup_media"], c.steps()
        st = c.status()
        assert st["interrupted"] == "backup_media" and st["backup_db"] == "0", st
        assert "INTERROMPIDO" in err, err


def test_unit_runs_only_the_runner_and_runner_lists_the_steps():
    unit = (ROOT / "ops" / "systemd" / "sq-backup.service").read_text()
    execs = [ln for ln in unit.splitlines() if ln.startswith("ExecStart=")]
    assert execs == ["ExecStart=/opt/smartquotation/scripts/backup_run.sh"], execs
    text = (ROOT / "scripts" / "backup_run.sh").read_text()
    assert f"STEPS=({' '.join(ORDER)})" in text
    for step in ORDER:
        assert (ROOT / "scripts" / f"{step}.sh").exists(), step


TESTS = [
    test_all_green_runs_every_step_in_order,
    test_key_offsite_failure_still_ships_the_dump_and_fails_at_the_end,
    test_db_failure_still_runs_offsite_over_what_exists,
    test_sigterm_during_a_step_stops_everything_with_143,
    test_unit_runs_only_the_runner_and_runner_lists_the_steps,
]

if __name__ == "__main__":
    n = run_tests(TESTS)
    print()
    if n:
        print(f"FAILED: {n}/{len(TESTS)} tests failed")
        sys.exit(1)
    print(f"OK: all {len(TESTS)} tests passed")
