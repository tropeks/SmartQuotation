"""
Tests: separação de credencial entre o remote do dump e o da chave, lida do rclone.conf
(ordem 003, revisão). O nome da seção não prova nada; os scripts leem o RCLONE_CONFIG e
recusam, SEM imprimir valor nenhum do arquivo:
  - wrapper (alias, crypt, union...) em qualquer das duas seções;
  - mesmo type + mesmo bucket, ainda que por seções diferentes;
  - mesmo valor em campo de identidade (account, access_key_id, key_id, user, client_id,
    service_account_file);
  - seção ausente (ou rclone.conf cifrado).
Os dois scripts (offsite_key_push e offsite_push) aplicam a mesma checagem.
"""
import re
import sys

from tests._offsite_fakes import OffsiteCase
from tests._ops_fakes import run_tests

IDENTITY_FIELDS = ("account", "access_key_id", "key_id", "user", "client_id", "service_account_file")


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


def test_wrapper_section_is_refused():
    _assert_refused(_conf(key_type="alias", key_extra="remote = sq-offsite:sq-backup"), "wrapper")
    _assert_refused(_conf(dump_type="crypt", dump_extra="password = SENHA-CRYPT-SEGREDO"), "wrapper")
    for wrapper in ("union", "combine", "chunker", "compress", "hasher", "cache"):
        _assert_refused(_conf(key_type=wrapper), "wrapper")


def test_same_bucket_same_type_is_refused_even_across_sections():
    _assert_refused(_conf(), "MESMO bucket",
                    {"OFFSITE_KEY_REMOTE": "sq-offsite-key:sq-backup/chave"})
    runs, c = _run_both(_conf(key_type="s3"), {"OFFSITE_KEY_REMOTE": "sq-offsite-key:sq-backup/chave"})
    with c:  # outro tipo de backend: o mesmo nome de bucket é outro bucket
        assert all(r.returncode == 0 for r in runs), [r.stderr for r in runs]


def test_same_identity_value_in_both_sections_is_refused_without_echo():
    for field in IDENTITY_FIELDS:
        line = f"{field} = IDENTIDADE-COMPARTILHADA-SEGREDO"
        conf = _conf(dump_extra=line, key_extra=line)
        if field == "account":
            conf = conf.replace("CONTA-CHAVE-SEGREDO", "CONTA-DUMP-SEGREDO")
        _assert_refused(conf, f"'{field}'")


def test_missing_section_or_encrypted_conf_is_refused():
    _assert_refused("[sq-offsite]\ntype = local\n", "não encontrada")
    _assert_refused("# Encrypted rclone configuration File\n\nRCLONE_ENCRYPT_V0:\nQUFBQS1TRUdSRURP\n",
                    "não encontrada")


TESTS = [
    test_distinct_sections_types_buckets_and_identities_are_accepted,
    test_wrapper_section_is_refused,
    test_same_bucket_same_type_is_refused_even_across_sections,
    test_same_identity_value_in_both_sections_is_refused_without_echo,
    test_missing_section_or_encrypted_conf_is_refused,
]

if __name__ == "__main__":
    n = run_tests(TESTS)
    print()
    if n:
        print(f"FAILED: {n}/{len(TESTS)} tests failed")
        sys.exit(1)
    print(f"OK: all {len(TESTS)} tests passed")
