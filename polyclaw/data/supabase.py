"""Supabase integration for PolyClaw.

Stores leaderboard snapshots, cross-exchange comparisons, copy-trade events,
and paper trade history in Supabase (Postgres).

All tables are prefixed with `polyclaw_` to share the database cleanly
with other projects (e.g. Redentor Tec).

Environment variables:
  SUPABASE_URL       — project URL (https://xxx.supabase.co)
  SUPABASE_ANON_KEY  — public anon key (or service role key for server-side)
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from typing import Any

import httpx

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

SUPABASE_URL = os.getenv("SUPABASE_URL", "")
SUPABASE_KEY = os.getenv("SUPABASE_ANON_KEY", "") or os.getenv("SUPABASE_SERVICE_KEY", "")


# ---------------------------------------------------------------------------
# Supabase REST client (lightweight — no heavy SDK dependency)
# ---------------------------------------------------------------------------


class SupabaseClient:
    """Minimal Supabase client using the PostgREST API.

    We use raw HTTP instead of the supabase-py SDK to keep the dependency
    footprint small for Vercel serverless deploys.
    """

    TABLE_PREFIX = "polyclaw_"

    def __init__(self, url: str | None = None, key: str | None = None):
        self.url = (url or SUPABASE_URL).rstrip("/")
        self.key = key or SUPABASE_KEY
        self._rest_url = f"{self.url}/rest/v1"
        self._client: httpx.AsyncClient | None = None

        if not self.url or not self.key:
            logger.warning(
                "Supabase not configured — set SUPABASE_URL and SUPABASE_ANON_KEY"
            )

    @property
    def is_configured(self) -> bool:
        return bool(self.url and self.key)

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                timeout=httpx.Timeout(30.0),
                headers={
                    "apikey": self.key,
                    "Authorization": f"Bearer {self.key}",
                    "Content-Type": "application/json",
                    "Prefer": "return=representation",
                },
            )
        return self._client

    def _table(self, name: str) -> str:
        """Prefix table name."""
        return f"{self.TABLE_PREFIX}{name}"

    # -- Generic CRUD -------------------------------------------------------

    async def insert(self, table: str, rows: list[dict[str, Any]]) -> list[dict]:
        """Insert rows into a prefixed table."""
        client = await self._get_client()
        resp = await client.post(
            f"{self._rest_url}/{self._table(table)}",
            json=rows,
        )
        resp.raise_for_status()
        return resp.json()

    async def select(
        self,
        table: str,
        *,
        columns: str = "*",
        filters: dict[str, str] | None = None,
        order: str | None = None,
        limit: int = 100,
    ) -> list[dict]:
        """Select rows from a prefixed table."""
        client = await self._get_client()
        params: dict[str, str] = {"select": columns, "limit": str(limit)}
        if filters:
            params.update(filters)
        if order:
            params["order"] = order
        resp = await client.get(
            f"{self._rest_url}/{self._table(table)}",
            params=params,
        )
        resp.raise_for_status()
        return resp.json()

    async def upsert(self, table: str, rows: list[dict[str, Any]]) -> list[dict]:
        """Upsert rows (insert or update on conflict)."""
        client = await self._get_client()
        resp = await client.post(
            f"{self._rest_url}/{self._table(table)}",
            json=rows,
            headers={
                "Prefer": "resolution=merge-duplicates,return=representation",
            },
        )
        resp.raise_for_status()
        return resp.json()

    # -- PolyClaw-specific helpers ------------------------------------------

    async def save_leaderboard_snapshot(
        self, traders: list[dict[str, Any]]
    ) -> list[dict]:
        """Save a leaderboard snapshot with timestamp."""
        now = datetime.now(timezone.utc).isoformat()
        rows = [
            {
                "snapshot_time": now,
                "rank": t.get("rank", 0),
                "address": t.get("address", ""),
                "tier": t.get("tier", ""),
                "score": t.get("score", 0),
                "trade_count": t.get("trade_count", 0),
                "total_volume_usd": t.get("total_volume_usd", 0),
                "avg_trade_size": t.get("avg_trade_size", 0),
                "maker_ratio": t.get("maker_ratio", 0),
                "trades_per_day": t.get("trades_per_day", 0),
                "is_likely_bot": t.get("is_likely_bot", False),
            }
            for t in traders
        ]
        return await self.insert("leaderboard_snapshots", rows)

    async def save_comparison(
        self, comparison: dict[str, Any], pairs: list[dict[str, Any]]
    ) -> list[dict]:
        """Save a cross-exchange comparison."""
        now = datetime.now(timezone.utc).isoformat()
        rows = [
            {
                "snapshot_time": now,
                "polymarket_question": p.get("polymarket_question", ""),
                "kalshi_title": p.get("kalshi_title", ""),
                "polymarket_yes_price": p.get("polymarket_yes_price", 0),
                "kalshi_yes_price": p.get("kalshi_yes_price", 0),
                "price_diff": p.get("price_diff", 0),
                "price_diff_pct": p.get("price_diff_pct", 0),
                "match_score": p.get("match_score", 0),
                "cheaper_on": p.get("cheaper_on", ""),
                "has_arb": p.get("has_arb", False),
                "total_polymarket": comparison.get("total_polymarket", 0),
                "total_kalshi": comparison.get("total_kalshi", 0),
            }
            for p in pairs
        ]
        return await self.insert("comparison_snapshots", rows)

    async def save_copytrade_event(self, event: dict[str, Any]) -> list[dict]:
        """Save a detected copy-trade fill."""
        return await self.insert("copytrade_events", [event])

    async def save_market_snapshot(self, markets: list[dict[str, Any]]) -> list[dict]:
        """Save market data snapshot."""
        now = datetime.now(timezone.utc).isoformat()
        for m in markets:
            m["snapshot_time"] = now
        return await self.insert("market_snapshots", markets)

    async def get_latest_leaderboard(self, limit: int = 25) -> list[dict]:
        """Get the most recent leaderboard snapshot."""
        return await self.select(
            "leaderboard_snapshots",
            order="snapshot_time.desc,rank.asc",
            limit=limit,
        )

    async def get_comparison_history(self, limit: int = 50) -> list[dict]:
        """Get recent comparison snapshots."""
        return await self.select(
            "comparison_snapshots",
            order="snapshot_time.desc",
            limit=limit,
        )

    async def close(self):
        if self._client and not self._client.is_closed:
            await self._client.aclose()
