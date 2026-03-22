#!/usr/bin/env bash
set -euo pipefail

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

info() { echo -e "${BLUE}[okane]${NC} $*"; }
success() { echo -e "${GREEN}[okane]${NC} $*"; }
warn() { echo -e "${YELLOW}[okane]${NC} $*"; }
error() { echo -e "${RED}[okane]${NC} $*" >&2; }

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

cd "$ROOT"

# ─── 1. Check prerequisites ─────────────────────────────────────────────────

info "Checking prerequisites..."

if ! command -v docker &>/dev/null; then
    error "Docker is not installed. Install from https://docs.docker.com/get-docker/"
    exit 1
fi

if ! docker compose version &>/dev/null 2>&1; then
    error "Docker Compose v2 is not installed."
    exit 1
fi

success "Prerequisites OK"

# ─── 2. Setup .env ──────────────────────────────────────────────────────────

if [ ! -f "$ROOT/.env" ]; then
    warn ".env not found — copying from .env.example"
    cp "$ROOT/.env.example" "$ROOT/.env"
    echo ""
    warn "ACTION REQUIRED: Fill in your secrets in $ROOT/.env before continuing."
    warn "  Required:"
    warn "    KALSHI_API_KEY_ID"
    warn "    KALSHI_PRIVATE_KEY_B64"
    warn "    ANTHROPIC_API_KEY"
    warn "    POSTGRES_PASSWORD"
    warn "    GRAFANA_ADMIN_PASSWORD"
    echo ""
    read -p "Press Enter when .env is filled in (Ctrl+C to cancel)..."
fi

# Check required vars
source "$ROOT/.env" 2>/dev/null || true
MISSING=()
for var in POSTGRES_PASSWORD; do
    if [ -z "${!var:-}" ]; then
        MISSING+=("$var")
    fi
done
if [ ${#MISSING[@]} -gt 0 ]; then
    error "Missing required environment variables in .env: ${MISSING[*]}"
    exit 1
fi

# ─── 3. Build images ────────────────────────────────────────────────────────

info "Building Docker images (this may take a few minutes)..."
docker compose build --parallel
success "Images built"

# ─── 4. Start infrastructure ────────────────────────────────────────────────

info "Starting infrastructure services (postgres, redis, chromadb)..."
docker compose up -d postgres redis chromadb

# Wait for postgres
info "Waiting for PostgreSQL to be ready..."
TIMEOUT=60
ELAPSED=0
until docker compose exec -T postgres pg_isready -U "${POSTGRES_USER:-okane}" -d "${POSTGRES_DB:-okane}" &>/dev/null; do
    if [ $ELAPSED -ge $TIMEOUT ]; then
        error "PostgreSQL did not start within ${TIMEOUT}s"
        docker compose logs postgres | tail -20
        exit 1
    fi
    sleep 2
    ELAPSED=$((ELAPSED + 2))
done
success "PostgreSQL is ready"

# ─── 5. Start remaining services ────────────────────────────────────────────

info "Starting all services..."
docker compose up -d
success "All services started"

# ─── 6. Final status ────────────────────────────────────────────────────────

echo ""
success "Okane is running!"
echo ""
echo -e "  ${GREEN}Dashboard:${NC}     http://localhost"
echo -e "  ${GREEN}Grafana:${NC}       http://localhost/grafana"
echo -e "  ${GREEN}API docs:${NC}      http://localhost/api/docs"
echo ""
echo -e "  Run ${YELLOW}docker compose logs -f${NC} to watch all logs"
echo -e "  Run ${YELLOW}./scripts/logs.sh agent-core${NC} to watch the agent"
echo ""
