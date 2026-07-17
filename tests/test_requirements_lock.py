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
OPS_TXT = REQ / "ops.txt"
OPS_LOCK = REQ / "ops.lock"

# Todo par (fonte, lock) do repo. Adicionar um par novo aqui o inscreve em TODOS os testes
# de contrato abaixo — foi assim que ops entrou depois de `pip install pyyaml` solto
# escapar do gate por não existir par para ele.
PAIRS = ((BASE_TXT, BASE_LOCK), (CI_TXT, CI_LOCK), (OPS_TXT, OPS_LOCK))
LOCKS = tuple(lock for _, lock in PAIRS)
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
    for lock in LOCKS:
        assert lock.exists(), (
            f"{lock.relative_to(ROOT)} não existe. Gere com:\n"
            f"  cd backend && pip-compile --generate-hashes --strip-extras "
            f"--output-file=requirements/{lock.name} requirements/{lock.stem}.txt"
        )


def test_lockfiles_have_hashes():
    """--require-hashes só protege se CADA pacote tiver hash — verificado por pacote,
    não pelo total do arquivo (um pacote com 100 hashes esconderia dez com zero)."""
    for lock in LOCKS:
        blocks = _lock_blocks(lock)
        assert blocks, f"{lock.relative_to(ROOT)} não tem nenhum pacote pinado."
        sem_hash = sorted(pkg for pkg, n in blocks.items() if n == 0)
        assert not sem_hash, (
            f"{lock.relative_to(ROOT)}: {len(sem_hash)} pacote(s) sem nenhum hash sha256 "
            f"({', '.join(sem_hash[:5])}). Regenere com --generate-hashes."
        )


def test_lock_pins_every_package_exactly():
    """Nenhuma dep pode ficar flutuante no lock — nem transitiva."""
    for lock in LOCKS:
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
    for txt, lock in PAIRS:
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
    for txt, lock in PAIRS:
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
    """Piso mínimo do Django. LEIA ISTO ANTES DE CONFIAR NESTE TESTE.

    Este teste é um PISO ESTÁTICO e, sozinho, é um carimbo. Ele já falhou uma vez
    exatamente assim: foi escrito em 2026-07-17 com `>= (5, 2, 8)` porque 5.2.8 era a
    versão pinada naquele dia, e passou verde enquanto o pin envelhecia 8 meses. Uma
    auditoria no mesmo dia rodou pip-audit e achou 26 advisories no 5.2.8 — inclusive
    PYSEC-2025-109, OUTRO SQLi de FilteredRelation, corrigido no 5.2.9. Ou seja: a
    classe de bug que o bump para 5.2.8 foi fechar já tinha sido re-quebrada, e este
    teste dizia que estava tudo bem.

    Quem PEGA regressão de verdade é o job `pip-audit` do CI (.github/workflows/ci.yml),
    que consulta a base de advisories ao vivo. Este teste é só a rede de proteção para
    quem rodar a suíte offline: ele impede voltar ATRÁS do piso conhecido, não detecta
    que o piso ficou velho.
    """
    locked = _pins(BASE_LOCK, _LOCK_PIN_RE)
    version = locked.get("django")
    assert version is not None, "django não está em base.lock."
    parts = tuple(int(p) for p in re.findall(r"\d+", version)[:3])
    assert parts >= (5, 2, 16), (
        f"django=={version} em base.lock está abaixo do piso conhecido. O 5.2.8 acumulou "
        "26 advisories (PYSEC-2025-104/109, PYSEC-2026-42..55, 197..201, 2090..2092, "
        "2448/2449), corrigidos ao longo da série até 5.2.16. Mínimo 5.2.16."
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


def test_ci_has_no_unhashed_pip_install():
    """NENHUM `pip install` do CI pode escapar do --require-hashes.

    O gate anterior só olhava a rota do ci.lock, então `pip install pyyaml` (solto, sem
    pin e sem hash) sobreviveu no job de ops — justamente o job que valida os contratos
    de backup e de lockfile. Uma auditoria posterior achou essa linha depois da rodada
    anterior ter afirmado "nenhuma rota de install sem hash sobrou". Este teste checa
    TODA linha `pip install`, não só as que alguém lembrou de conferir.
    """
    ofensores = []
    for i, line in enumerate(_text(CI_YML).splitlines(), 1):
        stripped = line.strip()
        if stripped.startswith("#") or "pip install" not in stripped:
            continue
        if "--require-hashes" in stripped:
            continue
        ofensores.append(f"ci.yml:{i}: {stripped}")
    assert not ofensores, (
        "install sem --require-hashes no CI:\n  " + "\n  ".join(ofensores)
        + "\nAdicione a dep ao lock apropriado (base/ci/ops) e instale com --require-hashes."
    )


def test_ci_runs_pip_audit_against_locks():
    """Piso estático de versão não detecta pin velho; base de advisories ao vivo detecta.

    `assert django >= (5,2,8)` passou verde por 8 meses enquanto o 5.2.8 acumulava 26
    advisories. Este job é o que pega a próxima vez, então ele precisa existir de fato.
    """
    text = _text(CI_YML)
    assert "pip-audit" in text, (
        ".github/workflows/ci.yml deve ter um job pip-audit — o piso estático em "
        "test_django_not_vulnerable_pin não detecta que o pin envelheceu."
    )
    for lock in ("base.lock", "ci.lock"):
        assert f"pip-audit --no-deps -r backend/requirements/{lock}" in text, (
            f"ci.yml deve rodar `pip-audit --no-deps -r backend/requirements/{lock}`."
        )


def test_base_and_ci_locks_agree_on_shared_packages():
    """CI e produção têm que instalar as MESMAS versões dos pacotes compartilhados.

    Se divergirem, o CI testa um código e a imagem embarca outro — e a suíte verde deixa
    de significar o que se pensa que significa. Hoje concordam nos 63 compartilhados; sem
    teste, isso é sorte que dura até alguém regenerar um lock só.
    """
    base = _pins(BASE_LOCK, _LOCK_PIN_RE)
    ci = _pins(CI_LOCK, _LOCK_PIN_RE)
    divergentes = [
        f"{nome}: base.lock={base[nome]} vs ci.lock={ci[nome]}"
        for nome in sorted(set(base) & set(ci))
        if _release(base[nome]) != _release(ci[nome])
    ]
    assert not divergentes, (
        "base.lock e ci.lock divergem — o CI não testa o que produção instala:\n  "
        + "\n  ".join(divergentes)
        + "\nRegenere os DOIS locks a partir dos .txt."
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
        test_ci_has_no_unhashed_pip_install,
        test_ci_runs_pip_audit_against_locks,
        test_base_and_ci_locks_agree_on_shared_packages,
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
