"""
SmartQuotation — Base Settings
Django 5.2 + django-tenants (schema-per-tenant). Session auth (não JWT).
Padrão adaptado do Vitali (fundação sólida), sem apps de saúde.
"""
from pathlib import Path
import environ

BASE_DIR = Path(__file__).resolve().parent.parent.parent
env = environ.Env(DEBUG=(bool, False))

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
]

# Apps de cada TENANT (isolamento por schema). Adicionados conforme construídos.
TENANT_APPS = [
    "rest_framework",
    "drf_spectacular",
    "django_filters",
    "apps.materials",
    # domínio (criados nas tasks seguintes):
    # "apps.accounts", "apps.engineering_params",
    # "apps.templates_lib", "apps.quotations", "apps.costing",
    # "apps.proposals", "apps.cost_discovery",
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
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
]

# ─── Celery / Redis ───────────────────────────────────────────────────────────
REDIS_URL = env("REDIS_URL", default="redis://localhost:6379/0")
CELERY_BROKER_URL = REDIS_URL
CELERY_RESULT_BACKEND = REDIS_URL
CELERY_TASK_SERIALIZER = "json"

# ─── i18n / tz ────────────────────────────────────────────────────────────────
LANGUAGE_CODE = "pt-br"
TIME_ZONE = "America/Sao_Paulo"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"

# django-encrypted-model-fields (preços/margens cifrados)
FIELD_ENCRYPTION_KEY = env("FIELD_ENCRYPTION_KEY", default="zHengIv2_t3vYh0Qm6m6Y8oF1n0YH3y7wE7c0pXq3kM=")

# ─── DRF + OpenAPI ─────────────────────────────────────────────────────────────
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework.authentication.SessionAuthentication",
    ],
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
}
