"""
age e rclone FALSOS para os testes do off-site (ordem 003). Stdlib pura; mesmo padrão do
docker falso de tests/_ops_fakes.py (scripts bash num bin/ temporário na frente do PATH).

  bin/age      Só cifra (-e, -r ..., -o OUT, entrada por stdin ou arquivo). Escreve um
               cabeçalho age plausível ("age-encryption.org/v1", uma stanza "-> X25519" por
               destinatário, "--- mac" aleatório: recifrar dá outro hash, como no age real) e
               depois o texto em CLARO, para o teste poder "decifrar" (split_age). Registra em
               FAKE_AGE_LOG: destinatários, sha256 da entrada e argv (nunca a entrada).
               Destinatário age1yubikey1… vira "-> piv-p256 <tag> <share>" (formato do
               age-plugin-yubikey) e, como no age real, exige age-plugin-yubikey no PATH.
               FAKE_AGE_EXTRA_STANZA=1 põe uma stanza a mais; FAKE_AGE_STANZA_TYPE força o
               tipo de TODAS as stanzas (ex.: X25519 para um destinatário YubiKey).
  bin/rclone   Um "bucket" por seção do rclone.conf em FAKE_BUCKETS/<secao>/<caminho>.
                 hashsum TIPO [--download] ALVO   "<hash>  <nome>"; nada se não existe
                                                  (FAKE_RCLONE_ABSENT_RC=3 simula "directory
                                                  not found"); FAKE_RCLONE_NO_HASH=1 sem hash,
                                                  salvo com --download (baixa e calcula)
                 copyto [--immutable] SRC ALVO    --immutable recusa sobrescrever conteúdo
                                                  diferente; FAKE_RCLONE_CORRUPT=1 grava um byte
                                                  a mais (o hash não confere)
                 FAKE_RCLONE_FAIL=<subcomando>    aquele subcomando sai 1 (rede/credencial)
               Qualquer outro subcomando (delete, purge, sync, move...) registra "VIOLATION"
               em FAKE_RCLONE_LOG e sai 99: o off-site não apaga nada no remoto (DP-27).

OffsiteCase monta o cenário completo: dump, mídia, chave 0600 em KEY_BACKUP_DIR e ISCAS (um
.env.prod e uma cópia da chave largados no BACKUP_DIR), com os asserts de vazamento.
"""
from __future__ import annotations

import gzip
import hashlib
import re
import secrets
import shutil
import tempfile
from pathlib import Path

from tests._ops_fakes import FakeEnv, _write_exec, synthetic_dump, write_gz, write_media_tar

DUMP = "sq_20260927_030000.sql.gz"
MEDIA = "media_20260927_030000.tar.gz"
DUMP_REMOTE = "sq-offsite:sq-backup/engematex"
KEY_REMOTE = "sq-offsite-key:sq-key-custody/engematex"
ENV_PROD_MARKER = "DJANGO_SECRET_KEY=segredo-sintetico-do-env-prod"
ALLOWED_RCLONE = {"hashsum", "copyto"}

_FAKE_AGE = r"""#!/usr/bin/env bash
orig="$*"
recips=(); out=""; in=""
while [ "$#" -gt 0 ]; do
  case "$1" in
    -e|--encrypt) shift ;;
    -r|--recipient) recips+=("$2"); shift 2 ;;
    -o|--output) out="$2"; shift 2 ;;
    -d|--decrypt) echo "age falso: não decifra" >&2; exit 1 ;;
    -*) echo "age falso: flag não suportada: $1" >&2; exit 1 ;;
    *) in="$1"; shift ;;
  esac
done
[ "${#recips[@]}" -gt 0 ] || { echo "age: error: missing recipients" >&2; exit 1; }
for r in "${recips[@]}"; do
  if [[ "$r" =~ ^age1yubikey1[a-z0-9]{59}$ ]]; then
    command -v age-plugin-yubikey >/dev/null 2>&1 \
      || { echo "age: error: age-plugin-yubikey not found in \$PATH" >&2; exit 1; }
    continue
  fi
  [[ "$r" =~ ^age1[a-z0-9]{58}$ ]] || { echo "age: error: unknown recipient type" >&2; exit 1; }
done
payload="$(mktemp)"
trap 'rm -f "$payload"' EXIT
if [ -n "$in" ]; then cat -- "$in" > "$payload"; else cat > "$payload"; fi
sha="$(sha256sum < "$payload" | cut -d' ' -f1)"
printf 'recipients=%s input_sha256=%s argv=%s\n' "$(IFS=,; echo "${recips[*]}")" "$sha" "$orig" >> "${FAKE_AGE_LOG:-/dev/null}"
rnd() { printf '%s%s%s' "$1" "$RANDOM" "$RANDOM" | sha256sum | cut -c1-43; }
{
  printf 'age-encryption.org/v1\n'
  for r in "${recips[@]}"; do
    case "$r" in
      age1yubikey1*) st="${FAKE_AGE_STANZA_TYPE:-piv-p256}"; args="$(rnd "$r" | cut -c1-6) $(rnd "$r")=" ;;
      *) st="${FAKE_AGE_STANZA_TYPE:-X25519}"; args="$(rnd "$r")" ;;
    esac
    printf -- '-> %s %s\n%s\n' "$st" "$args" "$(rnd corpo)"
  done
  if [ "${FAKE_AGE_EXTRA_STANZA:-0}" = "1" ]; then printf -- '-> X25519 extra\nextra\n'; fi
  printf -- '--- %s\n' "$(rnd mac)"
  cat "$payload"
} > "${out:-/dev/stdout}"
"""

_FAKE_RCLONE = r"""#!/usr/bin/env bash
printf '%s\n' "$*" >> "${FAKE_RCLONE_LOG:-/dev/null}"
cmd="${1:-}"; shift || true
immutable=0; download=0; args=()
for a in "$@"; do
  case "$a" in --immutable) immutable=1 ;; --download) download=1 ;; --*) ;; *) args+=("$a") ;; esac
done
path_of() { printf '%s/%s/%s' "${FAKE_BUCKETS}" "${1%%:*}" "${1#*:}"; }
[ -f "${RCLONE_CONFIG:-}" ] || { echo "rclone falso: RCLONE_CONFIG ausente" >&2; exit 1; }
if [ "${FAKE_RCLONE_FAIL:-}" = "$cmd" ]; then
  echo "ERROR : Failed to create file system: falha de rede simulada" >&2; exit 1
fi
case "$cmd" in
  hashsum)
    f="$(path_of "${args[1]}")"
    if [ ! -f "$f" ]; then
      [ -z "${FAKE_RCLONE_ABSENT_RC:-}" ] && exit 0
      echo "ERROR : directory not found" >&2; exit "${FAKE_RCLONE_ABSENT_RC}"
    fi
    h="$("${args[0]}sum" < "$f" | cut -d' ' -f1)"
    # Sem --download, o hash vem do "provedor" (que pode não guardá-lo); com --download o
    # rclone baixa e calcula, então sempre há hash.
    [ "${FAKE_RCLONE_NO_HASH:-0}" = "1" ] && [ "$download" = 0 ] && h=""
    printf '%40s  %s\n' "$h" "$(basename "$f")"
    exit 0 ;;
  copyto)
    src="${args[0]}"; f="$(path_of "${args[1]}")"
    if [ -f "$f" ] && [ "$immutable" = 1 ] && ! cmp -s "$src" "$f"; then
      echo "ERROR : Source and destination exist but do not match: immutable file modified" >&2; exit 1
    fi
    mkdir -p "$(dirname "$f")" && cp -- "$src" "$f"
    if [ "${FAKE_RCLONE_CORRUPT:-0}" = "1" ]; then printf 'X' >> "$f"; fi
    exit 0 ;;
esac
printf 'VIOLATION %s %s\n' "$cmd" "$*" >> "${FAKE_RCLONE_LOG:-/dev/null}"
echo "rclone falso: subcomando '$cmd' proibido no off-site (nada se apaga no remoto)" >&2
exit 99
"""

_BECH32 = "qpzry9x8gf2tvdw0s3jn54khce6mua7l"


def fake_age_recipient() -> str:
    """Chave pública age SINTÉTICA (formato válido; o checksum não: o age real a recusaria)."""
    return "age1" + "".join(secrets.choice(_BECH32) for _ in range(58))


def fake_yubikey_recipient() -> str:
    """Destinatário age-plugin-yubikey SINTÉTICO (age1yubikey1 + 59, P-256 comprimido)."""
    return "age1yubikey1" + "".join(secrets.choice(_BECH32) for _ in range(59))


def split_age(data: bytes) -> tuple[list[str], bytes]:
    """(linhas de stanza '-> ...', texto claro) de um .age produzido pelo age FALSO."""
    head, sep, body = data.partition(b"\n--- ")
    assert sep, "sem linha '--- ' no cabeçalho age"
    lines = head.decode().splitlines()
    assert lines[0] == "age-encryption.org/v1", lines[0]
    return [ln for ln in lines if ln.startswith("-> ")], body.partition(b"\n")[2]


def expand(data: bytes) -> bytes:
    """Bytes + texto claro do age falso + gunzip do que for gzip: onde a chave poderia estar."""
    out = data
    if data.startswith(b"age-encryption.org/v1\n"):
        data = split_age(data)[1]
        out += data
    if data[:2] == b"\x1f\x8b":
        out += gzip.decompress(data)
    return out


def objects(root: Path) -> list[Path]:
    return sorted(p for p in root.rglob("*") if p.is_file()) if root.exists() else []


def status(p: Path) -> dict:
    return dict(ln.split("=", 1) for ln in p.read_text().splitlines())


def _parse_age_line(line: str) -> dict:
    """'recipients=a,b input_sha256=H argv=...' (uma linha do FAKE_AGE_LOG)."""
    rec, sha, argv = (field.split("=", 1)[1] for field in line.split(" ", 2))
    return {"recipients": rec.split(","), "input_sha256": sha, "argv": argv}


class OffsiteCase:
    def __init__(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.base = Path(self._tmp.name)
        self.fk = FakeEnv(self.base)
        self._install_fakes()
        self.bdir = self.base / "backups" / "sq"
        self.kdir = self.base / "keys"
        self.bdir.mkdir(parents=True)
        self.kdir.mkdir(mode=0o700)
        self.fk.env.update({"BACKUP_DIR": str(self.bdir), "KEY_BACKUP_DIR": str(self.kdir)})
        write_gz(self.bdir / "sq_20260926_030000.sql.gz", synthetic_dump(quotations=1))
        write_gz(self.bdir / DUMP, synthetic_dump())
        write_media_tar(self.bdir / MEDIA, {"p/COT-SINT-0001.pdf": b"%PDF-1.4 sintetico"})
        self.key = self.fk.fernet().generate_key().decode()
        self.write_key(self.key)
        # Iscas largadas no BACKUP_DIR por engano: o off-site só leva sq_*.sql.gz e
        # media_*.tar.gz, então nenhuma das duas pode sair.
        env_prod = f"FIELD_ENCRYPTION_KEY={self.key}\n{ENV_PROD_MARKER}\n"
        (self.bdir / ".env.prod").write_text(env_prod)
        (self.bdir / "field_encryption_key").write_text(self.key)
        self.env_prod_sha = hashlib.sha256(env_prod.encode()).hexdigest()

    def _install_fakes(self):
        _write_exec(self.fk.bin / "age", _FAKE_AGE)
        _write_exec(self.fk.bin / "rclone", _FAKE_RCLONE)
        self.buckets = self.base / "buckets"
        self.buckets.mkdir()
        self.age_log = self.base / "age.log"
        self.rclone_log = self.base / "rclone.log"
        self.age_log.touch()
        self.rclone_log.touch()
        conf = self.base / "etc" / "rclone.conf"
        conf.parent.mkdir()
        conf.write_text("[sq-offsite]\ntype = local\n\n[sq-offsite-key]\ntype = local\n")
        conf.chmod(0o600)
        self.rcpt = {"instance": fake_age_recipient(), "recovery": fake_age_recipient()}
        self.fk.env.update({
            "FAKE_BUCKETS": str(self.buckets),
            "FAKE_AGE_LOG": str(self.age_log),
            "FAKE_RCLONE_LOG": str(self.rclone_log),
            "RCLONE_CONFIG": str(conf),
            "RCLONE_CACHE_DIR": str(self.base / "rclone-cache"),
            "OFFSITE_REMOTE": DUMP_REMOTE,
            "OFFSITE_KEY_REMOTE": KEY_REMOTE,
            "OFFSITE_AGE_RECIPIENT_INSTANCE": self.rcpt["instance"],
            "OFFSITE_AGE_RECIPIENT_RECOVERY": self.rcpt["recovery"],
        })

    def write_conf(self, text: str):
        """Troca o rclone.conf (continua 0600)."""
        conf = Path(self.fk.env["RCLONE_CONFIG"])
        conf.write_text(text)
        conf.chmod(0o600)

    def install_failing_mktemp(self):
        """mktemp que falha com FAKE_MKTEMP_FAIL=1 (prova que a falha propaga sob `|| exit 1`)."""
        real = shutil.which("mktemp")
        _write_exec(self.fk.bin / "mktemp",
                    f'#!/usr/bin/env bash\n[ "${{FAKE_MKTEMP_FAIL:-0}}" = 1 ] && exit 1\nexec {real} "$@"\n')

    def install_yubikey_plugin(self):
        """age-plugin-yubikey falso no PATH (o age falso só confere que ele existe)."""
        _write_exec(self.fk.bin / "age-plugin-yubikey", "#!/usr/bin/env bash\nexit 0\n")

    def path_without_yubikey_plugin(self) -> str:
        """PATH do teste sem nenhum diretório que tenha um age-plugin-yubikey real."""
        dirs = self.fk.env["PATH"].split(":")
        return ":".join(d for d in dirs if not (Path(d) / "age-plugin-yubikey").exists())

    def write_key(self, key):
        kf = self.kdir / "field_encryption_key"
        kf.write_text(key)
        kf.chmod(0o600)

    def bucket(self, remote: str) -> Path:
        section, _, path = remote.partition(":")
        return self.buckets / section / path

    @property
    def dump_bucket(self):
        return self.bucket(DUMP_REMOTE)

    @property
    def key_bucket(self):
        return self.bucket(KEY_REMOTE)

    def push(self, extra=None):
        return self.fk.run("offsite_push.sh", extra)

    def push_key(self, extra=None):
        return self.fk.run("offsite_key_push.sh", extra)

    def rclone_calls(self) -> list[str]:
        return self.rclone_log.read_text().splitlines()

    def copytos(self) -> list[str]:
        return [c for c in self.rclone_calls() if c.startswith("copyto ")]

    def age_calls(self) -> list[dict]:
        return [_parse_age_line(line) for line in self.age_log.read_text().splitlines()]

    def untouched(self) -> bool:
        """Recusa de configuração: nem age nem rclone foram chamados."""
        return not self.age_calls() and not self.rclone_calls()

    def __enter__(self):
        return self

    def __exit__(self, *a):
        self._tmp.cleanup()


def assert_no_rclone_violation(c: OffsiteCase):
    calls = c.rclone_calls()
    assert not [x for x in calls if x.startswith("VIOLATION")], calls
    cmds = {x.split()[0] for x in calls}
    assert cmds <= ALLOWED_RCLONE, f"subcomando rclone fora da lista (nada se apaga no remoto): {cmds}"
    for x in c.copytos():
        assert "--immutable" in x.split(), f"copyto sem --immutable: {x}"


def _assert_key_absent_from_dump_remote(c: OffsiteCase, kb: bytes):
    for p in objects(c.dump_bucket):
        data = expand(p.read_bytes())
        assert kb not in data, f"chave no remote do DUMP: {p.name}"
        assert ENV_PROD_MARKER.encode() not in data, f".env.prod no remote do DUMP: {p.name}"


_DUMP_STATUS = ("offsite_last_success", "offsite_manifest")
_KEY_STATUS = ("offsite_key_last_success", "offsite_key_fingerprint", "offsite_key_manifest")


def _assert_key_absent_from_status(c: OffsiteCase, kb: bytes):
    names = [c.bdir / n for n in _DUMP_STATUS] + [c.kdir / n for n in _KEY_STATUS]
    for p in names:
        assert not p.exists() or kb not in p.read_bytes(), f"chave em {p.name}"


def assert_no_leak(c: OffsiteCase, runs, *keys):
    """A chave (e o .env.prod) não aparecem em stdout, stderr, argv do age/rclone, arquivos de
    status, nem em NADA que o remote do dump recebeu: em claro ou cifrada para os
    destinatários do dump. Objetos da chave só existem no remote da chave."""
    keys = keys or (c.key,)
    runs = runs if isinstance(runs, list) else [runs]
    out = "".join(r.stdout + r.stderr for r in runs)
    for k in keys:
        assert k not in out, "chave vazou na saída"
        assert k not in c.rclone_log.read_text(), "chave em argv do rclone"
        assert k not in c.age_log.read_text(), "chave em argv do age"
        _assert_key_absent_from_dump_remote(c, k.encode())
        _assert_key_absent_from_status(c, k.encode())
    key_shas = {hashlib.sha256(k.encode()).hexdigest() for k in keys} | {c.env_prod_sha}
    for call in c.age_calls():
        if c.rcpt["instance"] in call["recipients"]:
            assert call["input_sha256"] not in key_shas, "chave/.env.prod cifrados para o DUMP"
    for p in objects(c.buckets):
        if p.name.startswith("field_encryption_key"):
            assert c.key_bucket in p.parents, f"objeto da chave fora do OFFSITE_KEY_REMOTE: {p}"


KEY_OBJECT_RE = re.compile(r"field_encryption_key\.([0-9a-f]{16})\.\d{8}T\d{6}\.\d{9}Z\.age")
DUMP_OBJECT_RE = re.compile(r"(sq_\d{8}_\d{6}\.sql\.gz|media_\d{8}_\d{6}\.tar\.gz)\.age")
