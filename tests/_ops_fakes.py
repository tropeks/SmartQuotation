"""
Docker FALSO para os testes de ops (backup/restore). Stdlib pura.

Nenhum teste de ops fala com um docker de verdade (não há docker no CI de ops, e produção é
intocável). Este módulo monta, num diretório temporário:

  bin/docker     fake do CLI. Registra cada chamada (argv) em FAKE_LOG e:
                   info                         -> exit 0, ou 1 se FAKE_INFO_OK=0
                   inspect -f '{{.State.Running}}' X -> imprime FAKE_STATE (true|false);
                                                   FAKE_STATE=absent -> exit 1
                   inspect -f '{{range .Config.Env}}...' X -> cat FAKE_ENV_FILE
                   exec [-i] X cmd...           -> roda `cmd...` LOCALMENTE com ctr_bin/ na
                                                   frente do PATH ("dentro do container") e
                                                   FAKE_CTR_ENV (VAR=valor ...) no ambiente
                   compose -f F exec -T svc cmd -> idem
                   run ...                      -> imprime um id; exit FAKE_RUN_EXIT (0)
                   rm ...                       -> exit 0
  ctr_bin/       ferramentas "de dentro do container", controladas por env:
                   pg_dumpall / pg_dump  grava argv em FAKE_DUMP_ARGV, imprime FAKE_DUMP_PAYLOAD
                                         (arquivo) e sai com FAKE_DUMP_EXIT (default 0)
                   tar                   tar real, mas com -C / trocado por FAKE_MEDIA_ROOT
                   python                o python que roda o teste (+ stub de cryptography se
                                         o ambiente não tiver a lib — caso do job ops do CI)
                   pg_isready            exit FAKE_PG_READY_EXIT (0)
                   psql                  restore (sem -c): consome stdin; consultas -c: responde
                                         por FAKE_SCHEMA_PRESENT / FAKE_TABLES / FAKE_QCOUNT

Chamadas com stdin (a chave, na prova de decifra) NÃO vão para o log: o log é argv, e o
teste de vazamento confere justamente que a chave nunca aparece em argv.
"""
from __future__ import annotations

import gzip
import io
import os
import shlex
import shutil
import subprocess
import sys
import tarfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "scripts"

FOOTER_CLUSTER = "-- PostgreSQL database cluster dump complete"
FOOTER_DB = "-- PostgreSQL database dump complete"

_FAKE_DOCKER = r"""#!/usr/bin/env bash
printf '%s\n' "$*" >> "${FAKE_LOG:-/dev/null}"
cmd="$1"; shift || true
case "$cmd" in
  info)
    [ "${FAKE_INFO_OK:-1}" = "1" ] && exit 0
    echo 'permission denied while trying to connect to the Docker daemon socket' >&2
    exit 1 ;;
  inspect)
    fmt=""
    if [ "${1:-}" = "-f" ] || [ "${1:-}" = "--format" ]; then fmt="$2"; shift 2; fi
    if [ "${FAKE_STATE:-true}" = "absent" ]; then
      echo "Error: No such object: $1" >&2; exit 1
    fi
    if [[ "$fmt" == *State.Running* ]]; then printf '%s\n' "${FAKE_STATE:-true}"
    elif [[ "$fmt" == *Config.Env* ]]; then cat "${FAKE_ENV_FILE:-/dev/null}"
    else echo '[{}]'; fi
    exit 0 ;;
  exec)
    while [ "$#" -gt 0 ] && [ "${1#-}" != "$1" ]; do shift; done
    shift  # container
    # shellcheck disable=SC2086
    exec env ${FAKE_CTR_ENV:-} PATH="${CTR_BIN}:${PATH}" "$@" ;;
  compose)
    while [ "$#" -gt 0 ] && [ "$1" != "exec" ]; do shift; done
    shift  # exec
    while [ "$#" -gt 0 ] && [ "${1#-}" != "$1" ]; do shift; done
    shift  # service
    PATH="${CTR_BIN}:${PATH}" exec "$@" ;;
  run)
    echo "fakecontainerid0123"
    exit "${FAKE_RUN_EXIT:-0}" ;;
  rm)
    exit 0 ;;
esac
exit 1
"""

_FAKE_PGDUMP = r"""#!/usr/bin/env bash
printf '%s\n' "$@" > "${FAKE_DUMP_ARGV:-/dev/null}"
[ -n "${FAKE_DUMP_PAYLOAD:-}" ] && cat "${FAKE_DUMP_PAYLOAD}"
exit "${FAKE_DUMP_EXIT:-0}"
"""

_FAKE_TAR = r"""#!/usr/bin/env bash
args=()
while [ "$#" -gt 0 ]; do
  if [ "$1" = "-C" ] && [ "${2:-}" = "/" ]; then args+=("-C" "${FAKE_MEDIA_ROOT}"); shift 2; continue; fi
  args+=("$1"); shift
done
exec __REAL_TAR__ "${args[@]}"
"""

_FAKE_PYTHON = r"""#!/usr/bin/env bash
export PYTHONPATH="${FAKE_PYTHONPATH:-}"
exec __PYTHON__ "$@"
"""

_FAKE_PSQL = r"""#!/usr/bin/env bash
sql=""
while [ "$#" -gt 0 ]; do
  case "$1" in
    -c) sql="$2"; shift 2 ;;
    *) shift ;;
  esac
done
if [ -z "$sql" ]; then
  cat > "${FAKE_RESTORE_SINK:-/dev/null}"
  echo "ERROR:  role \"sq\" already exists" >&2
  [ -n "${FAKE_PSQL_EXTRA_ERR:-}" ] && printf '%s\n' "${FAKE_PSQL_EXTRA_ERR}" >&2
  exit 0
fi
printf '%s\n' "$sql" >> "${FAKE_SQL_LOG:-/dev/null}"
case "$sql" in
  *information_schema.schemata*) echo "${FAKE_SCHEMA_PRESENT:-1}" ;;
  *information_schema.tables*)
    t="$(printf '%s' "$sql" | sed -n "s/.*table_name = '\([a-z0-9_]*\)'.*/\1/p")"
    case " ${FAKE_TABLES:-quotations_quotation quotations_quotationitem materials_material materials_materialprice} " in
      *" $t "*) echo 1 ;;
      *) echo 0 ;;
    esac ;;
  *count\(\*\)*) echo "${FAKE_QCOUNT:-3}" ;;
  *) echo 0 ;;
esac
"""


def _write_exec(path: Path, text: str) -> None:
    path.write_text(text)
    path.chmod(0o755)


def crypto_stub_needed() -> bool:
    if os.environ.get("SQ_TEST_CRYPTO_STUB") == "1":
        return True
    try:
        import cryptography.fernet  # noqa: F401
    except ImportError:
        return True
    return False


# Stub de cryptography.fernet: só para o job de ops do CI, que não instala cryptography
# (ops.lock é stdlib + pyyaml + pip-audit). Mesma API usada pela prova (Fernet(key).decrypt,
# generate_key, encrypt, InvalidToken); autenticado por HMAC, então chave errada falha como
# no Fernet real. NÃO é cifra de verdade e nunca sai do diretório temporário do teste.
_CRYPTO_STUB = r'''
import base64, hashlib, hmac, os


class InvalidToken(Exception):
    pass


class Fernet:
    def __init__(self, key):
        if isinstance(key, str):
            key = key.encode()
        raw = base64.urlsafe_b64decode(key)
        if len(raw) != 32:
            raise ValueError("Fernet key must be 32 url-safe base64-encoded bytes.")
        self._sign, self._enc = raw[:16], raw[16:]

    @classmethod
    def generate_key(cls):
        return base64.urlsafe_b64encode(os.urandom(32))

    def _stream(self, iv, n):
        out, i = b"", 0
        while len(out) < n:
            out += hashlib.sha256(self._enc + iv + i.to_bytes(4, "big")).digest()
            i += 1
        return out[:n]

    def encrypt(self, data):
        iv = os.urandom(16)
        ct = bytes(a ^ b for a, b in zip(data, self._stream(iv, len(data))))
        body = b"\x80" + iv + ct
        mac = hmac.new(self._sign, body, hashlib.sha256).digest()
        return base64.urlsafe_b64encode(body + mac)

    def decrypt(self, token):
        if isinstance(token, str):
            token = token.encode()
        try:
            raw = base64.urlsafe_b64decode(token)
        except Exception:
            raise InvalidToken()
        body, mac = raw[:-32], raw[-32:]
        if len(raw) < 49 or not hmac.compare_digest(mac, hmac.new(self._sign, body, hashlib.sha256).digest()):
            raise InvalidToken()
        iv, ct = body[1:17], body[17:]
        return bytes(a ^ b for a, b in zip(ct, self._stream(iv, len(ct))))
'''


class FakeEnv:
    """Um docker falso + ferramentas de container num diretório temporário."""

    def __init__(self, base: Path):
        self.base = base
        self.bin = base / "bin"
        self.ctr_bin = base / "ctr_bin"
        self.bin.mkdir()
        self.ctr_bin.mkdir()
        self.log = base / "docker.log"
        self.log.touch()
        self.media_root = base / "ctr_root"
        (self.media_root / "app" / "backend" / "media").mkdir(parents=True)
        self.pythonpath = ""
        if crypto_stub_needed():
            stub = base / "pystub" / "cryptography"
            stub.mkdir(parents=True)
            (stub / "__init__.py").write_text("")
            (stub / "fernet.py").write_text(_CRYPTO_STUB)
            self.pythonpath = str(base / "pystub")

        _write_exec(self.bin / "docker", _FAKE_DOCKER)
        _write_exec(self.ctr_bin / "pg_dumpall", _FAKE_PGDUMP)
        _write_exec(self.ctr_bin / "pg_dump", _FAKE_PGDUMP)
        _write_exec(self.ctr_bin / "tar", _FAKE_TAR.replace("__REAL_TAR__", shutil.which("tar")))
        _write_exec(self.ctr_bin / "python", _FAKE_PYTHON.replace("__PYTHON__", sys.executable))
        _write_exec(self.ctr_bin / "pg_isready", "#!/usr/bin/env bash\nexit \"${FAKE_PG_READY_EXIT:-0}\"\n")
        _write_exec(self.ctr_bin / "psql", _FAKE_PSQL)

        self.env = os.environ.copy()
        # Nada do ambiente de quem roda o teste vaza para o script (ex.: um POSTGRES_USER real).
        for k in list(self.env):
            if k.startswith(("POSTGRES_", "BACKUP_", "DB_", "MEDIA_", "KEY_", "RESTORE_", "FIELD_", "FAKE_")):
                del self.env[k]
        self.env.update({
            "PATH": f"{self.bin}:{self.env.get('PATH', '')}",
            "CTR_BIN": str(self.ctr_bin),
            "FAKE_LOG": str(self.log),
            "FAKE_MEDIA_ROOT": str(self.media_root),
            "FAKE_PYTHONPATH": self.pythonpath,
            "FAKE_DUMP_ARGV": str(base / "dump_argv"),
        })

    # --- fixtures de conteúdo -------------------------------------------------------------
    def set_dump(self, text: str, exit_code: int = 0) -> None:
        payload = self.base / "dump_payload.sql"
        payload.write_text(text)
        self.env["FAKE_DUMP_PAYLOAD"] = str(payload)
        self.env["FAKE_DUMP_EXIT"] = str(exit_code)

    def add_media_file(self, rel: str, data: bytes = b"%PDF-1.4 sintetico\n") -> None:
        p = self.media_root / "app" / "backend" / "media" / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(data)

    def set_container_env(self, lines: list[str]) -> None:
        f = self.base / "container_env"
        f.write_text("".join(line + "\n" for line in lines))
        self.env["FAKE_ENV_FILE"] = str(f)

    def fernet(self):
        """A classe Fernet que o 'container' vai usar (real se houver, stub senão)."""
        if self.pythonpath:
            sys.path.insert(0, self.pythonpath)
            try:
                for m in [m for m in sys.modules if m == "cryptography" or m.startswith("cryptography.")]:
                    del sys.modules[m]
                from cryptography.fernet import Fernet
            finally:
                sys.path.remove(self.pythonpath)
            return Fernet
        from cryptography.fernet import Fernet
        return Fernet

    def run(self, script: str, extra_env: dict | None = None, timeout: int = 60) -> subprocess.CompletedProcess:
        env = dict(self.env)
        env.update(extra_env or {})
        return subprocess.run(
            ["bash", str(SCRIPTS / script)], env=env, capture_output=True, text=True, timeout=timeout
        )

    def docker_calls(self) -> list[str]:
        return self.log.read_text().splitlines()


def synthetic_dump(
    lines: int = 200,
    *,
    schema: str = "engematex",
    footer: str | None = FOOTER_CLUSTER,
    materialprice_tokens: list[str] | None = None,
    quotations: int = 2,
) -> str:
    """Dump SINTÉTICO no formato do pg_dumpall (nenhum dado real da ENGEMATEX)."""
    out = [
        "--",
        "-- PostgreSQL database cluster dump",
        "--",
        "CREATE ROLE sq;",
        "\\connect smartquotation",
        f"CREATE SCHEMA {schema};",
        f"CREATE TABLE {schema}.quotations_quotation (id bigint NOT NULL, numero varchar(40));",
        f"CREATE TABLE {schema}.materials_materialprice (id bigint NOT NULL, forma varchar(20), "
        "preco_brl_kg varchar(64), fornecedor varchar(255), valid_from date, valid_until date, "
        "created_at timestamptz, material_id bigint);",
        f"COPY {schema}.quotations_quotation (id, numero) FROM stdin;",
    ]
    out += [f"{i}\tCOT-SINT-{i:04d}" for i in range(1, quotations + 1)]
    out.append("\\.")
    if materialprice_tokens is not None:
        out.append(
            f"COPY {schema}.materials_materialprice (id, forma, preco_brl_kg, fornecedor, "
            "valid_from, valid_until, created_at, material_id) FROM stdin;"
        )
        for i, tok in enumerate(materialprice_tokens, 1):
            out.append(f"{i}\tchapa\t{tok}\tFornecedor Sintetico\t2026-01-01\t\\N\t2026-01-01 00:00:00+00\t{i}")
        out.append("\\.")
    out += [f"-- linha sintética {i} {schema}" for i in range(lines)]
    out += ["--", "-- PostgreSQL database dump complete", "--"]
    if footer:
        out += ["", "--", footer, "--", ""]
    return "\n".join(out) + "\n"


def write_gz(path: Path, text: str) -> None:
    with gzip.open(path, "wt") as f:
        f.write(text)


def write_media_tar(path: Path, files: dict[str, bytes] | None = None) -> None:
    """tar.gz no mesmo layout do backup_media.sh (app/backend/media/...)."""
    with tarfile.open(path, "w:gz") as tf:
        d = tarfile.TarInfo("app/backend/media")
        d.type = tarfile.DIRTYPE
        d.mode = 0o755
        tf.addfile(d)
        for name, data in (files or {}).items():
            ti = tarfile.TarInfo(f"app/backend/media/{name}")
            ti.size = len(data)
            tf.addfile(ti, io.BytesIO(data))


def run_tests(tests) -> int:
    failed = []
    for t in tests:
        try:
            t()
            print(f"  PASS  {t.__name__}")
        except AssertionError as e:
            print(f"  FAIL  {t.__name__}: {e}")
            failed.append(t.__name__)
    return len(failed)


def q(s: str) -> str:
    return shlex.quote(s)
