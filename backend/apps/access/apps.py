import logging

from django.apps import AppConfig

logger = logging.getLogger(__name__)


class AccessConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.access"
    label = "access"
    verbose_name = "Controle de Acesso (RBAC configurável)"

    def ready(self):
        from django.db.models.signals import post_delete, post_save

        from apps.access.models import RolePermission
        from apps.access.signals import invalidate_matrix_on_change

        post_save.connect(
            invalidate_matrix_on_change,
            sender=RolePermission,
            dispatch_uid="access_rolepermission_post_save",
        )
        post_delete.connect(
            invalidate_matrix_on_change,
            sender=RolePermission,
            dispatch_uid="access_rolepermission_post_delete",
        )

        self._warn_on_registry_drift_if_debug()

    def _warn_on_registry_drift_if_debug(self):
        """
        Checagem de conveniência (DEV-only, best-effort): em DEBUG, loga um warning se
        algum `require_capability("x")`/`user_can(..., "x")` do código referenciar uma
        capability ausente do registry (`apps.access.capabilities.CAPABILITIES`).

        Escopo restrito a arquivos `views.py`/`api.py` (onde os decoradores realmente
        vivem) -- uma varredura sobre TODO `*.py` sob apps/ combinaria com os próprios
        exemplos citados neste docstring e no de
        `apps.access.tests_registry_integrity`, gerando falsos positivos.

        Esta checagem é só um alerta de log em startup local -- o gate de CI de
        verdade é o teste dedicado `apps.access.tests_registry_integrity`
        (fail-closed, quebra o build). Qualquer erro aqui é engolido: uma varredura
        de conveniência jamais pode impedir o servidor de subir.
        """
        from django.conf import settings

        if not getattr(settings, "DEBUG", False):
            return

        try:
            import re
            from pathlib import Path

            from apps.access.capabilities import CAPABILITIES

            require_re = re.compile(r"require_capability\(\s*['\"]([\w.]+)['\"]")
            user_can_re = re.compile(r"user_can\(\s*[^,()]+,\s*['\"]([\w.]+)['\"]")
            excluded_parts = {"migrations", "__pycache__", "node_modules"}
            source_filenames = ("views.py", "api.py")

            apps_root = Path(settings.BASE_DIR) / "apps"
            known = set(CAPABILITIES.keys())
            orphans = {}
            for filename in source_filenames:
                for path in apps_root.rglob(filename):
                    if excluded_parts.intersection(path.parts):
                        continue
                    text = path.read_text(encoding="utf-8")
                    for match in (
                        *require_re.finditer(text),
                        *user_can_re.finditer(text),
                    ):
                        code = match.group(1)
                        if code not in known:
                            orphans.setdefault(code, path)

            if orphans:
                logger.warning(
                    "RBAC registry drift: capabilities referenciadas no código mas "
                    "ausentes de CAPABILITIES (fail-closed => sempre negadas): %s. "
                    "Cadastre-as em apps/access/capabilities.py.",
                    ", ".join(f"{code!r} ({path})" for code, path in sorted(orphans.items())),
                )
        except Exception:  # pragma: no cover - checagem de conveniência, nunca fatal
            logger.debug("Checagem de drift do registry de capabilities falhou.", exc_info=True)
