"""
Tests: scripts/offsite_key_push.sh — a FIELD_ENCRYPTION_KEY em custódia off-site SEPARADA
(ordem 003, decisão (b) do Diretor), e a condição da 002 sobre a cadeia inteira: a chave e o
.env.prod nunca entram no que o remote do dump recebe.

age e rclone FALSOS (tests/_offsite_fakes.py). Chave SINTÉTICA (Fernet.generate_key).
"""
import hashlib
import stat
import sys

from tests._offsite_fakes import (
    DUMP_OBJECT_RE, DUMP_REMOTE, KEY_OBJECT_RE, KEY_REMOTE, OffsiteCase, assert_no_leak,
    assert_no_rclone_violation, objects, split_age, status,
)
from tests._ops_fakes import run_tests


def _fpr(key: str) -> str:
    return hashlib.sha256(key.encode()).hexdigest()[:16]


def _key_fprs(c) -> list:
    """Fingerprint de cada objeto no remote da chave (o nome tem de seguir o padrão)."""
    out = []
    for p in objects(c.key_bucket):
        m = KEY_OBJECT_RE.fullmatch(p.name)
        assert m, f"nome de objeto da chave fora do padrão: {p.name}"
        out.append(m.group(1))
    return sorted(out)


def test_key_goes_only_to_key_remote_encrypted_only_to_recovery():
    with OffsiteCase() as c:
        r = c.push_key()
        assert r.returncode == 0, r.stderr
        objs = objects(c.key_bucket)
        assert _key_fprs(c) == [_fpr(c.key)], objs
        stanzas, payload = split_age(objs[0].read_bytes())
        assert len(stanzas) == 1 and stanzas[0].split()[1] == "X25519", stanzas
        assert payload == c.key.encode()
        calls = c.age_calls()
        assert len(calls) == 1 and calls[0]["recipients"] == [c.rcpt["recovery"]], calls
        assert not objects(c.dump_bucket), "a chave não passa pelo remote do dump"
        for name in ("offsite_key_fingerprint", "offsite_key_last_success", "offsite_key_manifest"):
            assert stat.S_IMODE((c.kdir / name).stat().st_mode) == 0o600, name
        fp = status(c.kdir / "offsite_key_fingerprint")
        assert fp == {"sha256_16": _fpr(c.key), "object": objs[0].name}, fp
        st = status(c.kdir / "offsite_key_last_success")
        assert st["remote"] == KEY_REMOTE and st["result"] == "enviado", st
        assert st["hash"] == "sha1:" + hashlib.sha1(objs[0].read_bytes()).hexdigest(), st
        assert not list(c.kdir.glob(".offsite*")), "temporário da chave sobrou"
        assert_no_rclone_violation(c)
        assert_no_leak(c, r)


def test_key_is_sent_only_when_fingerprint_changes():
    with OffsiteCase() as c:
        k1 = c.key
        r1 = c.push_key()
        assert r1.returncode == 0, r1.stderr
        n_rclone = len(c.rclone_calls())
        r2 = c.push_key()
        assert r2.returncode == 0 and "inalterada" in r2.stderr and "conferido" in r2.stderr, r2.stderr
        assert len(c.age_calls()) == 1 and not c.copytos()[1:], "reenviou chave igual"
        new_calls = c.rclone_calls()[n_rclone:]
        assert len(new_calls) == 1 and new_calls[0].startswith("hashsum "), new_calls  # só confere
        k2 = c.fk.fernet().generate_key().decode()
        c.write_key(k2)
        r3 = c.push_key()
        assert r3.returncode == 0, r3.stderr
        assert _key_fprs(c) == sorted([_fpr(k1), _fpr(k2)])
        assert status(c.kdir / "offsite_key_fingerprint")["sha256_16"] == _fpr(k2)
        assert_no_rclone_violation(c)
        assert_no_leak(c, [r1, r2, r3], k1, k2)


def _refused_by_both_scripts(key_remote: str, word: str):
    with OffsiteCase() as c:
        for run in (c.push_key, c.push):
            r = run({"OFFSITE_KEY_REMOTE": key_remote})
            assert r.returncode == 1 and word in r.stderr, (key_remote, r.stderr)
        assert c.untouched()


def test_key_remote_equal_inside_or_same_section_as_dump_remote_is_refused():
    _refused_by_both_scripts(DUMP_REMOTE, "igual")
    _refused_by_both_scripts(DUMP_REMOTE + "/chave", "igual")
    _refused_by_both_scripts("sq-offsite:sq-backup", "igual")
    _refused_by_both_scripts("sq-offsite:outro-bucket", "mesma seção")
    with OffsiteCase() as c:
        r = c.push_key({"OFFSITE_KEY_REMOTE": ""})
        assert r.returncode == 1 and "OFFSITE_KEY_REMOTE ausente" in r.stderr, r.stderr


def test_key_recipient_missing_or_private_is_refused_without_echo():
    private = "AGE-SECRET-KEY-1" + "Q" * 58
    with OffsiteCase() as c:
        r = c.push_key({"OFFSITE_AGE_RECIPIENT_RECOVERY": private})
        assert r.returncode == 1 and "PRIVADA" in r.stderr and private not in r.stderr, r.stderr
        r = c.push_key({"OFFSITE_AGE_RECIPIENT_RECOVERY": ""})
        assert r.returncode == 1 and "ausente" in r.stderr, r.stderr
        assert c.untouched()


def test_key_file_not_0600_or_key_dir_inside_backup_dir_is_refused():
    with OffsiteCase() as c:
        (c.kdir / "field_encryption_key").chmod(0o640)
        r = c.push_key()
        assert r.returncode == 1 and "0600" in r.stderr, r.stderr
        assert c.untouched()
    with OffsiteCase() as c:
        inside = str(c.bdir / "keys")
        for run in (c.push_key, c.push):
            r = run({"KEY_BACKUP_DIR": inside})
            assert r.returncode == 1 and "NUNCA mora com o dump" in r.stderr, r.stderr
        assert c.untouched()


def test_full_chain_never_puts_key_or_env_prod_in_dump_remote():
    """Condição da 002 (item 5 da 003): tudo que o remote do dump recebeu é varrido."""
    with OffsiteCase() as c:
        r1 = c.push_key()
        r2 = c.push()
        assert r1.returncode == 0 and r2.returncode == 0, (r1.stderr, r2.stderr)
        names = [p.name for p in objects(c.dump_bucket)]
        assert names and all(DUMP_OBJECT_RE.fullmatch(n) for n in names), names
        assert objects(c.key_bucket), "a chave foi para a custódia"
        assert_no_leak(c, [r1, r2])


def test_new_host_with_same_key_appends_a_new_object_never_fails_daily():
    """Pós-desastre: host novo, mesma chave, sem fingerprint nem manifesto locais."""
    with OffsiteCase() as c:
        assert c.push_key().returncode == 0
        first = [p.name for p in objects(c.key_bucket)]
        for name in ("offsite_key_fingerprint", "offsite_key_manifest", "offsite_key_last_success"):
            (c.kdir / name).unlink()
        r = c.push_key()
        assert r.returncode == 0, r.stderr
        names = [p.name for p in objects(c.key_bucket)]
        assert len(names) == 2 and set(first) < set(names), names  # append, o antigo intacto
        assert _key_fprs(c) == [_fpr(c.key)] * 2
        r = c.push_key()  # e no dia seguinte, verde sem reenviar
        assert r.returncode == 0 and "inalterada" in r.stderr, r.stderr
        assert len(objects(c.key_bucket)) == 2
        assert_no_leak(c, r)


def test_unchanged_key_whose_object_vanished_or_remote_is_down_fails():
    with OffsiteCase() as c:
        assert c.push_key().returncode == 0
        r = c.push_key({"FAKE_RCLONE_FAIL": "hashsum"})
        assert r.returncode != 0 and "hashsum falhou" in r.stderr, r.stderr
        objects(c.key_bucket)[0].unlink()
        r = c.push_key()
        assert r.returncode != 0 and "sumiu" in r.stderr, r.stderr
        assert not c.copytos()[1:], "sumiço não é consertado reenviando por baixo dos panos"


TESTS = [
    test_key_goes_only_to_key_remote_encrypted_only_to_recovery,
    test_key_is_sent_only_when_fingerprint_changes,
    test_key_remote_equal_inside_or_same_section_as_dump_remote_is_refused,
    test_key_recipient_missing_or_private_is_refused_without_echo,
    test_key_file_not_0600_or_key_dir_inside_backup_dir_is_refused,
    test_full_chain_never_puts_key_or_env_prod_in_dump_remote,
    test_new_host_with_same_key_appends_a_new_object_never_fails_daily,
    test_unchanged_key_whose_object_vanished_or_remote_is_down_fails,
]

if __name__ == "__main__":
    n = run_tests(TESTS)
    print()
    if n:
        print(f"FAILED: {n}/{len(TESTS)} tests failed")
        sys.exit(1)
    print(f"OK: all {len(TESTS)} tests passed")
