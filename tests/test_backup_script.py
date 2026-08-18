"""
Tests: scripts/backup_db.sh exists and is executable.
"""
import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BACKUP_SCRIPT = ROOT / "scripts" / "backup_db.sh"
ENV_PROD_EXAMPLE = ROOT / ".env.prod.example"
INFRA_DOC = ROOT / "docs" / "INFRASTRUCTURE.md"


def test_backup_script_exists():
    assert BACKUP_SCRIPT.exists(), f"scripts/backup_db.sh must exist at {BACKUP_SCRIPT}"


def test_backup_script_is_executable():
    assert BACKUP_SCRIPT.exists(), f"scripts/backup_db.sh must exist at {BACKUP_SCRIPT}"
    assert os.access(BACKUP_SCRIPT, os.X_OK), "scripts/backup_db.sh must be executable"


def test_backup_script_contains_pg_dump():
    text = BACKUP_SCRIPT.read_text()
    assert "pg_dump" in text, "backup_db.sh must contain pg_dump"
    assert "POSTGRES_USER" in text, "backup_db.sh must reference POSTGRES_USER"
    assert "POSTGRES_DB" in text, "backup_db.sh must reference POSTGRES_DB"
    assert "gzip" in text, "backup_db.sh must pipe output through gzip"


def test_env_prod_example_has_backup_dir():
    text = ENV_PROD_EXAMPLE.read_text()
    assert "POSTGRES_BACKUP_DIR" in text, ".env.prod.example must contain POSTGRES_BACKUP_DIR"
    assert "POSTGRES_BACKUP_DIR=/backups/sq" in text, (
        ".env.prod.example must have POSTGRES_BACKUP_DIR=/backups/sq"
    )


def test_env_prod_example_has_media_backup_dir():
    """MEDIA_BACKUP_DIR must be documented in .env.prod.example.

    backup_media.sh resolves its destination as:
        BACKUP_DIR="${BACKUP_DIR:-${MEDIA_BACKUP_DIR:-/backups/sq}}"

    Without MEDIA_BACKUP_DIR in .env.prod.example an operator who customises
    POSTGRES_BACKUP_DIR to a dedicated path will not realise that media backups
    land in a different (default) directory.  Both vars must appear together in
    the Backup section so the operator configures them as a pair.
    """
    text = ENV_PROD_EXAMPLE.read_text()
    assert "MEDIA_BACKUP_DIR" in text, (
        ".env.prod.example must document MEDIA_BACKUP_DIR alongside "
        "POSTGRES_BACKUP_DIR so operators know where media backups land. "
        "Without it, customising POSTGRES_BACKUP_DIR silently puts DB and "
        "media backups in different directories."
    )
    assert "MEDIA_BACKUP_DIR=/backups/sq" in text, (
        ".env.prod.example must set MEDIA_BACKUP_DIR=/backups/sq (same default "
        "as POSTGRES_BACKUP_DIR so both go to the same place by default)."
    )


def test_env_prod_backup_vars_have_same_default():
    """POSTGRES_BACKUP_DIR and MEDIA_BACKUP_DIR should share the same default path.

    If their default values differ an operator who relies on the example file
    without reading it carefully will have DB and media backups silently
    separated, making a consistent restore harder.
    """
    text = ENV_PROD_EXAMPLE.read_text()
    import re
    pg_match = re.search(r"POSTGRES_BACKUP_DIR=(\S+)", text)
    media_match = re.search(r"MEDIA_BACKUP_DIR=(\S+)", text)
    assert pg_match, ".env.prod.example must define POSTGRES_BACKUP_DIR"
    assert media_match, ".env.prod.example must define MEDIA_BACKUP_DIR"
    assert pg_match.group(1) == media_match.group(1), (
        f"POSTGRES_BACKUP_DIR ({pg_match.group(1)!r}) and MEDIA_BACKUP_DIR "
        f"({media_match.group(1)!r}) must share the same default value in "
        f".env.prod.example so DB and media backups go to the same directory "
        f"out of the box."
    )


def test_backup_script_supports_both_compose_and_standalone_container():
    """Script must support BOTH docker-compose and a standalone ("avulso") container.

    Production does NOT run via docker-compose (see docs/HANDOFF_MIGRACAO.md §4 and
    docs/INFRASTRUCTURE.md): it is a standalone container named ``sq-prod-db``, so a
    script that only knows ``docker compose exec`` never runs a real backup there
    (this was exactly the bug in PR #112's open item). The script must therefore be
    able to target a named container directly (configurable via DB_CONTAINER, default
    sq-prod-db) *and* keep the docker-compose path as a fallback/alternative for
    environments that do use compose.
    """
    text = BACKUP_SCRIPT.read_text()
    assert "docker compose" in text or "docker-compose" in text, (
        "backup_db.sh must still support 'docker compose exec' for compose-based envs"
    )
    assert "DB_CONTAINER" in text, (
        "backup_db.sh must support targeting a standalone container by name via "
        "DB_CONTAINER, since production is not docker-compose"
    )
    assert "sq-prod-db" in text, (
        "backup_db.sh must default DB_CONTAINER to 'sq-prod-db', the real production "
        "container name"
    )
    assert "exec" in text, (
        "backup_db.sh must use '<docker> exec' (compose or standalone) to run the dump"
    )


def test_backup_script_mode_detection_is_overridable():
    """BACKUP_MODE must let an operator force compose|container instead of auto-detect."""
    text = BACKUP_SCRIPT.read_text()
    assert "BACKUP_MODE" in text, (
        "backup_db.sh must expose BACKUP_MODE (auto|container|compose) so an operator "
        "can override auto-detection when it guesses wrong"
    )


def test_backup_script_has_set_u():
    """Script must use set -u (or set -euo pipefail) so unbound vars are fatal, not silently empty."""
    text = BACKUP_SCRIPT.read_text()
    has_set_u = "set -u" in text or "set -euo pipefail" in text or "set -eu" in text
    assert has_set_u, (
        "backup_db.sh must use 'set -u' (or 'set -euo pipefail') so that missing "
        "POSTGRES_USER / POSTGRES_DB fail loudly instead of producing a corrupt dump"
    )


def test_cron_entry_sources_env_prod():
    """The documented cron entry must source .env.prod (with set -a) before calling backup_db.sh.

    A bare cron entry like:
        0 3 * * * /opt/smartquotation/scripts/backup_db.sh
    runs without the shell profile, so POSTGRES_USER/POSTGRES_DB are unbound
    and the script aborts (set -u). The cron entry must use:
        bash -c 'set -a && source /opt/smartquotation/.env.prod && set +a && /opt/.../backup_db.sh'
    or an equivalent that exports the .env.prod variables into the child process.
    """
    text = INFRA_DOC.read_text()
    lines = text.splitlines()
    cron_lines = [l for l in lines if "backup_db.sh" in l and ("* * *" in l or "cron" in l.lower())]
    # Find the literal cron schedule line (starts with digits or 0-59)
    schedule_lines = [l for l in lines if "backup_db.sh" in l and l.strip().startswith("0 ")]
    assert schedule_lines, (
        "INFRASTRUCTURE.md must contain a cron schedule line with 'backup_db.sh'"
    )
    for line in schedule_lines:
        sources_env = ".env.prod" in line or "env.prod" in line
        assert sources_env, (
            f"Cron entry must source .env.prod to export POSTGRES_USER/POSTGRES_DB, "
            f"but found: {line!r}. "
            f"Without sourcing .env.prod, the cron job fails with 'unbound variable'."
        )


def test_infrastructure_doc_sources_env_with_allexport():
    """INFRASTRUCTURE.md must document 'set -a' when sourcing .env.prod.

    Without 'set -a', variables defined in .env.prod without 'export' are only
    available in the current shell — not inherited by the child process
    (./scripts/backup_db.sh). With 'set -u' in the script, this causes
    POSTGRES_USER / POSTGRES_DB to be 'unbound' and the script aborts.

    The correct invocation is:
        set -a && source .env.prod && set +a && ./scripts/backup_db.sh
    or equivalently:
        ( set -a; source .env.prod; ./scripts/backup_db.sh )
    """
    text = INFRA_DOC.read_text()
    # The doc must show 'set -a' in the context of sourcing .env.prod
    assert "set -a" in text, (
        "INFRASTRUCTURE.md must document 'set -a' before 'source .env.prod' so that "
        "shell variables are exported and inherited by scripts/backup_db.sh child process. "
        "Without this, POSTGRES_USER/POSTGRES_DB are unbound in the script (set -u aborts)."
    )


def test_sourced_env_without_allexport_does_not_reach_child():
    """Regression: sourcing .env without 'export' leaves vars unset in child process.

    This test runs a minimal shell snippet that mirrors the bug scenario:
      source <env-without-export> && bash -c 'echo ${MY_VAR}'
    and verifies it fails (set -u) — confirming the fix (set -a) is necessary.
    """
    with tempfile.NamedTemporaryFile(mode="w", suffix=".env", delete=False) as f:
        f.write("MY_VAR=hello\n")  # no 'export'
        env_file = f.name

    with tempfile.NamedTemporaryFile(mode="w", suffix=".sh", delete=False) as f:
        f.write("#!/usr/bin/env bash\nset -u\necho ${MY_VAR}\n")
        child_script = f.name
    os.chmod(child_script, 0o755)

    # Without set -a: child should NOT inherit MY_VAR → set -u causes exit ≠ 0
    result = subprocess.run(
        ["bash", "-c", f"source {env_file} && {child_script}"],
        capture_output=True,
        text=True,
    )
    assert result.returncode != 0, (
        "Without 'set -a', sourced vars must NOT reach child process (set -u should abort). "
        "This confirms the bug is real and set -a is necessary."
    )

    # With set -a: child SHOULD inherit MY_VAR → exit 0
    result_fixed = subprocess.run(
        ["bash", "-c", f"set -a && source {env_file} && set +a && {child_script}"],
        capture_output=True,
        text=True,
    )
    assert result_fixed.returncode == 0, (
        "With 'set -a; source .env; set +a', vars must be inherited by child process."
    )
    assert "hello" in result_fixed.stdout, (
        "Child process must see MY_VAR=hello when sourced with set -a."
    )

    os.unlink(env_file)
    os.unlink(child_script)


# ---------------------------------------------------------------------------
# Content validation: exit code 0 is NOT proof of a good backup. The known
# gotcha is pg_dumpall pointed at the wrong port producing a ~20 byte file
# with exit code 0 (docs/HANDOFF_MIGRACAO.md §4, memory deploy-prod-gotchas).
# ---------------------------------------------------------------------------

def test_backup_script_validates_dump_content_not_just_exit_code():
    """Script must contain real content checks (size/line count), not just rely on $?."""
    text = BACKUP_SCRIPT.read_text()
    assert "wc -c" in text or "wc -l" in text, (
        "backup_db.sh must measure the decompressed dump size/line count — exit code "
        "alone is exactly what makes the wrong-port gotcha look like a good backup"
    )
    assert "BACKUP_MIN_BYTES" in text or "BACKUP_MIN_LINES" in text, (
        "backup_db.sh must reject a dump that is smaller than a configurable minimum"
    )


def _make_fake_docker(
    bin_dir: Path, *, inspect_ok: bool, payload: str, exec_exit: int = 0, info_ok: bool = True
) -> None:
    """Fake 'docker' binary: 'info' -> info_ok, 'inspect' -> inspect_ok, 'exec'/'compose' -> payload.

    'info' must be handled explicitly because backup_db.sh probes docker usability
    with it BEFORE asking whether the container exists (see
    test_backup_script_fails_fast_when_docker_is_inaccessible for why that order
    matters: 'inspect' failing for permission reasons is not the same as 'inspect'
    failing because the container is simply absent).
    """
    fake_docker = bin_dir / "docker"
    fake_docker.write_text(
        "#!/usr/bin/env bash\n"
        f"if [ \"$1\" = \"info\" ]; then exit {0 if info_ok else 1}; fi\n"
        f"if [ \"$1\" = \"inspect\" ]; then exit {0 if inspect_ok else 1}; fi\n"
        "if [ \"$1\" = \"exec\" ] || [ \"$1\" = \"compose\" ]; then\n"
        f"  printf %s {shlex_quote(payload)}\n"
        f"  exit {exec_exit}\n"
        "fi\n"
        "exit 1\n"
    )
    fake_docker.chmod(0o755)


def _make_inaccessible_docker(bin_dir: Path) -> None:
    """Fake 'docker' binary that fails on EVERY subcommand, like a permission-denied
    or unreachable daemon would (the case the deploy VPS actually hits: the deploy
    user is not in the 'docker' group, so unqualified 'docker ...' fails outright)."""
    fake_docker = bin_dir / "docker"
    fake_docker.write_text(
        "#!/usr/bin/env bash\n"
        "echo 'permission denied while trying to connect to the Docker daemon socket' >&2\n"
        "exit 1\n"
    )
    fake_docker.chmod(0o755)


def shlex_quote(s: str) -> str:
    import shlex

    return shlex.quote(s)


def _run_backup_db(bin_dir: Path, backup_dir: Path, extra_env: dict) -> subprocess.CompletedProcess:
    env = os.environ.copy()
    env["PATH"] = str(bin_dir) + ":" + env.get("PATH", "")
    env["BACKUP_DIR"] = str(backup_dir)
    env.setdefault("POSTGRES_USER", "sq")
    env.setdefault("POSTGRES_DB", "smartquotation")
    env.update(extra_env)
    return subprocess.run(
        ["bash", str(BACKUP_SCRIPT)], env=env, capture_output=True, text=True
    )


def test_backup_script_rejects_the_wrong_port_gotcha_empty_dump():
    """Reproduce the exact known gotcha: dump 'succeeds' (exit 0) but is ~20 bytes.

    This is the scenario documented in docs/HANDOFF_MIGRACAO.md §4 and the
    deploy-prod-gotchas memory: pg_dumpall against the wrong port fails silently,
    the pipe to gzip still exits 0, and a naive script would happily rename the
    near-empty file into a "successful" backup. The fixed script must reject it.
    """
    with tempfile.TemporaryDirectory() as bin_dir, tempfile.TemporaryDirectory() as backup_dir:
        # ~20 bytes of "output", exit code 0 — exactly the gotcha.
        _make_fake_docker(Path(bin_dir), inspect_ok=True, payload="x" * 20, exec_exit=0)

        result = _run_backup_db(Path(bin_dir), Path(backup_dir), {"DB_CONTAINER": "sq-prod-db"})

        assert result.returncode != 0, (
            "backup_db.sh must exit non-zero when the dump is suspiciously small, "
            f"even though the underlying command exited 0. stdout={result.stdout!r} "
            f"stderr={result.stderr!r}"
        )
        leftover = list(Path(backup_dir).glob("*.sql.gz"))
        assert not leftover, (
            f"backup_db.sh must NOT leave a .sql.gz behind for a rejected (too-small) "
            f"dump. Found: {[str(f) for f in leftover]}"
        )
        tmp_leftover = list(Path(backup_dir).glob("*.tmp"))
        assert not tmp_leftover, "backup_db.sh must clean up the temp file when validation fails"


def test_backup_script_accepts_a_realistic_dump():
    """A dump that is large enough and mentions the expected tenant must be accepted."""
    with tempfile.TemporaryDirectory() as bin_dir, tempfile.TemporaryDirectory() as backup_dir:
        payload = "\n".join(
            f"-- dump line {i} schema engematex data" for i in range(200)
        )
        _make_fake_docker(Path(bin_dir), inspect_ok=True, payload=payload, exec_exit=0)

        result = _run_backup_db(Path(bin_dir), Path(backup_dir), {"DB_CONTAINER": "sq-prod-db"})

        assert result.returncode == 0, (
            f"backup_db.sh must accept a realistic dump. stdout={result.stdout!r} "
            f"stderr={result.stderr!r}"
        )
        final_files = list(Path(backup_dir).glob("*.sql.gz"))
        assert final_files, "backup_db.sh must produce a .sql.gz file for a valid dump"


def test_backup_script_container_mode_used_when_container_exists():
    """When DB_CONTAINER exists (docker inspect succeeds), auto mode must use 'docker exec'."""
    with tempfile.TemporaryDirectory() as bin_dir, tempfile.TemporaryDirectory() as backup_dir:
        payload = "\n".join(f"-- container dump {i} engematex" for i in range(200))
        _make_fake_docker(Path(bin_dir), inspect_ok=True, payload=payload, exec_exit=0)

        result = _run_backup_db(Path(bin_dir), Path(backup_dir), {"DB_CONTAINER": "sq-prod-db"})

        assert result.returncode == 0, result.stderr
        final_files = list(Path(backup_dir).glob("*.sql.gz"))
        assert final_files, "backup_db.sh must produce a .sql.gz using the container path"


def test_backup_script_falls_back_to_compose_when_container_absent():
    """When DB_CONTAINER does not exist, auto mode must fall back to docker compose."""
    with tempfile.TemporaryDirectory() as bin_dir, tempfile.TemporaryDirectory() as backup_dir:
        payload = "\n".join(f"-- compose dump {i} engematex" for i in range(200))
        _make_fake_docker(Path(bin_dir), inspect_ok=False, payload=payload, exec_exit=0)

        result = _run_backup_db(Path(bin_dir), Path(backup_dir), {})

        assert result.returncode == 0, result.stderr
        final_files = list(Path(backup_dir).glob("*.sql.gz"))
        assert final_files, "backup_db.sh must fall back to the compose path and still succeed"


def test_backup_script_fails_fast_when_docker_is_inaccessible():
    """Docker inaccessible (permission/daemon) must NOT be mistaken for 'container absent'.

    This is the case that matters on the real deploy VPS: the deploy user is not in
    the 'docker' group, so 'docker inspect sq-prod-db' fails with a permission error
    — not because the container is missing. If the script treated that failure as
    'container absent' it would silently fall back to the compose path, which fails
    for the exact same underlying reason (docker inaccessible), but with a confusing
    error that talks about compose instead of the real problem (docker access). The
    script must probe docker usability first and fail immediately with a specific,
    actionable message instead of degrading to compose.
    """
    with tempfile.TemporaryDirectory() as bin_dir, tempfile.TemporaryDirectory() as backup_dir:
        _make_inaccessible_docker(Path(bin_dir))

        result = _run_backup_db(Path(bin_dir), Path(backup_dir), {"DB_CONTAINER": "sq-prod-db"})

        assert result.returncode != 0, (
            "backup_db.sh must exit non-zero when docker itself is inaccessible. "
            f"stdout={result.stdout!r} stderr={result.stderr!r}"
        )
        stderr_lower = result.stderr.lower()
        assert "docker" in stderr_lower, (
            f"error message must mention docker/permission, not just fail silently. "
            f"stderr={result.stderr!r}"
        )
        assert "permiss" in stderr_lower or "inacess" in stderr_lower or "grupo" in stderr_lower, (
            f"error message must point at the real cause (docker access), not compose. "
            f"stderr={result.stderr!r}"
        )
        assert "compose" not in result.stderr.lower(), (
            "backup_db.sh must NOT talk about docker compose when the real problem is "
            f"docker being inaccessible — that would mislead the operator at 3am. "
            f"stderr={result.stderr!r}"
        )
        leftover = list(Path(backup_dir).glob("*.sql.gz")) + list(Path(backup_dir).glob("*.tmp"))
        assert not leftover, (
            f"backup_db.sh must not leave any file behind when it fails fast. "
            f"Found: {[str(f) for f in leftover]}"
        )


def test_backup_script_announces_auto_detected_mode_on_stderr():
    """Auto mode must log WHICH mode it picked and why — silent auto-detection is
    hard to debug from a cron log at 3am."""
    with tempfile.TemporaryDirectory() as bin_dir, tempfile.TemporaryDirectory() as backup_dir:
        payload = "\n".join(f"-- dump line {i} engematex" for i in range(200))
        _make_fake_docker(Path(bin_dir), inspect_ok=True, payload=payload, exec_exit=0)

        result = _run_backup_db(Path(bin_dir), Path(backup_dir), {"DB_CONTAINER": "sq-prod-db"})

        assert result.returncode == 0, result.stderr
        assert "modo=container" in result.stderr or "modo = container" in result.stderr, (
            f"backup_db.sh must announce the auto-detected mode on stderr. stderr={result.stderr!r}"
        )


if __name__ == "__main__":
    tests = [
        test_backup_script_exists,
        test_backup_script_is_executable,
        test_backup_script_contains_pg_dump,
        test_env_prod_example_has_backup_dir,
        test_backup_script_supports_both_compose_and_standalone_container,
        test_backup_script_mode_detection_is_overridable,
        test_backup_script_has_set_u,
        test_cron_entry_sources_env_prod,
        test_infrastructure_doc_sources_env_with_allexport,
        test_sourced_env_without_allexport_does_not_reach_child,
        test_backup_script_validates_dump_content_not_just_exit_code,
        test_backup_script_rejects_the_wrong_port_gotcha_empty_dump,
        test_backup_script_accepts_a_realistic_dump,
        test_backup_script_container_mode_used_when_container_exists,
        test_backup_script_falls_back_to_compose_when_container_absent,
        test_backup_script_fails_fast_when_docker_is_inaccessible,
        test_backup_script_announces_auto_detected_mode_on_stderr,
    ]
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
