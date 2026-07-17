"""
Contrato dos lockfiles de dependência (stdlib puro — roda no job ops-tests do CI).

Achado /cso 2026-07-17: o repo não tinha lockfile e 7 das 18 deps diretas eram
flutuantes (`>=`), com a árvore transitiva inteiramente irrestrita. `docker build`
resolvia tudo na hora, então um release upstream comprometido entraria direto na
imagem de produção sem review, sem diff e sem forma de reconstruir o que uma imagem
anterior continha durante resposta a incidente.

Estes testes travam o contrato: os `.lock` existem, têm hashes, são consumidos com
`--require-hashes`, e não divergem das versões pinadas nos `.txt`.
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REQ = ROOT / "backend" / "requirements"
BASE_TXT = REQ / "base.txt"
BASE_LOCK = REQ / "base.lock"
CI_TXT = REQ / "ci.txt"
CI_LOCK = REQ / "ci.lock"
DOCKERFILE = ROOT / "backend" / "Dockerfile"
CI_YML = ROOT / ".github" / "workflows" / "ci.yml"

# Pin exato no .txt: "nome==versao" (ignora comentários e linhas com range).
_PIN_RE = re.compile(r"^([A-Za-z0-9._-]+)==([^\s#;]+)", re.MULTILINE)
# Pin no .lock gerado pelo pip-compile: "nome==versao \" seguido dos hashes.
_LOCK_PIN_RE = re.compile(r"^([A-Za-z0-9._-]+)==([^\s\\;]+)", re.MULTILINE)
# QUALQUER requisito no .txt, pinado ou com range: "nome", "nome[extra]>=1.2", etc.
# Sem isto, as deps de range ficariam fora da checagem de drift — que era exatamente
# o buraco: 7 das 18 diretas de base.txt usam >= e passavam despercebidas.
_REQ_NAME_RE = re.compile(r"^([A-Za-z0-9._-]+)(?:\[[^\]]*\])?\s*(?:[=<>!~]|$)")


def _text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _normalize(name: str) -> str:
    """PEP 503: pip-compile normaliza Django -> django, django_x -> django-x."""
    return re.sub(r"[-_.]+", "-", name).lower()


def _release(version: str) -> tuple:
    """Release tuple sem zeros à direita: 3.16 e 3.16.0 são a MESMA versão (PEP 440),
    então comparar as strings daria falso positivo."""
    parts = [int(p) for p in re.findall(r"\d+", version)]
    while len(parts) > 1 and parts[-1] == 0:
        parts.pop()
    return tuple(parts)


def _pins(path: Path, regex: re.Pattern) -> dict:
    return {_normalize(m.group(1)): m.group(2) for m in regex.finditer(_text(path))}


def _req_names(path: Path) -> set:
    """Todo nome de requisito declarado no .txt, com range ou pin."""
    names = set()
    for line in _text(path).splitlines():
        line = line.split("#", 1)[0].strip()
        if not line or line.startswith("-"):     # comentário, -r, --flag
            continue
        m = _REQ_NAME_RE.match(line)
        if m:
            names.add(_normalize(m.group(1)))
    return names


def _lock_blocks(path: Path) -> dict:
    """{pacote: n_hashes} — por PACOTE, não agregado. O total do arquivo não prova
    nada: um pacote com 100 hashes (brotli) mascara dez com zero."""
    blocks, current = {}, None
    for line in _text(path).splitlines():
        stripped = line.strip()
        m = _LOCK_PIN_RE.match(stripped)
        if m and not line.startswith(" "):
            current = _normalize(m.group(1))
            blocks[current] = 0
        elif current and stripped.startswith("--hash=sha256:"):
            blocks[current] += 1
    return blocks


def test_lockfiles_exist():
    """Sem lock, o build não é reproduzível e um incidente é irreconstruível."""
    for lock in (BASE_LOCK, CI_LOCK):
        assert lock.exists(), (
            f"{lock.relative_to(ROOT)} não existe. Gere com:\n"
            f"  cd backend && pip-compile --generate-hashes --strip-extras "
            f"--output-file=requirements/{lock.name} requirements/{lock.stem}.txt"
        )


def test_lockfiles_have_hashes():
    """--require-hashes só protege se CADA pacote tiver hash — verificado por pacote,
    não pelo total do arquivo (um pacote com 100 hashes esconderia dez com zero)."""
    for lock in (BASE_LOCK, CI_LOCK):
        blocks = _lock_blocks(lock)
        assert blocks, f"{lock.relative_to(ROOT)} não tem nenhum pacote pinado."
        sem_hash = sorted(pkg for pkg, n in blocks.items() if n == 0)
        assert not sem_hash, (
            f"{lock.relative_to(ROOT)}: {len(sem_hash)} pacote(s) sem nenhum hash sha256 "
            f"({', '.join(sem_hash[:5])}). Regenere com --generate-hashes."
        )


def test_lock_pins_every_package_exactly():
    """Nenhuma dep pode ficar flutuante no lock — nem transitiva."""
    for lock in (BASE_LOCK, CI_LOCK):
        for line in _text(lock).splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith(("#", "--", "\\")):
                continue
            if _LOCK_PIN_RE.match(stripped):
                continue
            assert not re.match(r"^[A-Za-z0-9._-]+\s*[><~!]=", stripped), (
                f"{lock.relative_to(ROOT)} tem especificador flutuante: {stripped!r}. "
                "O lock deve pinar tudo com ==."
            )


def test_lock_covers_every_declared_requirement():
    """TODA dep declarada no .txt precisa existir no .lock — inclusive as de range.
    Checar só as pinadas com == deixava 7 das 18 diretas de base.txt de fora: adicionar
    `foo>=1.0` sem regenerar o lock passaria verde, --require-hashes instalaria sem foo,
    e a imagem de produção quebraria com ImportError em runtime."""
    for txt, lock in ((BASE_TXT, BASE_LOCK), (CI_TXT, CI_LOCK)):
        declared = _req_names(txt)
        locked = set(_pins(lock, _LOCK_PIN_RE))
        faltando = sorted(declared - locked)
        assert not faltando, (
            f"{', '.join(faltando)} declarado(s) em {txt.name} mas ausente(s) de {lock.name}. "
            f"Regenere o lock (ver backend/requirements/README.md)."
        )


def test_lock_agrees_with_source_pins():
    """Um `.txt` editado sem regenerar o `.lock` deixa o build na versão velha —
    exatamente o caso do Django==5.2.8 (CVE-2025-64459). O lock é o que instala."""
    for txt, lock in ((BASE_TXT, BASE_LOCK), (CI_TXT, CI_LOCK)):
        src = _pins(txt, _PIN_RE)
        locked = _pins(lock, _LOCK_PIN_RE)
        for name, version in src.items():
            assert name in locked, (
                f"{name}=={version} está em {txt.name} mas não em {lock.name}. "
                f"Regenere o lock (ver backend/requirements/README.md)."
            )
            assert _release(locked[name]) == _release(version), (
                f"{name}: {txt.name} pina {version} mas {lock.name} tem {locked[name]}. "
                f"O lock é o que instala — regenere-o."
            )


def test_django_not_vulnerable_pin():
    """Django 5.2.0 tem CVE-2025-64459 (SQLi via kwarg _connector, CVSS 9.1, corrigido
    em 5.2.8) e CVE-2025-57833 (SQLi via FilteredRelation, corrigido em 5.2.6)."""
    locked = _pins(BASE_LOCK, _LOCK_PIN_RE)
    version = locked.get("django")
    assert version is not None, "django não está em base.lock."
    parts = tuple(int(p) for p in re.findall(r"\d+", version)[:3])
    assert parts >= (5, 2, 8), (
        f"django=={version} em base.lock é vulnerável a CVE-2025-64459 / CVE-2025-57833. "
        "Mínimo 5.2.8."
    )


def test_dockerfile_installs_from_lock_with_require_hashes():
    """A imagem de produção é o artefato que importa: tem que instalar do lock."""
    text = _text(DOCKERFILE)
    assert "--require-hashes" in text and "requirements/base.lock" in text, (
        "backend/Dockerfile deve rodar `pip install --require-hashes -r requirements/base.lock`. "
        "Instalar de base.txt resolve as deps no build e aceita qualquer release upstream."
    )
    assert "-r requirements/base.txt" not in text, (
        "backend/Dockerfile ainda instala de base.txt (sem hashes)."
    )


def test_dockerfile_base_image_pinned_by_digest():
    """Tag é mutável: `python:3.12-slim` rende imagens diferentes ao longo do tempo."""
    text = _text(DOCKERFILE)
    assert re.search(r"^FROM\s+python:[^\s@]+@sha256:[0-9a-f]{64}", text, re.MULTILINE), (
        "backend/Dockerfile deve pinar a imagem base por digest "
        "(FROM python:3.12-slim@sha256:...), não só por tag."
    )


def test_ci_installs_from_lock_with_require_hashes():
    text = _text(CI_YML)
    assert "--require-hashes -r requirements/ci.lock" in text, (
        ".github/workflows/ci.yml deve instalar com --require-hashes de requirements/ci.lock."
    )
    assert "pip install -r requirements/ci.txt" not in text, (
        ".github/workflows/ci.yml ainda instala de ci.txt (sem hashes)."
    )


def test_runner_registers_every_test():
    """A lista do __main__ é manual: uma função test_* definida e esquecida ali nunca
    roda e o CI fica verde sobre um teste que não existe na prática (aconteceu com
    test_lock_covers_every_declared_requirement)."""
    import __main__
    definidas = {
        name for name, obj in globals().items()
        if name.startswith("test_") and callable(obj)
    }
    registradas = {t.__name__ for t in getattr(__main__, "_REGISTERED", [])}
    if not registradas:
        return  # importado como módulo, não via __main__
    esquecidas = sorted(definidas - registradas)
    assert not esquecidas, (
        f"teste(s) definido(s) mas fora da lista do __main__: {', '.join(esquecidas)}"
    )


if __name__ == "__main__":
    tests = [
        test_lockfiles_exist,
        test_lockfiles_have_hashes,
        test_lock_pins_every_package_exactly,
        test_lock_covers_every_declared_requirement,
        test_lock_agrees_with_source_pins,
        test_django_not_vulnerable_pin,
        test_dockerfile_installs_from_lock_with_require_hashes,
        test_dockerfile_base_image_pinned_by_digest,
        test_ci_installs_from_lock_with_require_hashes,
        test_runner_registers_every_test,
    ]
    _REGISTERED = tests
    failed = []
    for t in tests:
        try:
            t()
            print(f"  PASS  {t.__name__}")
        except AssertionError as e:
            print(f"  FAIL  {t.__name__}: {e}")
            failed.append(t.__name__)
    print()
    if failed:
        print(f"FAILED: {len(failed)}/{len(tests)} tests failed")
        sys.exit(1)
    else:
        print(f"OK: all {len(tests)} tests passed")
