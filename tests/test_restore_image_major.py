"""
Tests: scripts/restore_check.sh — a imagem do drill segue a major de ORIGEM do dump (ordem 009).

A produção não tem a major registrada no repo (docs/ship/ORDEM_009_POSTGRES.md). O drill lê
"-- Dumped from database version X.Y" do próprio dump: sem RESTORE_IMAGE sobe postgres:<X>;
RESTORE_IMAGE de major menor que X, ou sem major legível na tag, reprova antes de subir
container. Mesmo docker falso e mesmo Case de tests/test_restore_check.py.
"""
import sys

from tests._ops_fakes import run_tests, synthetic_dump, write_gz
from tests.test_restore_check import Case


def _status(c):
    return dict(ln.split("=", 1) for ln in (c.bdir / "restore_last_success").read_text().splitlines())


def test_restore_image_default_derives_major_from_dump_source_version():
    """Sem RESTORE_IMAGE, a imagem efêmera é postgres:<major> — a major de ORIGEM do dump
    (linha "-- Dumped from database version"), nunca -alpine (produção é a família debian)."""
    with Case() as c:
        write_gz(c.bdir / "sq_20260928_030000.sql.gz", synthetic_dump(pg_version="16.4"))
        r = c.run()
        assert r.returncode == 0, r.stderr
        run, _ = c.container_name()
        assert "postgres:16" in run and "postgres:16-alpine" not in run, run
        status = _status(c)
        assert status["source_major"] == "16" and status["image"] == "postgres:16", status
    with Case() as c:  # dump 15 (default do fixture) -> postgres:15
        r = c.run()
        assert r.returncode == 0, r.stderr
        run, _ = c.container_name()
        assert "postgres:15" in run and "postgres:15-alpine" not in run, run


def test_restore_image_explicit_older_major_than_dump_source_is_refused():
    with Case() as c:
        write_gz(c.bdir / "sq_20260928_030000.sql.gz", synthetic_dump(pg_version="16.4"))
        r = c.run({"RESTORE_IMAGE": "postgres:15"})
        assert r.returncode != 0, r.stdout + r.stderr
        assert "mais velha que a major de origem" in r.stderr, r.stderr
        assert not [x for x in c.fk.docker_calls() if x.startswith("run ")], "reprova antes de subir container"
        assert "linha sintética" not in r.stdout + r.stderr, "conteúdo do dump não pode vazar na mensagem"


def test_restore_image_explicit_newer_or_equal_major_alpine_tag_is_accepted():
    with Case() as c:  # dump 15 (default), imagem 16-alpine: maior é aceito, mesmo -alpine
        r = c.run({"RESTORE_IMAGE": "postgres:16-alpine"})
        assert r.returncode == 0, r.stderr
        run, _ = c.container_name()
        assert "postgres:16-alpine" in run, run
        status = _status(c)
        assert status["source_major"] == "15" and status["image"] == "postgres:16-alpine", status


def test_restore_image_major_parsed_from_tag_despite_registry_port_suffix_or_digest():
    for image in ("registry:5000/postgres:16", "postgres:16.4-bookworm",
                  "postgres:16@sha256:" + "1" * 64):
        with Case() as c:  # dump 15: todas têm major 16 na tag, logo são aceitas
            r = c.run({"RESTORE_IMAGE": image})
            assert r.returncode == 0, (image, r.stderr)
            assert _status(c)["image"] == image, image


def test_restore_image_tag_without_readable_major_is_refused():
    with Case() as c:
        # registry:5000/postgres: a porta do registry não é tag. postgres@sha256:<hex que
        # começa com dígito>: o digest não é major (sem esta regra, "sha256:1111…" passaria
        # como major 1111 e aceitaria qualquer dump).
        for image in ("postgres:latest", "postgres", "registry.example.com/postgres:stable",
                      "registry:5000/postgres", "postgres@sha256:" + "1" * 64):
            r = c.run({"RESTORE_IMAGE": image})
            assert r.returncode != 0, (image, r.stdout + r.stderr)
            assert "major legível" in r.stderr, (image, r.stderr)
        assert not [x for x in c.fk.docker_calls() if x.startswith("run ")]


def test_restore_dump_without_version_header_is_refused():
    with Case() as c:
        write_gz(c.bdir / "sq_20260928_030000.sql.gz", synthetic_dump(pg_version=None))
        r = c.run()
        assert r.returncode != 0 and "cabeçalho de versão ausente" in r.stderr, r.stderr
        assert not [x for x in c.fk.docker_calls() if x.startswith("run ")]


TESTS = [
    test_restore_image_default_derives_major_from_dump_source_version,
    test_restore_image_explicit_older_major_than_dump_source_is_refused,
    test_restore_image_explicit_newer_or_equal_major_alpine_tag_is_accepted,
    test_restore_image_major_parsed_from_tag_despite_registry_port_suffix_or_digest,
    test_restore_image_tag_without_readable_major_is_refused,
    test_restore_dump_without_version_header_is_refused,
]

if __name__ == "__main__":
    n = run_tests(TESTS)
    print()
    if n:
        print(f"FAILED: {n}/{len(TESTS)} tests failed")
        sys.exit(1)
    print(f"OK: all {len(TESTS)} tests passed")
