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
