from django.core.exceptions import ImproperlyConfigured
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
# Obriga a env var — falha ruidosamente se não estiver setada no deploy. Sem isto,
# base.py cai no default "dev-insecure-change-me", que é commitado → público. A app
# subiria silenciosamente assinando com uma constante conhecida: hoje o alcance é
# forja de messages em cookie e enfraquecimento do segredo de CSRF (sessões são em
# DB e não há fluxo de reset), mas vira takeover no dia que alguém adicionar reset
# de senha, link assinado ou sessão em cookie.
SECRET_KEY = env("DJANGO_SECRET_KEY")
# Rejeita TODO valor público conhecido, não só o default de base.py. Os arquivos de
# exemplo são commitados e o CLAUDE.md manda `cp backend/.env.example backend/.env`,
# então o caminho DOCUMENTADO de setup entrega uma chave pública já setada — a var
# existe, env() não levanta, e sem esta lista a app subiria em silêncio com ela.
# Ao adicionar placeholder novo em qualquer .env*.example, adicione aqui também
# (tests/test_proposals_storage_contract.py trava essa correspondência).
_PUBLIC_SECRET_KEYS = frozenset({
    "dev-insecure-change-me",           # settings/base.py (default)
    "change-me-in-prod",                # backend/.env.example
    "CHANGE-ME-strong-random-secret",   # .env.prod.example
})
if SECRET_KEY in _PUBLIC_SECRET_KEYS:
    raise ImproperlyConfigured(
        "DJANGO_SECRET_KEY em produção é um placeholder público commitado no repo. "
        "Gere uma chave secreta nova: "
        "python -c \"from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())\""
    )
# Obriga a env var — falha ruidosamente se não estiver setada no deploy.
FIELD_ENCRYPTION_KEY = env("FIELD_ENCRYPTION_KEY")
# A chave de desenvolvimento é commitada (settings/development.py) → pública.
# Rejeita reutilizá-la em produção: dados cifrados (credenciais ERP, MaterialPrice)
# estariam efetivamente em claro para qualquer um com acesso ao repo.
_DEV_ENCRYPTION_KEY = "gq5BmjeBGD9Ji49jNTL6hSEj5woUlf515QRfBgcgSVU="
if FIELD_ENCRYPTION_KEY == _DEV_ENCRYPTION_KEY:
    raise ImproperlyConfigured(
        "FIELD_ENCRYPTION_KEY em produção é igual à chave de desenvolvimento commitada. "
        "Gere uma chave secreta nova: "
        "python -c \"from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())\""
    )

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
