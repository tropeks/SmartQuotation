"""
Templates de papel (RBAC V2 M2) — CÓDIGO, não tabela.

Cada template é o RECORTE do DEFAULT_MATRIX para um dos papéis built-in + seus traits.
Ao criar um papel A PARTIR de um template, o conteúdo é COPIADO (nunca vínculo vivo):
grava-se `source_template` + `template_version` na `Role` e as linhas `RolePermission`
correspondentes. Versionar (`TEMPLATE_VERSION`) deixa a UI distinguir "criado do template vN".

Fonte única das capabilities: `DEFAULT_MATRIX` (não duplicar aqui). O template "branco"
(do zero) NÃO vive aqui — é tratado na view (papel sem nenhuma capability marcada).
"""
from apps.accounts.models import UserProfile
from apps.access.matrix import DEFAULT_MATRIX

TEMPLATE_VERSION = 1

# key = papel built-in cujo recorte do DEFAULT_MATRIX serve de ponto de partida.
_TEMPLATE_SPECS = [
    {
        "key": UserProfile.ROLE_ORCAMENTISTA,
        "name": "Orçamentista",
        "description": "Cria e edita cotações e propostas; não converte em OF.",
        "requires_crea": False,
        "is_admin_like": False,
    },
    {
        "key": UserProfile.ROLE_ENGENHEIRO,
        "name": "Engenheiro",
        "description": "Engenharia técnica com CREA; assina o estágio técnico de aprovação.",
        "requires_crea": True,
        "is_admin_like": False,
    },
    {
        "key": UserProfile.ROLE_GESTOR_COMERCIAL,
        "name": "Gestor Comercial",
        "description": "Gestão comercial: preços, rates e aprovação comercial.",
        "requires_crea": False,
        "is_admin_like": False,
    },
    {
        "key": UserProfile.ROLE_VIEWER,
        "name": "Somente leitura",
        "description": "Consulta cotações; sem edição.",
        "requires_crea": False,
        "is_admin_like": False,
    },
    {
        "key": UserProfile.ROLE_ADMIN,
        "name": "Administrador",
        "description": "Acesso administrativo total ao tenant.",
        "requires_crea": False,
        "is_admin_like": True,
    },
]


def _caps_for(role_key):
    """Capabilities concedidas ao papel built-in `role_key` no DEFAULT_MATRIX."""
    return frozenset(
        cap for cap, roles in DEFAULT_MATRIX.items() if role_key in roles
    )


def role_templates():
    """Lista dos 5 templates com suas capabilities derivadas (para a UI de criação)."""
    return [
        {
            "key": spec["key"],
            "name": spec["name"],
            "description": spec["description"],
            "requires_crea": spec["requires_crea"],
            "is_admin_like": spec["is_admin_like"],
            "version": TEMPLATE_VERSION,
            "capabilities": _caps_for(spec["key"]),
        }
        for spec in _TEMPLATE_SPECS
    ]


def get_template(key):
    """Template pela `key`, ou None. `key` vazio/'blank' → None (papel do zero)."""
    if not key or key == "blank":
        return None
    for tpl in role_templates():
        if tpl["key"] == key:
            return tpl
    return None
