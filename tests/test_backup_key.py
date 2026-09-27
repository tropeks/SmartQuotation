"""
Tests: scripts/backup_key.sh — FIELD_ENCRYPTION_KEY coberta + prova de decifra (ordem 002).

Condições do Diretor provadas aqui:
  (D1) a prova imprime SÓ `ok`, `falha` ou `sem amostra` — nunca o valor decifrado nem a chave:
       test_proof_ok_*, test_wrong_key_*, test_no_sample_*,
       test_misbehaving_container_output_is_never_relayed.
  (D2) a chave não aparece em stdout, stderr, argv do docker, last_success/last_proof, nem em
       arquivo algum do BACKUP_DIR (nem em qualquer arquivo do teste fora do arquivo da chave):
       _assert_no_leak, chamado em TODOS os cenários.

Chave SINTÉTICA gerada no teste (Fernet.generate_key) e dump SINTÉTICO. Docker falso
(tests/_ops_fakes.py): o "python do container" é o python do teste, com um stub de
cryptography quando a lib não está instalada (job ops do CI).
"""
import gzip
import stat
import sys
import tempfile
from pathlib import Path

from tests._ops_fakes import FakeEnv, run_tests, synthetic_dump, write_gz

PLAINTEXT = b"PRECO-SINTETICO-987.65"


class Case:
    def __init__(self, *, container_key=None, dump_key=None, tokens=True, key_dir=None):
        self._tmp = tempfile.TemporaryDirectory()
        self.base = Path(self._tmp.name)
        self.fk = FakeEnv(self.base)
        Fernet = self.fk.fernet()
        self.key = container_key or Fernet.generate_key().decode()
        dump_key = dump_key or self.key
        self.bdir = self.base / "backups" / "sq"
        self.kdir = Path(key_dir) if key_dir else self.base / "keys"
        self.bdir.mkdir(parents=True)
        self.fk.env.update({"BACKUP_DIR": str(self.bdir), "KEY_BACKUP_DIR": str(self.kdir)})
        self.fk.set_container_env([
            "PATH=/usr/local/bin:/usr/bin",
            "POSTGRES_PASSWORD=senha-sintetica-do-teste",
            f"FIELD_ENCRYPTION_KEY={self.key}",
            "DJANGO_SECRET_KEY=outro-segredo-sintetico",
        ])
        toks = None
        if tokens:
            toks = [Fernet(dump_key.encode()).encrypt(PLAINTEXT).decode(), "\\N"]
        write_gz(self.bdir / "sq_20260927_030000.sql.gz", synthetic_dump(materialprice_tokens=toks))

    def set_key(self, key):
        self.key = key
        self.fk.set_container_env([f"FIELD_ENCRYPTION_KEY={key}"])

    def run(self, extra=None):
        return self.fk.run("backup_key.sh", extra)

    def __enter__(self):
        return self

    def __exit__(self, *a):
        self._tmp.cleanup()


def _all_files(root: Path):
    """Todo arquivo que o SCRIPT pode ter escrito. ctr_bin/ e pystub/ são a "imagem do
    container" montada pelo próprio teste (o fake malcomportado carrega o texto de isca)."""
    for p in root.rglob("*"):
        rel = p.relative_to(root).parts
        if p.is_file() and rel[0] not in ("ctr_bin", "pystub"):
            yield p


def _file_text(p: Path) -> bytes:
    data = p.read_bytes()
    if data[:2] == b"\x1f\x8b":  # gzip: procura também no conteúdo descomprimido
        data += gzip.decompress(data)
    return data


def _assert_no_leak(c: Case, r, *keys):
    """D2: nenhuma chave em stdout/stderr/argv/status/BACKUP_DIR; D1: nada decifrado em lugar algum."""
    keys = keys or (c.key,)
    key_files = {p.resolve() for p in c.kdir.glob("field_encryption_key*") if not p.name.endswith(".sha256")}
    fixture = Path(c.fk.env["FAKE_ENV_FILE"]).resolve()  # o "env do container" simulado
    for k in keys:
        kb = k.encode()
        assert k not in r.stdout, "chave vazou no stdout"
        assert k not in r.stderr, "chave vazou no stderr"
        assert k not in c.fk.log.read_text(), "chave apareceu em argv do docker"
        for p in _all_files(c.bdir):
            assert kb not in _file_text(p), f"chave dentro do BACKUP_DIR: {p.name}"
        for p in _all_files(c.base):
            if p.resolve() in key_files or p.resolve() == fixture:
                continue
            assert kb not in _file_text(p), f"chave fora do arquivo da chave: {p}"
    assert PLAINTEXT.decode() not in r.stdout + r.stderr, "valor decifrado vazou na saída"
    for p in _all_files(c.base):
        assert PLAINTEXT not in _file_text(p), f"valor decifrado gravado em {p}"


def _proof_word(stdout: str) -> str:
    line = [ln for ln in stdout.splitlines() if "prova de decifra:" in ln]
    assert len(line) == 1, stdout
    return line[0].split("prova de decifra: ", 1)[1].split(" (", 1)[0]


def test_proof_ok_saves_key_0600_separately_and_records_success():
    with Case() as c:
        r = c.run()
        assert r.returncode == 0, r.stderr
        assert _proof_word(r.stdout) == "ok", r.stdout
        kf = c.kdir / "field_encryption_key"
        assert kf.read_text() == c.key, "arquivo da chave tem que conter exatamente a chave"
        assert stat.S_IMODE(kf.stat().st_mode) == 0o600
        assert stat.S_IMODE(c.kdir.stat().st_mode) == 0o700
        fpr = (c.kdir / "field_encryption_key.sha256").read_text().strip()
        assert fpr.startswith("sha256_16=") and len(fpr) == len("sha256_16=") + 16, fpr
        status = (c.kdir / "last_success").read_text()
        assert "result=ok" in status and "dump=sq_20260927_030000.sql.gz" in status, status
        assert not list(c.bdir.glob("*key*")), "nada da chave no diretório dos dumps"
        # só FIELD_ENCRYPTION_KEY sai do env do container, os outros segredos não
        assert b"senha-sintetica" not in kf.read_bytes() and b"outro-segredo" not in kf.read_bytes()
        _assert_no_leak(c, r)


def test_key_and_token_travel_by_stdin_never_argv_or_env():
    with Case() as c:
        r = c.run()
        assert r.returncode == 0, r.stderr
        execs = [ln for ln in c.fk.docker_calls() if ln.startswith("exec ")]
        assert len(execs) == 1 and execs[0].startswith("exec -i sq-web-proto python -c"), execs
        assert " -e " not in execs[0] and "--env" not in execs[0], execs
        _assert_no_leak(c, r)


def test_wrong_key_is_a_failed_proof_with_nonzero_exit():
    Fernet = FakeEnv(Path(tempfile.mkdtemp())).fernet()
    other = Fernet.generate_key().decode()
    with Case(dump_key=other) as c:
        r = c.run()
        assert r.returncode == 2, (r.returncode, r.stderr)
        assert _proof_word(r.stdout) == "falha", r.stdout
        assert not (c.kdir / "last_success").exists(), "falha não grava last_success"
        assert "result=falha" in (c.kdir / "last_proof").read_text()
        _assert_no_leak(c, r, c.key, other)


def test_no_sample_is_a_distinct_state_not_a_false_green():
    with Case(tokens=False) as c:
        r = c.run()
        assert r.returncode == 3, (r.returncode, r.stderr)
        assert _proof_word(r.stdout) == "sem amostra", r.stdout
        assert not (c.kdir / "last_success").exists()
        assert "result=sem amostra" in (c.kdir / "last_proof").read_text()
        _assert_no_leak(c, r)
        r = c.run({"KEY_PROOF_ALLOW_NO_SAMPLE": "1"})
        assert r.returncode == 0 and _proof_word(r.stdout) == "sem amostra", r.stdout
        assert not (c.kdir / "last_success").exists(), "sem amostra nunca vira last_success"
        _assert_no_leak(c, r)


def test_misbehaving_container_output_is_never_relayed():
    """Se o python do container imprimir a chave e o valor decifrado, o script não repassa."""
    with Case() as c:
        (c.fk.ctr_bin / "python").write_text(
            "#!/usr/bin/env bash\n"
            "read -r k; read -r t\n"
            "echo \"ok $k\"\n"
            f"echo {PLAINTEXT.decode()}\n"
            "echo \"$k\" >&2\n"
        )
        r = c.run()
        assert r.returncode == 2, (r.returncode, r.stdout, r.stderr)
        assert _proof_word(r.stdout) == "falha", r.stdout
        assert "suprimida" in r.stderr, r.stderr
        _assert_no_leak(c, r)


def test_key_dir_inside_backup_dir_is_refused():
    with tempfile.TemporaryDirectory() as d:
        with Case(key_dir=Path(d) / "placeholder") as c:
            inside = c.bdir / "keys"
            r = c.run({"KEY_BACKUP_DIR": str(inside)})
            assert r.returncode == 1 and "NUNCA" in r.stderr, r.stderr
            assert not inside.exists()
            assert c.fk.docker_calls() == [], c.fk.docker_calls()
            r = c.run({"KEY_BACKUP_DIR": str(c.bdir)})
            assert r.returncode == 1
            r = c.run({"KEY_BACKUP_DIR": str(c.bdir.parent)})
            assert r.returncode == 1, "BACKUP_DIR dentro do diretório da chave também é recusado"


def test_missing_or_malformed_key_fails_without_echoing_the_value():
    with Case() as c:
        c.fk.set_container_env(["POSTGRES_PASSWORD=senha-sintetica-do-teste"])
        r = c.run()
        assert r.returncode == 1 and "ausente" in r.stderr, r.stderr
        assert not (c.kdir / "field_encryption_key").exists()
        bogus = "valor-que-nao-e-fernet-SINTETICO"
        c.set_key(bogus)
        r = c.run()
        assert r.returncode == 1 and "formato" in r.stderr, r.stderr
        assert bogus not in r.stdout + r.stderr
        assert not (c.kdir / "field_encryption_key").exists()
        assert not list(c.kdir.glob("*.tmp*")), list(c.kdir.iterdir())


def test_key_rotation_preserves_previous_key():
    with Case() as c:
        k1 = c.key
        r = c.run()
        assert r.returncode == 0, r.stderr
        k2 = c.fk.fernet().generate_key().decode()
        c.set_key(k2)
        r = c.run()  # a prova falha (dump foi cifrado com k1), mas a k1 tem que sobreviver
        assert r.returncode == 2, r.stderr
        prev = list(c.kdir.glob("field_encryption_key.prev.*"))
        assert len(prev) == 1 and prev[0].read_text() == k1, prev
        assert stat.S_IMODE(prev[0].stat().st_mode) == 0o600
        assert (c.kdir / "field_encryption_key").read_text() == k2
        assert "MUDOU" in r.stderr, r.stderr
        _assert_no_leak(c, r, k1, k2)



def test_stopped_container_is_an_environment_error_not_a_failed_proof():
    with Case() as c:
        r = c.run({"FAKE_STATE": "false"})
        assert r.returncode == 1, (r.returncode, r.stderr)
        assert "PARADO" in r.stderr, r.stderr
        assert "prova de decifra:" not in r.stdout, "parado não pode virar resultado de prova"
        assert not (c.kdir / "last_proof").exists() and not (c.kdir / "field_encryption_key").exists()
        assert not [x for x in c.fk.docker_calls() if x.startswith("exec ")]
        _assert_no_leak(c, r)


TESTS = [
    test_proof_ok_saves_key_0600_separately_and_records_success,
    test_key_and_token_travel_by_stdin_never_argv_or_env,
    test_wrong_key_is_a_failed_proof_with_nonzero_exit,
    test_no_sample_is_a_distinct_state_not_a_false_green,
    test_misbehaving_container_output_is_never_relayed,
    test_key_dir_inside_backup_dir_is_refused,
    test_missing_or_malformed_key_fails_without_echoing_the_value,
    test_key_rotation_preserves_previous_key,
    test_stopped_container_is_an_environment_error_not_a_failed_proof,
]

if __name__ == "__main__":
    n = run_tests(TESTS)
    print()
    if n:
        print(f"FAILED: {n}/{len(TESTS)} tests failed")
        sys.exit(1)
    print(f"OK: all {len(TESTS)} tests passed")
