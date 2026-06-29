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


def test_backup_script_uses_compose_exec_not_hardcoded_container():
    """Script must use 'docker compose exec' (service name) not a hardcoded container name."""
    text = BACKUP_SCRIPT.read_text()
    assert "docker exec" not in text, (
        "backup_db.sh must not use 'docker exec' with a hardcoded container name; "
        "use 'docker compose exec' so COMPOSE_PROJECT_NAME changes don't break it silently"
    )
    assert "docker compose" in text or "docker-compose" in text, (
        "backup_db.sh must use 'docker compose exec' to reference the db service by name"
    )
    assert "exec" in text, (
        "backup_db.sh must use 'docker compose exec' to reference the db service by name"
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


if __name__ == "__main__":
    tests = [
        test_backup_script_exists,
        test_backup_script_is_executable,
        test_backup_script_contains_pg_dump,
        test_env_prod_example_has_backup_dir,
        test_backup_script_uses_compose_exec_not_hardcoded_container,
        test_backup_script_has_set_u,
        test_cron_entry_sources_env_prod,
        test_infrastructure_doc_sources_env_with_allexport,
        test_sourced_env_without_allexport_does_not_reach_child,
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
