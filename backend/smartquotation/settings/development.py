from .base import *  # noqa
DEBUG = True
ALLOWED_HOSTS = ["*"]
AXES_ENABLED = False  # desativado em dev/test (axes.client.login() incompatível sem request)

# Chave de cifragem SÓ para desenvolvimento/CI (conhecida, JAMAIS usar em produção).
# Produção exige FIELD_ENCRYPTION_KEY via env (settings/production.py); base.py não tem default.
FIELD_ENCRYPTION_KEY = env("FIELD_ENCRYPTION_KEY", default="gq5BmjeBGD9Ji49jNTL6hSEj5woUlf515QRfBgcgSVU=")
