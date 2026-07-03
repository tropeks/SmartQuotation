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

echo "=== SmartQuotation UI/UX Sprint Test ==="
echo ""

echo "[1/2] Running Django system check..."
"$PYTHON_BIN" manage.py check
echo "✓ Django check passed"
echo ""

echo "[2/2] Running quotations app tests..."
"$PYTHON_BIN" manage.py test apps.quotations -v 1
echo "✓ Quotation tests passed"
echo ""

echo "=== ALL TESTS PASSED ✓ ==="
