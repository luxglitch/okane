#!/usr/bin/env bash
# Usage: ./scripts/logs.sh [service-name]
# If no service is given, tails all services.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

cd "$ROOT"

SERVICE="${1:-}"
docker compose logs -f --tail=100 $SERVICE
