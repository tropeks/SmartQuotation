import ast
import importlib.util
import pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent
MODULE_PATH = ROOT / "tests" / "validate_permutador_completo.py"


def _load_gate_module():
    spec = importlib.util.spec_from_file_location("validate_permutador_completo", MODULE_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _check_geometria_call_sites():
    call_sites = {}
    for path in ROOT.rglob("*.py"):
        rel = path.relative_to(ROOT).as_posix()
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Assign):
                continue
            if not isinstance(node.value, ast.Call):
                continue
            func = node.value.func
            if not isinstance(func, ast.Name) or func.id != "check_geometria":
                continue
            target = node.targets[0]
            if isinstance(target, ast.Tuple):
                call_sites[rel] = len(target.elts)
            else:
                call_sites[rel] = None
    return call_sites


def test_check_geometria_call_sites_estao_auditados_e_desempacotam_3_valores():
    gate = _load_gate_module()
    atual = _check_geometria_call_sites()
    assert atual == gate.CHECK_GEOMETRIA_CALL_SITES_AUDIT
    assert all(n == 3 for n in atual.values())
