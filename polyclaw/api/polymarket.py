"""Polymarket CLOB API client.

Provides access to Polymarket's public market data:
- Active markets and events
- Order book snapshots
- Historical price/odds data
- Market metadata (liquidity, volume, etc.)

Docs: https://docs.polymarket.com/
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any

import httpx
from pydantic import BaseModel, Field

from polyclaw.config import config

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------

class Market(BaseModel):
    """A single Polymarket binary outcome market."""

    condition_id: str = ""
    question: str = ""
    description: str = ""
    market_slug: str = ""
    end_date_iso: str = ""
    game_start_time: str | None = None
    active: bool = True
    closed: bool = False
    tokens: list[dict[str, Any]] = Field(default_factory=list)
    minimum_order_size: float = 0.0
    minimum_tick_size: float = 0.01

    # Gamma enrichment fields
    volume: float = 0.0
    volume_24h: float = 0.0
    liquidity: float = 0.0
    best_bid: float = 0.0
    best_ask: float = 0.0
    last_price: float = 0.0
    outcome_prices: str = ""  # JSON string from gamma: e.g. "[0.55, 0.45]"
    category: str = ""
    spread: float = 0.0

    @property
    def midpoint(self) -> float:
        if self.best_bid and self.best_ask:
            return (self.best_bid + self.best_ask) / 2
        return self.last_price

    @property
    def implied_probability(self) -> float:
        return self.midpoint


class Event(BaseModel):
    """A Polymarket event containing one or more markets."""

    id: str = ""
    title: str = ""
    slug: str = ""
    description: str = ""
    category: str = ""
    end_date: str = ""
    active: bool = True
    closed: bool = False
    markets: list[Market] = Field(default_factory=list)
    volume: float = 0.0
    liquidity: float = 0.0
    comment_count: int = 0


class OrderBookSnapshot(BaseModel):
    """A snapshot of the order book for a token."""

    token_id: str = ""
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    bids: list[dict[str, float]] = Field(default_factory=list)  # [{"price": 0.55, "size": 100}]
    asks: list[dict[str, float]] = Field(default_factory=list)
    best_bid: float = 0.0
    best_ask: float = 0.0
    spread: float = 0.0
    mid: float = 0.0


# ---------------------------------------------------------------------------
# API Client
# ---------------------------------------------------------------------------

class PolymarketClient:
    """Async client for the Polymarket CLOB and Gamma APIs."""

    def __init__(self):
        self.clob_url = config.api.polymarket_base_url
        self.gamma_url = config.api.polymarket_gamma_url
        self._client: httpx.AsyncClient | None = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                timeout=httpx.Timeout(30.0),
                headers={"Accept": "application/json"},
            )
        return self._client

    async def close(self):
        if self._client and not self._client.is_closed:
            await self._client.aclose()

    # -- Gamma API (enriched market data) -----------------------------------

    async def get_events(
        self,
        *,
        active: bool = True,
        closed: bool = False,
        limit: int = 50,
        offset: int = 0,
        order: str = "volume",
        ascending: bool = False,
        category: str | None = None,
    ) -> list[Event]:
        """Fetch events from the Gamma API with optional filters."""
        client = await self._get_client()
        params: dict[str, Any] = {
            "active": str(active).lower(),
            "closed": str(closed).lower(),
            "limit": limit,
            "offset": offset,
            "order": order,
            "ascending": str(ascending).lower(),
        }
        if category:
            params["tag"] = category

        resp = await client.get(f"{self.gamma_url}/events", params=params)
        resp.raise_for_status()
        raw_events = resp.json()

        events = []
        for ev in raw_events:
            markets = []
            for m in ev.get("markets", []):
                markets.append(
                    Market(
                        condition_id=m.get("conditionId", ""),
                        question=m.get("question", ""),
                        description=m.get("description", ""),
                        market_slug=m.get("marketSlug", ""),
                        end_date_iso=m.get("endDate", ""),
                        active=m.get("active", True),
                        closed=m.get("closed", False),
                        volume=float(m.get("volume", 0) or 0),
                        volume_24h=float(m.get("volume24hr", 0) or 0),
                        liquidity=float(m.get("liquidity", 0) or 0),
                        best_bid=float(m.get("bestBid", 0) or 0),
                        best_ask=float(m.get("bestAsk", 0) or 0),
                        last_price=float(m.get("lastTradePrice", 0) or 0),
                        outcome_prices=m.get("outcomePrices", ""),
                        spread=float(m.get("spread", 0) or 0),
                    )
                )
            events.append(
                Event(
                    id=ev.get("id", ""),
                    title=ev.get("title", ""),
                    slug=ev.get("slug", ""),
                    description=ev.get("description", ""),
                    category=ev.get("category", ""),
                    end_date=ev.get("endDate", ""),
                    active=ev.get("active", True),
                    closed=ev.get("closed", False),
                    markets=markets,
                    volume=float(ev.get("volume", 0) or 0),
                    liquidity=float(ev.get("liquidity", 0) or 0),
                    comment_count=int(ev.get("commentCount", 0) or 0),
                )
            )
        return events

    async def get_markets(
        self,
        *,
        active: bool = True,
        closed: bool = False,
        limit: int = 100,
        offset: int = 0,
        order: str = "volume24hr",
        ascending: bool = False,
    ) -> list[Market]:
        """Fetch markets directly from the Gamma API."""
        client = await self._get_client()
        params: dict[str, Any] = {
            "active": str(active).lower(),
            "closed": str(closed).lower(),
            "limit": limit,
            "offset": offset,
            "order": order,
            "ascending": str(ascending).lower(),
        }
        resp = await client.get(f"{self.gamma_url}/markets", params=params)
        resp.raise_for_status()
        raw = resp.json()

        return [
            Market(
                condition_id=m.get("conditionId", ""),
                question=m.get("question", ""),
                description=m.get("description", ""),
                market_slug=m.get("marketSlug", ""),
                end_date_iso=m.get("endDate", ""),
                active=m.get("active", True),
                closed=m.get("closed", False),
                volume=float(m.get("volume", 0) or 0),
                volume_24h=float(m.get("volume24hr", 0) or 0),
                liquidity=float(m.get("liquidity", 0) or 0),
                best_bid=float(m.get("bestBid", 0) or 0),
                best_ask=float(m.get("bestAsk", 0) or 0),
                last_price=float(m.get("lastTradePrice", 0) or 0),
                outcome_prices=m.get("outcomePrices", ""),
                spread=float(m.get("spread", 0) or 0),
                category=m.get("category", ""),
            )
            for m in raw
        ]

    # -- CLOB API (order book) ----------------------------------------------

    async def get_order_book(self, token_id: str) -> OrderBookSnapshot:
        """Fetch the current order book for a token from the CLOB API."""
        client = await self._get_client()
        resp = await client.get(
            f"{self.clob_url}/book",
            params={"token_id": token_id},
        )
        resp.raise_for_status()
        data = resp.json()

        bids = [
            {"price": float(b["price"]), "size": float(b["size"])}
            for b in data.get("bids", [])
        ]
        asks = [
            {"price": float(a["price"]), "size": float(a["size"])}
            for a in data.get("asks", [])
        ]

        best_bid = bids[0]["price"] if bids else 0.0
        best_ask = asks[0]["price"] if asks else 0.0
        spread = best_ask - best_bid if (best_bid and best_ask) else 0.0
        mid = (best_bid + best_ask) / 2 if (best_bid and best_ask) else 0.0

        return OrderBookSnapshot(
            token_id=token_id,
            bids=bids,
            asks=asks,
            best_bid=best_bid,
            best_ask=best_ask,
            spread=spread,
            mid=mid,
        )

    async def get_market_trades(
        self, condition_id: str, *, limit: int = 100
    ) -> list[dict[str, Any]]:
        """Fetch recent trades for a market condition."""
        client = await self._get_client()
        resp = await client.get(
            f"{self.gamma_url}/trades",
            params={"market": condition_id, "limit": limit},
        )
        resp.raise_for_status()
        return resp.json()

    # -- Convenience ---------------------------------------------------------

    async def search_markets(self, query: str, *, limit: int = 20) -> list[Market]:
        """Search markets by keyword."""
        client = await self._get_client()
        resp = await client.get(
            f"{self.gamma_url}/markets",
            params={"_q": query, "limit": limit, "active": "true"},
        )
        resp.raise_for_status()
        raw = resp.json()
        return [
            Market(
                condition_id=m.get("conditionId", ""),
                question=m.get("question", ""),
                volume=float(m.get("volume", 0) or 0),
                volume_24h=float(m.get("volume24hr", 0) or 0),
                liquidity=float(m.get("liquidity", 0) or 0),
                best_bid=float(m.get("bestBid", 0) or 0),
                best_ask=float(m.get("bestAsk", 0) or 0),
                last_price=float(m.get("lastTradePrice", 0) or 0),
                outcome_prices=m.get("outcomePrices", ""),
                spread=float(m.get("spread", 0) or 0),
                category=m.get("category", ""),
            )
            for m in raw
        ]
