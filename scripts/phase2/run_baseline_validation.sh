#!/usr/bin/env bash
# Phase 2 NON-INTRUSIVE validation (safe for desktop sessions).
#
# This script does NOT:
# - start any services
# - stop any services
# - spawn background daemons
# - send kill signals
#
# It only validates that environment-driven hardening is in place.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$REPO_ROOT"

STRICT_MODE=false
if [[ "${1:-}" == "--strict" ]]; then
  STRICT_MODE=true
elif [[ -n "${1:-}" ]]; then
  echo "Usage: $0 [--strict]" >&2
  exit 2
fi

out="artifacts/phase2/$(date +%Y%m%d-%H%M%S)"
mkdir -p "$out"
echo "Artifact directory: $out"

echo "=== Phase 2 Non-Intrusive Checks ==="
if [[ "$STRICT_MODE" == true ]]; then
  echo "Mode: strict"
else
  echo "Mode: standard"
fi

if [[ "$STRICT_MODE" == true ]]; then
  echo "=== Strict env presence checks ==="
  required_vars=(
    SECRET_KEY
    DEBUG
    ALLOWED_HOSTS
    DJANGO_BASE_URL
  )

  missing=()
  for var in "${required_vars[@]}"; do
    if [[ -z "${!var:-}" ]]; then
      missing+=("$var")
    fi
  done

  if [[ ${#missing[@]} -gt 0 ]]; then
    {
      echo "result=FAIL"
      echo "reason=missing_required_env"
      echo "missing=${missing[*]}"
    } > "$out/strict_env_check.txt"
    echo "FAIL: Missing required env vars: ${missing[*]}" >&2
    exit 1
  fi

  {
    echo "result=PASS"
    echo "required_vars=${required_vars[*]}"
  } > "$out/strict_env_check.txt"
  echo "✓ Strict env presence checks"

  echo "=== Phase 3 readiness checks ==="
  python - <<'PY' > "$out/phase3_runtime_check.txt"
import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'nethriq.settings')
django.setup()

from django.conf import settings

print(f"DEBUG={settings.DEBUG}")
print(f"DATABASE_ENGINE={settings.DATABASES['default']['ENGINE']}")
print(f"DATABASE_URL_HAS_SSLMODE={('sslmode=require' in (os.getenv('DATABASE_URL') or ''))}")

required_r2 = [
    'AWS_ACCESS_KEY_ID',
    'AWS_SECRET_ACCESS_KEY',
    'AWS_STORAGE_BUCKET_NAME',
    'AWS_S3_ENDPOINT_URL',
]
missing = [k for k in required_r2 if not os.getenv(k)]
print(f"R2_MISSING={','.join(missing)}")
PY

db_engine="$(grep '^DATABASE_ENGINE=' "$out/phase3_runtime_check.txt" | cut -d= -f2-)"
sslmode_ok="$(grep '^DATABASE_URL_HAS_SSLMODE=' "$out/phase3_runtime_check.txt" | cut -d= -f2-)"
effective_debug="$(grep '^DEBUG=' "$out/phase3_runtime_check.txt" | cut -d= -f2-)"
r2_missing="$(grep '^R2_MISSING=' "$out/phase3_runtime_check.txt" | cut -d= -f2-)"

if [[ "$db_engine" != "django.db.backends.postgresql" ]]; then
    echo "FAIL: Effective DATABASE_ENGINE is '$db_engine', expected PostgreSQL for Phase 3." >&2
    exit 1
fi
if [[ "$sslmode_ok" != "True" ]]; then
    echo "FAIL: DATABASE_URL should include sslmode=require for Neon." >&2
    exit 1
fi
echo "✓ Effective DB config is PostgreSQL + sslmode=require"

  # R2 keys are required only when DEBUG is false.
  if [[ "$effective_debug" == "False" ]]; then
    r2_required=(
      AWS_ACCESS_KEY_ID
      AWS_SECRET_ACCESS_KEY
      AWS_STORAGE_BUCKET_NAME
      AWS_S3_ENDPOINT_URL
    )
    if [[ -n "$r2_missing" ]]; then
      echo "FAIL: DEBUG=False requires R2 env vars: $r2_missing" >&2
      exit 1
    fi
    echo "✓ R2 env vars present for DEBUG=False"
  else
    echo "INFO: DEBUG is true; R2 vars not required for local runtime." | tee -a "$out/phase3_readiness_warn.txt"
  fi
fi

# 1) Verify Django settings can load and system checks pass.
python manage.py check > "$out/django_system_check.txt" 2>&1
echo "✓ Django system check"

# 2) Verify runtime settings resolved from env.
python - <<'PY' > "$out/django_env_resolve.txt"
import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'nethriq.settings')
django.setup()

from django.conf import settings

print(f"DEBUG={settings.DEBUG}")
print(f"SECRET_KEY_length={len(settings.SECRET_KEY)}")
print(f"ALLOWED_HOSTS={','.join(settings.ALLOWED_HOSTS)}")
print(f"DATABASE_ENGINE={settings.DATABASES['default']['ENGINE']}")
print(f"DATABASE_NAME={settings.DATABASES['default']['NAME']}")
PY
echo "✓ Django env resolution"

# 3) Verify Node resolves DJANGO_BASE_URL from dotenv.
(cd node && node -e "require('dotenv').config({path:'../.env'}); console.log('DJANGO_BASE_URL=' + (process.env.DJANGO_BASE_URL || 'NOT_SET'))") \
  > "$out/node_env_resolve.txt"

if grep -q 'NOT_SET' "$out/node_env_resolve.txt"; then
  echo "FAIL: DJANGO_BASE_URL is not set in .env" >&2
  exit 1
fi
echo "✓ Node env resolution"

# 4) Optional connectivity checks (read-only).
curl -sf http://localhost:8000/api/health/ > "$out/django_health.json" && echo "✓ Django health endpoint"
curl -s -o /dev/null -w '%{http_code}\n' http://localhost:3000/ > "$out/node_http_status.txt" && echo "✓ Node reachable"

{
  echo "result=PASS"
  echo "mode=non-intrusive"
  echo "strict_mode=$STRICT_MODE"
  echo "timestamp=$(date -Iseconds)"
} > "$out/phase2_summary.txt"

echo ""
echo "Phase 2 non-intrusive validation passed"
echo "Artifacts: $out"

