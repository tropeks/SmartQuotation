"""
Tests: destinatário YubiKey (age-plugin-yubikey, DP-41) no off-site da ordem 003.

A chave de recuperação da Quantum pode ser X25519 (age1…) ou YubiKey (age1yubikey1…) — a forma
é decisão de instalação. Com YubiKey, o age escreve a stanza "-> piv-p256 <tag> <share>" e
chama o age-plugin-yubikey para CIFRAR (a identidade fica no token). Provado aqui, com o age
falso de tests/_offsite_fakes.py:
  - mistura X25519 + YubiKey cifra, confere uma stanza do tipo certo por destinatário e envia;
  - stanza de tipo errado para o destinatário é recusada antes do envio;
  - YubiKey sem o plugin no PATH é recusado antes de tocar em age/rclone;
  - identidade do plugin (AGE-PLUGIN-YUBIKEY-…) no lugar do destinatário é recusada sem eco;
  - configuração só X25519 não exige o plugin.
"""
import sys

from tests._offsite_fakes import (
    DUMP, MEDIA, OffsiteCase, assert_no_leak, assert_no_rclone_violation, fake_yubikey_recipient,
    objects, split_age,
)
from tests._ops_fakes import run_tests

IDENTITY = "AGE-PLUGIN-YUBIKEY-1" + "Q" * 60


def _types(obj) -> list:
    return sorted(s.split()[1] for s in split_age(obj.read_bytes())[0])


def _yubikey_case(which: str) -> OffsiteCase:
    c = OffsiteCase()
    c.install_yubikey_plugin()
    c.rcpt[which] = fake_yubikey_recipient()
    c.fk.env[f"OFFSITE_AGE_RECIPIENT_{which.upper()}"] = c.rcpt[which]
    return c


def test_x25519_instance_plus_yubikey_recovery_succeeds_with_typed_stanzas():
    with _yubikey_case("recovery") as c:
        rk, rp = c.push_key(), c.push()
        assert rk.returncode == 0 and rp.returncode == 0, (rk.stderr, rp.stderr)
        for name in (DUMP, MEDIA):
            obj = c.dump_bucket / f"{name}.age"
            assert _types(obj) == ["X25519", "piv-p256"], _types(obj)
            piv = [s for s in split_age(obj.read_bytes())[0] if s.split()[1] == "piv-p256"]
            assert len(piv[0].split()) == 4, f"piv-p256 sem <tag> <share>: {piv}"
        key_objs = objects(c.key_bucket)
        assert len(key_objs) == 1 and _types(key_objs[0]) == ["piv-p256"], key_objs
        assert c.age_calls()[0]["recipients"] == [c.rcpt["recovery"]]
        assert_no_rclone_violation(c)
        assert_no_leak(c, [rk, rp])


def test_yubikey_instance_plus_x25519_recovery_also_works():
    with _yubikey_case("instance") as c:
        r = c.push()
        assert r.returncode == 0, r.stderr
        assert _types(c.dump_bucket / f"{DUMP}.age") == ["X25519", "piv-p256"]
        r = c.push_key()
        assert r.returncode == 0, r.stderr
        assert _types(objects(c.key_bucket)[0]) == ["X25519"]


def test_stanza_of_wrong_type_for_recipient_is_refused_before_upload():
    with _yubikey_case("recovery") as c:
        for run in (c.push_key, c.push):
            r = run({"FAKE_AGE_STANZA_TYPE": "X25519"})
            assert r.returncode == 1 and "do tipo esperado" in r.stderr, r.stderr
        assert not c.copytos() and not objects(c.buckets), "nada pode ser enviado"
    with OffsiteCase() as c:  # só X25519, mas o age escreveu piv-p256
        c.install_yubikey_plugin()
        r = c.push({"FAKE_AGE_STANZA_TYPE": "piv-p256"})
        assert r.returncode == 1 and "do tipo esperado" in r.stderr, r.stderr
        assert not c.copytos()


def test_yubikey_without_plugin_is_refused_before_any_tool():
    for which in ("recovery", "instance"):
        with OffsiteCase() as c:
            yk = fake_yubikey_recipient()
            extra = {f"OFFSITE_AGE_RECIPIENT_{which.upper()}": yk, "PATH": c.path_without_yubikey_plugin()}
            runs = [c.push(extra)] + ([c.push_key(extra)] if which == "recovery" else [])
            for r in runs:
                assert r.returncode == 1 and "age-plugin-yubikey não está no PATH" in r.stderr, r.stderr
            assert c.untouched(), "tocou em age/rclone sem o plugin"


def test_plugin_identity_is_refused_without_echo():
    with OffsiteCase() as c:
        for run in (c.push_key, c.push):
            r = run({"OFFSITE_AGE_RECIPIENT_RECOVERY": IDENTITY})
            assert r.returncode == 1 and "IDENTIDADE" in r.stderr, r.stderr
            assert IDENTITY not in r.stdout + r.stderr, "identidade do plugin exibida"
        assert c.untouched()


def test_x25519_only_does_not_require_the_plugin():
    with OffsiteCase() as c:
        extra = {"PATH": c.path_without_yubikey_plugin()}
        rk, rp = c.push_key(extra), c.push(extra)
        assert rk.returncode == 0 and rp.returncode == 0, (rk.stderr, rp.stderr)


def test_fictitious_yubikey_recipient_is_refused():
    with OffsiteCase() as c:
        c.install_yubikey_plugin()
        r = c.push({"OFFSITE_AGE_RECIPIENT_RECOVERY": "age1yubikey1" + "q" * 59})
        assert r.returncode == 1 and "FICTÍCIO" in r.stderr, r.stderr
        assert c.untouched()


TESTS = [
    test_x25519_instance_plus_yubikey_recovery_succeeds_with_typed_stanzas,
    test_yubikey_instance_plus_x25519_recovery_also_works,
    test_stanza_of_wrong_type_for_recipient_is_refused_before_upload,
    test_yubikey_without_plugin_is_refused_before_any_tool,
    test_plugin_identity_is_refused_without_echo,
    test_x25519_only_does_not_require_the_plugin,
    test_fictitious_yubikey_recipient_is_refused,
]

if __name__ == "__main__":
    n = run_tests(TESTS)
    print()
    if n:
        print(f"FAILED: {n}/{len(TESTS)} tests failed")
        sys.exit(1)
    print(f"OK: all {len(TESTS)} tests passed")
