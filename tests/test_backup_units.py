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
    assert one(unit, s, "EnvironmentFile") == "/etc/smartquotation/backup.env", name
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


def test_backup_service_runs_the_runner_hardened():
    """Um ExecStart só, o backup_run.sh: ele roda db, media, key, key-offsite e offsite em
    ordem e segue depois de falha (ordem das etapas: tests/test_backup_run.py)."""
    unit = parse_unit(UNITS / "sq-backup.service")
    _assert_hardened_oneshot(unit, "sq-backup.service")
    execs = [c.split()[0] for c in get(unit, "Service", "ExecStart")]
    assert execs == ["/opt/smartquotation/scripts/backup_run.sh"], execs
    assert "network-online.target" in one(unit, "Unit", "After"), "o off-site precisa de rede"
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


BACKUP_ENV = UNITS / "backup.env.example"
BACKUP_ENV_TARGET = "/etc/smartquotation/backup.env"
# O que pode morar no env file das units: variáveis de backup e nomes de container.
ALLOWED_ENV = re.compile(r"^(BACKUP_[A-Z_]+|KEY_[A-Z_]+|RESTORE_[A-Z_]+|MEDIA_[A-Z_]+|DB_CONTAINER[A-Z_]*|DB_SERVICE|WEB_CONTAINER|WEB_SERVICE|COMPOSE_FILE|OFFSITE_[A-Z_]+|RCLONE_CONFIG|RCLONE_CACHE_DIR)$")


# Só do drill manual (o restore_check os recusa sob systemd): fora do backup.env.
DRILL_ONLY = ("RESTORE_DUMP_FILE", "RESTORE_MEDIA_FILE")


def _env_assignments(path: Path) -> dict:
    out = {}
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        key, sep, value = line.partition("=")
        assert sep, f"{path.name}: linha inválida {line!r}"
        out[key.strip()] = value.strip()
    return out


def test_units_use_dedicated_env_file_never_env_prod():
    """O .env.prod tem FIELD_ENCRYPTION_KEY, DJANGO_SECRET_KEY, POSTGRES_PASSWORD e AWS_*:
    carregá-lo poria tudo isso no ambiente de todo processo da unit."""
    for name in ("sq-backup.service", "sq-restore-check.service"):
        text = (UNITS / name).read_text()
        assert ".env.prod" not in text, f"{name} não pode referenciar .env.prod (nem em comentário)"
        unit = parse_unit(UNITS / name)
        assert get(unit, "Service", "EnvironmentFile") == [BACKUP_ENV_TARGET], name
        extra = [e for e in get(unit, "Service", "Environment") if not e.startswith("PATH=")]
        assert not extra, f"{name}: variáveis vão no backup.env (só PATH fica na unit): {extra}"


def test_backup_service_path_is_explicit_system_only_for_age_plugin():
    """age, rclone e age-plugin-yubikey (DP-41) são achados pelo PATH da unit: explícito,
    só diretórios do sistema, nada de home (ProtectHome=read-only)."""
    unit = parse_unit(UNITS / "sq-backup.service")
    env = get(unit, "Service", "Environment")
    assert len(env) == 1 and env[0].startswith("PATH="), env
    dirs = env[0][len("PATH="):].split(":")
    assert "/usr/local/bin" in dirs and "/usr/bin" in dirs, dirs
    assert not [d for d in dirs if d.startswith(("/root", "/home", "~")) or not d.startswith("/")], dirs
    assert one(unit, "Service", "ProtectHome") == "read-only"
    assert any("age-plugin-yubikey" in c for c in unit["_comments"]), "comentário do plugin na unit"


def test_backup_env_example_has_only_backup_vars_and_no_secrets():
    env = _env_assignments(BACKUP_ENV)
    assert env, "backup.env.example vazio"
    for key in env:
        assert ALLOWED_ENV.match(key), f"{key} não é variável de backup — fora do backup.env"
        assert key not in DRILL_ONLY, f"{key} é do drill manual: nunca no backup.env"
    for key in DRILL_ONLY:
        assert not re.search(rf"^\s*#?\s*{key}=", BACKUP_ENV.read_text(), re.M), f"{key} nem comentado no backup.env"
    text = BACKUP_ENV.read_text()
    for secret in ("FIELD_ENCRYPTION_KEY=", "DJANGO_SECRET_KEY=", "POSTGRES_PASSWORD=",
                   "AWS_SECRET_ACCESS_KEY=", "AWS_ACCESS_KEY_ID="):
        assert secret not in text, f"backup.env.example não pode ter {secret}"
    assert not re.search(r"AGE-(SECRET-KEY|PLUGIN-YUBIKEY)-1[0-9A-Z]{20,}", text), (
        "chave privada/identidade age no backup.env.example")
    # modo container: vale o POSTGRES_USER do próprio sq-prod-db
    assert "POSTGRES_USER" not in env and "POSTGRES_DB" not in env, env
    assert not re.search(r"^\s*DOCKER=.*sudo", text, re.M), "sudo não passa pelo NoNewPrivileges"


def test_backup_env_dirs_match_unit_rw_paths():
    """O que a unit deixa escrever tem que ser o que o backup.env.example manda usar."""
    env = _env_assignments(BACKUP_ENV)
    rw = one(parse_unit(UNITS / "sq-backup.service"), "Service", "ReadWritePaths").split()
    for var in ("BACKUP_DIR", "KEY_BACKUP_DIR", "RCLONE_CACHE_DIR"):
        assert var in env, f"backup.env.example precisa definir {var}"
        assert env[var] in rw, f"{var}={env[var]} fora de ReadWritePaths {rw}"
    rw_restore = one(parse_unit(UNITS / "sq-restore-check.service"), "Service", "ReadWritePaths").split()
    assert env["BACKUP_DIR"] in rw_restore, rw_restore
    assert env["RCLONE_CACHE_DIR"] in rw_restore, "o drill semanal confere o off-site com rclone"
    assert env["KEY_BACKUP_DIR"] != env["BACKUP_DIR"], "chave e dump no mesmo diretório"


def test_backup_env_offsite_example_is_fictitious_public_and_separated():
    """Chaves de exemplo: formato de chave PÚBLICA, obviamente fictícias (um caractere
    repetido) e recusadas pelo script; a chave vai para outra seção do rclone.conf."""
    import subprocess
    env = _env_assignments(BACKUP_ENV)
    for var in ("OFFSITE_AGE_RECIPIENT_INSTANCE", "OFFSITE_AGE_RECIPIENT_RECOVERY"):
        v = env[var]
        assert re.fullmatch(r"age1[a-z0-9]{58}", v) and len(set(v[4:])) == 1, f"{var}={v}"
        r = subprocess.run(
            ["bash", "-c", f'SQ_SCRIPT=t; . scripts/lib/offsite_common.sh; sq_offsite_check_recipient {var}'],
            cwd=ROOT, env={"PATH": "/usr/bin:/bin", var: v}, capture_output=True, text=True)
        assert r.returncode == 1 and "FICTÍCIO" in r.stderr, (var, r.stderr)
    assert env["OFFSITE_AGE_RECIPIENT_INSTANCE"] != env["OFFSITE_AGE_RECIPIENT_RECOVERY"]
    dump, key = env["OFFSITE_REMOTE"], env["OFFSITE_KEY_REMOTE"]
    assert dump.split(":")[0] != key.split(":")[0], "chave e dump na mesma seção do rclone.conf"
    assert env["RCLONE_CONFIG"].startswith("/etc/smartquotation/"), env["RCLONE_CONFIG"]



def _section(text: str, start: str, end: str) -> str:
    a = text.index(start)
    return text[a:text.index(end, a + len(start))]


def test_infra_doc_env_prod_is_key_material_in_custody_not_in_dump_package():
    """Condição C: o .env.prod contém a FIELD_ENCRYPTION_KEY, então segue a custódia separada
    e nunca vai no pacote do dump da 003 — escrito na §6 E na seção de off-site."""
    doc = (ROOT / "docs" / "INFRASTRUCTURE.md").read_text()
    sec6 = _section(doc, "## 6. Backup e Recuperação", "## 7.")
    offsite = _section(sec6, "### Off-site", "\n### ")
    head = sec6[: sec6.index("### Off-site")]
    for name, part in (("§6", head), ("off-site", offsite)):
        flat = " ".join(part.split())
        assert "/opt/smartquotation/.env.prod" in flat, f"{name}: citar o .env.prod"
        assert "material de chave" in flat, f"{name}: dizer que o .env.prod é material de chave"
        assert "custódia separada" in flat, f"{name}: mesma custódia separada da chave"
        assert re.search(r"nunca\W+(vai|entra) no pacote do dump", flat, re.I), (
            f"{name}: dizer que nunca vai no pacote do dump da 003"
        )
    assert "NUNCA viaja junto com o dump no off-site (ordem 003)" in " ".join(sec6.split())

TESTS = [
    test_backup_service_runs_the_runner_hardened,
    test_backup_timer_daily_at_3am_persistent,
    test_restore_check_service_hardened_and_runs_restore_check,
    test_restore_check_timer_weekly_persistent,
    test_units_use_dedicated_env_file_never_env_prod,
    test_backup_service_path_is_explicit_system_only_for_age_plugin,
    test_backup_env_example_has_only_backup_vars_and_no_secrets,
    test_backup_env_dirs_match_unit_rw_paths,
    test_backup_env_offsite_example_is_fictitious_public_and_separated,
    test_infra_doc_env_prod_is_key_material_in_custody_not_in_dump_package,
]

if __name__ == "__main__":
    n = run_tests(TESTS)
    print()
    if n:
        print(f"FAILED: {n}/{len(TESTS)} tests failed")
        sys.exit(1)
    print(f"OK: all {len(TESTS)} tests passed")
