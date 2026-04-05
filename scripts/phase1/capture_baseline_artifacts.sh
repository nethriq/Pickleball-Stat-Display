#!/usr/bin/env bash
set -euo pipefail

# Purpose:
# Capture reproducible Phase 1 baseline artifacts for localhost parity verification.
# This script does not execute the full job flow; it records environment/runtime evidence
# and creates a structured folder for manual run artifacts.

# Note: callers should run `pyenv activate project-venv` before invoking this script.
# In non-interactive shells, `pyenv activate` may not be available even when pyenv is installed.
if [[ -z "${VIRTUAL_ENV:-}" ]]; then
  echo "WARNING: no active virtualenv detected."
  echo "Run 'pyenv activate project-venv' before this script for best results."
fi

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$REPO_ROOT"

STAMP="$(date +%Y%m%d-%H%M%S)"
OUT_DIR="artifacts/phase1/$STAMP"
mkdir -p "$OUT_DIR"

echo "[phase1] writing artifacts to $OUT_DIR"

{
  echo "timestamp=$STAMP"
  echo "cwd=$PWD"
  echo "python=$(python --version 2>&1)"
  echo "node=$(node --version 2>&1 || true)"
  echo "npm=$(npm --version 2>&1 || true)"
  echo "ffmpeg=$(ffmpeg -version 2>/dev/null | head -n 1 || echo 'not-found')"
} > "$OUT_DIR/runtime_versions.txt"

python manage.py check > "$OUT_DIR/django_check.txt" 2>&1 || true

curl -sS http://localhost:8000/api/health/ > "$OUT_DIR/health.json" 2>/dev/null || \
  echo '{"status":"unavailable","reason":"django_not_running_or_not_reachable"}' > "$OUT_DIR/health.json"

{
  echo "# manual captures to add after running one full test job"
  echo "# - django.log"
  echo "# - node.log"
  echo "# - celery.log"
  echo "# - job_status_timeline.txt"
  echo "# - deliverables_tree.txt"
} > "$OUT_DIR/README.txt"

# Save an env key inventory snapshot without exposing secret values.
{
  echo "PBVISION_API_KEY="
  echo "NODE_WEBHOOK_URL="
  echo "NODE_ENDPOINT="
  echo "DJANGO_BASE_URL="
  echo "AWS_ACCESS_KEY_ID="
  echo "AWS_SECRET_ACCESS_KEY="
  echo "AWS_STORAGE_BUCKET_NAME="
  echo "AWS_S3_REGION_NAME="
  echo "CELERY_BROKER_URL="
  echo "CELERY_RESULT_BACKEND="
  echo "FILE_UPLOAD_MAX_MEMORY_SIZE="
  echo "DATA_UPLOAD_MAX_MEMORY_SIZE="
  echo "FILE_UPLOAD_TEMP_DIR="
  echo "EMAIL_DELIVERY_ENABLED="
  echo "EMAIL_DELIVERY_MAX_ATTACHMENT_BYTES="
  echo "EMAIL_BACKEND="
  echo "EMAIL_HOST="
  echo "EMAIL_PORT="
  echo "EMAIL_HOST_USER="
  echo "EMAIL_HOST_PASSWORD="
  echo "EMAIL_USE_TLS="
  echo "EMAIL_USE_SSL="
  echo "EMAIL_TIMEOUT="
  echo "DEFAULT_FROM_EMAIL="
  echo "CLUB_NAME="
  echo "CLAIM_LINK_TTL_HOURS="
  echo "CLAIM_URL_BASE="
  echo "PRESERVE_SOURCE_VIDEO="
  echo "CLEANUP_ON_DELIVERY="
} > "$OUT_DIR/env_template_snapshot.txt"

echo "[phase1] baseline artifact scaffold created"
