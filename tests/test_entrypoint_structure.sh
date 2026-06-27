#!/bin/bash
# Structural validation for entrypoint.sh and Dockerfile.
# Does NOT require Docker — checks file existence, permissions, and content.
set -e

FAIL=0
PASS=0

check() {
    local desc="$1"
    local result="$2"
    if [ "$result" = "ok" ]; then
        echo "PASS: $desc"
        PASS=$((PASS+1))
    else
        echo "FAIL: $desc — $result"
        FAIL=$((FAIL+1))
    fi
}

ENTRY="backend/entrypoint.sh"
DOCKERFILE="backend/Dockerfile"

# 1. entrypoint.sh exists
[ -f "$ENTRY" ] && check "entrypoint.sh exists" "ok" || check "entrypoint.sh exists" "file not found"

# 2. entrypoint.sh is executable
[ -x "$ENTRY" ] && check "entrypoint.sh is executable" "ok" || check "entrypoint.sh is executable" "not executable"

# 3. shebang #!/bin/bash
grep -q "^#!/bin/bash" "$ENTRY" && check "has #!/bin/bash shebang" "ok" || check "has #!/bin/bash shebang" "missing"

# 4. set -e
grep -q "^set -e" "$ENTRY" && check "has set -e" "ok" || check "has set -e" "missing"

# 5. migrate_schemas --shared
grep -q "migrate_schemas --shared" "$ENTRY" && check "migrate_schemas --shared present" "ok" || check "migrate_schemas --shared present" "missing"

# 6. migrate_schemas --tenant
grep -q "migrate_schemas --tenant" "$ENTRY" && check "migrate_schemas --tenant present" "ok" || check "migrate_schemas --tenant present" "missing"

# 7. collectstatic --noinput
grep -q "collectstatic --noinput" "$ENTRY" && check "collectstatic --noinput present" "ok" || check "collectstatic --noinput present" "missing"

# 8. entrypoint execs the image/compose command (so web=gunicorn, worker/beat=celery
#    all work after the shared migrate+collectstatic init — NOT a hardcoded gunicorn).
grep -q 'exec "$@"' "$ENTRY" && check 'entrypoint execs "$@"' "ok" || check 'entrypoint execs "$@"' "missing"

# 9-12. gunicorn config lives in the Dockerfile CMD (the default service command).
grep -q "\-\-bind.*0.0.0.0:8000\|0.0.0.0:8000" "$DOCKERFILE" && check "Dockerfile CMD gunicorn --bind 0.0.0.0:8000" "ok" || check "Dockerfile CMD gunicorn --bind 0.0.0.0:8000" "missing"
grep -q "\-\-workers=4" "$DOCKERFILE" && check "Dockerfile CMD gunicorn --workers=4" "ok" || check "Dockerfile CMD gunicorn --workers=4" "missing"
grep -q "\-\-timeout=60" "$DOCKERFILE" && check "Dockerfile CMD gunicorn --timeout=60" "ok" || check "Dockerfile CMD gunicorn --timeout=60" "missing"
grep -q "smartquotation.wsgi" "$DOCKERFILE" && check "Dockerfile CMD wsgi = smartquotation.wsgi" "ok" || check "Dockerfile CMD wsgi = smartquotation.wsgi" "missing"

# 13. bash syntax check
bash -n "$ENTRY" && check "bash -n syntax check passes" "ok" || check "bash -n syntax check passes" "syntax error"

# 14. Dockerfile exists
[ -f "$DOCKERFILE" ] && check "Dockerfile exists" "ok" || check "Dockerfile exists" "file not found"

# 15. Dockerfile stages entrypoint.sh into the image (explicit COPY or via COPY backend/).
grep -qE "COPY (backend/ \.|backend/entrypoint.sh|entrypoint.sh /app/)" "$DOCKERFILE" && check "Dockerfile copies entrypoint.sh into /app" "ok" || check "Dockerfile copies entrypoint.sh into /app" "missing"

# 16. Dockerfile chmod +x
grep -q "chmod +x /app/entrypoint.sh" "$DOCKERFILE" && check "Dockerfile chmod +x /app/entrypoint.sh" "ok" || check "Dockerfile chmod +x /app/entrypoint.sh" "missing"

# 17. Dockerfile ENTRYPOINT
grep -q 'ENTRYPOINT \["/app/entrypoint.sh"\]' "$DOCKERFILE" && check 'Dockerfile ENTRYPOINT ["/app/entrypoint.sh"]' "ok" || check 'Dockerfile ENTRYPOINT ["/app/entrypoint.sh"]' "missing"

echo ""
echo "Results: $PASS passed, $FAIL failed"
[ "$FAIL" -eq 0 ] && echo "ALL PASS" && exit 0 || { echo "SOME FAILED"; exit 1; }
