"""FastAPI entrypoint for Vercel serverless deployment.

Exposes PolyClaw's analysis engine as a REST API.
Vercel auto-detects this file at api/index.py.
"""

from __future__ import annotations

import asyncio
import logging
import os
import sys
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Any

# Ensure the project root is on sys.path so polyclaw package imports work
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Response models
# ---------------------------------------------------------------------------


class HealthResponse(BaseModel):
    status: str = "ok"
    version: str = "0.1.0"
    timestamp: str = ""


class MarketResponse(BaseModel):
    question: str = ""
    condition_id: str = ""
    best_bid: float = 0.0
    best_ask: float = 0.0
    spread: float = 0.0
    midpoint: float = 0.0
    volume: float = 0.0
    volume_24h: float = 0.0
    liquidity: float = 0.0
    category: str = ""


class MarketScanResponse(BaseModel):
    markets: list[MarketResponse] = []
    total: int = 0
    timestamp: str = ""


class KalshiMarketResponse(BaseModel):
    ticker: str = ""
    title: str = ""
    event_ticker: str = ""
    status: str = ""
    yes_bid: float = 0.0
    yes_ask: float = 0.0
    spread: float = 0.0
    midpoint: float = 0.0
    volume: float = 0.0
    volume_24h: float = 0.0
    last_price: float = 0.0


class KalshiScanResponse(BaseModel):
    markets: list[KalshiMarketResponse] = []
    total: int = 0
    with_volume: int = 0
    timestamp: str = ""


class MarketPairResponse(BaseModel):
    polymarket_question: str = ""
    kalshi_title: str = ""
    polymarket_yes_price: float = 0.0
    kalshi_yes_price: float = 0.0
    price_diff: float = 0.0
    price_diff_pct: float = 0.0
    match_score: float = 0.0
    cheaper_on: str = ""
    has_arb: bool = False
    category: str = ""


class ComparisonResponse(BaseModel):
    pairs: list[MarketPairResponse] = []
    total_polymarket: int = 0
    total_kalshi: int = 0
    matched: int = 0
    arb_opportunities: int = 0
    avg_price_diff: float = 0.0
    timestamp: str = ""


class LeaderboardTrader(BaseModel):
    rank: int = 0
    address: str = ""
    tier: str = ""
    score: float = 0.0
    trade_count: int = 0
    total_volume_usd: float = 0.0
    avg_trade_size: float = 0.0
    maker_ratio: float = 0.0
    trades_per_day: float = 0.0
    is_likely_bot: bool = False


class LeaderboardResponse(BaseModel):
    traders: list[LeaderboardTrader] = []
    total_fills_analyzed: int = 0
    total_unique_wallets: int = 0
    time_window_hours: float = 0.0
    scan_duration_seconds: float = 0.0
    timestamp: str = ""


# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup/shutdown lifecycle."""
    logger.info("PolyClaw API starting")
    yield
    logger.info("PolyClaw API shutting down")


app = FastAPI(
    title="PolyClaw API",
    description="Prediction market research & analysis engine — Polymarket × Kalshi",
    version="0.1.0",
    lifespan=lifespan,
)

# CORS — allow the frontend (Vercel, localhost, custom domain)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://localhost:5173",
        "https://polyclaw.vercel.app",
        "https://polyclaw.redentortec.com",
        "https://*.vercel.app",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@app.get("/api/health", response_model=HealthResponse)
async def health():
    """Health check."""
    return HealthResponse(status="ok", version="0.1.0", timestamp=_now_iso())


@app.get("/api/markets", response_model=MarketScanResponse)
async def get_markets(
    limit: int = Query(default=50, ge=1, le=200),
    active: bool = Query(default=True),
    order: str = Query(default="volume24hr"),
):
    """Fetch Polymarket markets ranked by volume."""
    try:
        from polyclaw.api.polymarket import PolymarketClient

        client = PolymarketClient()
        try:
            raw = await client.get_markets(
                limit=limit, active=active, order=order
            )
            markets = [
                MarketResponse(
                    question=m.question,
                    condition_id=m.condition_id,
                    best_bid=m.best_bid,
                    best_ask=m.best_ask,
                    spread=m.spread,
                    midpoint=m.midpoint,
                    volume=m.volume,
                    volume_24h=m.volume_24h,
                    liquidity=m.liquidity,
                    category=m.category,
                )
                for m in raw
            ]
            return MarketScanResponse(
                markets=markets, total=len(markets), timestamp=_now_iso()
            )
        finally:
            await client.close()
    except Exception as e:
        logger.exception("Failed to fetch Polymarket markets")
        raise HTTPException(status_code=502, detail=str(e))


@app.get("/api/kalshi/markets", response_model=KalshiScanResponse)
async def get_kalshi_markets(
    status_filter: str = Query(default="open", alias="status"),
    limit: int = Query(default=200, ge=1, le=2000),
):
    """Fetch Kalshi markets."""
    try:
        from polyclaw.api.kalshi import KalshiClient

        client = KalshiClient(demo=False)
        try:
            raw = await client.get_all_markets(status=status_filter)
            # Sort by volume, take top `limit`
            raw.sort(key=lambda m: m.volume, reverse=True)
            raw = raw[:limit]

            with_volume = sum(1 for m in raw if m.volume > 0)

            markets = [
                KalshiMarketResponse(
                    ticker=m.ticker,
                    title=m.title,
                    event_ticker=m.event_ticker,
                    status=m.status,
                    yes_bid=m.yes_bid,
                    yes_ask=m.yes_ask,
                    spread=m.spread,
                    midpoint=m.midpoint,
                    volume=m.volume,
                    volume_24h=float(m.volume_24h_fp or "0"),
                    last_price=m.last_price,
                )
                for m in raw
            ]
            return KalshiScanResponse(
                markets=markets,
                total=len(markets),
                with_volume=with_volume,
                timestamp=_now_iso(),
            )
        finally:
            await client.close()
    except Exception as e:
        logger.exception("Failed to fetch Kalshi markets")
        raise HTTPException(status_code=502, detail=str(e))


@app.get("/api/compare", response_model=ComparisonResponse)
async def compare_exchanges(
    max_markets: int = Query(default=100, ge=10, le=500),
):
    """Cross-exchange comparison — find matched markets & arb opportunities."""
    try:
        from polyclaw.analysis.compare import CrossExchangeAnalyzer

        analyzer = CrossExchangeAnalyzer(kalshi_demo=False)
        try:
            comp = await analyzer.compare(max_markets=max_markets)
            pairs = [
                MarketPairResponse(
                    polymarket_question=p.polymarket_question,
                    kalshi_title=p.kalshi_title,
                    polymarket_yes_price=p.polymarket_yes_price,
                    kalshi_yes_price=p.kalshi_yes_price,
                    price_diff=p.price_diff,
                    price_diff_pct=p.price_diff_pct,
                    match_score=p.match_score,
                    cheaper_on=p.cheaper_on,
                    has_arb=p.has_arb_opportunity,
                    category=p.category,
                )
                for p in comp.matched_pairs
            ]
            return ComparisonResponse(
                pairs=pairs,
                total_polymarket=comp.total_polymarket,
                total_kalshi=comp.total_kalshi,
                matched=len(pairs),
                arb_opportunities=comp.arb_opportunities,
                avg_price_diff=comp.avg_price_diff,
                timestamp=_now_iso(),
            )
        finally:
            await analyzer.close()
    except Exception as e:
        logger.exception("Cross-exchange comparison failed")
        raise HTTPException(status_code=502, detail=str(e))


@app.get("/api/leaderboard", response_model=LeaderboardResponse)
async def get_leaderboard(
    fills: int = Query(default=2000, ge=500, le=10000),
    top_n: int = Query(default=25, ge=5, le=100),
):
    """Build a ranked leaderboard of top Polymarket traders."""
    try:
        from polyclaw.analysis.leaderboard import LeaderboardBuilder

        builder = LeaderboardBuilder(total_fills=fills, top_n=top_n)
        try:
            board = await builder.build()
            traders = [
                LeaderboardTrader(
                    rank=t.rank,
                    address=t.address,
                    tier=t.tier,
                    score=round(t.score, 2),
                    trade_count=t.trade_count,
                    total_volume_usd=round(t.total_volume_usd, 2),
                    avg_trade_size=round(t.avg_trade_size, 2),
                    maker_ratio=round(t.maker_ratio, 3),
                    trades_per_day=round(t.trades_per_day, 2),
                    is_likely_bot=t.is_likely_bot,
                )
                for t in board.traders
            ]
            return LeaderboardResponse(
                traders=traders,
                total_fills_analyzed=board.total_fills_analyzed,
                total_unique_wallets=board.total_unique_wallets,
                time_window_hours=round(board.time_window_hours, 2),
                scan_duration_seconds=round(board.scan_duration_seconds, 2),
                timestamp=_now_iso(),
            )
        finally:
            await builder.close()
    except Exception as e:
        logger.exception("Leaderboard build failed")
        raise HTTPException(status_code=502, detail=str(e))


@app.get("/api/search", response_model=MarketScanResponse)
async def search_markets(
    q: str = Query(..., min_length=2, description="Search keyword"),
    limit: int = Query(default=20, ge=1, le=100),
):
    """Search Polymarket markets by keyword."""
    try:
        from polyclaw.api.polymarket import PolymarketClient

        client = PolymarketClient()
        try:
            raw = await client.search_markets(q, limit=limit)
            markets = [
                MarketResponse(
                    question=m.question,
                    condition_id=m.condition_id,
                    best_bid=m.best_bid,
                    best_ask=m.best_ask,
                    spread=m.spread,
                    midpoint=m.midpoint,
                    volume=m.volume,
                    volume_24h=m.volume_24h,
                    liquidity=m.liquidity,
                    category=m.category,
                )
                for m in raw
            ]
            return MarketScanResponse(
                markets=markets, total=len(markets), timestamp=_now_iso()
            )
        finally:
            await client.close()
    except Exception as e:
        logger.exception("Market search failed")
        raise HTTPException(status_code=502, detail=str(e))


# ---------------------------------------------------------------------------
# Supabase-backed persistence routes
# ---------------------------------------------------------------------------


class SupabaseStatusResponse(BaseModel):
    configured: bool = False
    url: str = ""


@app.get("/api/supabase/status", response_model=SupabaseStatusResponse)
async def supabase_status():
    """Check if Supabase is configured."""
    from polyclaw.data.supabase import SupabaseClient

    client = SupabaseClient()
    return SupabaseStatusResponse(
        configured=client.is_configured,
        url=client.url if client.is_configured else "",
    )


@app.post("/api/supabase/save-leaderboard")
async def save_leaderboard_to_supabase(
    fills: int = Query(default=2000, ge=500, le=10000),
    top_n: int = Query(default=25, ge=5, le=100),
):
    """Build leaderboard and persist snapshot to Supabase."""
    from polyclaw.data.supabase import SupabaseClient

    sb = SupabaseClient()
    if not sb.is_configured:
        raise HTTPException(status_code=503, detail="Supabase not configured")

    try:
        from polyclaw.analysis.leaderboard import LeaderboardBuilder

        builder = LeaderboardBuilder(total_fills=fills, top_n=top_n)
        try:
            board = await builder.build()
            traders = [
                {
                    "rank": t.rank,
                    "address": t.address,
                    "tier": t.tier,
                    "score": round(t.score, 2),
                    "trade_count": t.trade_count,
                    "total_volume_usd": round(t.total_volume_usd, 2),
                    "avg_trade_size": round(t.avg_trade_size, 2),
                    "maker_ratio": round(t.maker_ratio, 3),
                    "trades_per_day": round(t.trades_per_day, 2),
                    "is_likely_bot": t.is_likely_bot,
                }
                for t in board.traders
            ]
            saved = await sb.save_leaderboard_snapshot(traders)
            return {
                "status": "saved",
                "rows": len(saved),
                "timestamp": _now_iso(),
            }
        finally:
            await builder.close()
            await sb.close()
    except httpx.HTTPStatusError as e:
        raise HTTPException(status_code=e.response.status_code, detail=str(e))
    except Exception as e:
        logger.exception("Leaderboard save failed")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/supabase/save-comparison")
async def save_comparison_to_supabase(
    max_markets: int = Query(default=100, ge=10, le=500),
):
    """Run cross-exchange comparison and persist to Supabase."""
    from polyclaw.data.supabase import SupabaseClient

    sb = SupabaseClient()
    if not sb.is_configured:
        raise HTTPException(status_code=503, detail="Supabase not configured")

    try:
        from polyclaw.analysis.compare import CrossExchangeAnalyzer

        analyzer = CrossExchangeAnalyzer(kalshi_demo=False)
        try:
            comp = await analyzer.compare(max_markets=max_markets)
            pairs = [
                {
                    "polymarket_question": p.polymarket_question,
                    "kalshi_title": p.kalshi_title,
                    "polymarket_yes_price": p.polymarket_yes_price,
                    "kalshi_yes_price": p.kalshi_yes_price,
                    "price_diff": p.price_diff,
                    "price_diff_pct": p.price_diff_pct,
                    "match_score": p.match_score,
                    "cheaper_on": p.cheaper_on,
                    "has_arb": p.has_arb_opportunity,
                }
                for p in comp.matched_pairs
            ]
            comparison_meta = {
                "total_polymarket": comp.total_polymarket,
                "total_kalshi": comp.total_kalshi,
            }
            saved = await sb.save_comparison(comparison_meta, pairs)
            return {
                "status": "saved",
                "rows": len(saved),
                "arb_opportunities": comp.arb_opportunities,
                "timestamp": _now_iso(),
            }
        finally:
            await analyzer.close()
            await sb.close()
    except Exception as e:
        logger.exception("Comparison save failed")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/supabase/leaderboard-history")
async def get_leaderboard_history(
    limit: int = Query(default=25, ge=1, le=200),
):
    """Get the most recent leaderboard from Supabase."""
    from polyclaw.data.supabase import SupabaseClient

    sb = SupabaseClient()
    if not sb.is_configured:
        raise HTTPException(status_code=503, detail="Supabase not configured")

    try:
        rows = await sb.get_latest_leaderboard(limit=limit)
        return {"rows": rows, "total": len(rows), "timestamp": _now_iso()}
    except Exception as e:
        logger.exception("Leaderboard history fetch failed")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        await sb.close()


@app.get("/api/supabase/comparison-history")
async def get_comparison_history(
    limit: int = Query(default=50, ge=1, le=500),
):
    """Get recent cross-exchange comparisons from Supabase."""
    from polyclaw.data.supabase import SupabaseClient

    sb = SupabaseClient()
    if not sb.is_configured:
        raise HTTPException(status_code=503, detail="Supabase not configured")

    try:
        rows = await sb.get_comparison_history(limit=limit)
        return {"rows": rows, "total": len(rows), "timestamp": _now_iso()}
    except Exception as e:
        logger.exception("Comparison history fetch failed")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        await sb.close()
