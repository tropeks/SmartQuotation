from .base import *  # noqa
DEBUG = False
SECURE_SSL_REDIRECT = True
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SECURE_HSTS_SECONDS = 31536000
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = "DENY"
# Obriga a env var — falha ruidosamente se não estiver setada no deploy.
FIELD_ENCRYPTION_KEY = env("FIELD_ENCRYPTION_KEY")

# ─── Static files (WhiteNoise + optional S3 for media) ───────────────────────
STATIC_URL = "/static/"
STATIC_ROOT = "/app/staticfiles"

STORAGES = {
    "default": {
        "BACKEND": (
            "storages.backends.s3boto3.S3Boto3Storage"
            if env.bool("USE_S3", default=False)
            else "django.core.files.storage.FileSystemStorage"
        ),
    },
    "staticfiles": {
        "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage",
    },
}
