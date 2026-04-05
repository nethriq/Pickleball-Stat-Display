#!/usr/bin/env bash
# Non-intrusive Cloudflare R2 probe for Phase 3.
# Does not start/stop services or send kill signals.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$REPO_ROOT"

out="artifacts/phase3/$(date +%Y%m%d-%H%M%S)"
mkdir -p "$out"

echo "Artifact directory: $out"

env DEBUG=False timeout 60s python - <<'PY' | tee "$out/r2_probe_output.txt"
import os
import traceback
from datetime import datetime

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'nethriq.settings')
import django
django.setup()

from django.core.files.storage import default_storage
from django.core.files.base import ContentFile

name = f"r2_probe/test_upload_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.txt"
print('STORAGE_BACKEND=', default_storage.__class__.__module__ + '.' + default_storage.__class__.__name__)

try:
    path = default_storage.save(name, ContentFile(b'Cloudflare R2 probe'))
    print('UPLOAD_OK=', path)
except Exception as e:
    print('UPLOAD_FAIL=', type(e).__name__, str(e))
    traceback.print_exc()
    raise
PY

echo "Probe complete."
echo "Check your R2 bucket for the uploaded key under: r2_probe/"
