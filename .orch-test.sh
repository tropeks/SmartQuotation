#!/bin/bash
set -e

ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT/backend"

PYTHON_BIN="python"
if [ -x ".venv/bin/python" ]; then
  PYTHON_BIN=".venv/bin/python"
fi

export POSTGRES_HOST="${POSTGRES_HOST:-localhost}"
export POSTGRES_PORT="${POSTGRES_PORT:-5436}"
export POSTGRES_USER="${POSTGRES_USER:-sq}"
export POSTGRES_PASSWORD="${POSTGRES_PASSWORD:-sq}"
export POSTGRES_DB="${POSTGRES_DB:-smartquotation}"

echo "=== SmartQuotation UI/UX Sprint 05-07 Test ==="
echo ""

echo "[1/3] Django system check..."
"$PYTHON_BIN" manage.py check
echo "✓ check ok"
echo ""

echo "[2/3] makemigrations --check (nenhuma migration pendente)..."
"$PYTHON_BIN" manage.py makemigrations --check --dry-run
echo "✓ migrations ok"
echo ""

echo "[3/3] Tests dos apps tocados pelo sprint..."
"$PYTHON_BIN" manage.py test apps.quotations apps.proposals apps.production apps.audit apps.accounts -v 1
echo "✓ tests ok"
echo ""

echo "=== ALL TESTS PASSED ✓ ==="
