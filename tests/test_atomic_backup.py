"""
Tests: backup scripts must use atomic writes (temp file + mv on success).

If pg_dump, tar, gzip, or docker compose exec fails mid-stream, the script
must NOT leave a partial .sql.gz / .tar.gz with a valid-looking filename.
The fix is the standard atomic-write pattern:
  1. Write to FINAL.tmp
  2. On success: mv FINAL.tmp FINAL
  3. On failure (trap): rm -f FINAL.tmp
"""
import subprocess
import sys
import os
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BACKUP_DB_SCRIPT = ROOT / "scripts" / "backup_db.sh"
BACKUP_MEDIA_SCRIPT = ROOT / "scripts" / "backup_media.sh"


# ---------------------------------------------------------------------------
# Static analysis: verify the atomic-write pattern is present in each script
# ---------------------------------------------------------------------------

def test_backup_db_uses_temp_file():
    """backup_db.sh must write to a temp file, not directly to the final filename.

    Without this, a failed pg_dump leaves a .sql.gz with bytes 0..N that looks
    valid but is truncated and unrestorable.
    """
    text = BACKUP_DB_SCRIPT.read_text()
    has_tmp = ".tmp" in text or "TMPFILE" in text or "tmp_file" in text or "TMP" in text
    assert has_tmp, (
        "backup_db.sh must write to a temporary file (e.g. FINAL.tmp) and rename "
        "only on success. Currently it writes directly to the final .sql.gz, so a "
        "failed pg_dump leaves a corrupt file with a valid-looking name."
    )


def test_backup_db_renames_on_success():
    """backup_db.sh must move the temp file to the final name on success (mv)."""
    text = BACKUP_DB_SCRIPT.read_text()
    assert "mv " in text or "mv\t" in text, (
        "backup_db.sh must use 'mv' to rename the temp file to the final .sql.gz "
        "name only after pg_dump completes successfully."
    )


def test_backup_db_cleans_up_on_failure():
    """backup_db.sh must clean up the temp file when the dump fails.

    A trap (or equivalent error handler) must remove the .tmp file so that a
    failed backup does not leave a partial file on disk.
    """
    text = BACKUP_DB_SCRIPT.read_text()
    assert "trap " in text, (
        "backup_db.sh must use 'trap' to remove the temp file if pg_dump fails. "
        "Without this, a partial .tmp file is left on disk after a failure."
    )


def test_backup_media_uses_temp_file():
    """backup_media.sh must write to a temp file, not directly to the final filename."""
    text = BACKUP_MEDIA_SCRIPT.read_text()
    has_tmp = ".tmp" in text or "TMPFILE" in text or "tmp_file" in text or "TMP" in text
    assert has_tmp, (
        "backup_media.sh must write to a temporary file (e.g. FINAL.tmp) and rename "
        "only on success. Currently it writes directly to the final .tar.gz, so a "
        "failed tar/docker exec leaves a corrupt file with a valid-looking name."
    )


def test_backup_media_renames_on_success():
    """backup_media.sh must move the temp file to the final name on success (mv)."""
    text = BACKUP_MEDIA_SCRIPT.read_text()
    assert "mv " in text or "mv\t" in text, (
        "backup_media.sh must use 'mv' to rename the temp file to the final .tar.gz "
        "name only after the archive completes successfully."
    )


def test_backup_media_cleans_up_on_failure():
    """backup_media.sh must clean up the temp file when archiving fails."""
    text = BACKUP_MEDIA_SCRIPT.read_text()
    assert "trap " in text, (
        "backup_media.sh must use 'trap' to remove the temp file if tar/docker fails. "
        "Without this, a partial .tmp file is left on disk after a failure."
    )


# ---------------------------------------------------------------------------
# Behavioural: run the script with a mock docker that fails, confirm no
# partial backup file remains and no final file was created.
# ---------------------------------------------------------------------------

def _make_failing_docker(tmpdir: Path) -> str:
    """Create a fake 'docker' binary on PATH that writes partial data then exits 1."""
    fake_docker = tmpdir / "docker"
    fake_docker.write_text(
        "#!/usr/bin/env bash\n"
        "# Simulate pg_dump/tar writing partial data then failing\n"
        "printf 'partial'\n"  # some output
        "exit 1\n"
    )
    fake_docker.chmod(0o755)
    return str(tmpdir)


def _make_succeeding_docker(tmpdir: Path) -> str:
    """Create a fake 'docker' binary that writes a minimal valid payload and exits 0."""
    fake_docker = tmpdir / "docker"
    fake_docker.write_text(
        "#!/usr/bin/env bash\n"
        "printf 'OK'\n"
        "exit 0\n"
    )
    fake_docker.chmod(0o755)
    return str(tmpdir)


def test_backup_db_no_partial_file_on_failure():
    """If docker/pg_dump fails, backup_db.sh must leave no .sql.gz file behind."""
    with tempfile.TemporaryDirectory() as fake_bin_dir, \
         tempfile.TemporaryDirectory() as backup_dir:

        _make_failing_docker(Path(fake_bin_dir))

        env = os.environ.copy()
        env["PATH"] = fake_bin_dir + ":" + env.get("PATH", "")
        env["BACKUP_DIR"] = backup_dir
        env["POSTGRES_USER"] = "testuser"
        env["POSTGRES_DB"] = "testdb"
        env["COMPOSE_FILE"] = "docker-compose.prod.yml"

        result = subprocess.run(
            ["bash", str(BACKUP_DB_SCRIPT)],
            env=env,
            capture_output=True,
            text=True,
        )

        assert result.returncode != 0, (
            "backup_db.sh must exit non-zero when docker/pg_dump fails. "
            f"stdout={result.stdout!r} stderr={result.stderr!r}"
        )

        leftover = list(Path(backup_dir).glob("*.sql.gz"))
        assert not leftover, (
            f"backup_db.sh must NOT leave a .sql.gz file when pg_dump fails. "
            f"Found: {[str(f) for f in leftover]}"
        )

        tmp_leftover = list(Path(backup_dir).glob("*.tmp"))
        assert not tmp_leftover, (
            f"backup_db.sh must clean up temp files on failure. "
            f"Found: {[str(f) for f in tmp_leftover]}"
        )


def test_backup_db_final_file_exists_on_success():
    """If docker/pg_dump succeeds, backup_db.sh must produce a .sql.gz file."""
    with tempfile.TemporaryDirectory() as fake_bin_dir, \
         tempfile.TemporaryDirectory() as backup_dir:

        _make_succeeding_docker(Path(fake_bin_dir))

        env = os.environ.copy()
        env["PATH"] = fake_bin_dir + ":" + env.get("PATH", "")
        env["BACKUP_DIR"] = backup_dir
        env["POSTGRES_USER"] = "testuser"
        env["POSTGRES_DB"] = "testdb"
        env["COMPOSE_FILE"] = "docker-compose.prod.yml"

        result = subprocess.run(
            ["bash", str(BACKUP_DB_SCRIPT)],
            env=env,
            capture_output=True,
            text=True,
        )

        assert result.returncode == 0, (
            f"backup_db.sh must exit 0 on success. "
            f"stdout={result.stdout!r} stderr={result.stderr!r}"
        )

        final_files = list(Path(backup_dir).glob("*.sql.gz"))
        assert final_files, (
            "backup_db.sh must produce a .sql.gz file on success. "
            f"backup_dir contents: {list(Path(backup_dir).iterdir())}"
        )

        no_tmp = list(Path(backup_dir).glob("*.tmp"))
        assert not no_tmp, (
            f"backup_db.sh must not leave .tmp files after a successful run. "
            f"Found: {[str(f) for f in no_tmp]}"
        )


def test_backup_media_no_partial_file_on_failure():
    """If docker/tar fails, backup_media.sh must leave no .tar.gz file behind."""
    with tempfile.TemporaryDirectory() as fake_bin_dir, \
         tempfile.TemporaryDirectory() as backup_dir:

        _make_failing_docker(Path(fake_bin_dir))

        env = os.environ.copy()
        env["PATH"] = fake_bin_dir + ":" + env.get("PATH", "")
        env["BACKUP_DIR"] = backup_dir
        env["COMPOSE_FILE"] = "docker-compose.prod.yml"

        result = subprocess.run(
            ["bash", str(BACKUP_MEDIA_SCRIPT)],
            env=env,
            capture_output=True,
            text=True,
        )

        assert result.returncode != 0, (
            "backup_media.sh must exit non-zero when docker/tar fails. "
            f"stdout={result.stdout!r} stderr={result.stderr!r}"
        )

        leftover = list(Path(backup_dir).glob("*.tar.gz"))
        assert not leftover, (
            f"backup_media.sh must NOT leave a .tar.gz file when tar/docker fails. "
            f"Found: {[str(f) for f in leftover]}"
        )

        tmp_leftover = list(Path(backup_dir).glob("*.tmp"))
        assert not tmp_leftover, (
            f"backup_media.sh must clean up temp files on failure. "
            f"Found: {[str(f) for f in tmp_leftover]}"
        )


def test_backup_media_final_file_exists_on_success():
    """If docker/tar succeeds, backup_media.sh must produce a .tar.gz file."""
    with tempfile.TemporaryDirectory() as fake_bin_dir, \
         tempfile.TemporaryDirectory() as backup_dir:

        _make_succeeding_docker(Path(fake_bin_dir))

        env = os.environ.copy()
        env["PATH"] = fake_bin_dir + ":" + env.get("PATH", "")
        env["BACKUP_DIR"] = backup_dir
        env["COMPOSE_FILE"] = "docker-compose.prod.yml"

        result = subprocess.run(
            ["bash", str(BACKUP_MEDIA_SCRIPT)],
            env=env,
            capture_output=True,
            text=True,
        )

        assert result.returncode == 0, (
            f"backup_media.sh must exit 0 on success. "
            f"stdout={result.stdout!r} stderr={result.stderr!r}"
        )

        final_files = list(Path(backup_dir).glob("*.tar.gz"))
        assert final_files, (
            "backup_media.sh must produce a .tar.gz file on success. "
            f"backup_dir contents: {list(Path(backup_dir).iterdir())}"
        )

        no_tmp = list(Path(backup_dir).glob("*.tmp"))
        assert not no_tmp, (
            f"backup_media.sh must not leave .tmp files after a successful run. "
            f"Found: {[str(f) for f in no_tmp]}"
        )


if __name__ == "__main__":
    tests = [
        test_backup_db_uses_temp_file,
        test_backup_db_renames_on_success,
        test_backup_db_cleans_up_on_failure,
        test_backup_media_uses_temp_file,
        test_backup_media_renames_on_success,
        test_backup_media_cleans_up_on_failure,
        test_backup_db_no_partial_file_on_failure,
        test_backup_db_final_file_exists_on_success,
        test_backup_media_no_partial_file_on_failure,
        test_backup_media_final_file_exists_on_success,
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
