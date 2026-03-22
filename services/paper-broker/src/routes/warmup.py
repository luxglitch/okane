from fastapi import APIRouter, Request

router = APIRouter()

# Snapshots needed per strategy
THRESHOLDS = {
    "sentiment": 1,    # fires immediately
    "momentum": 14,    # RSI-14
    "stat_arb": 50,    # z-score window
    "pattern": 20,     # ChromaDB RAG needs some history
}


@router.get("/warmup")
async def warmup_status(request: Request):
    pool = request.app.state.pool

    async with pool.acquire() as conn:
        # Only count markets actively being fetched (seen in last 5 minutes)
        row = await conn.fetchrow("""
            SELECT
                COUNT(DISTINCT market_ticker) AS market_count,
                PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY snap_count) AS median_snaps,
                MIN(snap_count) AS min_snaps,
                MAX(snap_count) AS max_snaps
            FROM (
                SELECT market_ticker, COUNT(*) AS snap_count
                FROM market_snapshots
                WHERE market_ticker IN (
                    SELECT DISTINCT market_ticker FROM market_snapshots
                    WHERE ts >= NOW() - INTERVAL '5 minutes'
                )
                AND ts >= NOW() - INTERVAL '2 hours'
                GROUP BY market_ticker
            ) t
        """)

        # Per-strategy readiness (same active markets only)
        ready_counts = await conn.fetch("""
            SELECT market_ticker, COUNT(*) AS snap_count
            FROM market_snapshots
            WHERE market_ticker IN (
                SELECT DISTINCT market_ticker FROM market_snapshots
                WHERE ts >= NOW() - INTERVAL '5 minutes'
            )
            AND ts >= NOW() - INTERVAL '2 hours'
            GROUP BY market_ticker
        """)

    median = float(row["median_snaps"] or 0)
    market_count = row["market_count"] or 0
    counts = [r["snap_count"] for r in ready_counts]

    strategies = {}
    for name, threshold in THRESHOLDS.items():
        ready = sum(1 for c in counts if c >= threshold)
        strategies[name] = {
            "threshold": threshold,
            "markets_ready": ready,
            "markets_total": market_count,
            "pct": round(ready / market_count * 100) if market_count else 0,
            "ready": ready == market_count and market_count > 0,
        }

    # Overall: use stat_arb (hardest) as the bar
    stat_arb_pct = strategies["stat_arb"]["pct"]
    snaps_needed = max(0, THRESHOLDS["stat_arb"] - int(median))
    seconds_per_snap = 30
    eta_seconds = snaps_needed * seconds_per_snap

    return {
        "market_count": market_count,
        "median_snapshots": int(median),
        "min_snapshots": row["min_snaps"] or 0,
        "max_snapshots": row["max_snaps"] or 0,
        "overall_pct": stat_arb_pct,
        "eta_seconds": eta_seconds,
        "strategies": strategies,
    }
