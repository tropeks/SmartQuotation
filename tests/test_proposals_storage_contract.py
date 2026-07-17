"""
Tests: proposals service and views correctly route all file I/O through default_storage.

The proposals app generates DOCX/PDF files and serves them for download.  All file
operations must go through Django's `default_storage` abstraction so that swapping
from FileSystemStorage to S3Boto3Storage (USE_S3=True) requires zero code changes.

These tests are static-analysis only — they parse source files without importing
Django — so they run in the ops-tests job without a database or full Django stack.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SERVICES_PY = ROOT / "backend" / "apps" / "proposals" / "services.py"
VIEWS_PY = ROOT / "backend" / "apps" / "proposals" / "views.py"
PRODUCTION_PY = ROOT / "backend" / "smartquotation" / "settings" / "production.py"
DOCKERIGNORE = ROOT / ".dockerignore"
DOCKERFILE = ROOT / "backend" / "Dockerfile"
COMPOSE_PROD = ROOT / "docker-compose.prod.yml"


def _text(path: Path) -> str:
    assert path.exists(), f"Expected file not found: {path}"
    return path.read_text()


# ──── services.py contract ───────────────────────────────────────────────────

def test_services_imports_default_storage():
    """services.py must import default_storage (not use direct filesystem I/O)."""
    text = _text(SERVICES_PY)
    assert "default_storage" in text, (
        "proposals/services.py must import and use default_storage. "
        "Removing it breaks S3-configured deployments silently."
    )


def test_services_save_uses_default_storage():
    """The internal save helper must call default_storage.save, not open(..., 'wb')."""
    text = _text(SERVICES_PY)
    assert "default_storage.save" in text, (
        "proposals/services.py must call default_storage.save() to persist generated "
        "files. Direct open(..., 'wb') writes bypass the storage backend and break S3."
    )


def test_services_read_uses_default_storage():
    """SHA-256 hashing and any file reads must go through default_storage.open."""
    text = _text(SERVICES_PY)
    assert "default_storage.open" in text, (
        "proposals/services.py must use default_storage.open() for reading stored files "
        "(e.g. SHA-256 computation). Direct open() calls bypass the storage backend."
    )


def test_services_no_direct_media_root_write():
    """services.py must NOT construct file paths from MEDIA_ROOT for writing."""
    text = _text(SERVICES_PY)
    # Constructing paths like open(os.path.join(settings.MEDIA_ROOT, ...)) for writing
    # bypasses the storage abstraction.  Writing temp files is fine (tempfile.*), but
    # the final persist must go through default_storage.save.
    has_media_root_write = "MEDIA_ROOT" in text and any(
        pat in text
        for pat in (
            "open(os.path.join",
            'open(f"{settings.MEDIA_ROOT',
            "open(settings.MEDIA_ROOT",
        )
    )
    assert not has_media_root_write, (
        "proposals/services.py must not build file paths from settings.MEDIA_ROOT for "
        "writing. Use default_storage.save() so S3 and filesystem storage both work."
    )


def test_services_generate_docx_exists():
    """generate_docx function must exist in services.py."""
    text = _text(SERVICES_PY)
    assert "def generate_docx" in text, (
        "proposals/services.py must define generate_docx(). "
        "Renaming or removing it breaks the proposal generation flow."
    )


def test_services_generate_exists():
    """generate function must exist in services.py."""
    text = _text(SERVICES_PY)
    assert "def generate(" in text, (
        "proposals/services.py must define generate(). "
        "This is the entry point that calls generate_docx + generate_pdf and saves hashes."
    )


def test_services_generate_saves_storage_names():
    """generate() must persist storage names (docx_path, pdf_path) and hashes."""
    text = _text(SERVICES_PY)
    assert "docx_path" in text and "pdf_path" in text, (
        "proposals/services.py generate() must save docx_path and pdf_path on the Proposal "
        "model. These are storage-relative names used by proposal_download."
    )
    assert "docx_sha256" in text and "pdf_sha256" in text, (
        "proposals/services.py generate() must save sha256 hashes for integrity verification."
    )


# ──── views.py contract ──────────────────────────────────────────────────────

def test_views_imports_default_storage():
    """views.py must import default_storage for the download view."""
    text = _text(VIEWS_PY)
    assert "default_storage" in text, (
        "proposals/views.py must import and use default_storage. "
        "Using open() directly breaks S3-backed deployments."
    )


def test_views_download_uses_default_storage_open():
    """proposal_download must open files via default_storage.open, not open()."""
    text = _text(VIEWS_PY)
    assert "default_storage.open" in text, (
        "proposals/views.py must use default_storage.open() to serve downloads. "
        "A bare open() call reads from the local filesystem and fails with S3 storage."
    )


def test_views_download_checks_default_storage_exists():
    """proposal_download must check file existence via default_storage.exists."""
    text = _text(VIEWS_PY)
    assert "default_storage.exists" in text, (
        "proposals/views.py must use default_storage.exists() to verify the file is present "
        "before serving it. Using os.path.exists() fails in S3-backed deployments."
    )


def test_views_no_os_path_open_for_download():
    """proposal_download must not use os.path.join(MEDIA_ROOT, ...) to locate files."""
    text = _text(VIEWS_PY)
    has_media_root_open = "MEDIA_ROOT" in text and any(
        pat in text
        for pat in ("open(os.path.join", "open(settings.MEDIA_ROOT")
    )
    assert not has_media_root_open, (
        "proposals/views.py must not build download paths from settings.MEDIA_ROOT. "
        "Use default_storage.exists/open so S3 and filesystem storage both work."
    )


# ──── production.py storage config ──────────────────────────────────────────

def test_production_storages_dict_has_default():
    """production.py must define STORAGES dict with a 'default' key."""
    text = _text(PRODUCTION_PY)
    assert "STORAGES" in text, (
        "production.py must define the STORAGES dict. Without it Django falls back to "
        "a bare FileSystemStorage with no S3 option."
    )
    assert '"default"' in text or "'default'" in text, (
        "STORAGES dict must include a 'default' key for the proposals storage backend."
    )


def test_production_s3boto3_storage_referenced():
    """production.py must reference S3Boto3Storage as the S3 backend option."""
    text = _text(PRODUCTION_PY)
    assert "S3Boto3Storage" in text, (
        "production.py must reference S3Boto3Storage so the USE_S3 flag actually switches "
        "to S3. Without this import path, USE_S3=True silently does nothing."
    )


def test_production_use_s3_env_var_gates_s3_backend():
    """production.py must gate the S3 backend on the USE_S3 environment variable."""
    text = _text(PRODUCTION_PY)
    assert "USE_S3" in text, (
        "production.py must check the USE_S3 env var to switch between FileSystemStorage "
        "and S3Boto3Storage. Without this gate, storage is unconditional."
    )


def test_production_filesystem_storage_is_fallback():
    """production.py must keep FileSystemStorage as the fallback when USE_S3=False."""
    text = _text(PRODUCTION_PY)
    assert "FileSystemStorage" in text, (
        "production.py must include FileSystemStorage as the fallback storage backend "
        "when USE_S3=False. Without it, the app breaks in non-S3 deployments."
    )


# ──── tenant isolation: proposal storage names ──────────────────────────────

def test_services_prefixes_storage_by_tenant_schema():
    """services.py must prefix proposal storage names with the tenant schema, so the
    shared MEDIA_ROOT / S3 bucket isolates tenants. A bare `proposals/{number}` name
    lets two tenants with the same proposal number overwrite/read each other's files."""
    text = _text(SERVICES_PY)
    assert "connection.schema_name" in text, (
        "proposals/services.py must derive the storage path from the current tenant "
        "(connection.schema_name). Without it, files land in a shared, tenant-agnostic path."
    )
    # The old vulnerable literal must be gone.
    assert 'f"proposals/{proposal.number}.pdf"' not in text, (
        "proposals/services.py still builds the un-prefixed name "
        'f"proposals/{proposal.number}.pdf" — that is not tenant-isolated.'
    )
    assert 'f"proposals/{proposal.number}.docx"' not in text, (
        "proposals/services.py still builds the un-prefixed name "
        'f"proposals/{proposal.number}.docx" — that is not tenant-isolated.'
    )


# ──── secrets hardening: encryption key + docker ────────────────────────────

def test_production_rejects_dev_encryption_key():
    """production.py must refuse to boot if FIELD_ENCRYPTION_KEY equals the committed
    dev key — that key is public in the repo, so reusing it leaves ERP creds in clear."""
    text = _text(PRODUCTION_PY)
    assert "gq5BmjeBGD9Ji49jNTL6hSEj5woUlf515QRfBgcgSVU=" in text and "ImproperlyConfigured" in text, (
        "production.py must raise ImproperlyConfigured when FIELD_ENCRYPTION_KEY matches "
        "the committed development key. Otherwise a copy-pasted dev key silently ships."
    )


def test_production_requires_secret_key_env():
    """production.py must re-source SECRET_KEY with no default. base.py falls back to
    the committed literal "dev-insecure-change-me", so without this the app boots
    silently on a public signing key whenever DJANGO_SECRET_KEY is missing from the
    deploy env — while FIELD_ENCRYPTION_KEY, the sibling secret, refuses to boot."""
    text = _text(PRODUCTION_PY)
    assert 'SECRET_KEY = env("DJANGO_SECRET_KEY")' in text, (
        'production.py must set SECRET_KEY = env("DJANGO_SECRET_KEY") with NO default, '
        "so a missing env var raises instead of falling back to base.py's dev literal."
    )


def test_production_rejects_dev_secret_key():
    """production.py must refuse to boot if SECRET_KEY equals the committed dev default."""
    text = _text(PRODUCTION_PY)
    assert "dev-insecure-change-me" in text and "ImproperlyConfigured" in text, (
        "production.py must raise ImproperlyConfigured when DJANGO_SECRET_KEY matches the "
        "committed development default. Otherwise a copy-pasted dev key silently ships."
    )


def test_production_rejects_every_committed_secret_key_placeholder():
    """Guarding only base.py's default is theatre: CLAUDE.md tells you to
    `cp backend/.env.example backend/.env`, and that file ships its OWN placeholder.
    The env var IS set, so env() never raises — the app boots silently on a key that
    is public in the repo. Every placeholder in every committed .env*.example must be
    in production.py's rejected set."""
    prod = _text(PRODUCTION_PY)
    examples = sorted(ROOT.glob(".env*.example")) + sorted((ROOT / "backend").glob(".env*.example"))
    assert examples, "no .env*.example files found — check the glob."
    missing = []
    for path in examples:
        for line in _text(path).splitlines():
            line = line.strip()
            if not line.startswith("DJANGO_SECRET_KEY="):
                continue
            value = line.split("=", 1)[1].strip()
            # Placeholders that can't parse as a usable key fail loudly on their own.
            if not value or value.startswith("<"):
                continue
            if value not in prod:
                missing.append(f"{path.relative_to(ROOT)} ships DJANGO_SECRET_KEY={value!r}")
    assert not missing, (
        "production.py must reject these committed placeholder secret keys, but does not:\n  "
        + "\n  ".join(missing)
        + "\nAdd them to _PUBLIC_SECRET_KEYS in backend/smartquotation/settings/production.py."
    )


def test_dockerignore_excludes_env_secrets():
    """A .dockerignore at the build-context root must exclude .env files so secrets are
    not baked into the image by `COPY backend/ .`."""
    assert DOCKERIGNORE.exists(), (
        ".dockerignore is missing at the repo root (docker build context). Without it, "
        "backend/.env — with FIELD_ENCRYPTION_KEY and DB password — is baked into the image."
    )
    text = _text(DOCKERIGNORE)
    assert ".env" in text and "backend/.env" in text, (
        ".dockerignore must exclude .env and backend/.env to keep secrets out of the image."
    )


def test_dockerfile_runs_as_non_root():
    """backend/Dockerfile must drop to a non-root user before running the app."""
    text = _text(DOCKERFILE)
    assert "USER appuser" in text, (
        "backend/Dockerfile must switch to a non-root USER (appuser). Running gunicorn as "
        "root widens the blast radius of any RCE in the web process."
    )


def test_prod_compose_requires_postgres_password():
    """docker-compose.prod.yml must not ship a weak default DB password; it must require
    POSTGRES_PASSWORD from the environment (`:?` fails fast if unset)."""
    text = _text(COMPOSE_PROD)
    assert "POSTGRES_PASSWORD:-sq" not in text, (
        "docker-compose.prod.yml still defaults POSTGRES_PASSWORD to 'sq' — a guessable "
        "production secret. Require it from the environment instead."
    )
    assert "${POSTGRES_PASSWORD:?" in text, (
        "docker-compose.prod.yml must require POSTGRES_PASSWORD via ${POSTGRES_PASSWORD:?...} "
        "so `docker compose up` aborts when it is not set."
    )


if __name__ == "__main__":
    tests = [
        test_services_imports_default_storage,
        test_services_save_uses_default_storage,
        test_services_read_uses_default_storage,
        test_services_no_direct_media_root_write,
        test_services_generate_docx_exists,
        test_services_generate_exists,
        test_services_generate_saves_storage_names,
        test_services_prefixes_storage_by_tenant_schema,
        test_views_imports_default_storage,
        test_views_download_uses_default_storage_open,
        test_views_download_checks_default_storage_exists,
        test_views_no_os_path_open_for_download,
        test_production_storages_dict_has_default,
        test_production_s3boto3_storage_referenced,
        test_production_use_s3_env_var_gates_s3_backend,
        test_production_filesystem_storage_is_fallback,
        test_production_rejects_dev_encryption_key,
        test_production_requires_secret_key_env,
        test_production_rejects_dev_secret_key,
        test_production_rejects_every_committed_secret_key_placeholder,
        test_dockerignore_excludes_env_secrets,
        test_dockerfile_runs_as_non_root,
        test_prod_compose_requires_postgres_password,
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
