from .base import *  # noqa
DEBUG = False
SECURE_SSL_REDIRECT = True
# Deploys sit behind a TLS-terminating reverse proxy (Cloudflare Tunnel); trust its
# X-Forwarded-Proto so request.is_secure() is True and SECURE_SSL_REDIRECT doesn't
# infinite-loop (proxy forwards plain HTTP, Django would otherwise always redirect).
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
CSRF_TRUSTED_ORIGINS = env.list("CSRF_TRUSTED_ORIGINS", default=[])
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
MEDIA_URL = "/media/"
MEDIA_ROOT = "/app/backend/media"

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
