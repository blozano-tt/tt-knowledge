#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="$REPO_ROOT/deploy/.env"
COMPOSE_FILE="$REPO_ROOT/deploy/compose.yaml"

if [[ ! -f "$ENV_FILE" ]]; then
    echo "Missing deploy/.env" >&2
    exit 1
fi

set -a
# shellcheck disable=SC1090
source "$ENV_FILE"
set +a

docker compose -f "$COMPOSE_FILE" --env-file "$ENV_FILE" ps
printf '\nPublic health endpoint:\n'
curl --fail --silent --show-error "https://${DOMAIN}/healthz"
printf '\n'
