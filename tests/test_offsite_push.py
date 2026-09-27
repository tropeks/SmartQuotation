"""
Tests: scripts/offsite_push.sh — dump e mídia cifrados com age para dois destinatários e
enviados com rclone (ordem 003). Também a decisão (a) do Diretor no docs/SECURITY.md e o
runbook na §6 do INFRASTRUCTURE.

age e rclone FALSOS (tests/_offsite_fakes.py). Dump, mídia e chave SINTÉTICOS.
"""
import hashlib
import re
import stat
import subprocess
import sys
from pathlib import Path

from tests._offsite_fakes import (
    DUMP, DUMP_REMOTE, MEDIA, OffsiteCase, assert_no_leak, assert_no_rclone_violation,
    objects, split_age, status,
)
from tests._ops_fakes import ROOT, run_tests

PRIVATE = "AGE-SECRET-KEY-1" + "Q" * 58


def _assert_is_two_recipient_age_of(obj: Path, local: Path):
    stanzas, payload = split_age(obj.read_bytes())
    assert len(stanzas) == 2 and all(s.split()[1] == "X25519" for s in stanzas), stanzas
    assert payload == local.read_bytes(), f"{obj.name}: conteúdo enviado != arquivo local"


def test_success_pushes_newest_dump_and_media_to_two_recipients_and_records_status():
    with OffsiteCase() as c:
        r = c.push()
        assert r.returncode == 0, r.stderr
        objs = objects(c.dump_bucket)
        assert sorted(p.name for p in objs) == sorted([f"{DUMP}.age", f"{MEDIA}.age"]), objs
        for p in objs:
            _assert_is_two_recipient_age_of(p, c.bdir / p.name[:-4])
        calls = c.age_calls()
        assert len(calls) == 2, calls
        assert all(sorted(x["recipients"]) == sorted(c.rcpt.values()) for x in calls), calls
        st_path = c.bdir / "offsite_last_success"
        assert stat.S_IMODE(st_path.stat().st_mode) == 0o600
        st = status(st_path)
        dump_obj = c.dump_bucket / f"{DUMP}.age"
        assert st["remote"] == DUMP_REMOTE and st["dump"] == f"{DUMP}.age", st
        assert st["dump_result"] == "enviado", st
        assert st["dump_hash"] == "sha1:" + hashlib.sha1(dump_obj.read_bytes()).hexdigest(), st
        assert st["dump_bytes"] == str(dump_obj.stat().st_size), st
        assert st["media"] == f"{MEDIA}.age" and st["media_hash"].startswith("sha1:"), st
        assert stat.S_IMODE((c.bdir / "offsite_manifest").stat().st_mode) == 0o600
        leftovers = list(c.bdir.glob("*.tmp*")) + list(c.bdir.glob(".offsite*"))
        assert not leftovers, leftovers
        assert_no_rclone_violation(c)
        assert_no_leak(c, r)


def test_second_run_is_idempotent_and_skips_upload():
    with OffsiteCase() as c:
        r1 = c.push()
        assert r1.returncode == 0, r1.stderr
        first = {p.name: p.read_bytes() for p in objects(c.dump_bucket)}
        n_copy, n_age = len(c.copytos()), len(c.age_calls())
        r2 = c.push()
        assert r2.returncode == 0, r2.stderr
        assert len(c.copytos()) == n_copy and len(c.age_calls()) == n_age, "segundo envio não pulou"
        assert {p.name: p.read_bytes() for p in objects(c.dump_bucket)} == first
        st = status(c.bdir / "offsite_last_success")
        assert st["dump_result"] == "já presente" and st["media_result"] == "já presente", st
        assert_no_rclone_violation(c)
        assert_no_leak(c, [r1, r2])


def test_absent_object_reported_as_directory_not_found_is_uploaded():
    with OffsiteCase() as c:
        r = c.push({"FAKE_RCLONE_ABSENT_RC": "3"})
        assert r.returncode == 0, r.stderr
        assert len(c.copytos()) == 2


def test_foreign_remote_object_is_never_overwritten():
    with OffsiteCase() as c:
        target = c.dump_bucket / f"{DUMP}.age"
        target.parent.mkdir(parents=True)
        target.write_bytes(b"objeto de outro host")
        r = c.push()
        assert r.returncode != 0 and "nunca é sobrescrito" in r.stderr, r.stderr
        assert target.read_bytes() == b"objeto de outro host"
        assert not c.copytos() and not (c.bdir / "offsite_last_success").exists()
        assert_no_rclone_violation(c)


def test_remote_object_changed_after_upload_is_never_overwritten():
    with OffsiteCase() as c:
        assert c.push().returncode == 0
        target = c.dump_bucket / f"{DUMP}.age"
        target.write_bytes(b"adulterado")
        n = len(c.copytos())
        r = c.push()
        assert r.returncode != 0 and "DIFERENTE" in r.stderr, r.stderr
        assert len(c.copytos()) == n and target.read_bytes() == b"adulterado"


def test_remote_hash_mismatch_after_upload_fails_without_status():
    with OffsiteCase() as c:
        r = c.push({"FAKE_RCLONE_CORRUPT": "1"})
        assert r.returncode != 0 and "não confere" in r.stderr, r.stderr
        assert not (c.bdir / "offsite_last_success").exists()
        # a próxima execução não "conserta" sobrescrevendo: o objeto errado é divergente
        r = c.push()
        assert r.returncode != 0 and "DIFERENTE" in r.stderr, r.stderr
        assert_no_rclone_violation(c)


def test_header_without_exactly_two_x25519_stanzas_is_not_sent():
    for extra in ({"FAKE_AGE_EXTRA_STANZA": "1"}, {"FAKE_AGE_STANZA_TYPE": "scrypt"}):
        with OffsiteCase() as c:
            r = c.push(extra)
            assert r.returncode != 0 and "stanza" in r.stderr, (extra, r.stderr)
            assert not c.copytos() and not objects(c.dump_bucket)
            assert not (c.bdir / "offsite_last_success").exists()
            assert not list(c.bdir.glob(".offsite*")), "temporário .age sobrou"


def _refused_before_any_tool(extra_or_fn, word):
    with OffsiteCase() as c:
        extra = extra_or_fn(c) if callable(extra_or_fn) else extra_or_fn
        r = c.push(extra)
        assert r.returncode == 1 and word in r.stderr, (extra, r.stderr)
        assert PRIVATE not in r.stdout + r.stderr, "valor da chave privada exibido"
        assert c.untouched(), "tocou em age/rclone antes de recusar"


def test_missing_single_private_or_fictitious_recipient_is_refused():
    _refused_before_any_tool({"OFFSITE_AGE_RECIPIENT_INSTANCE": ""}, "ausente")
    _refused_before_any_tool({"OFFSITE_AGE_RECIPIENT_RECOVERY": ""}, "ausente")
    _refused_before_any_tool({"OFFSITE_AGE_RECIPIENT_RECOVERY": PRIVATE}, "PRIVADA")
    _refused_before_any_tool({"OFFSITE_AGE_RECIPIENT_INSTANCE": "age1naoechave"}, "formato")
    _refused_before_any_tool({"OFFSITE_AGE_RECIPIENT_INSTANCE": "age1" + "q" * 58}, "FICTÍCIO")
    _refused_before_any_tool(lambda c: {"OFFSITE_AGE_RECIPIENT_RECOVERY": c.rcpt["instance"]}, "MESMA")


def test_rclone_config_readable_by_others_or_connection_string_is_refused():
    _refused_before_any_tool({"OFFSITE_REMOTE": ":b2,account=ID,key=SEGREDO:bucket"}, "inválido")
    with OffsiteCase() as c:
        Path(c.fk.env["RCLONE_CONFIG"]).chmod(0o644)
        r = c.push()
        assert r.returncode == 1 and "chmod 600" in r.stderr, r.stderr
        assert c.untouched()


def test_rclone_lookup_error_is_not_read_as_absent():
    with OffsiteCase() as c:
        r = c.push({"FAKE_RCLONE_FAIL": "hashsum"})
        assert r.returncode != 0 and "hashsum falhou" in r.stderr, r.stderr
        assert not c.copytos(), "erro de consulta não pode virar envio"


def test_remote_without_hash_fails_loudly():
    with OffsiteCase() as c:
        assert c.push().returncode == 0
        r = c.push({"FAKE_RCLONE_NO_HASH": "1"})
        assert r.returncode != 0 and "OFFSITE_HASH_DOWNLOAD" in r.stderr, r.stderr


_FORBIDDEN = re.compile(r"\b(delete|deletefile|purge|sync|move|moveto|rmdirs?|cleanup|dedupe)\b")


def _rclone_code_lines(name: str) -> list[str]:
    lines = (ROOT / "scripts" / name).read_text().splitlines()
    return [ln for ln in lines if "RCLONE" in ln and not ln.lstrip().startswith("#")]


def test_no_remote_delete_ever():
    """Sem poda remota enquanto a DP-27 estiver aberta: nem os scripts chamam, nem o fake aceita."""
    with OffsiteCase() as c:
        runs = [c.push_key(), c.push(), c.push()]
        assert all(x.returncode == 0 for x in runs), [x.stderr for x in runs]
        assert_no_rclone_violation(c)
        # o fake de fato pega um delete (senão o assert acima seria vazio)
        p = subprocess.run(["rclone", "delete", DUMP_REMOTE], env=c.fk.env, capture_output=True)
        assert p.returncode == 99 and "VIOLATION delete" in c.rclone_log.read_text()
    for name in ("offsite_push.sh", "offsite_key_push.sh", "lib/offsite_common.sh"):
        bad = [ln.strip() for ln in _rclone_code_lines(name) if _FORBIDDEN.search(ln)]
        assert not bad, f"{name}: {bad}"


# --- documentação (decisão (a) e runbook) ----------------------------------------------------

def test_security_doc_says_foreign_offsite_is_allowed_by_dp29():
    doc = (ROOT / "docs" / "SECURITY.md").read_text()
    row = [ln for ln in doc.splitlines() if ln.startswith("| J-29")]
    assert len(row) == 1, row
    assert "permitido pela DP-29" in row[0] and "parecer J-29 pode mudar o destino" in row[0], row
    assert "espera o parecer" not in doc, "off-site estrangeiro não espera mais o parecer (decisão (a))"


def test_infra_doc_offsite_section_covers_scripts_remotes_ship_and_drill():
    doc = (ROOT / "docs" / "INFRASTRUCTURE.md").read_text()
    sec6 = " ".join(doc[doc.index("## 6. Backup e Recuperação"):doc.index("## 7.")].split())
    for needle in ("offsite_push.sh", "offsite_key_push.sh", "OFFSITE_REMOTE", "OFFSITE_KEY_REMOTE",
                   "OFFSITE_AGE_RECIPIENT_INSTANCE", "OFFSITE_AGE_RECIPIENT_RECOVERY",
                   "DP-29", "DP-27", "DP-41", "drill trimestral", "RESTORE_DUMP_FILE",
                   "offsite_last_success", "rclone.conf", "parecer J-29 pode mudar o destino",
                   "age1yubikey1", "age-plugin-yubikey", "decisão de instalação", "só para cifrar"):
        assert needle in sec6, f"§6 não cita {needle}"
    assert "Off-site (ordem 003, não existe)" not in doc


TESTS = [
    test_success_pushes_newest_dump_and_media_to_two_recipients_and_records_status,
    test_second_run_is_idempotent_and_skips_upload,
    test_absent_object_reported_as_directory_not_found_is_uploaded,
    test_foreign_remote_object_is_never_overwritten,
    test_remote_object_changed_after_upload_is_never_overwritten,
    test_remote_hash_mismatch_after_upload_fails_without_status,
    test_header_without_exactly_two_x25519_stanzas_is_not_sent,
    test_missing_single_private_or_fictitious_recipient_is_refused,
    test_rclone_config_readable_by_others_or_connection_string_is_refused,
    test_rclone_lookup_error_is_not_read_as_absent,
    test_remote_without_hash_fails_loudly,
    test_no_remote_delete_ever,
    test_security_doc_says_foreign_offsite_is_allowed_by_dp29,
    test_infra_doc_offsite_section_covers_scripts_remotes_ship_and_drill,
]

if __name__ == "__main__":
    n = run_tests(TESTS)
    print()
    if n:
        print(f"FAILED: {n}/{len(TESTS)} tests failed")
        sys.exit(1)
    print(f"OK: all {len(TESTS)} tests passed")
