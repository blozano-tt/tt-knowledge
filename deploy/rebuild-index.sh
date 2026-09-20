#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."
[[ -f deploy/.env ]] || { echo 'Run deploy/setup.sh HOSTNAME first.' >&2; exit 1; }
git submodule sync --recursive
git submodule update --init --recursive
python3 scripts/prepare_knowledge.py
COMPOSE=(docker compose -f deploy/compose.yaml --env-file deploy/.env)
"${COMPOSE[@]}" pull postgres hindsight ingest gateway caddy
"${COMPOSE[@]}" up -d --wait --wait-timeout 600 postgres hindsight
# Pause public reads while the Git-owned bank is replaced. A failed ingest
# deliberately leaves MCP offline; the protected dashboard remains available.
"${COMPOSE[@]}" stop gateway
"${COMPOSE[@]}" run --rm ingest
"${COMPOSE[@]}" up -d --force-recreate --no-deps --wait gateway
"${COMPOSE[@]}" up -d --force-recreate --no-deps caddy
echo 'Hindsight bank rebuilt and public MCP started. Run deploy/test-mcp.py to verify.'
