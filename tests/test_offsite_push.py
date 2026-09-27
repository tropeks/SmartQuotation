"""
Tests: scripts/offsite_push.sh — dump e mídia cifrados com age para dois destinatários e
enviados com rclone (ordem 003). Também a decisão (a) do Diretor no docs/SECURITY.md e o
runbook na §6 do INFRASTRUCTURE.

age e rclone FALSOS (tests/_offsite_fakes.py). Dump, mídia e chave SINTÉTICOS.
"""
import hashlib
import os
import re
import stat
import time
import subprocess
import sys
from pathlib import Path

from tests._offsite_fakes import (
    DUMP, DUMP_REMOTE, MEDIA, OffsiteCase, assert_no_leak, assert_no_rclone_violation,
    objects, split_age, status,
)
from tests._ops_fakes import ROOT, run_tests, write_gz

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
        local = sorted(p.name + ".age" for p in c.bdir.glob("sq_*.sql.gz")) + [f"{MEDIA}.age"]
        assert sorted(p.name for p in objs) == sorted(local), objs  # backfill: todos os locais
        for p in objs:
            _assert_is_two_recipient_age_of(p, c.bdir / p.name[:-4])
        calls = c.age_calls()
        assert len(calls) == len(local), calls
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
        assert st["backfill"] == "1", st  # o dump de 26/09
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
        assert len(c.copytos()) == 3


def test_foreign_remote_object_is_never_overwritten():
    with OffsiteCase() as c:
        target = c.dump_bucket / f"{DUMP}.age"
        target.parent.mkdir(parents=True)
        target.write_bytes(b"objeto de outro host")
        r = c.push()
        assert r.returncode != 0 and "nunca é sobrescrito" in r.stderr, r.stderr
        assert target.read_bytes() == b"objeto de outro host"
        assert not [x for x in c.copytos() if DUMP in x], c.copytos()
        assert not (c.bdir / "offsite_last_success").exists()
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
    with OffsiteCase() as c:  # a credencial da string nunca vai para o journal
        for bad in (":b2,account=ID,key=SEGREDO:bucket", "sq-offsite:bucket:SEGREDO"):
            r = c.push({"OFFSITE_REMOTE": bad})
            assert r.returncode == 1 and "SEGREDO" not in r.stdout + r.stderr, r.stderr
            r = c.push_key({"OFFSITE_KEY_REMOTE": bad})
            assert r.returncode == 1 and "SEGREDO" not in r.stdout + r.stderr, r.stderr
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


def _code_lines(name: str) -> list[str]:
    """TODAS as linhas de código (não só as que citam RCLONE): um alias ou variável não esconde
    um delete. Nomes de funções DEFINIDAS no próprio script (ex.: cleanup) são descontados."""
    text = (ROOT / "scripts" / name).read_text()
    local_funcs = re.findall(r"^\s*([A-Za-z_][A-Za-z0-9_]*)\(\)\s*\{", text, re.M)
    lines = [ln for ln in text.splitlines() if not ln.lstrip().startswith("#")]
    for fn in local_funcs:
        lines = [re.sub(rf"\b{fn}\b", "", ln) for ln in lines]
    return lines


def test_no_remote_delete_ever():
    """Sem poda remota enquanto a DP-27 estiver aberta: nem os scripts chamam, nem o fake aceita."""
    with OffsiteCase() as c:
        runs = [c.push_key(), c.push(), c.push()]
        assert all(x.returncode == 0 for x in runs), [x.stderr for x in runs]
        assert_no_rclone_violation(c)
        # o fake de fato pega um delete (senão o assert acima seria vazio)
        p = subprocess.run(["rclone", "delete", DUMP_REMOTE], env=c.fk.env, capture_output=True)
        assert p.returncode == 99 and "VIOLATION delete" in c.rclone_log.read_text()
    for name in ("offsite_push.sh", "offsite_key_push.sh", "lib/offsite_common.sh",
                 "backup_run.sh", "restore_check.sh"):
        bad = [ln.strip() for ln in _code_lines(name) if _FORBIDDEN.search(ln)]
        assert not bad, f"{name}: {bad}"


def test_newest_first_then_backfill_oldest_first_and_skips_sent_ones():
    with OffsiteCase() as c:
        write_gz(c.bdir / "sq_20260925_030000.sql.gz", "dump sintetico 25\n")
        later = [c.bdir / "sq_20260926_030000.sql.gz", c.bdir / DUMP]
        parked = c.base / "parked"
        parked.mkdir()
        for p in later:
            p.rename(parked / p.name)
        assert c.push({"OFFSITE_MAX_AGE_HOURS": "0"}).returncode == 0  # só o de 25/09 vai
        for p in later:
            (parked / p.name).rename(p)
        n = len(c.copytos())
        r = c.push()
        assert r.returncode == 0, r.stderr
        sent = [x.split()[-1].rsplit("/", 1)[-1] for x in c.copytos()[n:]]
        dumps = [s for s in sent if s.startswith("sq_")]
        assert dumps == [f"{DUMP}.age", "sq_20260926_030000.sql.gz.age"], sent  # o de hoje primeiro
        assert not [s for s in sent if "20260925" in s], "o já enviado não volta"
        assert status(c.bdir / "offsite_last_success")["backfill"] == "1"


def test_pending_manifest_entry_is_retried_by_backfill():
    """Registro 'pendente' (upload que não aconteceu) não conta como enviado."""
    with OffsiteCase() as c:
        r = c.push({"FAKE_RCLONE_FAIL": "copyto"})
        assert r.returncode != 0
        assert "pendente" in (c.bdir / "offsite_manifest").read_text()
        r = c.push()
        assert r.returncode == 0, r.stderr
        assert len(objects(c.dump_bucket)) == 3


def test_status_is_not_renewed_over_a_stale_newest_dump():
    with OffsiteCase() as c:
        old = time.time() - 30 * 3600
        for p in c.bdir.glob("sq_*.sql.gz"):
            os.utime(p, (old, old))
        r = c.push()
        assert r.returncode != 0 and "NÃO foi renovado" in r.stderr, r.stderr
        assert not (c.bdir / "offsite_last_success").exists()
        assert (c.dump_bucket / f"{DUMP}.age").exists(), "o dump velho sai mesmo assim"
        r = c.push({"OFFSITE_MAX_AGE_HOURS": "48"})
        assert r.returncode == 0, r.stderr


def test_hash_download_mode_works_when_provider_has_no_hash():
    with OffsiteCase() as c:
        r = c.push({"FAKE_RCLONE_NO_HASH": "1", "OFFSITE_HASH_DOWNLOAD": "1"})
        assert r.returncode == 0, r.stderr
        hs = [x for x in c.rclone_calls() if x.startswith("hashsum ")]
        assert hs and all("--download" in x.split() for x in hs), hs


def test_mktemp_failure_inside_remote_hash_propagates():
    with OffsiteCase() as c:
        c.install_failing_mktemp()
        r = c.push({"FAKE_MKTEMP_FAIL": "1"})
        assert r.returncode != 0 and "mktemp falhou" in r.stderr, r.stderr
        assert not c.copytos(), "falha interna não pode virar envio"


def test_old_divergent_object_does_not_block_todays_dump():
    """Manifesto perdido + objeto antigo divergente no remote: o de hoje sai e é confirmado,
    o exit é != 0 e a falha antiga é nomeada."""
    with OffsiteCase() as c:
        old = c.dump_bucket / "sq_20260926_030000.sql.gz.age"
        old.parent.mkdir(parents=True)
        old.write_bytes(b"objeto antigo de outro envio")
        r = c.push()
        assert r.returncode != 0, r.stderr
        assert "sq_20260926_030000.sql.gz.age" in r.stderr.split("FALHA —")[-1], r.stderr
        today = c.dump_bucket / f"{DUMP}.age"
        assert today.exists() and split_age(today.read_bytes())[1] == (c.bdir / DUMP).read_bytes()
        manifest = (c.bdir / "offsite_manifest").read_text()
        assert f"{DUMP}.age\t" in manifest and manifest.split(f"{DUMP}.age\t")[1].split("\n")[0].endswith("\tok")
        assert (c.dump_bucket / f"{MEDIA}.age").exists(), "a mídia também sai"
        assert old.read_bytes() == b"objeto antigo de outro envio", "o antigo nunca é sobrescrito"
        assert "está confirmado" in r.stderr, r.stderr
        assert not (c.bdir / "offsite_last_success").exists()


def test_backfill_is_capped_per_run_and_resumes_next_run():
    with OffsiteCase() as c:
        for day in range(18, 26):  # 8 dumps antigos + o de 26/09 = 9 pendentes além do de hoje
            write_gz(c.bdir / f"sq_202609{day:02d}_030000.sql.gz", f"dump {day}\n")
        r = c.push()
        assert r.returncode == 0, r.stderr
        st = status(c.bdir / "offsite_last_success")
        assert st["backfill"] == "6" and st["backfill_pending"] == "3", st
        names = sorted(p.name for p in objects(c.dump_bucket) if p.name.startswith("sq_"))
        assert f"{DUMP}.age" in names and len(names) == 7, names
        assert names[0] == "sq_20260918_030000.sql.gz.age", "backfill do mais antigo para o mais novo"
        r = c.push()
        assert r.returncode == 0, r.stderr
        st = status(c.bdir / "offsite_last_success")
        assert st["backfill"] == "3" and st["backfill_pending"] == "0", st
        assert len([p for p in objects(c.dump_bucket) if p.name.startswith("sq_")]) == 10


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
                   "age1yubikey1", "age-plugin-yubikey", "decisão de instalação", "só para cifrar",
                   "backup_run.sh", "backfill", "OFFSITE_MAX_AGE_HOURS", "MANUAL e offline",
                   "contas diferentes de verdade", "wrapper", "backup_run_last",
                   "decifre com CADA identidade", "age-keygen -y sq-instancia.agekey",
                   "OFFSITE_BACKFILL_MAX", "não bloqueia o de hoje", "allowlist de armazenamento direto",
                   "RCLONE_CONFIG_<SEÇÃO>_*", "SQ_BACKUP_UNIT=1", "hash indisponível sem download"):
        assert needle in sec6, f"§6 não cita {needle}"
    drill = doc[doc.index("### Drill trimestral a partir do off-site"):]
    drill_code = drill[drill.index("```bash"):drill.index("```", drill.index("```bash") + 7)]
    assert drill_code.split("\n")[1].startswith("umask 077"), "o drill começa com umask 077"
    assert "chmod" not in drill_code, "nada de chmod depois: o umask já cuida"
    assert "Off-site (ordem 003, não existe)" not in doc
    assert "INVOCATION_ID" not in doc, "o marcador é SQ_BACKUP_UNIT, não INVOCATION_ID"


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
    test_newest_first_then_backfill_oldest_first_and_skips_sent_ones,
    test_old_divergent_object_does_not_block_todays_dump,
    test_backfill_is_capped_per_run_and_resumes_next_run,
    test_pending_manifest_entry_is_retried_by_backfill,
    test_status_is_not_renewed_over_a_stale_newest_dump,
    test_hash_download_mode_works_when_provider_has_no_hash,
    test_mktemp_failure_inside_remote_hash_propagates,
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
