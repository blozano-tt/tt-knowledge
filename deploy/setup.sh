#!/usr/bin/env bash
# Generate host-local credentials. Never put passwords on a command line.
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")"
python3 - "${1:?Usage: deploy/setup.sh HOSTNAME}" <<'PY'
import os
from pathlib import Path
import re
import secrets
import subprocess
import sys

host = sys.argv[1]
if not re.fullmatch(r'[A-Za-z0-9](?:[A-Za-z0-9.-]*[A-Za-z0-9])?', host):
    raise SystemExit('Expected a DNS hostname without a scheme or path')
if Path('.env').exists() or Path('admin-password.txt').exists():
    raise SystemExit('Refusing to replace existing deployment credentials')
os.umask(0o077)
password = secrets.token_urlsafe(32)
image = os.environ.get('CADDY_IMAGE', 'caddy:2-alpine')
hashed = subprocess.check_output(
    ['docker', 'run', '--rm', '-i', image, 'caddy', 'hash-password', '--algorithm', 'bcrypt'],
    input=password + '\n', text=True).strip()
if not hashed.startswith('$2') or '\n' in hashed:
    raise SystemExit('Unexpected password hash output')
with Path('admin-password.txt').open('x') as file:
    file.write(password + '\n')
with Path('.env').open('x') as file:
    file.write(f"DOMAIN={host}\nPOSTGRES_PASSWORD={secrets.token_hex(32)}\nUI_PASSWORD_HASH='{hashed}'\n")
print('Created deploy/.env and deploy/admin-password.txt (mode 0600). Dashboard user: admin.')
PY
