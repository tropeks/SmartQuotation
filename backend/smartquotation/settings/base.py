"""
SmartQuotation — Base Settings
Django 5.2 + django-tenants (schema-per-tenant). Session auth (não JWT).
Padrão adaptado do Vitali (fundação sólida), sem apps de saúde.
"""
import sys
from datetime import timedelta
from pathlib import Path
import environ

BASE_DIR = Path(__file__).resolve().parent.parent.parent
env = environ.Env(DEBUG=(bool, False))

# pricing_engine (lib pura, zero Django) importável: repo root local ou /app no Docker.
for _candidate in (BASE_DIR.parent, Path("/app")):
    if (_candidate / "pricing_engine" / "__init__.py").exists():
        if str(_candidate) not in sys.path:
            sys.path.insert(0, str(_candidate))
        break

SECRET_KEY = env("DJANGO_SECRET_KEY", default="dev-insecure-change-me")
DEBUG = env.bool("DJANGO_DEBUG", default=False)
ALLOWED_HOSTS = env.list("DJANGO_ALLOWED_HOSTS", default=["localhost", "127.0.0.1", ".localhost"])

# ─── Django-Tenants ───────────────────────────────────────────────────────────
SHARED_APPS = [
    "django_tenants",                 # must be first
    "apps.tenants",                   # Tenant, Domain, Plan (public schema)
    "django.contrib.contenttypes",
    "django.contrib.auth",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.admin",
    "django_celery_beat",
    "axes",                           # brute-force protection (shared: caches por IP)
]

# Apps de cada TENANT (isolamento por schema). Adicionados conforme construídos.
TENANT_APPS = [
    "rest_framework",
    "drf_spectacular",
    "django_filters",
    "apps.accounts",
    "apps.audit",
    "apps.integrations.protheus.apps.ProtheusConfig",
    "apps.materials",
    "apps.engineering_params",
    "apps.quotations",
    "apps.proposals",
    "apps.production",
    "apps.cost_discovery",
    "apps.tema_templates",
    # domínio (criados nas tasks seguintes):
    # "apps.costing",
]

INSTALLED_APPS = list(SHARED_APPS) + [a for a in TENANT_APPS if a not in SHARED_APPS]

TENANT_MODEL = "tenants.Tenant"
TENANT_DOMAIN_MODEL = "tenants.Domain"
DATABASE_ROUTERS = ["django_tenants.routers.TenantSyncRouter"]
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# ─── Middleware (session auth; sem JWT/MFA do Vitali no MVP) ───────────────────
MIDDLEWARE = [
    "django_tenants.middleware.main.TenantMainMiddleware",  # must be first
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "axes.middleware.AxesMiddleware",  # deve vir após AuthenticationMiddleware
    "django.middleware.locale.LocaleMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "smartquotation.urls"
PUBLIC_SCHEMA_URLCONF = "smartquotation.urls_public"
WSGI_APPLICATION = "smartquotation.wsgi.application"

TEMPLATES = [{
    "BACKEND": "django.template.backends.django.DjangoTemplates",
    "DIRS": [BASE_DIR / "templates"],
    "APP_DIRS": True,
    "OPTIONS": {"context_processors": [
        "django.template.context_processors.debug",
        "django.template.context_processors.request",
        "django.contrib.auth.context_processors.auth",
        "django.contrib.messages.context_processors.messages",
    ]},
}]

# ─── Database (django-tenants backend) ────────────────────────────────────────
DATABASES = {
    "default": {
        "ENGINE": "django_tenants.postgresql_backend",
        "NAME": env("POSTGRES_DB", default="smartquotation"),
        "USER": env("POSTGRES_USER", default="sq"),
        "PASSWORD": env("POSTGRES_PASSWORD", default="sq"),
        "HOST": env("POSTGRES_HOST", default="localhost"),
        "PORT": env("POSTGRES_PORT", default="5432"),
    }
}

# ─── Auth ─────────────────────────────────────────────────────────────────────
PASSWORD_HASHERS = [
    "django.contrib.auth.hashers.Argon2PasswordHasher",
    "django.contrib.auth.hashers.PBKDF2PasswordHasher",
]
LOGIN_URL = "/login/"
LOGIN_REDIRECT_URL = "/"
LOGOUT_REDIRECT_URL = "/login/"
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator", "OPTIONS": {"min_length": 10}},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# ─── Celery / Redis ───────────────────────────────────────────────────────────
REDIS_URL = env("REDIS_URL", default="redis://localhost:6379/0")
CELERY_BROKER_URL = REDIS_URL
CELERY_RESULT_BACKEND = REDIS_URL
CELERY_TASK_SERIALIZER = "json"
PROTHEUS_PULL_INTERVAL_MINUTES = max(1, env.int("PROTHEUS_PULL_INTERVAL_MINUTES", default=15))
PROTHEUS_PULL_INTERVAL = timedelta(minutes=PROTHEUS_PULL_INTERVAL_MINUTES)

# ─── i18n / tz ────────────────────────────────────────────────────────────────
LANGUAGE_CODE = "pt-br"
TIME_ZONE = "America/Sao_Paulo"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STATICFILES_DIRS = [BASE_DIR / "static"]
MEDIA_URL = "media/"
MEDIA_ROOT = BASE_DIR / "media"

# django-encrypted-model-fields (preços/margens cifrados)
# Chave dev — gerada localmente, NÃO publicada. Produção DEVE sobrescrever via env var.
FIELD_ENCRYPTION_KEY = env("FIELD_ENCRYPTION_KEY", default="gq5BmjeBGD9Ji49jNTL6hSEj5woUlf515QRfBgcgSVU=")

# ─── django-axes (brute-force protection) ────────────────────────────────────
AXES_FAILURE_LIMIT = 5            # tentativas antes do lockout
AXES_COOLOFF_TIME = 1             # horas de lockout
AXES_LOCKOUT_PARAMETERS = ["ip_address"]
AXES_RESET_ON_SUCCESS = True      # limpa contador após login bem-sucedido
AUTHENTICATION_BACKENDS = [
    "axes.backends.AxesStandaloneBackend",  # deve ser primeiro
    "django.contrib.auth.backends.ModelBackend",
]

# ─── DRF + OpenAPI ─────────────────────────────────────────────────────────────
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework.authentication.SessionAuthentication",
    ],
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
}
