"""
Invariante de compliance CREA (RBAC V2 M1).

Regra: um papel que assina o estágio TÉCNICO (`approval.technical_sign`) DEVE ter o trait
`requires_crea=True`. Caso contrário o pilar de compliance (CREA/ART) quebraria silenciosamente
— exatamente o risco descrito na issue #86.

Em M1 os dados-semente já satisfazem o invariante (só `engenheiro` tem technical_sign E
requires_crea). Esta função é a fonte da verdade que a UI de papéis (M2) vai chamar antes de:
- conceder `technical_sign` a um papel sem CREA; ou
- remover `requires_crea` de um papel que já assina o estágio técnico.
"""
from apps.accounts.models import Role

TECHNICAL_SIGN_CAP = "approval.technical_sign"


def technical_sign_compliance_ok(role_key, *, model=None):
    """
    True se `role_key` está em conformidade: se tem `technical_sign` concedido, então
    o papel tem `requires_crea=True`. Papel sem technical_sign → sempre ok.

    Lê a concessão da matriz por tenant (RolePermission). Fail-safe: papel inexistente
    → não pode assinar nada de forma válida, mas não há violação a reportar → True.
    """
    if not role_key:
        return True

    from apps.access.models import RolePermission

    RP = model or RolePermission
    grants_technical = RP.objects.filter(
        role=role_key, capability=TECHNICAL_SIGN_CAP, allowed=True
    ).exists()
    if not grants_technical:
        return True
    return Role.objects.filter(key=role_key, requires_crea=True).exists()
