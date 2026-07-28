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
    "apps.health",                    # infra: /health/ endpoint (sem modelo, sem migrations)
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
    "apps.access",
    "apps.audit",
    "apps.integrations.protheus.apps.ProtheusConfig",
    "apps.integrations.omie.apps.OmieConfig",
    "apps.integrations.nomus.apps.NomusConfig",
    "apps.integrations.sap_b1.apps.SAPB1Config",
    "apps.integrations.bling.apps.BlingConfig",
    "apps.materials",
    "apps.engineering_params",
    "apps.quotations",
    "apps.proposals",
    "apps.production",
    "apps.cost_discovery",
    "apps.cost_structure",
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
    "whitenoise.middleware.WhiteNoiseMiddleware",  # serve static em prod (logo após Security)
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "axes.middleware.AxesMiddleware",  # deve vir após AuthenticationMiddleware
    "apps.accounts.middleware.TenantMembershipMiddleware",  # barra user sem profile no schema ativo
    "apps.accounts.middleware.MustChangePasswordMiddleware",  # força troca de senha provisória
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
SAP_B1_EXPORT_CHECK_INTERVAL_MINUTES = max(1, env.int("SAP_B1_EXPORT_CHECK_INTERVAL_MINUTES", default=15))
SAP_B1_EXPORT_CHECK_INTERVAL = timedelta(minutes=SAP_B1_EXPORT_CHECK_INTERVAL_MINUTES)

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

# django-encrypted-model-fields (preços/margens + credenciais de ERP cifradas)
# SEM default: cada ambiente DEVE prover a chave via env var. base/production falham
# ruidosamente se faltar (não há chave conhecida embutida). Só development.py define uma
# chave dev local — nunca usar em produção.
FIELD_ENCRYPTION_KEY = env("FIELD_ENCRYPTION_KEY", default=None)

# ─── django-axes (brute-force protection) ────────────────────────────────────
AXES_FAILURE_LIMIT = 5            # tentativas antes do lockout
AXES_COOLOFF_TIME = 1             # horas de lockout
# O bucket de lockout PRECISA conter o username. Chavear só por ip_address anulava a
# proteção inteira: o deploy fica atrás de um túnel que termina TLS (Cloudflare, ver
# production.py), django-ipware não está instalado, e nesse caso o axes cai em
# REMOTE_ADDR (axes/helpers.py get_client_ip_address: CLIENT_IP_CALLABLE -> ipware ->
# REMOTE_ADDR). Atrás do túnel REMOTE_ADDR é o endereço do cloudflared em TODA request,
# então a plataforma inteira compartilhava UM contador. Com username no bucket, 5 senhas
# erradas contra uma conta travam AQUELA conta, venha o request de onde vier.
AXES_LOCKOUT_PARAMETERS = [["username", "ip_address"], "username"]
# NÃO reativar sem antes garantir que o bucket contenha username. Com o bucket antigo
# (só ip), o reset filtrava AccessAttempt por ip_address e deletava TUDO: qualquer login
# bem-sucedido de qualquer usuário zerava as falhas acumuladas contra todos os outros.
# Um atacante alternava 4 tentativas erradas contra o admin + 1 login na própria conta,
# indefinidamente, e o cool-off nunca disparava.
AXES_RESET_ON_SUCCESS = False
# Trade-off aceito: com username no bucket, alguém que saiba um username pode trancá-lo
# por AXES_COOLOFF_TIME. É o trade-off clássico de qualquer política de lockout, limitado
# a 1h. O contrário — adivinhação online ilimitada de senha, sem MFA e sem rate limit no
# /login/ — é pior.
# PENDENTE (precisa de infra, não de código): instalar django-ipware e usar
# HTTP_CF_CONNECTING_IP restauraria o IP real do cliente, devolvendo precisão ao componente
# de IP do bucket. Só é seguro DEPOIS que a origem parar de aceitar tráfego direto —
# docker-compose.prod.yml publica 8000 em 0.0.0.0, então hoje o header seria spoofável e
# trocaríamos este bug por um pior.
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
