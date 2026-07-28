#!/usr/bin/env python3
"""Harness de screenshot para rede de segurança visual (troca de pele CSS).

Sobe (ou reaproveita) o servidor de dev do tenant ENGEMATEX, garante um usuário +
uma cotação de feixe + uma OF de exemplo no schema, autentica de verdade pelo
formulário de login (via Playwright + Chromium do sistema) e salva um PNG de cada
tela crítica no diretório passado como argumento.

USO (precisa do Postgres/Redis do docker compose de cima, ver CLAUDE.md):
    cd /home/rcosta00/dev/SmartQuotation
    export POSTGRES_PORT=5436 POSTGRES_HOST=localhost POSTGRES_USER=sq \
           POSTGRES_PASSWORD=sq POSTGRES_DB=smartquotation
    backend/.venv/bin/python scripts/visual_baseline.py docs/visual/antes

Rodável 2x sem sujeira: o diretório de saída é limpo (só *.png e manifest.json)
antes de cada rodada; dados de demo (user/cotação/OF) são idempotentes
(get_or_create) — rodar de novo não duplica nada.

Requer:
  - playwright instalado no venv usado para rodar este script
    (`backend/.venv/bin/pip install playwright` — NÃO precisa `playwright install`,
    usamos o Chromium do sistema via --chromium-bin).
  - um binário chromium/chromium-browser/google-chrome no PATH ou em --chromium-bin.

Capturando o "antes" enquanto outra sessão já edita backend/static/css/ no checkout
principal: rode a partir de um `git worktree` apontando pro commit anterior à troca de
pele, reaproveitando o venv do checkout principal (tem playwright/Django instalados):
    git worktree add /tmp/sq-antes <commit-antes-da-troca>
    backend/.venv/bin/python scripts/visual_baseline.py docs/visual/antes \
        --repo-root /tmp/sq-antes
    git worktree remove /tmp/sq-antes
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import shutil
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
BACKEND_DIR = REPO_ROOT / "backend"
VENV_PYTHON = BACKEND_DIR / ".venv" / "bin" / "python"

DEFAULT_TENANT_HOST = "engematex.localhost"

# Esta máquina é uma VPS compartilhada com dezenas de outros serviços (gunicorn de
# outros projetos, apps não relacionados) espalhados por toda a faixa 8000-8099 —
# NENHUMA porta fixa é confiável aqui. Por isso escolhemos uma porta livre de
# verdade (bind efêmero) na hora, em vez de uma constante tipo 8000/8020.

DEMO_USER = "visual_baseline"
DEMO_PASSWORD = "VisualBaseline!2026"

# título usado para achar/ancorar a cotação de demo (idempotência)
DEMO_QUOTATION_TITLE = "Feixe Tubular Demo — Visual Baseline"

CHROMIUM_CANDIDATES = ["chromium", "chromium-browser", "google-chrome", "google-chrome-stable"]


# ─────────────────────────── setup de ambiente Django ──────────────────────────

DEFAULT_PG_ENV = {
    "POSTGRES_PORT": "5436",
    "POSTGRES_HOST": "localhost",
    "POSTGRES_USER": "sq",
    "POSTGRES_PASSWORD": "sq",
    "POSTGRES_DB": "smartquotation",
}


def build_env() -> dict:
    env = os.environ.copy()
    for k, v in DEFAULT_PG_ENV.items():
        env.setdefault(k, v)
    env.setdefault("DJANGO_SETTINGS_MODULE", "smartquotation.settings.development")
    return env


# ────────────────────────────── dados de demo ───────────────────────────────

ENSURE_DATA_SCRIPT = r"""
import sys
from django.contrib.auth.models import User
from django_tenants.utils import schema_context

SCHEMA = "engematex"
DEMO_USER = "visual_baseline"
DEMO_PASSWORD = "VisualBaseline!2026"
DEMO_QUOTATION_TITLE = "Feixe Tubular Demo — Visual Baseline"

with schema_context(SCHEMA):
    from apps.accounts.models import UserProfile
    from apps.quotations.models import Customer, Quotation
    from apps.quotations.services import create_feixe_quotation
    from apps.audit.services import approve_quotation
    from apps.production import services as of_services
    from apps.production.models import OrdemFabricacao

    # usuário de login usado pelo harness (papel admin: vê tudo, sem gate de RBAC)
    viewer_user, _ = User.objects.get_or_create(
        username=DEMO_USER, defaults={"email": "visual-baseline@engematex.local"}
    )
    viewer_user.set_password(DEMO_PASSWORD)
    viewer_user.is_active = True
    viewer_user.save()
    viewer_profile, _ = UserProfile.objects.get_or_create(
        user=viewer_user,
        defaults={"full_name": "Visual Baseline", "role": UserProfile.ROLE_ADMIN, "is_active": True},
    )
    if viewer_profile.role != UserProfile.ROLE_ADMIN or not viewer_profile.is_active:
        viewer_profile.role = UserProfile.ROLE_ADMIN
        viewer_profile.is_active = True
        viewer_profile.save()

    # engenheiro só para poder aprovar tecnicamente e converter em OF
    eng_user, _ = User.objects.get_or_create(
        username="eng_demo_visual", defaults={"email": "eng.demo.visual@engematex.local"}
    )
    eng_user.set_password("EngDemoVisual!2026")
    eng_user.is_active = True
    eng_user.save()
    engineer, _ = UserProfile.objects.get_or_create(
        user=eng_user,
        defaults={
            "full_name": "Eng. Demo Visual",
            "role": UserProfile.ROLE_ENGENHEIRO,
            "crea_number": "CREA-VISUAL-999",
            "crea_state": "SP",
        },
    )
    if not engineer.crea_number:
        engineer.role = UserProfile.ROLE_ENGENHEIRO
        engineer.crea_number = "CREA-VISUAL-999"
        engineer.crea_state = "SP"
        engineer.save()

    customer, _ = Customer.objects.get_or_create(company_name="ACME Trocadores Demo (visual baseline)")

    quotation = Quotation.objects.filter(title=DEMO_QUOTATION_TITLE, customer=customer).first()
    if quotation is None:
        quotation = create_feixe_quotation(customer, DEMO_QUOTATION_TITLE, created_by=eng_user)
        print(f"[ensure_data] Quotation criada: pk={quotation.pk}")
    else:
        print(f"[ensure_data] Quotation ja existia: pk={quotation.pk}")

    of = OrdemFabricacao.objects.filter(quotation=quotation).exclude(status="cancelada").first()
    if of is None:
        try:
            approve_quotation(quotation, engineer, art_number="ART-VISUAL-BASELINE-1")
        except Exception as e:
            print(f"[ensure_data] aviso na aprovacao tecnica (pode ja existir): {e!r}")
        try:
            of = of_services.convert_quotation_to_of(quotation, created_by=eng_user)
            print(f"[ensure_data] OF criada: pk={of.pk} status={of.status}")
        except Exception as e:
            print(f"[ensure_data] AVISO: conversao para OF falhou: {e!r}")
    else:
        print(f"[ensure_data] OF ja existia: pk={of.pk} status={of.status}")

print(f"ENSURE_DATA_RESULT quotation_pk={quotation.pk} of_pk={of.pk if of else ''}")
"""


def ensure_data(env: dict, backend_dir: Path, venv_python: Path) -> dict:
    print("== Garantindo usuário + cotação + OF de demonstração no schema engematex ==")
    proc = subprocess.run(
        [str(venv_python), "manage.py", "shell"],
        input=ENSURE_DATA_SCRIPT,
        cwd=str(backend_dir),
        env=env,
        text=True,
        capture_output=True,
        timeout=180,
    )
    print(proc.stdout)
    if proc.returncode != 0:
        print(proc.stderr, file=sys.stderr)
        raise SystemExit(f"ensure_data falhou (exit={proc.returncode})")
    result_line = next((l for l in proc.stdout.splitlines() if l.startswith("ENSURE_DATA_RESULT")), None)
    if not result_line:
        print(proc.stderr, file=sys.stderr)
        raise SystemExit("ensure_data: não encontrei a linha ENSURE_DATA_RESULT na saída — algo falhou silenciosamente.")
    parts = dict(p.split("=", 1) for p in result_line.split()[1:])
    quotation_pk = parts.get("quotation_pk")
    of_pk = parts.get("of_pk") or None
    if not quotation_pk:
        raise SystemExit("ensure_data: quotation_pk vazio — não há cotação de demo para fotografar.")
    if not of_pk:
        print("[ensure_data] AVISO: sem OF de demo (conversão falhou) — pulo o screenshot de OF detalhe.")
    return {"quotation_pk": quotation_pk, "of_pk": of_pk}


# ────────────────────────────── servidor dev ───────────────────────────────

def loopback_url(base_url: str) -> tuple[str, str]:
    """Converte `http://engematex.localhost:PORT` em `(http://127.0.0.1:PORT, host)`.

    Esta máquina NÃO resolve `*.localhost` — `getent hosts engematex.localhost` volta
    vazio. O django-tenants precisa do domínio do tenant para escolher o schema, mas
    isso é decidido pelo cabeçalho `Host`, não pelo DNS. Então falamos com o loopback
    e mandamos o Host na mão.

    Era exatamente aqui que a sonda morria: cinco tentativas de subir servidor que
    subia bem, com o log de erro vazio porque o erro não era do servidor.
    """
    rest = base_url.split("://", 1)[1]
    host, _, port = rest.partition(":")
    return f"http://127.0.0.1:{port}" if port else "http://127.0.0.1", host


def server_is_up(base_url: str) -> bool:
    loopback, host = loopback_url(base_url)
    req = urllib.request.Request(f"{loopback}/health/", headers={"Host": host})
    try:
        with urllib.request.urlopen(req, timeout=3) as resp:
            return resp.status == 200
    except (urllib.error.URLError, ConnectionError, TimeoutError, OSError):
        return False


def find_free_port() -> int:
    """Bind efêmero em 0.0.0.0 pra achar uma porta livre AGORA. Máquina compartilhada
    com dezenas de outros serviços na faixa 8000-8099 → nada de porta fixa (ver topo
    do arquivo)."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("0.0.0.0", 0))
        return s.getsockname()[1]


def start_server_with_retry(env: dict, log_path: Path, tenant_host: str, backend_dir: Path, venv_python: Path, attempts: int = 5):
    """Tenta subir manage.py runserver numa porta livre; se colidir com algo que
    grudou a porta entre o find_free_port() e o bind real do Django (comum nesta
    VPS lotada), tenta de novo com outra porta."""
    last_log = ""
    for attempt in range(1, attempts + 1):
        port = find_free_port()
        base_url = f"http://{tenant_host}:{port}"
        log_file = open(log_path, "w")
        proc = subprocess.Popen(
            [str(venv_python), "manage.py", "runserver", f"0.0.0.0:{port}", "--noreload"],
            cwd=str(backend_dir),
            env=env,
            stdout=log_file,
            stderr=subprocess.STDOUT,
        )
        print(f"== Subindo manage.py runserver 0.0.0.0:{port} (tentativa {attempt}/{attempts}) ==")
        # dá uma folga pro processo bindar (ou morrer com "port already in use")
        time.sleep(1.5)
        if proc.poll() is not None:
            last_log = log_path.read_text(errors="replace")
            print(f"   processo morreu logo (porta {port} provavelmente já ocupada por outro serviço), tentando outra porta...")
            continue
        if wait_for_server(base_url, timeout=45, raise_on_timeout=False):
            print(f"== Servidor pronto em {base_url} ==")
            return proc, base_url
        # não respondeu a tempo: mata e tenta de nov
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()
        last_log = log_path.read_text(errors="replace")
    raise SystemExit(
        f"Não consegui subir o servidor em {attempts} tentativas (portas coincidindo com outros "
        f"serviços da VPS?). Log da última tentativa:\n{last_log}"
    )


def wait_for_server(base_url: str, timeout: float = 30.0, raise_on_timeout: bool = True) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if server_is_up(base_url):
            return True
        time.sleep(0.5)
    if raise_on_timeout:
        raise SystemExit(f"Servidor não respondeu em {base_url}/health/ após {timeout}s.")
    return False


def find_chromium(explicit: str | None) -> str:
    if explicit:
        return explicit
    for name in CHROMIUM_CANDIDATES:
        path = shutil.which(name)
        if path:
            return path
    raise SystemExit(
        "Nenhum binário chromium/chromium-browser/google-chrome encontrado no PATH. "
        "Instale um deles ou passe --chromium-bin /caminho/para/binario."
    )


# ────────────────────────────── captura ───────────────────────────────

def build_pages(base_url: str, quotation_pk: str, of_pk: str | None) -> list[dict]:
    pages = [
        {"name": "01_login", "url": f"{base_url}/login/", "auth": False},
        {"name": "02_dashboard", "url": f"{base_url}/", "auth": True},
        {"name": "03_cotacoes_lista", "url": f"{base_url}/cotacoes/", "auth": True},
        {"name": "04_cotacao_detalhe_resumo", "url": f"{base_url}/cotacoes/{quotation_pk}/", "auth": True},
        {
            "name": "05_cotacao_detalhe_eap",
            "url": f"{base_url}/cotacoes/{quotation_pk}/",
            "auth": True,
            "click_tab": "EAP",
        },
        {"name": "06_permutador_data_sheet", "url": f"{base_url}/tema/permutador/", "auth": True},
        {"name": "07_ofs_lista", "url": f"{base_url}/ofs/", "auth": True},
    ]
    if of_pk:
        pages.append({"name": "08_of_detalhe", "url": f"{base_url}/ofs/{of_pk}/", "auth": True})
    return pages


def capture(base_url: str, out_dir: Path, chromium_bin: str, quotation_pk: str, of_pk: str | None) -> list[dict]:
    from playwright.sync_api import sync_playwright

    pages = build_pages(base_url, quotation_pk, of_pk)
    results = []

    with sync_playwright() as p:
        # `--host-resolver-rules` faz o Chromium mapear o domínio do tenant para o
        # loopback sem passar pelo DNS (que não resolve `*.localhost` nesta máquina) e
        # sem exigir root para editar /etc/hosts. O Host da requisição continua sendo o
        # domínio do tenant, que é o que o django-tenants usa para escolher o schema.
        tenant_host = urllib.parse.urlparse(base_url).hostname or ""
        browser = p.chromium.launch(
            executable_path=chromium_bin,
            headless=True,
            args=["--no-sandbox", f"--host-resolver-rules=MAP {tenant_host} 127.0.0.1"],
        )
        context = browser.new_context(viewport={"width": 1440, "height": 900})
        page = context.new_page()

        # tela de login SEM sessão (screenshot antes de autenticar)
        login_spec = pages[0]
        page.goto(login_spec["url"], wait_until="networkidle")
        page.screenshot(path=str(out_dir / f"{login_spec['name']}.png"), full_page=True)
        results.append({"name": login_spec["name"], "url": login_spec["url"], "status": 200})

        # autentica de verdade pelo form (HTMX: POST -> 204 + HX-Redirect)
        page.fill("input[name=identifier]", DEMO_USER)
        page.fill("input[name=password]", DEMO_PASSWORD)
        with page.expect_response(lambda r: r.request.method == "POST" and "/login/" in r.url) as resp_info:
            page.click("#login-submit")
        login_resp = resp_info.value
        if login_resp.status != 204:
            raise SystemExit(
                f"Login falhou: POST /login/ voltou {login_resp.status} (esperado 204 + HX-Redirect). "
                "Confira usuário/senha de demo ou a UserProfile no schema engematex."
            )
        page.wait_for_timeout(800)
        page.wait_for_load_state("networkidle")
        if page.url.rstrip("/").endswith("/login"):
            raise SystemExit("Login falhou: ainda na página de login após o POST 204.")

        for spec in pages[1:]:
            resp = page.goto(spec["url"], wait_until="networkidle")
            status = resp.status if resp else None
            page.wait_for_timeout(300)
            if spec.get("click_tab"):
                tab_button = page.locator(".g-tab", has_text=spec["click_tab"])
                tab_button.first.click()
                page.wait_for_timeout(300)
            png_path = out_dir / f"{spec['name']}.png"
            page.screenshot(path=str(png_path), full_page=True)
            results.append({"name": spec["name"], "url": spec["url"], "status": status})
            print(f"  [{status}] {spec['name']} <- {spec['url']}")

        browser.close()

    return results


# ────────────────────────────── validação ───────────────────────────────

SMALL_PNG_WARN_BYTES = 10_000


def validate(out_dir: Path, results: list[dict]) -> None:
    print("\n== Validação dos PNGs ==")
    problems = []
    for r in results:
        png_path = out_dir / f"{r['name']}.png"
        if not png_path.exists():
            problems.append(f"{r['name']}: PNG não foi criado")
            continue
        size = png_path.stat().st_size
        r["bytes"] = size
        flag = ""
        if size < SMALL_PNG_WARN_BYTES:
            flag = "  <-- SUSPEITO (muito pequeno, pode ser página em branco/erro)"
            problems.append(f"{r['name']}: apenas {size} bytes")
        if r.get("status") and r["status"] >= 400:
            flag += f"  <-- HTTP {r['status']}"
            problems.append(f"{r['name']}: HTTP {r['status']}")
        print(f"  {r['name']}.png: {size:>8} bytes{flag}")

    if problems:
        print("\nATENÇÃO — possíveis screenshots quebrados:")
        for p in problems:
            print(f"  - {p}")
    else:
        print("\nTodos os PNGs parecem OK (tamanho razoável, HTTP 2xx/3xx).")


# ────────────────────────────── main ───────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("out_dir", help="Diretório onde salvar os PNGs (ex.: docs/visual/antes)")
    parser.add_argument(
        "--base-url",
        default=None,
        help="URL de um servidor já no ar (ex.: http://engematex.localhost:8020). "
        "Se omitido, o script escolhe uma porta livre e sobe o próprio manage.py runserver.",
    )
    parser.add_argument("--tenant-host", default=DEFAULT_TENANT_HOST)
    parser.add_argument("--chromium-bin", default=None)
    parser.add_argument("--skip-data", action="store_true", help="Pula a garantia de dados de demo (assume que já existem)")
    parser.add_argument("--skip-server-autostart", action="store_true", help="Não sobe servidor — falha se não estiver no ar")
    parser.add_argument(
        "--repo-root",
        default=str(REPO_ROOT),
        help="Raiz do checkout Django a rodar (ex.: um `git worktree` separado apontando pra um "
        "commit antigo, pra fotografar o 'antes' sem que outra sessão editando backend/static/css "
        "no checkout principal contamine o baseline). O binário python do venv usado continua sendo "
        "o do checkout principal (--venv-python) — só o código Django/templates vem de --repo-root.",
    )
    parser.add_argument(
        "--venv-python",
        default=str(VENV_PYTHON),
        help="Interpretador (com Django/playwright instalados) usado para rodar manage.py. "
        "Default: venv do checkout principal — reaproveitável mesmo apontando --repo-root pra outro worktree.",
    )
    args = parser.parse_args()

    repo_root = Path(args.repo_root).resolve()
    backend_dir = repo_root / "backend"
    venv_python = Path(args.venv_python).resolve()

    if not venv_python.exists():
        raise SystemExit(f"venv não encontrado em {venv_python}. Rode: cd backend && python -m venv .venv && ...")
    if not (backend_dir / "manage.py").exists():
        raise SystemExit(f"manage.py não encontrado em {backend_dir} — --repo-root aponta pro lugar certo?")

    try:
        import playwright  # noqa: F401
    except ImportError:
        raise SystemExit(
            "playwright não instalado no interpretador usado para rodar este script.\n"
            f"Rode este script com: {VENV_PYTHON} {Path(__file__)} ...\n"
            f"(e garanta que {VENV_PYTHON} -m pip show playwright funciona)"
        )

    chromium_bin = find_chromium(args.chromium_bin)
    env = build_env()

    out_dir = Path(args.out_dir)
    if not out_dir.is_absolute():
        out_dir = REPO_ROOT / out_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    for stale in glob.glob(str(out_dir / "*.png")):
        os.remove(stale)
    manifest_path = out_dir / "manifest.json"
    if manifest_path.exists():
        manifest_path.unlink()

    server_proc = None
    base_url = args.base_url
    try:
        if base_url and server_is_up(base_url):
            print(f"== Servidor já no ar em {base_url} — reaproveitando ==")
        elif args.skip_server_autostart:
            raise SystemExit(f"{base_url} não está no ar e --skip-server-autostart foi passado.")
        else:
            log_path = out_dir / "_runserver.log"
            server_proc, base_url = start_server_with_retry(env, log_path, args.tenant_host, backend_dir, venv_python)

        if args.skip_data:
            print("== --skip-data: pulando garantia de dados (assumindo pk=1 para cotação/OF) ==")
            ids = {"quotation_pk": "1", "of_pk": "1"}
        else:
            ids = ensure_data(env, backend_dir, venv_python)

        print(f"\n== Capturando screenshots em {out_dir} (servidor: {base_url}) ==")
        results = capture(base_url, out_dir, chromium_bin, ids["quotation_pk"], ids.get("of_pk"))

        manifest_path.write_text(json.dumps({"base_url": base_url, "pages": results}, indent=2, ensure_ascii=False))
        validate(out_dir, results)
        print(f"\nOK — {len(results)} screenshots salvos em {out_dir}")
    finally:
        if server_proc is not None:
            print(f"== Encerrando servidor de dev que este script subiu (pid={server_proc.pid}) ==")
            server_proc.terminate()
            try:
                server_proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                server_proc.kill()


if __name__ == "__main__":
    main()
