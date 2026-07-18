"""
Templates de FLUXO de aprovação (RBAC V2 M3) — CÓDIGO, não tabela.

Cada template é uma lista ORDENADA de estágios. O estágio técnico (CREA) é built-in e
sempre presente/travado (compliance). Os demais estágios consomem slots de capability de
assinatura do registry (commercial/quality/custom_sign_N).

Aplicar um template ao fluxo do tenant COPIA os estágios (nunca vínculo vivo): remove os
estágios não-builtin atuais e recria a partir do template. O estágio técnico é preservado.
"""
WORKFLOW_TEMPLATE_VERSION = 1

# O estágio técnico mantém o approver_capability histórico (approval.request_remote) para
# preservar 100% o gate CREA anterior ao F10. Os demais usam os slots de assinatura (M0).
_TECHNICAL = {
    "key": "technical",
    "label": "Aprovação técnica (CREA)",
    "order": 10,
    "required": True,
    "approver_capability": "approval.request_remote",
    "is_builtin": True,
}
_COMMERCIAL = {
    "key": "commercial",
    "label": "Aprovação comercial",
    "order": 20,
    "required": True,
    "approver_capability": "approval.commercial_sign",
    "is_builtin": False,
}
_QUALITY = {
    "key": "quality",
    "label": "Aprovação de qualidade",
    "order": 30,
    "required": True,
    "approver_capability": "approval.quality_sign",
    "is_builtin": False,
}

WORKFLOW_TEMPLATES = [
    {
        "key": "technical_only",
        "name": "Só técnica (CREA)",
        "description": "Comportamento padrão: só a aprovação técnica com CREA gateia a conversão.",
        "stages": [_TECHNICAL],
    },
    {
        "key": "tech_commercial",
        "name": "Técnica + Comercial",
        "description": "Técnica (CREA) e depois uma aprovação comercial.",
        "stages": [_TECHNICAL, _COMMERCIAL],
    },
    {
        "key": "tech_comm_quality",
        "name": "Técnica + Comercial + Qualidade",
        "description": "Técnica, comercial e qualidade em sequência.",
        "stages": [_TECHNICAL, _COMMERCIAL, _QUALITY],
    },
    {
        "key": "blank",
        "name": "Do zero",
        "description": "Só a técnica travada; adicione os estágios manualmente.",
        "stages": [_TECHNICAL],
    },
]

# Slots de capability para estágios custom (do zero). Consumidos em ordem.
CUSTOM_SIGN_SLOTS = [
    "approval.custom_sign_1",
    "approval.custom_sign_2",
    "approval.custom_sign_3",
]


def workflow_templates():
    """Lista dos templates (para a UI)."""
    return WORKFLOW_TEMPLATES


def get_workflow_template(key):
    """Template pela `key`, ou None."""
    for tpl in WORKFLOW_TEMPLATES:
        if tpl["key"] == key:
            return tpl
    return None


def seed_workflow(*, wf_model=None, stage_model=None):
    """
    Idempotente: garante o fluxo default `of.convert` no schema ATIVO e anexa a ele
    qualquer ApprovalStage órfão (workflow nulo — estágios legados pré-M3).

    `wf_model`/`stage_model`: injeta os models históricos numa data migration.
    """
    if wf_model is None:
        from apps.access.models import ApprovalWorkflow as wf_model  # noqa: N806
    if stage_model is None:
        from apps.access.models import ApprovalStage as stage_model  # noqa: N806

    wf, _created = wf_model.objects.get_or_create(
        action_type="of.convert",
        defaults={"name": "Conversão em Ordem de Fabricação", "is_active": True},
    )
    stage_model.objects.filter(workflow__isnull=True).update(workflow=wf)
    return wf
