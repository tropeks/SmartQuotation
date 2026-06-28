"""
Tests: scripts/backup_db.sh exists and is executable.
"""
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BACKUP_SCRIPT = ROOT / "scripts" / "backup_db.sh"
ENV_PROD_EXAMPLE = ROOT / ".env.prod.example"


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


if __name__ == "__main__":
    tests = [
        test_backup_script_exists,
        test_backup_script_is_executable,
        test_backup_script_contains_pg_dump,
        test_env_prod_example_has_backup_dir,
        test_backup_script_uses_compose_exec_not_hardcoded_container,
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
