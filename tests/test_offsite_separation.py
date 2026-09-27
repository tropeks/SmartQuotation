"""
Tests: separação de credencial entre o remote do dump e o da chave, lida do rclone.conf
(ordem 003, revisão). O nome da seção não prova nada; os scripts leem o RCLONE_CONFIG e
recusam, SEM imprimir valor nenhum do arquivo:
  - type fora da allowlist de armazenamento direto (wrappers e afins);
  - o mesmo bucket em QUALQUER tipo (B2 nativo e S3 da Backblaze são o mesmo bucket);
  - qualquer valor de credencial em comum, sem olhar o nome do campo (account= no b2 e
    access_key_id= no s3 com a mesma chave);
  - variável RCLONE_CONFIG_<SEÇÃO>_* no ambiente;
  - seção ausente (ou rclone.conf cifrado).
Os dois scripts (offsite_key_push e offsite_push) aplicam a mesma checagem.
"""
import re
import sys

from tests._offsite_fakes import OffsiteCase
from tests._ops_fakes import run_tests

IDENTITY_FIELDS = ("account", "access_key_id", "key_id", "user", "client_id", "service_account_file")
SHARED = "K-COMPARTILHADA-SEGREDO"


def _conf(dump_extra="", key_extra="", dump_type="local", key_type="local"):
    return (f"[sq-offsite]\ntype = {dump_type}\naccount = CONTA-DUMP-SEGREDO\n"
            f"key = CHAVE-DUMP-SEGREDO\n{dump_extra}\n"
            f"[sq-offsite-key]\ntype = {key_type}\naccount = CONTA-CHAVE-SEGREDO\n"
            f"key = CHAVE-CHAVE-SEGREDO\n{key_extra}\n")


def _conf_values(text: str) -> list:
    """Valores do conf que não podem aparecer na saída (o type é nome de backend, não segredo,
    e a mensagem de wrapper o cita de propósito)."""
    return [v.strip() for k, v in re.findall(r"^\s*([a-z_]+)\s*=\s*(.+)$", text, re.M)
            if k != "type" and len(v.strip()) > 5]


def _run_both(conf: str, extra=None):
    """(resultados dos dois scripts, o caso) — sempre confere que nada do conf vazou."""
    c = OffsiteCase()
    c.write_conf(conf)
    runs = [c.push_key(extra), c.push(extra)]
    for r in runs:
        out = r.stdout + r.stderr
        for v in _conf_values(conf):
            assert v not in out, f"valor do rclone.conf vazou: {v!r}"
    return runs, c


def _assert_refused(conf: str, word: str, extra=None):
    runs, c = _run_both(conf, extra)
    with c:
        for r in runs:
            assert r.returncode == 1 and word in r.stderr, (word, r.stderr)
        assert c.untouched(), "tocou em age/rclone antes de recusar"


def test_distinct_sections_types_buckets_and_identities_are_accepted():
    runs, c = _run_both(_conf())
    with c:
        assert all(r.returncode == 0 for r in runs), [r.stderr for r in runs]


def test_only_direct_storage_backends_are_accepted():
    """Allowlist: wrapper (e qualquer backend fora da lista) é recusado por padrão."""
    _assert_refused(_conf(key_type="alias", key_extra="remote = sq-offsite:sq-backup"), "armazenamento direto")
    _assert_refused(_conf(dump_type="crypt", dump_extra="password = SENHA-CRYPT-SEGREDO"), "armazenamento direto")
    for other in ("union", "combine", "chunker", "compress", "hasher", "cache", "webdav", "ftp", "memory"):
        _assert_refused(_conf(key_type=other), "armazenamento direto")
    _assert_refused("[sq-offsite]\ntype = local\n[sq-offsite-key]\naccount = X-SEGREDO-1\n", "armazenamento direto")
    for ok in ("s3", "b2", "gcs", "azureblob", "swift", "oos", "sftp"):
        runs, c = _run_both(_conf(dump_type=ok, key_type=ok))
        with c:
            assert all(r.returncode == 0 for r in runs), (ok, [r.stderr for r in runs])


def test_same_bucket_is_refused_in_any_type():
    same_bucket = {"OFFSITE_KEY_REMOTE": "sq-offsite-key:sq-backup/chave"}
    for key_type in ("local", "s3", "b2"):
        _assert_refused(_conf(key_type=key_type), "MESMO bucket", same_bucket)


def test_b2_native_and_s3_backblaze_with_the_same_key_are_refused_without_echo():
    """A mesma application key da Backblaze como account= (b2) e access_key_id= (s3)."""
    b2 = f"[sq-offsite]\ntype = b2\naccount = {SHARED}\nkey = SEGREDO-APP-KEY-B2\n"
    s3 = (f"[sq-offsite-key]\ntype = s3\nprovider = Other\naccess_key_id = {SHARED}\n"
          "secret_access_key = SEGREDO-S3-OUTRO\nendpoint = s3.us-west-000.backblazeb2.com\n")
    _assert_refused(b2 + s3, "VALOR de credencial em comum")
    _assert_refused(b2 + s3, "MESMO bucket", {"OFFSITE_KEY_REMOTE": "sq-offsite-key:sq-backup/chave"})
    s3_same_secret = s3.replace(SHARED, "OUTRA-ID-SEGREDO").replace("SEGREDO-S3-OUTRO", "SEGREDO-APP-KEY-B2")
    _assert_refused(b2 + s3_same_secret, "VALOR de credencial em comum")


def test_rclone_config_env_override_for_either_section_is_refused_without_echo():
    for var in ("RCLONE_CONFIG_SQ_OFFSITE_KEY_ACCOUNT", "RCLONE_CONFIG_SQ_OFFSITE_TYPE"):
        runs, c = _run_both(_conf(), {var: "VALOR-DO-ENV-SEGREDO"})
        with c:
            for r in runs:
                assert r.returncode == 1 and "RCLONE_CONFIG_" in r.stderr, r.stderr
                assert "VALOR-DO-ENV-SEGREDO" not in r.stdout + r.stderr
            assert c.untouched()


def test_same_credential_value_is_refused_whatever_the_field_names():
    for field in IDENTITY_FIELDS:
        for other in IDENTITY_FIELDS:
            conf = _conf(dump_extra=f"{field} = {SHARED}", key_extra=f"{other} = {SHARED}")
            conf = conf.replace("account = CONTA-DUMP-SEGREDO\n", "", 1) if field == "account" else conf
            _assert_refused(conf, "VALOR de credencial em comum")


def test_missing_section_or_encrypted_conf_is_refused():
    _assert_refused("[sq-offsite]\ntype = local\n", "não encontrada")
    _assert_refused("# Encrypted rclone configuration File\n\nRCLONE_ENCRYPT_V0:\nQUFBQS1TRUdSRURP\n",
                    "não encontrada")


TESTS = [
    test_distinct_sections_types_buckets_and_identities_are_accepted,
    test_only_direct_storage_backends_are_accepted,
    test_same_bucket_is_refused_in_any_type,
    test_b2_native_and_s3_backblaze_with_the_same_key_are_refused_without_echo,
    test_rclone_config_env_override_for_either_section_is_refused_without_echo,
    test_same_credential_value_is_refused_whatever_the_field_names,
    test_missing_section_or_encrypted_conf_is_refused,
]

if __name__ == "__main__":
    n = run_tests(TESTS)
    print()
    if n:
        print(f"FAILED: {n}/{len(TESTS)} tests failed")
        sys.exit(1)
    print(f"OK: all {len(TESTS)} tests passed")
