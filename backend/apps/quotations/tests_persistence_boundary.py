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

Padrões detectados (por função — `visit_FunctionDef` empilha o nome, então cada achado sabe
em que função apareceu):

  (i)   `<Model>.objects.{create,bulk_create,bulk_update,get_or_create,update_or_create}`
        para Model em {QuotationItem, ItemMaterial, ItemOperation, CalculationSnapshot}
        (sempre — essas linhas SÃO o resultado do motor); e cadeias `<Model>.objects....
        {update,delete}` para esses MESMOS models + Quotation (aqui via padrão iii-kwarg,
        que já filtra por Quotation ter um kwarg de campo de resultado — Quotation também
        é gravada por metadado puro, então só conta quando o campo é de resultado).
  (ii)  `.itens`, `.materiais` ou `.operacoes` (os related_names da EAP) seguidos de
        `create`, `delete`, `update` (ou variantes bulk/get_or_create/update_or_create) em
        qualquer ponto da cadeia — pega `quotation.itens.all().delete()`, por exemplo.
  (iii) atribuição (`x.campo = ...`) a um dos campos de resultado (custo_material, custo_mo,
        custo_total, preco_sem_impostos, preco_com_impostos, peso_bruto_kg, peso_liquido_kg,
        computed_at) — MODELO-AGNÓSTICO por nome de campo (ver limite conhecido, abaixo); e
        esses MESMOS nomes como kwarg de create/update/update_or_create/get_or_create/
        bulk_create/bulk_update — aqui SIM restrito a Model em {Quotation, QuotationItem,
        ItemMaterial, ItemOperation, CalculationSnapshot}, para não confundir com um model
        de OUTRO domínio que reusa o mesmo nome de campo por convenção (ver próximo
        parágrafo).

ACHADO durante a varredura, tratado (não escondido): `apps.production.services.
convert_quotation_to_of` cria OrdemFabricacao/OFItem/OFMaterial/OFOperation com kwargs
chamados custo_material/custo_mo/... — MESMOS nomes, modelos DIFERENTES. Não é uma violação:
a função nunca chama o motor (`pricing_engine.*`); ela copia valores já computados e já
ASSINADOS do CalculationSnapshot (a fonte de verdade pós-aprovação — comentário 'M1.1' no
próprio código) para um model de OUTRO domínio (produção), depois que a cotação já saiu da
EAP. Por isso o padrão (iii)-kwarg é restrito aos 5 models da EAP: sem essa restrição o
scanner falso-positivaria em qualquer model de negócio que reuse os mesmos nomes de campo.
A atribuição (iii)-assign (`x.campo = valor`, sem create/update no mesmo nó) continua
model-agnóstica por nome — na varredura completa desta ordem, toda ocorrência real ficou
dentro de apps.quotations (nunca em outro app), o que é o motivo da não-restrição adicional
aqestampcolunas: implementar resolução de tipo por análise de dataflow é desproporcional ao
risco observado.

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

LIMITES CONHECIDOS (documentados, não resolvidos por este teste):
  - `setattr(obj, nome_dinamico, valor)` não é pego — o teste só entende `ast.Attribute`
    literal (`obj.campo = valor`), não indireção por string.
  - `obj.save()` SEM atribuição visível na mesma função (ex.: campo mutado antes, em outra
    função, e só `.save()` aparece aqui) não aponta o autor da escrita — o teste aponta a
    ATRIBUIÇÃO, não o commit no banco.
  - Resolução de "a que Model esta variável pertence" é heurística (nome da classe no
    `.objects.<Model>` ou no construtor), não dataflow: um alias (`M = QuotationItem; M.
    objects.create(...)`) escaparia. Não observado no código atual.
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
RELATED_WRITE_METHODS = {"create", "delete", "update", "bulk_create", "get_or_create", "update_or_create"}
OBJECTS_WRITE_METHODS = {"create", "bulk_create", "bulk_update", "get_or_create", "update_or_create",
                          "update", "delete"}
CREATE_UPDATE_METHODS = {"create", "update", "update_or_create", "get_or_create", "bulk_create", "bulk_update"}
FIELD_NAMES = {"custo_material", "custo_mo", "custo_total", "preco_sem_impostos",
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


class Finding(NamedTuple):
    module: str
    func: str
    lineno: int
    pattern: str
    detail: str

    def __repr__(self):
        return f"{self.module}:{self.lineno} em {self.func}() [{self.pattern}] {self.detail}"


class _EapWriteVisitor(ast.NodeVisitor):
    """Varre um módulo em busca dos padrões (i)/(ii)/(iii) — ver docstring do arquivo."""

    def __init__(self, module: str):
        self.module = module
        self._stack = []
        self.findings: list[Finding] = []

    def _qualname(self) -> str:
        return ".".join(self._stack) if self._stack else "<module>"

    def _add(self, node, pattern, detail):
        self.findings.append(Finding(self.module, self._qualname(), node.lineno, pattern, detail))

    def visit_FunctionDef(self, node):
        self._stack.append(node.name)
        self.generic_visit(node)
        self._stack.pop()

    visit_AsyncFunctionDef = visit_FunctionDef

    def visit_ClassDef(self, node):
        self._stack.append(node.name)
        self.generic_visit(node)
        self._stack.pop()

    def _check_objects_and_related_chains(self, node, outer_method, attrs, root_name):
        if ("objects" in attrs and root_name in EAP_RESULT_MODELS
                and outer_method in OBJECTS_WRITE_METHODS):
            self._add(node, "i", f"{root_name}.objects.{outer_method}(...)")
        if (any(a in RELATED_MANAGERS for a in attrs) and outer_method in RELATED_WRITE_METHODS):
            rel = next(a for a in attrs if a in RELATED_MANAGERS)
            self._add(node, "ii", f".{rel}. ... .{outer_method}(...)")
        return root_name

    def _check_result_kwargs(self, node, outer_method, root_name):
        if outer_method not in CREATE_UPDATE_METHODS or root_name not in EAP_MODELS_ALL:
            return
        for kw in node.keywords:
            if kw.arg in FIELD_NAMES:
                self._add(node, "iii-kwarg", f"{root_name}.{outer_method}(..., {kw.arg}=...)")

    def visit_Call(self, node):
        if isinstance(node.func, ast.Attribute):
            outer_method = node.func.attr
            attrs, root_name = _unwrap_call_chain(node.func.value)
            self._check_objects_and_related_chains(node, outer_method, attrs, root_name)
            self._check_result_kwargs(node, outer_method, root_name)
        elif isinstance(node.func, ast.Name) and node.func.id in EAP_MODELS_ALL:
            for kw in node.keywords:
                if kw.arg in FIELD_NAMES:
                    self._add(node, "iii-kwarg", f"{node.func.id}(..., {kw.arg}=...)")
        self.generic_visit(node)

    def visit_Assign(self, node):
        for target in node.targets:
            if isinstance(target, ast.Attribute) and target.attr in FIELD_NAMES:
                self._add(node, "iii-assign", f"...{target.attr} = ...")
        self.generic_visit(node)

    def visit_AugAssign(self, node):
        if isinstance(node.target, ast.Attribute) and node.target.attr in FIELD_NAMES:
            self._add(node, "iii-assign", f"...{node.target.attr} {ast.dump(node.op)}= ...")
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
    """Autoteste com fonte SINTÉTICA: prova que cada padrão (i)/(ii)/(iii) é detectado, e
    que os controles negativos (metadado puro, model de outro domínio) NÃO disparam."""

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

    def test_padrao_iii_assign(self):
        findings = _scan_source(
            "def f(quotation):\n"
            "    quotation.custo_total = Decimal('1')\n"
        )
        self.assertTrue(any(f.pattern == "iii-assign" for f in findings), findings)

    def test_padrao_iii_kwarg_em_model_da_eap(self):
        findings = _scan_source(
            "def f():\n"
            "    Quotation.objects.create(title='X', custo_total=Decimal('1'))\n"
        )
        self.assertTrue(any(f.pattern == "iii-kwarg" for f in findings), findings)

    def test_negativo_metadado_puro_nao_dispara(self):
        findings = _scan_source(
            "def f():\n"
            "    Quotation.objects.create(title='X', status='draft', number='COT-1')\n"
        )
        self.assertEqual(findings, [])

    def test_negativo_kwarg_em_model_de_outro_dominio_nao_dispara(self):
        """Documenta a restrição deliberada do padrão (iii)-kwarg (ver docstring do
        módulo): OrdemFabricacao reusa os MESMOS nomes de campo por convenção de domínio,
        mas não é a EAP — copia um resultado JÁ assinado (CalculationSnapshot)."""
        findings = _scan_source(
            "def f():\n"
            "    OrdemFabricacao.objects.create(custo_total=Decimal('1'))\n"
        )
        self.assertEqual(findings, [])

    def test_achados_carregam_a_funcao_de_origem(self):
        findings = _scan_source(
            "class Foo:\n"
            "    def bar(self):\n"
            "        QuotationItem.objects.create(codigo_item='X')\n"
        )
        self.assertEqual([f.func for f in findings if f.pattern == "i"], ["Foo.bar"])
