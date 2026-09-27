"""
Tests: media backup script and INFRASTRUCTURE.md consistency.

After media was moved to media_data:/app/backend/media, the old backup
strategy referenced /data/uploads. These tests enforce that:
  1. scripts/backup_media.sh exists and backs up the correct volume/path.
  2. INFRASTRUCTURE.md restore runbook uses the correct media path.
  3. The backup strategy docs no longer reference the obsolete /data/uploads path
     in the context of media backups.
"""
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BACKUP_MEDIA_SCRIPT = ROOT / "scripts" / "backup_media.sh"
INFRA_DOC = ROOT / "docs" / "INFRASTRUCTURE.md"

MEDIA_PATH = "/app/backend/media"
VOLUME_NAME = "media_data"
OLD_UPLOADS_PATH = "/data/uploads"


def test_backup_media_script_exists():
    assert BACKUP_MEDIA_SCRIPT.exists(), (
        f"scripts/backup_media.sh must exist at {BACKUP_MEDIA_SCRIPT}. "
        f"backup_db.sh only backs up the database; a separate script is needed "
        f"to backup PDFs/DOCX stored in {VOLUME_NAME}:{MEDIA_PATH}."
    )


def test_backup_media_script_is_executable():
    assert BACKUP_MEDIA_SCRIPT.exists(), f"scripts/backup_media.sh must exist"
    assert os.access(BACKUP_MEDIA_SCRIPT, os.X_OK), (
        "scripts/backup_media.sh must be executable (chmod +x)"
    )


def test_backup_media_script_references_media_path():
    """Script must reference /app/backend/media (the actual container path)."""
    assert BACKUP_MEDIA_SCRIPT.exists(), "scripts/backup_media.sh must exist"
    text = BACKUP_MEDIA_SCRIPT.read_text()
    assert MEDIA_PATH in text, (
        f"backup_media.sh must reference {MEDIA_PATH!r} — the path where "
        f"media_data volume is mounted inside the container."
    )


def test_backup_media_script_uses_docker_compose():
    """Script must use 'docker compose' (not a hardcoded container name)."""
    assert BACKUP_MEDIA_SCRIPT.exists(), "scripts/backup_media.sh must exist"
    text = BACKUP_MEDIA_SCRIPT.read_text()
    assert "docker compose" in text or "docker-compose" in text, (
        "backup_media.sh must use 'docker compose' to reference services by name, "
        "not a hardcoded container name that breaks when COMPOSE_PROJECT_NAME changes."
    )


def test_backup_media_script_has_set_u():
    """Script must use set -u so unbound vars cause a loud failure."""
    assert BACKUP_MEDIA_SCRIPT.exists(), "scripts/backup_media.sh must exist"
    text = BACKUP_MEDIA_SCRIPT.read_text()
    has_set_u = "set -u" in text or "set -euo pipefail" in text or "set -eu" in text
    assert has_set_u, (
        "backup_media.sh must use 'set -u' (or 'set -euo pipefail') so that "
        "missing env vars fail loudly instead of silently producing bad backups."
    )


def test_backup_media_script_produces_compressed_archive():
    """Script must produce a compressed archive (tar.gz or similar)."""
    assert BACKUP_MEDIA_SCRIPT.exists(), "scripts/backup_media.sh must exist"
    text = BACKUP_MEDIA_SCRIPT.read_text()
    has_compression = "gzip" in text or "tar" in text or ".tar.gz" in text or ".tgz" in text
    assert has_compression, (
        "backup_media.sh must compress the backup (tar+gzip or equivalent). "
        "Uncompressed media backups waste disk space and slow off-site sync."
    )


def test_infrastructure_doc_restore_uses_media_path():
    """INFRASTRUCTURE.md restore procedure must reference media_data or /app/backend/media.

    After the volume rename (uploads→media_data, /data/uploads→/app/backend/media),
    the old restore steps are wrong: they rsync to /data/uploads which no longer
    exists in docker-compose.prod.yml.
    """
    text = INFRA_DOC.read_text()
    # Restore section should mention the new media path or the volume name
    assert MEDIA_PATH in text or VOLUME_NAME in text, (
        f"INFRASTRUCTURE.md must reference {MEDIA_PATH!r} or {VOLUME_NAME!r} in the "
        f"restore runbook. The old /data/uploads path is gone from docker-compose.prod.yml."
    )


def test_infrastructure_doc_backup_uses_media_data_volume():
    """INFRASTRUCTURE.md backup strategy must document media_data volume backup.

    backup_db.sh only dumps the database. The strategy section must show how
    to backup the media_data volume (PDFs/DOCX produced by proposals).
    """
    text = INFRA_DOC.read_text()
    assert VOLUME_NAME in text or "backup_media" in text, (
        f"INFRASTRUCTURE.md backup strategy must document {VOLUME_NAME!r} backup "
        f"or reference backup_media.sh. Without this, proposals (PDF/DOCX) are "
        f"silently excluded from the backup."
    )


def test_infrastructure_restore_does_not_use_old_uploads_path():
    """Restore runbook must not instruct restoring to /data/uploads.

    /data/uploads does not appear in docker-compose.prod.yml anymore; restoring
    there would silently lose all media because the app reads from /app/backend/media.
    """
    text = INFRA_DOC.read_text()
    lines = text.splitlines()
    # Look for rsync restore lines that still target /data/uploads
    restore_to_old_path = [
        l for l in lines
        if OLD_UPLOADS_PATH in l and ("rsync" in l or "restore" in l.lower() or "cp " in l)
    ]
    assert not restore_to_old_path, (
        f"INFRASTRUCTURE.md restore runbook must not reference {OLD_UPLOADS_PATH!r} "
        f"as a restore destination. Found problematic lines:\n"
        + "\n".join(restore_to_old_path)
    )


# ---------------------------------------------------------------------------
# Comportamento (ordem 002): container avulso sq-web-proto, validação por conteúdo,
# umask 077, retenção. Docker FALSO (tests/_ops_fakes.py).
# ---------------------------------------------------------------------------

def _media_env():
    import tempfile
    from tests._ops_fakes import FakeEnv
    tmp = tempfile.TemporaryDirectory()
    fk = FakeEnv(Path(tmp.name))
    bdir = Path(tmp.name) / "backups"
    fk.env["BACKUP_DIR"] = str(bdir)
    return tmp, fk, bdir


def test_media_container_mode_produces_validated_0600_archive():
    import stat
    import tarfile
    tmp, fk, bdir = _media_env()
    with tmp:
        fk.add_media_file("proposals/2026/COT-SINT-0001.pdf")
        r = fk.run("backup_media.sh")
        assert r.returncode == 0, r.stderr
        assert "modo=container" in r.stderr, r.stderr
        calls = fk.docker_calls()
        assert any(c.startswith("exec sq-web-proto tar czf - -C / app/backend/media") for c in calls), calls
        files = sorted(bdir.glob("media_*.tar.gz"))
        assert len(files) == 1, files
        assert stat.S_IMODE(files[0].stat().st_mode) == 0o600
        with tarfile.open(files[0]) as tf:
            assert "app/backend/media/proposals/2026/COT-SINT-0001.pdf" in tf.getnames()
        status = (bdir / "media_last_success").read_text()
        assert f"file={files[0].name}" in status and "entries=" in status, status


def test_media_empty_dir_rejected_unless_explicitly_allowed():
    tmp, fk, bdir = _media_env()
    with tmp:
        r = fk.run("backup_media.sh")
        assert r.returncode != 0 and "vazio" in r.stderr, r.stderr
        assert not list(bdir.glob("media_*")), list(bdir.iterdir())
        r = fk.run("backup_media.sh", {"MEDIA_ALLOW_EMPTY": "1"})
        assert r.returncode == 0, r.stderr
        assert len(list(bdir.glob("media_*.tar.gz"))) == 1


def test_media_garbage_archive_is_rejected():
    tmp, fk, bdir = _media_env()
    with tmp:
        # "tar" que sai 0 mas devolve lixo (não-gzip): exit code não é prova de nada.
        (fk.ctr_bin / "tar").write_text("#!/usr/bin/env bash\nprintf 'nao sou um tar'\nexit 0\n")
        r = fk.run("backup_media.sh", {"MEDIA_ALLOW_EMPTY": "1"})
        assert r.returncode != 0, r.stderr
        assert not list(bdir.glob("media_*")), list(bdir.iterdir())


def test_media_stopped_container_and_inaccessible_docker_fail_fast():
    tmp, fk, bdir = _media_env()
    with tmp:
        fk.add_media_file("a.pdf")
        r = fk.run("backup_media.sh", {"FAKE_STATE": "false"})
        assert r.returncode != 0 and "PARADO" in r.stderr, r.stderr
        r = fk.run("backup_media.sh", {"FAKE_INFO_OK": "0"})
        assert r.returncode != 0 and "inacess" in r.stderr and "compose" not in r.stderr, r.stderr
        assert not list(bdir.glob("media_*")), list(bdir.iterdir())


def test_media_retention_prunes_only_old_media_after_success():
    import os
    import time
    tmp, fk, bdir = _media_env()
    with tmp:
        bdir.mkdir(parents=True)
        old = bdir / "media_20200101_030000.tar.gz"
        db_old = bdir / "sq_20200101_030000.sql.gz"
        for p in (old, db_old):
            p.write_bytes(b"x")
            t = time.time() - 40 * 86400
            os.utime(p, (t, t))
        r = fk.run("backup_media.sh")  # vazio → falha → não poda
        assert r.returncode != 0 and old.exists()
        fk.add_media_file("a.pdf")
        r = fk.run("backup_media.sh")
        assert r.returncode == 0, r.stderr
        assert not old.exists() and db_old.exists()


def test_media_large_listing_does_not_false_fail():
    """>2000 entradas (listagem bem acima dos 64 KiB do pipe): grep -q saindo cedo não pode
    matar o produtor com SIGPIPE e virar vermelho falso sob pipefail."""
    tmp, fk, bdir = _media_env()
    with tmp:
        for i in range(2500):
            fk.add_media_file(f"proposals/2026/COT-SINT-{i:06d}-proposta-tecnica-comercial.pdf", b"%PDF")
        r = fk.run("backup_media.sh")
        assert r.returncode == 0, r.stderr
        status = (bdir / "media_last_success").read_text()
        assert "entries=2502" in status, status  # 2500 arquivos + proposals/ + proposals/2026/
        assert not list(bdir.glob("*.tmp*")), list(bdir.iterdir())


def _tar_exiting_with(fk, code: int) -> None:
    real = fk.ctr_bin / "tar.real"
    (fk.ctr_bin / "tar").rename(real)
    (fk.ctr_bin / "tar").write_text(f'#!/usr/bin/env bash\n"{real}" "$@"\nexit {code}\n')
    (fk.ctr_bin / "tar").chmod(0o755)


def test_media_tar_exit_1_is_a_warning_validated_by_content():
    """GNU tar sai 1 em "file changed as we read it" (mídia sendo gravada durante o backup):
    é aviso — quem decide é a validação por conteúdo que vem depois."""
    tmp, fk, bdir = _media_env()
    with tmp:
        fk.add_media_file("a.pdf")
        _tar_exiting_with(fk, 1)
        r = fk.run("backup_media.sh")
        assert r.returncode == 0, r.stderr
        assert "aviso" in r.stderr.lower(), r.stderr
        assert len(list(bdir.glob("media_*.tar.gz"))) == 1


def test_media_tar_exit_above_1_is_a_failure():
    tmp, fk, bdir = _media_env()
    with tmp:
        fk.add_media_file("a.pdf")
        _tar_exiting_with(fk, 2)
        r = fk.run("backup_media.sh")
        assert r.returncode != 0, r.stderr
        assert not list(bdir.glob("media_*")), list(bdir.iterdir())


if __name__ == "__main__":
    tests = [
        test_backup_media_script_exists,
        test_backup_media_script_is_executable,
        test_backup_media_script_references_media_path,
        test_backup_media_script_uses_docker_compose,
        test_backup_media_script_has_set_u,
        test_backup_media_script_produces_compressed_archive,
        test_infrastructure_doc_restore_uses_media_path,
        test_infrastructure_doc_backup_uses_media_data_volume,
        test_infrastructure_restore_does_not_use_old_uploads_path,
        test_media_container_mode_produces_validated_0600_archive,
        test_media_empty_dir_rejected_unless_explicitly_allowed,
        test_media_garbage_archive_is_rejected,
        test_media_stopped_container_and_inaccessible_docker_fail_fast,
        test_media_retention_prunes_only_old_media_after_success,
        test_media_large_listing_does_not_false_fail,
        test_media_tar_exit_1_is_a_warning_validated_by_content,
        test_media_tar_exit_above_1_is_a_failure,
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
