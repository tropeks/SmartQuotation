"""
Smoke tests: media_data volume config and MEDIA_ROOT setting.
Checks docker-compose.prod.yml and production.py without starting services.
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
COMPOSE_PROD = ROOT / "docker-compose.prod.yml"
PRODUCTION_PY = ROOT / "backend" / "smartquotation" / "settings" / "production.py"
ENV_PROD_EXAMPLE = ROOT / ".env.prod.example"

MEDIA_PATH = "/app/backend/media"


def test_production_py_has_media_root():
    text = PRODUCTION_PY.read_text()
    assert "MEDIA_ROOT" in text, "production.py must define MEDIA_ROOT"
    assert MEDIA_PATH in text, f"production.py MEDIA_ROOT must point to {MEDIA_PATH!r}"


def test_compose_prod_has_media_volume_declared():
    text = COMPOSE_PROD.read_text()
    assert "media_data:" in text, "docker-compose.prod.yml must declare 'media_data' named volume"


def test_compose_prod_web_mounts_media():
    text = COMPOSE_PROD.read_text()
    assert MEDIA_PATH in text, (
        f"docker-compose.prod.yml must mount {MEDIA_PATH!r} (in web or worker)"
    )
    # Ensure at least two occurrences (web + worker)
    count = text.count(MEDIA_PATH)
    assert count >= 2, (
        f"Expected {MEDIA_PATH!r} at least twice (web + worker), found {count} time(s)"
    )


def test_env_prod_example_has_use_s3():
    text = ENV_PROD_EXAMPLE.read_text()
    assert "USE_S3" in text, ".env.prod.example must contain USE_S3"
    assert "USE_S3=False" in text, ".env.prod.example must have USE_S3=False as default"


def test_env_prod_example_has_commented_aws_vars():
    text = ENV_PROD_EXAMPLE.read_text()
    for var in ("AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY", "AWS_STORAGE_BUCKET_NAME"):
        assert f"# {var}" in text or f"#{var}" in text, (
            f".env.prod.example must have {var!r} commented out"
        )


if __name__ == "__main__":
    tests = [
        test_production_py_has_media_root,
        test_compose_prod_has_media_volume_declared,
        test_compose_prod_web_mounts_media,
        test_env_prod_example_has_use_s3,
        test_env_prod_example_has_commented_aws_vars,
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
