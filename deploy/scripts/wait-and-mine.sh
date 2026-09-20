#!/bin/sh
set -eu

python - <<'PY'
import os
import time
import urllib.request

base = os.environ.get("MEMPALACE_QDRANT_URL", "http://qdrant:6333").rstrip("/")
url = base + "/healthz"
deadline = time.monotonic() + 90
last_error = None

while time.monotonic() < deadline:
    try:
        with urllib.request.urlopen(url, timeout=2) as response:
            if response.status == 200:
                print("Qdrant is ready.", flush=True)
                break
    except Exception as exc:  # startup race; retry until deadline
        last_error = exc
    time.sleep(1)
else:
    raise SystemExit(f"Qdrant did not become ready within 90s: {last_error}")
PY

# The index is rebuilt from the prepared source/chunk manifest.
exec python /opt/tt-knowledge/index-knowledge.py
