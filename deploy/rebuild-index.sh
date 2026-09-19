#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

ENV_FILE="$REPO_ROOT/deploy/.env"
COMPOSE_FILE="$REPO_ROOT/deploy/compose.yaml"

if [[ ! -f "$ENV_FILE" ]]; then
    echo "Missing deploy/.env" >&2
    echo "Run: cp deploy/.env.example deploy/.env" >&2
    echo "Then set DOMAIN and MEMPALACE_MCP_HTTP_TOKEN." >&2
    exit 1
fi

set -a
# shellcheck disable=SC1090
source "$ENV_FILE"
set +a

if [[ -z "${DOMAIN:-}" || "$DOMAIN" == "knowledge.example.com" ]]; then
    echo "Set a real DOMAIN in deploy/.env before deploying." >&2
    exit 1
fi

if [[ -z "${MEMPALACE_MCP_HTTP_TOKEN:-}" || "$MEMPALACE_MCP_HTTP_TOKEN" == replace-* ]]; then
    echo "Set MEMPALACE_MCP_HTTP_TOKEN in deploy/.env." >&2
    echo "Generate one with: openssl rand -hex 32" >&2
    exit 1
fi

if git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
    export GIT_SHA
    GIT_SHA="$(git rev-parse HEAD)"
else
    echo "Deployment requires a Git checkout with pinned submodules." >&2
    exit 1
fi

printf '\n==> Initializing pinned upstream repositories recursively\n'
git submodule sync --recursive
git submodule update --init --recursive
python3 scripts/prepare_knowledge.py

COMPOSE=(docker compose -f "$COMPOSE_FILE" --env-file "$ENV_FILE")

printf '\n==> Building tt-knowledge MemPalace image (%s)\n' "$GIT_SHA"
"${COMPOSE[@]}" build --pull mempalace

printf '\n==> Stopping query service while the truth index is rebuilt\n'
"${COMPOSE[@]}" stop mempalace >/dev/null 2>&1 || true
"${COMPOSE[@]}" rm -f mempalace >/dev/null 2>&1 || true
"${COMPOSE[@]}" stop qdrant >/dev/null 2>&1 || true
"${COMPOSE[@]}" rm -f qdrant >/dev/null 2>&1 || true

printf '\n==> Removing old searchable state (embedding cache and TLS certs are preserved)\n'
for volume in tt-knowledge-qdrant-data tt-knowledge-mempalace-state; do
    if docker volume inspect "$volume" >/dev/null 2>&1; then
        docker volume rm "$volume"
    fi
done

printf '\n==> Initializing writable state and model-cache volumes\n'
"${COMPOSE[@]}" run --rm --no-deps volume-init

printf '\n==> Starting fresh Qdrant\n'
"${COMPOSE[@]}" up -d qdrant

printf '\n==> Mining current Git corpus from scratch\n'
"${COMPOSE[@]}" run --rm indexer

printf '\n==> Starting read-only MemPalace MCP + HTTPS proxy\n'
"${COMPOSE[@]}" up -d mempalace caddy

printf '\nDeployment complete.\n'
printf 'Health: https://%s/healthz\n' "$DOMAIN"
printf 'MCP:    https://%s/mcp\n' "$DOMAIN"
