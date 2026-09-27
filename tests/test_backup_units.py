"""
Tests: units systemd do backup (ops/systemd/), leitura estática (ordem 002).

Parser próprio, stdlib: unit systemd admite chave repetida (vários ExecStart=), o que o
configparser não representa. Confere os campos que fazem o agendamento funcionar e falhar
de forma visível, e que as units apontam para scripts que existem no repo.
"""
import re
import sys
from pathlib import Path

from tests._ops_fakes import ROOT, run_tests

UNITS = ROOT / "ops" / "systemd"
INSTALL_PREFIX = "/opt/smartquotation/"


def parse_unit(path: Path) -> dict:
    """{secao: [(chave, valor), ...]} + '_comments' com o texto dos comentários."""
    sections, current, comments = {}, None, []
    for raw in path.read_text().splitlines():
        line = raw.strip()
        if not line:
            continue
        if line.startswith(("#", ";")):
            comments.append(line)
            continue
        m = re.fullmatch(r"\[(.+)\]", line)
        if m:
            current = sections.setdefault(m.group(1), [])
            continue
        assert current is not None, f"{path.name}: diretiva fora de seção: {line!r}"
        key, sep, value = line.partition("=")
        assert sep, f"{path.name}: linha sem '=': {line!r}"
        current.append((key.strip(), value.strip()))
    sections["_comments"] = comments
    return sections


def get(unit: dict, section: str, key: str) -> list:
    return [v for k, v in unit.get(section, []) if k == key]


def one(unit: dict, section: str, key: str) -> str:
    vals = get(unit, section, key)
    assert len(vals) == 1, f"[{section}] {key} deve aparecer 1 vez, achei {vals}"
    return vals[0]


def _script_default(script: str, var: str) -> str:
    m = re.search(rf'^{var}="\$\{{{var}:-([^}}"]+)\}}"', (ROOT / "scripts" / script).read_text(), re.M)
    assert m, f"default de {var} não encontrado em {script}"
    return m.group(1)


def _assert_hardened_oneshot(unit: dict, name: str):
    s = "Service"
    assert one(unit, s, "Type") == "oneshot", name
    assert one(unit, s, "User") == "root", name
    assert any("grupo docker" in c for c in unit["_comments"]), (
        f"{name}: User=root precisa do comentário justificando (deploy fora do grupo docker)"
    )
    assert one(unit, s, "EnvironmentFile") == "/opt/smartquotation/.env.prod", name
    assert one(unit, s, "ProtectSystem") == "strict", name
    assert one(unit, s, "PrivateTmp") == "true", name
    assert one(unit, s, "NoNewPrivileges") == "true", name
    assert one(unit, s, "UMask") == "0077", name
    assert "docker.service" in one(unit, "Unit", "After"), name
    # Nada de Restart=: oneshot que falha tem que FICAR failed, visível.
    assert not get(unit, s, "Restart"), f"{name}: Restart= mascararia a falha"
    for cmd in get(unit, s, "ExecStart"):
        path = cmd.split()[0].lstrip("-+!@:")
        assert not cmd.split()[0].startswith("-"), f"{name}: '-' no ExecStart engoliria a falha"
        assert path.startswith(INSTALL_PREFIX), path
        repo = ROOT / path[len(INSTALL_PREFIX):]
        assert repo.exists(), f"{name}: {path} não existe no repo ({repo})"


def _assert_timer(unit: dict, name: str, service: str, calendar_re: str):
    t = "Timer"
    cal = one(unit, t, "OnCalendar")
    assert re.fullmatch(calendar_re, cal), f"{name}: OnCalendar={cal!r}"
    assert one(unit, t, "Persistent") == "true", name
    delay = one(unit, t, "RandomizedDelaySec")
    m = re.fullmatch(r"(\d+)(min|s)?", delay)
    assert m, f"{name}: RandomizedDelaySec={delay!r}"
    seconds = int(m.group(1)) * (60 if m.group(2) == "min" else 1)
    assert 0 < seconds <= 30 * 60, f"{name}: RandomizedDelaySec deve ser pequeno ({delay})"
    assert one(unit, t, "Unit") == service, name
    assert one(unit, "Install", "WantedBy") == "timers.target", name


def test_backup_service_runs_db_media_key_in_order_hardened():
    unit = parse_unit(UNITS / "sq-backup.service")
    _assert_hardened_oneshot(unit, "sq-backup.service")
    execs = [c.split()[0] for c in get(unit, "Service", "ExecStart")]
    assert execs == [
        "/opt/smartquotation/scripts/backup_db.sh",
        "/opt/smartquotation/scripts/backup_media.sh",
        "/opt/smartquotation/scripts/backup_key.sh",
    ], execs
    rw = one(unit, "Service", "ReadWritePaths").split()
    assert _script_default("backup_key.sh", "KEY_BACKUP_DIR") in rw, rw
    assert "/backups/sq" in rw, rw


def test_backup_timer_daily_at_3am_persistent():
    unit = parse_unit(UNITS / "sq-backup.timer")
    _assert_timer(unit, "sq-backup.timer", "sq-backup.service", r"\*-\*-\* 03:00(:00)?")


def test_restore_check_service_hardened_and_runs_restore_check():
    unit = parse_unit(UNITS / "sq-restore-check.service")
    _assert_hardened_oneshot(unit, "sq-restore-check.service")
    execs = [c.split()[0] for c in get(unit, "Service", "ExecStart")]
    assert execs == ["/opt/smartquotation/scripts/restore_check.sh"], execs
    assert "/backups/sq" in one(unit, "Service", "ReadWritePaths").split()


def test_restore_check_timer_weekly_persistent():
    unit = parse_unit(UNITS / "sq-restore-check.timer")
    _assert_timer(
        unit, "sq-restore-check.timer", "sq-restore-check.service",
        r"(Mon|Tue|Wed|Thu|Fri|Sat|Sun) \*-\*-\* \d\d:\d\d(:\d\d)?",
    )


def test_env_example_backup_dir_matches_unit_rw_paths():
    """O que a unit deixa escrever tem que ser o que o .env.prod.example manda usar."""
    env = (ROOT / ".env.prod.example").read_text()
    unit = parse_unit(UNITS / "sq-backup.service")
    rw = one(unit, "Service", "ReadWritePaths").split()
    for var in ("POSTGRES_BACKUP_DIR", "MEDIA_BACKUP_DIR", "KEY_BACKUP_DIR"):
        m = re.search(rf"^#?\s*{var}=(\S+)", env, re.M)
        assert m, f".env.prod.example precisa documentar {var}"
        assert m.group(1) in rw, f"{var}={m.group(1)} fora de ReadWritePaths {rw}"


TESTS = [
    test_backup_service_runs_db_media_key_in_order_hardened,
    test_backup_timer_daily_at_3am_persistent,
    test_restore_check_service_hardened_and_runs_restore_check,
    test_restore_check_timer_weekly_persistent,
    test_env_example_backup_dir_matches_unit_rw_paths,
]

if __name__ == "__main__":
    n = run_tests(TESTS)
    print()
    if n:
        print(f"FAILED: {n}/{len(TESTS)} tests failed")
        sys.exit(1)
    print(f"OK: all {len(TESTS)} tests passed")
