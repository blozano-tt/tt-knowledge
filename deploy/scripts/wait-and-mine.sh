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

# The index is rebuilt from an empty backend by deploy/rebuild-index.sh.
# No init step is needed for project-mode mining; the source is read-only.
exec mempalace mine /knowledge --wing tt-knowledge
