from .base import *  # noqa
DEBUG = True
ALLOWED_HOSTS = ["*"]
AXES_ENABLED = False  # desativado em dev/test (axes.client.login() incompatível sem request)
