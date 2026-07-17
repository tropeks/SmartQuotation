"""
Teste de integridade FAIL-CLOSED (T8): toda capability referenciada em decoradores
`require_capability(...)` ou em chamadas `user_can(..., ...)` no código-fonte das apps
DEVE existir no catálogo `apps.access.capabilities.CAPABILITIES`.

Motivação: o catálogo é a fonte da verdade do que EXISTE (registry em código); a matriz
papel×capability (RolePermission, em banco) resolve quem PODE. Se um decorator/flag
referenciar um code que nunca foi cadastrado no registry, `role_can`/`user_can` resolvem
esse code fail-closed (sempre False) -- ou seja, ninguém acessaria a view, ou a flag de
UI ficaria sempre desligada, silenciosamente. Isso é um bug de deploy (esqueceram de
adicionar a capability ao registry), não uma decisão de RBAC -- e deve quebrar o CI em
vez de vazar pra produção como "todo mundo perdeu acesso a X".

Esta suíte varre os `views.py`/`api.py` de `backend/apps/**` (onde os decoradores de
view realmente vivem) com regex simples -- não faz parsing de AST -- cobrindo o padrão
real usado no código:
    @require_capability("codigo")
    require_capability("codigo")                 # atribuído a uma constante
    user_can(request.user, "codigo")
    user_can(user, "codigo")

O escopo é deliberadamente restrito a `views.py`/`api.py` (em vez de todo `*.py` sob
apps/): módulos como `apps/access/apps.py`, `capabilities.py`, `enforcement.py` e os
próprios arquivos de teste CITAM esses padrões em docstrings/comentários como
documentação -- uma varredura ampla combinaria com esse texto e geraria falsos
positivos (órfãos fantasma que não são decorators reais). `views.py`/`api.py` é onde
os decoradores/flags são de fato aplicados.

Não valida o inverso (capability no registry sem nenhum uso no código) -- catálogo pode
ter entradas "reservadas" (ex.: access.manage é referenciado só uma vez, cost stages
futuros) sem que isso seja um erro.
"""
import re
from pathlib import Path

from django.conf import settings
from django.test import SimpleTestCase

from apps.access.capabilities import CAPABILITIES

# Diretórios cujo conteúdo não é código de view/API "vivo" (migrations são snapshots
# históricos; __pycache__ é bytecode).
_EXCLUDED_DIR_PARTS = {"migrations", "__pycache__", "node_modules"}
_SOURCE_FILENAMES = ("views.py", "api.py")

_REQUIRE_CAPABILITY_RE = re.compile(r"require_capability\(\s*['\"]([\w.]+)['\"]")
_USER_CAN_RE = re.compile(r"user_can\(\s*[^,()]+,\s*['\"]([\w.]+)['\"]")


def _apps_root() -> Path:
    return Path(settings.BASE_DIR) / "apps"


def _iter_source_files():
    root = _apps_root()
    for filename in _SOURCE_FILENAMES:
        for path in root.rglob(filename):
            if _EXCLUDED_DIR_PARTS.intersection(path.parts):
                continue
            yield path


def _find_referenced_capability_codes():
    """
    {code: [ "arquivo.py:linha", ... ] } para cada capability code referenciado por
    `require_capability(...)` ou `user_can(..., ...)` em qualquer arquivo de apps/**.
    """
    referenced = {}
    for path in _iter_source_files():
        text = path.read_text(encoding="utf-8")
        for lineno, line in enumerate(text.splitlines(), start=1):
            for match in _REQUIRE_CAPABILITY_RE.finditer(line):
                referenced.setdefault(match.group(1), []).append(f"{path}:{lineno}")
            for match in _USER_CAN_RE.finditer(line):
                referenced.setdefault(match.group(1), []).append(f"{path}:{lineno}")
    return referenced


class CapabilityRegistryIntegrityTests(SimpleTestCase):
    """Fail-closed: nenhum decorator/flag pode referenciar capability fora do catálogo."""

    def test_scan_finds_the_expected_call_sites(self):
        # Sanity check da própria varredura: se isto vier vazio, a regex/caminho quebrou
        # silenciosamente e o teste principal passaria de forma falsa-positiva (vazio
        # está sempre "todo mundo no catálogo").
        referenced = _find_referenced_capability_codes()
        self.assertGreater(
            len(referenced),
            10,
            "A varredura de require_capability()/user_can() em views.py/api.py encontrou "
            "poucos ou nenhum call site -- verifique se o caminho de apps/ ou a regex "
            "não quebrou.",
        )

    def test_every_referenced_capability_is_in_registry(self):
        referenced = _find_referenced_capability_codes()
        known = set(CAPABILITIES.keys())
        orphans = {code: sites for code, sites in referenced.items() if code not in known}

        if orphans:
            details = "\n".join(
                f"  - {code!r} referenciado em: {', '.join(sites)}"
                for code, sites in sorted(orphans.items())
            )
            self.fail(
                "Capabilities referenciadas por require_capability()/user_can() mas "
                "AUSENTES de apps.access.capabilities.CAPABILITIES (fail-closed -- "
                "cadastre no registry antes de fazer deploy):\n" + details
            )
