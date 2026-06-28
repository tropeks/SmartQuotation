"""
Smoke tests: media_data volume config and MEDIA_ROOT setting.
Checks docker-compose.prod.yml and production.py without starting services.
"""
import re
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
COMPOSE_PROD = ROOT / "docker-compose.prod.yml"
PRODUCTION_PY = ROOT / "backend" / "smartquotation" / "settings" / "production.py"
ENV_PROD_EXAMPLE = ROOT / ".env.prod.example"

MEDIA_PATH = "/app/backend/media"
MEDIA_VOLUME = "media_data"


def _load_compose_prod():
    return yaml.safe_load(COMPOSE_PROD.read_text())


def _volume_list_has_media_data(volumes):
    """Return True if a service volume list binds media_data to MEDIA_PATH."""
    if not volumes:
        return False
    for vol in volumes:
        if isinstance(vol, str):
            # short syntax: "source:target" or "source:target:mode"
            parts = vol.split(":")
            if parts[0] == MEDIA_VOLUME and parts[1] == MEDIA_PATH:
                return True
        elif isinstance(vol, dict):
            # long syntax: {type: volume, source: ..., target: ...}
            if vol.get("source") == MEDIA_VOLUME and vol.get("target") == MEDIA_PATH:
                return True
    return False


def test_production_py_has_media_root():
    text = PRODUCTION_PY.read_text()
    assert "MEDIA_ROOT" in text, "production.py must define MEDIA_ROOT"
    assert MEDIA_PATH in text, f"production.py MEDIA_ROOT must point to {MEDIA_PATH!r}"


def test_compose_prod_media_data_volume_declared():
    """Top-level 'volumes' section must declare 'media_data'."""
    data = _load_compose_prod()
    top_volumes = data.get("volumes", {}) or {}
    assert MEDIA_VOLUME in top_volumes, (
        f"docker-compose.prod.yml top-level volumes must declare '{MEDIA_VOLUME}'; "
        f"found: {list(top_volumes.keys())}"
    )


def test_compose_prod_web_service_mounts_media_data():
    """'web' service must explicitly mount media_data at MEDIA_PATH."""
    data = _load_compose_prod()
    web_volumes = data["services"]["web"].get("volumes", [])
    assert _volume_list_has_media_data(web_volumes), (
        f"web service must mount '{MEDIA_VOLUME}:{MEDIA_PATH}'; "
        f"web volumes: {web_volumes}"
    )


def test_compose_prod_worker_service_mounts_media_data():
    """'worker' service must explicitly mount media_data at MEDIA_PATH."""
    data = _load_compose_prod()
    worker_volumes = data["services"]["worker"].get("volumes", [])
    assert _volume_list_has_media_data(worker_volumes), (
        f"worker service must mount '{MEDIA_VOLUME}:{MEDIA_PATH}'; "
        f"worker volumes: {worker_volumes}"
    )


def test_compose_prod_declared_volume_is_the_one_used():
    """The volume declared at top-level must be the exact volume used in web and worker."""
    data = _load_compose_prod()
    top_volumes = data.get("volumes", {}) or {}
    assert MEDIA_VOLUME in top_volumes, (
        f"'{MEDIA_VOLUME}' not declared in top-level volumes"
    )
    web_volumes = data["services"]["web"].get("volumes", [])
    worker_volumes = data["services"]["worker"].get("volumes", [])
    assert _volume_list_has_media_data(web_volumes), (
        f"web service does not use the declared '{MEDIA_VOLUME}' volume at {MEDIA_PATH!r}"
    )
    assert _volume_list_has_media_data(worker_volumes), (
        f"worker service does not use the declared '{MEDIA_VOLUME}' volume at {MEDIA_PATH!r}"
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
        test_compose_prod_media_data_volume_declared,
        test_compose_prod_web_service_mounts_media_data,
        test_compose_prod_worker_service_mounts_media_data,
        test_compose_prod_declared_volume_is_the_one_used,
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
