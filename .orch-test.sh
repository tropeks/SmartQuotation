#!/usr/bin/env bash
# Orchestrator test command for SmartQuotation.
#
# This is the project-agnostic `.orch-test.sh` convention consumed by the
# orchestrator (ClaudeProxy → orch_testcmd.detect): a committed, reviewable script
# that declares this project's EXACT test command, so the platform never needs any
# SmartQuotation-specific knowledge. The independent VERIFY re-runner falls back to
# this when the worker omits its TEST_CMD: marker.
#
# Run contract: the orchestrator runs it from the task's git WORKTREE (cwd = worktree
# root). Because backend/.venv is gitignored it is absent in worktrees, so we fall
# back to the canonical repo's interpreter. The CODE under test is the worktree's;
# only the interpreter (Django deps) comes from the canonical venv.
#
# DB isolation (A3): honor ORCH_DB_NAME when the orchestrator injects it so concurrent
# re-runs don't collide on the same Django test database; default to the dev DB.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PY="$ROOT/backend/.venv/bin/python"
[ -x "$PY" ] || PY="/home/rcosta00/dev/SmartQuotation/backend/.venv/bin/python"

cd "$ROOT/backend"
exec env \
  POSTGRES_PORT="${POSTGRES_PORT:-5436}" \
  POSTGRES_HOST="${POSTGRES_HOST:-localhost}" \
  POSTGRES_USER="${POSTGRES_USER:-sq}" \
  POSTGRES_PASSWORD="${POSTGRES_PASSWORD:-sq}" \
  POSTGRES_DB="${ORCH_DB_NAME:-${POSTGRES_DB:-smartquotation}}" \
  DJANGO_SETTINGS_MODULE="${DJANGO_SETTINGS_MODULE:-smartquotation.settings.development}" \
  "$PY" manage.py test "$@"
