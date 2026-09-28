"""
Teste ESTRUTURAL (ordem 005): prova, por AST — sem rodar Django nem banco — que só o
adapter (e a allowlist nomeada abaixo) escreve RESULTADO na EAP (Quotation/QuotationItem/
ItemMaterial/ItemOperation/CalculationSnapshot). Companheiro mecânico do contrato de
import-linter "so-o-adapter-persiste" (.importlinter): aquele trava QUEM PODE IMPORTAR o
motor; este trava QUEM ESCREVE o resultado nos models da EAP, incluindo escritas que não
passam pelo motor nenhuma vez (overrides manuais do drawer).

O que é varrido: todo `backend/apps/**/*.py`, EXCETO `tests*.py`/`test_*.py` (fixtures de
teste chamam o motor/adapter direto, de propósito — não é caminho de produção) e
`migrations/` (não escrevem resultado, só schema).

CAMPOS DE RESULTADO por model (`RESULT_FIELDS`, lido de `apps/quotations/models.py`):
  - Quotation: os totais (custo_material, custo_mo, custo_total, preco_sem_impostos,
    preco_com_impostos, peso_bruto_kg, peso_liquido_kg, computed_at) + fator_preco,
    impostos_pct, avisos (proveniência/validação do resultado, não metadado comercial).
  - QuotationItem: custo_material, custo_mo.
  - ItemMaterial: peso_bruto_kg, peso_liquido_kg, preco_kgf, custo.
  - ItemOperation: custo, horas_hh, horas_hm, taxa_hora, taxa_hora_hm e as *_sugerida,
    aplicavel, origem.
  - CalculationSnapshot: snapshot_hash, inputs, outputs, engine_version, standard_refs.
`status`, `title`, `inputs` (do data sheet), `number`, `revision`, `scope`, `created_by`
etc. NÃO entram — são metadado, não resultado do motor (Quotation também é gravada por
metadado puro: quotation_set_status, quotation_update_meta).

RESOLUÇÃO DE MODEL (para não confundir campo de mesmo nome em OUTRO model): o teste
resolve, por função, um mapa {variável: Model} best-effort a partir de:
  - construtor direto `Model(...)`;
  - `Model.objects.{create,get,first,last}(...)` e `get_object_or_404(Model, ...)`;
  - `for x in <alguma_coisa>.itens/.materiais/.operacoes...:` (x vira QuotationItem/
    ItemMaterial/ItemOperation);
  - `self`, dentro de um método de uma classe que É um dos 5 models (ex.:
    `ItemOperation.recalc_custo`: `self.custo = ...` é `ItemOperation.custo`).
Quando a variável resolve, a checagem usa o conjunto de campos DESSE model (preciso).
Quando NÃO resolve, cai num conjunto REDUZIDO e mais "óbvio" (só os nomes compostos —
custo_material, custo_mo, custo_total, preco_sem_impostos, preco_com_impostos,
peso_bruto_kg, peso_liquido_kg, computed_at) para não falso-positivar em nomes genéricos
(custo, origem, aplicavel, avisos, horas_hh...) usados por OUTRO model em outro app.

Padrões detectados (por função — `visit_FunctionDef` empilha o nome, então cada achado sabe
em que função apareceu):

  (i)    `<Model>.objects.{create,bulk_create,bulk_update,get_or_create,update_or_create}`
         para Model em {QuotationItem, ItemMaterial, ItemOperation, CalculationSnapshot}
         (SEMPRE — essas linhas SÃO o resultado do motor, com ou sem kwarg nomeado); e
         cadeias `<Model>.objects....{update,delete}` para esses MESMOS models.
  (ii)   `.itens`, `.materiais` ou `.operacoes` (os related_names da EAP) seguidos de
         `create`, `delete`, `update` (ou variantes bulk/get_or_create/update_or_create)
         em qualquer ponto da cadeia — pega `quotation.itens.all().delete()`.
  (iii)  atribuição (`x.campo = ...`) ou `+=`/`-=`/etc. a um campo de RESULT_FIELDS do
         model resolvido para `x` (ou do conjunto reduzido, se `x` não resolve).
  (iv)   kwarg de create/update/update_or_create/get_or_create/bulk_create/bulk_update
         (inclusive construtor direto `Model(...)`) batendo em RESULT_FIELDS do model —
         para Quotation TAMBÉM (não só os 4 sempre-flagados), já que Quotation é gravada
         por metadado puro e só o campo de RESULTADO desqualifica isso; e um `**kwargs`
         (kw.arg is None, "splat") em create/update de qualquer um dos 5 models é
         SEMPRE suspeito (não dá para verificar estaticamente o que entra no dict).
  (v)    `Model(...)` (construtor direto, sem `.objects`) atribuído a uma variável e
         essa variável chamando `.save(...)` depois, na MESMA função — jeito alternativo
         de fazer o que `.objects.create()` faz, e pattern (i) só olha `.objects`.
  (vi)   `.delete()` chamado numa variável resolvida para um dos 5 models (via `.objects.
         get/create/first/last`, construtor ou `self`) — deleção de uma linha da EAP.

ACHADO durante a varredura, tratado (não escondido): `apps.production.services.
convert_quotation_to_of` cria OrdemFabricacao/OFItem/OFMaterial/OFOperation com kwargs
chamados custo_material/custo_mo/... — MESMOS nomes, modelos DIFERENTES. Não é uma violação:
a função nunca chama o motor (`pricing_engine.*`); ela copia valores já computados e já
ASSINADOS do CalculationSnapshot (a fonte de verdade pós-aprovação — comentário 'M1.1' no
próprio código) para um model de OUTRO domínio (produção), depois que a cotação já saiu da
EAP. Por isso o padrão (iv) é restrito aos 5 models da EAP (resolvidos por nome de classe no
próprio nó, sem ambiguidade — `OrdemFabricacao`/`OFItem`/`OFMaterial`/`OFOperation` não estão
em `EAP_MODELS_ALL`).

SEGUNDO ACHADO (varredura ampliada da revisão do Opus), também tratado: incluir
`fator_preco`/`impostos_pct` em `RESULT_FIELDS["Quotation"]` (porque em `persist_complete`
eles VÊM do resultado do motor — `resultado.get("fator_preco", 1)`) fez a varredura acender
`apps.quotations.views.quotation_edit` e o ramo não-"complete" de `quotation_revise`: os
dois fazem `Quotation.objects.create(fator_preco=orig.fator_preco, impostos_pct=orig.
impostos_pct, ...)` antes de chamar `adapter.recompute()`. NÃO é uma segunda via de
persistência do resultado: é CARREGAR ADIANTE o valor de CONFIG da cotação anterior para o
rascunho novo (mesmo padrão do resto do `Quotation.objects.create(...)` ali — `scope`,
`customer`, `inputs`); quem grava o CUSTO/PREÇO de verdade continua sendo só o
`recompute()` chamado logo em seguida, dentro do adapter. `_is_same_field_passthrough`
isenta especificamente esse formato (`campo=outra_instância.campo`, o MESMO nome dos dois
lados) — um copiar-adiante provadamente não-computado — sem isentar
`fator_preco=resultado.get(...)` (persist_complete), que continua detectado.

ALLOWLIST (por módulo, ou módulo+função; cada entrada tem o motivo):
  - apps.quotations.adapter (módulo inteiro): É o adapter — o único caminho que persiste
    resultado do motor pela regra do INTENT v3 §Limites (mesma trava do import-linter
    "so-o-adapter-persiste", contrato C2, ordem 004/005).
  - apps.quotations.services.create_calculation_snapshot: grava o REGISTRO
    (CalculationSnapshot) do resultado que o adapter JÁ computou — não computa nada novo,
    é o payload assinável, não uma segunda fonte de cálculo.
  - apps.quotations.views.eap_item_save / .eap_op_restore / ._rollup_peso: override manual
    do drawer EAP — grava ajuste do orçamentista DIRETO nas linhas (ou desfaz o ajuste,
    restaurando a sugestão já persistida nas colunas *_sugerida), por design SEM chamar o
    motor e SEM criar revisão (guardrail documentado nas próprias funções, Tela 05 item 4).
    `_rollup_peso` é o ressoma de peso chamado por ambas.
  - apps.quotations.models.ItemOperation.recalc_custo: `self.custo = horas × taxa;
    self.save(update_fields=["custo"])` — é o PRÓPRIO model derivando seu campo a partir
    de horas/taxa já gravadas na linha. Só é chamado de dois lugares, os dois JÁ
    allowlisted acima (eap_item_save, eap_op_restore) — não é uma segunda via de escrita,
    é a MESMA (o override manual delega ao model o cálculo de horas×taxa). Confirmado por
    grep: nenhum outro caller em código de produção.

LIMITES CONHECIDOS (documentados, não resolvidos por este teste):
  - `setattr(obj, nome_dinamico, valor)` não é pego — o teste só entende `ast.Attribute`
    literal (`obj.campo = valor`), não indireção por string.
  - `obj.save()` SEM atribuição visível na mesma função (ex.: campo mutado antes, em outra
    função, e só `.save()` aparece aqui) não aponta o autor da escrita — o teste aponta a
    ATRIBUIÇÃO/kwarg, não o commit no banco (exceção: o padrão (v), construtor+save, que
    não precisa ver o campo).
  - Resolução de "a que Model esta variável pertence" é heurística, função a função (sem
    dataflow entre funções, sem seguir retorno de função auxiliar que devolve a instância,
    sem entender alias de classe: `M = QuotationItem; M.objects.create(...)` escaparia).
    Quando não resolve, cai no conjunto reduzido (só nomes compostos, ver acima) — o que
    pode deixar passar uma atribuição de campo genérico (`origem`, `aplicavel`, `custo`)
    numa variável não resolvida. Não observado no código atual (ver varredura da ordem 005).
"""
import ast
import os
import unittest
from typing import NamedTuple

from django.test import SimpleTestCase

APPS_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BACKEND_DIR = os.path.dirname(APPS_DIR)

EAP_RESULT_MODELS = {"QuotationItem", "ItemMaterial", "ItemOperation", "CalculationSnapshot"}
EAP_MODELS_ALL = EAP_RESULT_MODELS | {"Quotation"}
RELATED_MANAGERS = {"itens", "materiais", "operacoes"}
RELATED_MODEL_OF_MANAGER = {"itens": "QuotationItem", "materiais": "ItemMaterial", "operacoes": "ItemOperation"}
RELATED_WRITE_METHODS = {"create", "delete", "update", "bulk_create", "get_or_create", "update_or_create"}
OBJECTS_WRITE_METHODS = {"create", "bulk_create", "bulk_update", "get_or_create", "update_or_create",
                          "update", "delete"}
CREATE_UPDATE_METHODS = {"create", "update", "update_or_create", "get_or_create", "bulk_create", "bulk_update"}
# métodos de manager que devolvem (ou plausivelmente devolvem) UMA instância — usados para
# resolver {variável: Model} best-effort (padrões iii/v/vi).
SINGLE_INSTANCE_METHODS = {"create", "get", "first", "last"}

# Campos de RESULTADO por model (ver docstring). Fonte: apps/quotations/models.py.
RESULT_FIELDS = {
    "Quotation": {
        "custo_material", "custo_mo", "custo_total", "preco_sem_impostos", "preco_com_impostos",
        "peso_bruto_kg", "peso_liquido_kg", "computed_at", "fator_preco", "impostos_pct", "avisos",
    },
    "QuotationItem": {"custo_material", "custo_mo"},
    "ItemMaterial": {"peso_bruto_kg", "peso_liquido_kg", "preco_kgf", "custo"},
    "ItemOperation": {
        "custo", "horas_hh", "horas_hm", "taxa_hora", "taxa_hora_hm",
        "horas_hh_sugerida", "horas_hm_sugerida", "taxa_hora_sugerida", "taxa_hora_hm_sugerida",
        "aplicavel", "origem",
    },
    "CalculationSnapshot": {"snapshot_hash", "inputs", "outputs", "engine_version", "standard_refs"},
}
# conjunto reduzido p/ quando a variável NÃO resolve a um model (só nomes compostos,
# improváveis em outro domínio) — ver "LIMITES CONHECIDOS".
UNRESOLVED_FALLBACK_FIELDS = {"custo_material", "custo_mo", "custo_total", "preco_sem_impostos",
                              "preco_com_impostos", "peso_bruto_kg", "peso_liquido_kg", "computed_at"}

# (módulo -> {"*"} | {nomes de função}) -> motivo. Ver docstring do módulo.
ALLOWLIST = {
    "apps.quotations.adapter": {
        "*": "único caminho que persiste resultado do motor (INTENT v3 §Limites; mesma "
             "trava do import-linter so-o-adapter-persiste).",
    },
    "apps.quotations.services": {
        "create_calculation_snapshot": "grava o REGISTRO do resultado já computado pelo "
                                        "adapter — não computa nada novo.",
    },
    "apps.quotations.views": {
        "eap_item_save": "override manual do drawer EAP — grava ajuste do orçamentista "
                          "direto nas linhas, sem chamar o motor (guardrail documentado).",
        "eap_op_restore": "desfaz o override manual (restaura *_sugerida já persistida) — "
                           "mesmo guardrail de eap_item_save.",
        "_rollup_peso": "ressoma peso_bruto/liquido_kg das linhas de material após um "
                         "override manual — soma, não recálculo do motor.",
    },
    "apps.quotations.models": {
        "ItemOperation.recalc_custo": "o próprio model derivando custo=horas×taxa a partir "
            "de campos já gravados na linha; só chamado por eap_item_save/eap_op_restore "
            "(já allowlisted) — mesmo override manual, não uma segunda via.",
    },
}


def _module_name(path: str) -> str:
    rel = os.path.relpath(path, BACKEND_DIR)
    return rel[:-len(".py")].replace(os.sep, ".")


def _is_test_or_migration(path: str) -> bool:
    parts = path.split(os.sep)
    if "migrations" in parts:
        return True
    base = os.path.basename(path)
    return base == "tests.py" or base.startswith("tests_") or base.startswith("test_")


def _iter_scanned_files():
    for dirpath, dirnames, filenames in os.walk(APPS_DIR):
        dirnames[:] = [d for d in dirnames if d not in ("migrations", "__pycache__")]
        for fn in filenames:
            if not fn.endswith(".py"):
                continue
            path = os.path.join(dirpath, fn)
            if _is_test_or_migration(path):
                continue
            yield path


def _unwrap_call_chain(node):
    """Desce por .value/.func a partir do node inicial, coletando os `.attr` vistos e o
    Name raiz (se houver). Usado para achar `<Model>.objects....<método>` e
    `<obj>.itens....<método>` independente de quantos `.filter()/.all()` vierem no meio."""
    attrs = []
    root_name = None
    while True:
        if isinstance(node, ast.Call):
            node = node.func
        elif isinstance(node, ast.Attribute):
            attrs.append(node.attr)
            node = node.value
        elif isinstance(node, ast.Name):
            root_name = node.id
            break
        else:
            break
    return attrs, root_name


def _is_same_field_passthrough(kw: ast.keyword) -> bool:
    """`fator_preco=orig.fator_preco` (o valor é um atributo de OUTRO objeto com o MESMO
    nome do kwarg) é carregar um valor de CONFIG adiante para uma revisão nova — não é
    computar um resultado. Achado real da ordem 005 (revisão do Opus): quotation_edit e
    o ramo não-'complete' de quotation_revise fazem exatamente isso com fator_preco/
    impostos_pct antes de chamar adapter.recompute() — que é quem persiste o resultado de
    verdade. Isolado aqui (não é um "sempre ignora X"): só isenta o formato específico de
    passthrough, então `fator_preco=resultado.get("fator_preco")` (persist_complete, onde
    o valor VEM do motor) continua batendo."""
    return isinstance(kw.value, ast.Attribute) and kw.value.attr == kw.arg


def _resolve_call_to_model(call: ast.Call):
    """Se `call` plausivelmente devolve UMA instância de um dos 5 models da EAP, devolve
    (model, via_ctor). via_ctor=True só para o construtor direto `Model(...)` (sem
    `.objects`) — é o que distingue o padrão (v) (ctor + save)."""
    if isinstance(call.func, ast.Name) and call.func.id in EAP_MODELS_ALL:
        return call.func.id, True
    if isinstance(call.func, ast.Attribute):
        outer_method = call.func.attr
        attrs, root_name = _unwrap_call_chain(call.func.value)
        if "objects" in attrs and root_name in EAP_MODELS_ALL and outer_method in SINGLE_INSTANCE_METHODS:
            return root_name, False
    # get_object_or_404(Model, ...) / get_object_or_404(Model, pk=pk)
    if (isinstance(call.func, ast.Name) and call.func.id == "get_object_or_404"
            and call.args and isinstance(call.args[0], ast.Name) and call.args[0].id in EAP_MODELS_ALL):
        return call.args[0].id, False
    return None, False


class Finding(NamedTuple):
    module: str
    func: str
    lineno: int
    pattern: str
    detail: str

    def __repr__(self):
        return f"{self.module}:{self.lineno} em {self.func}() [{self.pattern}] {self.detail}"


class _Scope:
    """Estado por função: nome da variável -> (model, via_ctor). Empilhado/desempilhado
    junto com FunctionDef (sem dataflow entre funções, de propósito — ver LIMITES)."""

    def __init__(self, self_model=None):
        self.var_models: dict[str, tuple[str, bool]] = {}
        if self_model:
            self.var_models["self"] = (self_model, False)

    def resolve(self, name: str):
        return self.var_models.get(name)


class _EapWriteVisitor(ast.NodeVisitor):
    """Varre um módulo em busca dos padrões (i)-(vi) — ver docstring do arquivo."""

    def __init__(self, module: str):
        self.module = module
        self._name_stack: list[str] = []
        self._class_stack: list[str] = []
        self._scopes: list[_Scope] = []
        self.findings: list[Finding] = []

    def _qualname(self) -> str:
        return ".".join(self._name_stack) if self._name_stack else "<module>"

    def _add(self, node, pattern, detail):
        self.findings.append(Finding(self.module, self._qualname(), node.lineno, pattern, detail))

    def _scope(self) -> _Scope:
        return self._scopes[-1] if self._scopes else _Scope()

    def visit_ClassDef(self, node):
        self._name_stack.append(node.name)
        self._class_stack.append(node.name)
        self.generic_visit(node)
        self._class_stack.pop()
        self._name_stack.pop()

    def visit_FunctionDef(self, node):
        self._name_stack.append(node.name)
        enclosing_class = self._class_stack[-1] if self._class_stack else None
        self_model = enclosing_class if enclosing_class in EAP_MODELS_ALL else None
        is_method = bool(node.args.args) and node.args.args[0].arg == "self"
        self._scopes.append(_Scope(self_model=self_model if is_method else None))
        self.generic_visit(node)
        self._scopes.pop()
        self._name_stack.pop()

    visit_AsyncFunctionDef = visit_FunctionDef

    # ---- padrões (i)/(ii): .objects.<escrita> e .itens/.materiais/.operacoes.<escrita> ----
    def _check_objects_and_related_chains(self, node, outer_method, attrs, root_name):
        if ("objects" in attrs and root_name in EAP_RESULT_MODELS
                and outer_method in OBJECTS_WRITE_METHODS):
            self._add(node, "i", f"{root_name}.objects.{outer_method}(...)")
        if any(a in RELATED_MANAGERS for a in attrs) and outer_method in RELATED_WRITE_METHODS:
            rel = next(a for a in attrs if a in RELATED_MANAGERS)
            self._add(node, "ii", f".{rel}. ... .{outer_method}(...)")

    # ---- padrão (iv): kwarg de resultado (ou **splat) em create/update/ctor ----
    def _check_result_kwargs(self, node, outer_method, root_name, via_ctor=False):
        if root_name not in EAP_MODELS_ALL:
            return
        if not via_ctor and outer_method not in CREATE_UPDATE_METHODS:
            return
        campos = RESULT_FIELDS.get(root_name, set())
        for kw in node.keywords:
            if kw.arg is None:
                self._add(node, "iv-splat", f"{root_name}(**...) — kwargs dinâmico, não dá p/ verificar")
            elif kw.arg in campos and not _is_same_field_passthrough(kw):
                self._add(node, "iv-kwarg", f"{root_name}(..., {kw.arg}=...)")

    def visit_Call(self, node):
        if isinstance(node.func, ast.Attribute):
            outer_method = node.func.attr
            attrs, root_name = _unwrap_call_chain(node.func.value)
            self._check_objects_and_related_chains(node, outer_method, attrs, root_name)
            self._check_result_kwargs(node, outer_method, root_name)
            # padrão (vi): <var>.delete() numa variável resolvida p/ um dos 5 models.
            if outer_method == "delete" and isinstance(node.func.value, ast.Name):
                resolved = self._scope().resolve(node.func.value.id)
                if resolved:
                    self._add(node, "vi-delete", f"{node.func.value.id}:{resolved[0]}.delete()")
            # padrão (v): <var>.save() numa variável que veio de um construtor DIRETO.
            if outer_method == "save" and isinstance(node.func.value, ast.Name):
                resolved = self._scope().resolve(node.func.value.id)
                if resolved and resolved[1]:
                    self._add(node, "v-ctor-save",
                              f"{resolved[0]}(...) -> {node.func.value.id}.save(...)")
        elif isinstance(node.func, ast.Name) and node.func.id in EAP_MODELS_ALL:
            self._check_result_kwargs(node, "", node.func.id, via_ctor=True)
        self.generic_visit(node)

    # ---- resolução best-effort de {variável: Model}, p/ precisão do padrão (iii) ----
    def _maybe_track_assignment(self, target, value):
        if not isinstance(target, ast.Name):
            return
        if isinstance(value, ast.Call):
            model, via_ctor = _resolve_call_to_model(value)
            if model:
                self._scope().var_models[target.id] = (model, via_ctor)

    def visit_Assign(self, node):
        campos_por_alvo = []
        for target in node.targets:
            if isinstance(target, ast.Attribute) and isinstance(target.value, ast.Name):
                resolved = self._scope().resolve(target.value.id)
                campos_por_alvo.append((target, resolved))
            if len(node.targets) == 1:
                self._maybe_track_assignment(target, node.value)
        for target, resolved in campos_por_alvo:
            self._check_attr_write(node, target, resolved)
        self.generic_visit(node)

    def visit_AugAssign(self, node):
        if isinstance(node.target, ast.Attribute) and isinstance(node.target.value, ast.Name):
            resolved = self._scope().resolve(node.target.value.id)
            self._check_attr_write(node, node.target, resolved, op=ast.dump(node.op))
        self.generic_visit(node)

    def _check_attr_write(self, node, target: ast.Attribute, resolved, op="="):
        if resolved:
            model, _ = resolved
            if target.attr in RESULT_FIELDS.get(model, set()):
                self._add(node, "iii-assign", f"...{target.attr} {op}= ... [{model}]")
        elif target.attr in UNRESOLVED_FALLBACK_FIELDS:
            self._add(node, "iii-assign", f"...{target.attr} {op}= ... [model não resolvido]")

    # ---- padrão best-effort: `for x in <...>.itens/.materiais/.operacoes...:` ----
    def visit_For(self, node):
        if isinstance(node.target, ast.Name):
            attrs, _root = _unwrap_call_chain(node.iter)
            rel = next((a for a in attrs if a in RELATED_MANAGERS), None)
            if rel:
                self._scope().var_models[node.target.id] = (RELATED_MODEL_OF_MANAGER[rel], False)
        self.generic_visit(node)


def _scan_source(src: str, module: str = "<synthetic>") -> list[Finding]:
    tree = ast.parse(src)
    visitor = _EapWriteVisitor(module)
    visitor.visit(tree)
    return visitor.findings


def _scan_codebase() -> list[Finding]:
    findings = []
    for path in _iter_scanned_files():
        with open(path, encoding="utf-8") as fh:
            src = fh.read()
        findings.extend(_scan_source(src, module=_module_name(path)))
    return findings


def _is_allowed(finding: Finding, used: set) -> bool:
    entry = ALLOWLIST.get(finding.module)
    if entry is None:
        return False
    if "*" in entry:
        used.add((finding.module, "*"))
        return True
    if finding.func in entry:
        used.add((finding.module, finding.func))
        return True
    return False


class SoOAdapterEscreveResultadoDaEapTests(SimpleTestCase):
    """Contraparte estrutural do contrato de import-linter (ver docstring do módulo)."""

    def test_nenhuma_escrita_de_resultado_fora_da_allowlist(self):
        findings = _scan_codebase()
        used = set()
        fora_da_allowlist = [f for f in findings if not _is_allowed(f, used)]
        self.assertEqual(
            fora_da_allowlist, [],
            "Escrita de resultado da EAP fora do adapter e fora da allowlist nomeada — "
            "PARE e relate, não esconda na allowlist:\n"
            + "\n".join(f"  {f!r}" for f in fora_da_allowlist),
        )

    def test_allowlist_sem_entrada_orfa(self):
        """Toda entrada da allowlist tem de corresponder a pelo menos um achado real —
        senão a permissão sobrevive ao código que a justificava (ordem 005: exigido)."""
        findings = _scan_codebase()
        used = set()
        for f in findings:
            _is_allowed(f, used)
        esperadas = {
            (modulo, chave)
            for modulo, funcs in ALLOWLIST.items()
            for chave in funcs
        }
        orfas = esperadas - used
        self.assertEqual(
            orfas, set(),
            f"Entrada(s) da allowlist sem achado correspondente (remova): {sorted(orfas)}",
        )


class ScannerAutoTesteTests(unittest.TestCase):
    """Autoteste com fonte SINTÉTICA: prova que cada padrão (i)-(vi) é detectado, e que os
    controles negativos (metadado puro, model de outro domínio, variável não resolvida com
    campo genérico) NÃO disparam."""

    def test_padrao_i_objects_create_em_model_da_eap(self):
        findings = _scan_source(
            "def f():\n"
            "    QuotationItem.objects.create(codigo_item='X')\n"
        )
        self.assertTrue(any(f.pattern == "i" for f in findings), findings)

    def test_padrao_i_objects_update_chain(self):
        findings = _scan_source(
            "def f():\n"
            "    ItemOperation.objects.filter(pk=1).update(custo=Decimal('1'))\n"
        )
        self.assertTrue(any(f.pattern == "i" for f in findings), findings)

    def test_padrao_ii_related_manager_delete(self):
        findings = _scan_source(
            "def f(quotation):\n"
            "    quotation.itens.all().delete()\n"
        )
        self.assertTrue(any(f.pattern == "ii" for f in findings), findings)

    def test_padrao_ii_related_manager_create(self):
        findings = _scan_source(
            "def f(item):\n"
            "    item.materiais.create(codigo_mp='X')\n"
        )
        self.assertTrue(any(f.pattern == "ii" for f in findings), findings)

    def test_padrao_iii_assign_sem_resolver_variavel(self):
        findings = _scan_source(
            "def f(quotation):\n"
            "    quotation.custo_total = Decimal('1')\n"
        )
        self.assertTrue(any(f.pattern == "iii-assign" for f in findings), findings)

    def test_padrao_iii_assign_resolvido_por_for_in_related_manager(self):
        """Prova concreta pedida na revisão: `self.custo = ...` dentro de um MÉTODO de
        ItemOperation precisa ser detectado (ItemOperation.recalc_custo)."""
        findings = _scan_source(
            "class ItemOperation:\n"
            "    def recalc_custo(self):\n"
            "        self.custo = self.horas_hh * self.taxa_hora\n"
            "        self.save(update_fields=['custo'])\n"
        )
        self.assertTrue(any(f.pattern == "iii-assign" and f.func == "ItemOperation.recalc_custo"
                            for f in findings), findings)

    def test_padrao_iii_assign_resolvido_por_for_em_materiais(self):
        findings = _scan_source(
            "def f(item):\n"
            "    for mat in item.materiais.all():\n"
            "        mat.peso_bruto_kg = Decimal('1')\n"
        )
        self.assertTrue(any(f.pattern == "iii-assign" and "ItemMaterial" in f.detail
                            for f in findings), findings)

    def test_padrao_iii_augassign(self):
        findings = _scan_source(
            "def f(quotation):\n"
            "    quotation.custo_total += Decimal('1')\n"
        )
        self.assertTrue(any(f.pattern == "iii-assign" for f in findings), findings)

    def test_padrao_iv_kwarg_em_model_da_eap(self):
        findings = _scan_source(
            "def f():\n"
            "    Quotation.objects.create(title='X', custo_total=Decimal('1'))\n"
        )
        self.assertTrue(any(f.pattern == "iv-kwarg" for f in findings), findings)

    def test_padrao_iv_splat_em_model_da_eap_e_sempre_suspeito(self):
        findings = _scan_source(
            "def f(d):\n"
            "    Quotation.objects.create(**d)\n"
        )
        self.assertTrue(any(f.pattern == "iv-splat" for f in findings), findings)

    def test_padrao_v_construtor_direto_mais_save(self):
        findings = _scan_source(
            "def f():\n"
            "    q = Quotation(custo_total=Decimal('1'))\n"
            "    q.save()\n"
        )
        self.assertTrue(any(f.pattern == "v-ctor-save" for f in findings), findings)
        # e também o kwarg do construtor, via padrão (iv):
        self.assertTrue(any(f.pattern == "iv-kwarg" for f in findings), findings)

    def test_padrao_vi_delete_de_instancia_resolvida(self):
        findings = _scan_source(
            "def f(pk):\n"
            "    mp = ItemMaterial.objects.get(pk=pk)\n"
            "    mp.delete()\n"
        )
        self.assertTrue(any(f.pattern == "vi-delete" for f in findings), findings)

    def test_negativo_passthrough_do_mesmo_campo_nao_dispara(self):
        """quotation_edit/quotation_revise (ramo feixe/parts) fazem `fator_preco=orig.
        fator_preco` antes de chamar adapter.recompute() — carregar CONFIG adiante, não
        computar. Achado real tratado na revisão do Opus (ver docstring do módulo)."""
        findings = _scan_source(
            "def f(orig):\n"
            "    Quotation.objects.create(fator_preco=orig.fator_preco,\n"
            "                             impostos_pct=orig.impostos_pct)\n"
        )
        self.assertEqual(findings, [])

    def test_padrao_iv_kwarg_de_resultado_do_motor_continua_detectado(self):
        """O passthrough NÃO isenta o formato onde o valor vem do resultado do motor
        (persist_complete: `fator_preco=resultado.get("fator_preco", 1)`)."""
        findings = _scan_source(
            "def f(resultado):\n"
            "    Quotation.objects.create(fator_preco=resultado.get('fator_preco', 1))\n"
        )
        self.assertTrue(any(f.pattern == "iv-kwarg" for f in findings), findings)

    def test_negativo_metadado_puro_nao_dispara(self):
        findings = _scan_source(
            "def f():\n"
            "    Quotation.objects.create(title='X', status='draft', number='COT-1')\n"
        )
        self.assertEqual(findings, [])

    def test_negativo_kwarg_em_model_de_outro_dominio_nao_dispara(self):
        """Documenta a restrição deliberada do padrão (iv) (ver docstring do módulo):
        OrdemFabricacao reusa os MESMOS nomes de campo por convenção de domínio, mas não é
        a EAP — copia um resultado JÁ assinado (CalculationSnapshot)."""
        findings = _scan_source(
            "def f():\n"
            "    OrdemFabricacao.objects.create(custo_total=Decimal('1'))\n"
        )
        self.assertEqual(findings, [])

    def test_negativo_campo_generico_em_variavel_nao_resolvida_nao_dispara(self):
        """Limite deliberado (ver docstring): campo genérico (custo/origem/aplicavel) numa
        variável que o teste não conseguiu resolver a um dos 5 models não dispara — só os
        nomes compostos (UNRESOLVED_FALLBACK_FIELDS) dispara sem resolução."""
        findings = _scan_source(
            "def f(alguma_coisa_de_outro_dominio):\n"
            "    alguma_coisa_de_outro_dominio.custo = 1\n"
            "    alguma_coisa_de_outro_dominio.origem = 'x'\n"
        )
        self.assertEqual(findings, [])

    def test_negativo_delete_de_instancia_de_outro_model_nao_dispara(self):
        findings = _scan_source(
            "def f(pk):\n"
            "    of = OrdemFabricacao.objects.get(pk=pk)\n"
            "    of.delete()\n"
        )
        self.assertEqual(findings, [])

    def test_achados_carregam_a_funcao_de_origem(self):
        findings = _scan_source(
            "class Foo:\n"
            "    def bar(self):\n"
            "        QuotationItem.objects.create(codigo_item='X')\n"
        )
        self.assertEqual([f.func for f in findings if f.pattern == "i"], ["Foo.bar"])
