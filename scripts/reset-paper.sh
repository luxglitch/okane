#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

cd "$ROOT"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo -e "${YELLOW}WARNING: This will reset all paper trading data:${NC}"
echo "  - All positions (open and closed)"
echo "  - All trade signals"
echo "  - Portfolio history"
echo "  - Agent thoughts"
echo "  - Post-mortems"
echo ""
read -p "Type 'reset' to confirm: " CONFIRM

if [ "$CONFIRM" != "reset" ]; then
    echo "Cancelled."
    exit 0
fi

echo -e "${YELLOW}Resetting paper portfolio...${NC}"

# Truncate tables (market data and agent weights are preserved)
docker compose exec -T postgres psql \
    -U "${POSTGRES_USER:-okane}" \
    -d "${POSTGRES_DB:-okane}" \
    -c "
TRUNCATE TABLE positions CASCADE;
TRUNCATE TABLE portfolio_snapshots CASCADE;
TRUNCATE TABLE trade_signals CASCADE;
TRUNCATE TABLE agent_thoughts CASCADE;
TRUNCATE TABLE post_mortems CASCADE;
TRUNCATE TABLE llm_calls CASCADE;
"

echo -e "${GREEN}Tables truncated.${NC}"

# Restart agent-core and paper-broker so they reinitialize
docker compose restart paper-broker agent-core

echo -e "${GREEN}Done! Paper portfolio reset to starting balance.${NC}"
