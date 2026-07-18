"""
Catálogo (registry) de CAPABILITIES do RBAC configurável.

Fonte da verdade do conjunto de permissões protegíveis, mantida em CÓDIGO
(não em banco). Cada capability tem um `code` estável usado pelos decoradores
(`require_capability`) e pelas flags de template (`user_can`). A matriz papel×
capability (quem PODE cada uma) vive no banco em `RolePermission`; este arquivo
apenas DECLARA o catálogo — análogo a `accounts.rbac.ROLE_GROUPS`/`ensure_groups`.

Regra fail-closed (T3/T8): um `code` referenciado por um decorator MAS ausente
deste registry é erro de deploy; um `code` do registry sem linha em RolePermission
resolve como negado (False).

Cada entrada: code -> {label, description, category, is_dangerous}.
- category: agrupa na UI de configuração.
- is_dangerous: sinaliza na UI capabilities sensíveis (segurança/dinheiro/
  irreversíveis). NÃO altera enforcement — é só metadado de apresentação.
"""

# Categorias (apenas rótulos de agrupamento para a UI).
CAT_QUOTATION = "quotation"
CAT_PRODUCTION = "production"
CAT_APPROVAL = "approval"
CAT_ENGINEERING = "engineering"
CAT_PROPOSAL = "proposal"
CAT_CATALOG = "catalog"
CAT_INTEGRATION = "integration"
CAT_ADMIN = "admin"


CAPABILITIES = {
    # ── Cotações ──────────────────────────────────────────────────────────
    "quotation.create": {
        "label": "Criar cotação",
        "description": "Iniciar uma nova cotação (entrada de dados).",
        "category": CAT_QUOTATION,
        "is_dangerous": False,
    },
    "quotation.write": {
        "label": "Editar cotação",
        "description": "Alterar itens, recalcular e salvar cotações existentes.",
        "category": CAT_QUOTATION,
        "is_dangerous": False,
    },
    "quotation.read": {
        "label": "Ver cotação",
        "description": "Visualizar cotações e seus detalhes.",
        "category": CAT_QUOTATION,
        "is_dangerous": False,
    },
    "quotation.price_api": {
        "label": "Precificar via API",
        "description": "Endpoints DRF de precificação/escrita de cotação.",
        "category": CAT_QUOTATION,
        "is_dangerous": False,
    },
    # ── Produção / Ordens de Fabricação ──────────────────────────────────
    "of.convert": {
        "label": "Converter em OF",
        "description": "Converter uma cotação aprovada em Ordem de Fabricação.",
        "category": CAT_PRODUCTION,
        "is_dangerous": False,
    },
    "of.transition": {
        "label": "Transicionar OF",
        "description": "Avançar o status de uma Ordem de Fabricação.",
        "category": CAT_PRODUCTION,
        "is_dangerous": False,
    },
    "itp.manage": {
        "label": "Gerenciar ITP",
        "description": "Criar/editar o Plano de Inspeção e Testes (ITP).",
        "category": CAT_PRODUCTION,
        "is_dangerous": False,
    },
    # ── Aprovações ───────────────────────────────────────────────────────
    "approval.request_remote": {
        "label": "Solicitar aprovação remota",
        "description": "Abrir pedido de aprovação técnica remota.",
        "category": CAT_APPROVAL,
        "is_dangerous": False,
    },
    "approval.request_presencial": {
        "label": "Aprovar presencialmente",
        "description": "Registrar aprovação presencial.",
        "category": CAT_APPROVAL,
        "is_dangerous": False,
    },
    "approval.panel_read": {
        "label": "Ver painel de aprovações",
        "description": "Consultar o painel de convertibilidade/aprovações.",
        "category": CAT_APPROVAL,
        "is_dangerous": False,
    },
    # ── Assinatura de estágios de aprovação (RBAC V2 — registry estático, M0) ──
    # Slots FIXOS de capabilities de assinatura. Ainda NÃO enforced (M0 é só o
    # catálogo + seed da matriz); o builder de fluxos (M3/M4) liga estes codes aos
    # estágios via ApprovalStage.approver_capability. O gate técnico CREA atual NÃO
    # muda em M0 — technical_sign só passa a valer com o trait requires_crea (M1).
    "approval.technical_sign": {
        "label": "Assinar aprovação técnica",
        "description": "Assinar o estágio técnico do fluxo (exigirá trait requires_crea + CREA na role — M1).",
        "category": CAT_APPROVAL,
        "is_dangerous": True,
    },
    "approval.commercial_sign": {
        "label": "Assinar aprovação comercial",
        "description": "Assinar o estágio comercial do fluxo (gestor/diretoria).",
        "category": CAT_APPROVAL,
        "is_dangerous": True,
    },
    "approval.quality_sign": {
        "label": "Assinar aprovação de qualidade",
        "description": "Assinar o estágio de qualidade (ITP/ISO em caldeiraria).",
        "category": CAT_APPROVAL,
        "is_dangerous": True,
    },
    "approval.custom_sign_1": {
        "label": "Assinar estágio custom 1",
        "description": "Slot de assinatura para estágio 'do zero' (o admin renomeia o label do estágio).",
        "category": CAT_APPROVAL,
        "is_dangerous": True,
    },
    "approval.custom_sign_2": {
        "label": "Assinar estágio custom 2",
        "description": "Slot de assinatura para estágio 'do zero' (o admin renomeia o label do estágio).",
        "category": CAT_APPROVAL,
        "is_dangerous": True,
    },
    "approval.custom_sign_3": {
        "label": "Assinar estágio custom 3",
        "description": "Slot de assinatura para estágio 'do zero' (o admin renomeia o label do estágio).",
        "category": CAT_APPROVAL,
        "is_dangerous": True,
    },
    # ── Engenharia (custeio / rates) ─────────────────────────────────────
    "cost_discovery.write": {
        "label": "Editar cadeia de custos",
        "description": "Wizard de descoberta de custos (cost discovery).",
        "category": CAT_ENGINEERING,
        "is_dangerous": True,
    },
    "rate.change": {
        "label": "Aplicar sugestões de rate",
        "description": "Aplicar/alterar rates de engenharia (sugestões).",
        "category": CAT_ENGINEERING,
        "is_dangerous": True,
    },
    "rate.edit": {
        "label": "Editar rate",
        "description": "Editar diretamente os valores de rate.",
        "category": CAT_ENGINEERING,
        "is_dangerous": True,
    },
    # ── Propostas ────────────────────────────────────────────────────────
    "proposal.write": {
        "label": "Editar proposta",
        "description": "Gerar/editar a proposta comercial (DOCX/PDF).",
        "category": CAT_PROPOSAL,
        "is_dangerous": False,
    },
    # ── Catálogos (TEMA / materiais) ─────────────────────────────────────
    "tema_template.write": {
        "label": "Editar template TEMA",
        "description": "Salvar data sheets / templates TEMA.",
        "category": CAT_CATALOG,
        "is_dangerous": False,
    },
    "material.read": {
        "label": "Ver materiais",
        "description": "Consultar o catálogo de materiais e preços.",
        "category": CAT_CATALOG,
        "is_dangerous": False,
    },
    "material.write": {
        "label": "Editar materiais/preços",
        "description": "Editar materiais e preços do catálogo.",
        "category": CAT_CATALOG,
        "is_dangerous": True,
    },
    # ── Integrações ──────────────────────────────────────────────────────
    "nomus.reexport": {
        "label": "Reexportar para Nomus",
        "description": "Reexportar dados para a integração Nomus.",
        "category": CAT_INTEGRATION,
        "is_dangerous": False,
    },
    # ── Administração do tenant ──────────────────────────────────────────
    "members.manage": {
        "label": "Gerenciar membros",
        "description": "Criar/editar/desativar usuários e papéis do tenant.",
        "category": CAT_ADMIN,
        "is_dangerous": True,
    },
    "access.manage": {
        "label": "Gerenciar permissões",
        "description": "Editar a matriz papel×capability e o fluxo de aprovações.",
        "category": CAT_ADMIN,
        "is_dangerous": True,
    },
    # RBAC V2 (M0): separa "criar/editar/excluir roles" de "editar a matriz"
    # (access.manage) — um admin pequeno pode delegar um sem o outro. Enforced a
    # partir da página "Papéis" (M2).
    "role.manage": {
        "label": "Gerenciar papéis",
        "description": "Criar, editar e excluir papéis do tenant (distinto de editar a matriz).",
        "category": CAT_ADMIN,
        "is_dangerous": True,
    },
}


def capability_codes():
    """Conjunto de todos os codes válidos do catálogo."""
    return set(CAPABILITIES.keys())


def is_known_capability(code):
    """True se `code` está no catálogo (fail-closed: desconhecido -> False)."""
    return code in CAPABILITIES


def ensure_capabilities():
    """
    Idempotente. O catálogo é registry-only (em código), portanto não há tabela
    a semear — esta função existe como ponto de extensão análogo a
    `accounts.rbac.ensure_groups()` e para validar a integridade do registry
    (codes não-vazios e únicos). Retorna o conjunto de codes conhecidos.

    NO-OP de persistência por design: a matriz de permissões (quem pode o quê)
    vive em `RolePermission`; o catálogo (o que EXISTE) vive aqui.
    """
    codes = list(CAPABILITIES.keys())
    assert codes, "CAPABILITIES não pode estar vazio."
    assert len(codes) == len(set(codes)), "codes de capability devem ser únicos."
    for code, meta in CAPABILITIES.items():
        assert code and isinstance(code, str), f"code inválido: {code!r}"
        assert meta.get("label"), f"capability {code} sem label."
        assert "category" in meta, f"capability {code} sem category."
    return set(codes)
