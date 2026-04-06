"""Polymarket on-chain trade data client via Goldsky subgraph.

Fetches trade fills, aggregates by wallet, and builds trader profiles
using the orderbook subgraph (the live, public data source).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

import httpx

logger = logging.getLogger(__name__)

ORDERBOOK_SUBGRAPH = (
    "https://api.goldsky.com/api/public/"
    "project_cl6mb8i9h0003e201j6li0diw/subgraphs/"
    "orderbook-subgraph/0.0.1/gn"
)

# Known Polymarket contract addresses (not real traders)
KNOWN_CONTRACTS = {
    "0x4bfb41d5b3570defd03c39a9a4d8de6bd8b8982e",  # CTF Exchange
    "0xc5d563a36ae78145c45a50134d48a1215220f80a",  # Neg Risk Exchange
    "0x0000000000000000000000000000000000000000",
}


@dataclass
class TraderFill:
    """A single order fill event."""

    maker: str
    taker: str
    maker_amount: float  # USDC (6 decimals)
    taker_amount: float
    timestamp: int
    tx_hash: str = ""

    @property
    def dt(self) -> datetime:
        return datetime.fromtimestamp(self.timestamp, tz=timezone.utc)


@dataclass
class TraderProfile:
    """Aggregated on-chain trader profile."""

    address: str
    trade_count: int = 0
    total_volume_usd: float = 0.0
    maker_count: int = 0  # times they were maker (limit orders)
    taker_count: int = 0  # times they were taker (market orders)
    first_trade: datetime | None = None
    last_trade: datetime | None = None
    avg_trade_size: float = 0.0
    activity_days: int = 0
    trades_per_day: float = 0.0
    maker_ratio: float = 0.0  # higher = more sophisticated (limit orders)
    recent_fills: list[TraderFill] = field(default_factory=list)

    @property
    def is_likely_bot(self) -> bool:
        """Heuristic: high frequency + mostly maker = likely bot."""
        return self.trades_per_day > 30 and self.maker_ratio > 0.7

    @property
    def profile_url(self) -> str:
        return f"https://polymarket.com/profile/{self.address}"


@dataclass
class Leaderboard:
    """Ranked trader leaderboard."""

    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    traders: list[TraderProfile] = field(default_factory=list)
    total_fills_analyzed: int = 0
    time_window_hours: float = 0.0

    @property
    def total_traders(self) -> int:
        return len(self.traders)


class SubgraphClient:
    """Client for querying Polymarket's Goldsky subgraph."""

    def __init__(self, url: str = ORDERBOOK_SUBGRAPH):
        self.url = url
        self._client: httpx.AsyncClient | None = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(timeout=httpx.Timeout(30.0))
        return self._client

    async def close(self):
        if self._client and not self._client.is_closed:
            await self._client.aclose()

    async def query(self, graphql: str) -> dict[str, Any]:
        """Execute a GraphQL query against the subgraph."""
        client = await self._get_client()
        resp = await client.post(self.url, json={"query": graphql})
        resp.raise_for_status()
        data = resp.json()
        if "errors" in data:
            logger.error("Subgraph query error: %s", data["errors"])
        return data.get("data", {})

    async def get_recent_fills(
        self,
        limit: int = 1000,
        min_timestamp: int | None = None,
    ) -> list[TraderFill]:
        """Fetch recent order fill events."""
        where_clause = ""
        if min_timestamp:
            where_clause = f', where: {{ timestamp_gte: "{min_timestamp}" }}'

        query = f"""
        {{
          orderFilledEvents(
            first: {limit},
            orderBy: timestamp,
            orderDirection: desc
            {where_clause}
          ) {{
            id
            maker
            taker
            makerAmountFilled
            takerAmountFilled
            timestamp
          }}
        }}
        """
        data = await self.query(query)
        fills = data.get("orderFilledEvents", [])

        return [
            TraderFill(
                maker=f["maker"],
                taker=f["taker"],
                maker_amount=int(f["makerAmountFilled"]) / 1e6,
                taker_amount=int(f["takerAmountFilled"]) / 1e6,
                timestamp=int(f["timestamp"]),
                tx_hash=f.get("id", "").split("_")[0] if "_" in f.get("id", "") else "",
            )
            for f in fills
        ]

    async def get_fills_paginated(
        self,
        total: int = 5000,
        batch_size: int = 1000,
    ) -> list[TraderFill]:
        """Fetch fills in batches for deeper analysis."""
        all_fills: list[TraderFill] = []
        last_timestamp: int | None = None

        while len(all_fills) < total:
            remaining = min(batch_size, total - len(all_fills))

            where = ""
            if last_timestamp:
                where = f', where: {{ timestamp_lt: "{last_timestamp}" }}'

            query = f"""
            {{
              orderFilledEvents(
                first: {remaining},
                orderBy: timestamp,
                orderDirection: desc
                {where}
              ) {{
                id
                maker
                taker
                makerAmountFilled
                takerAmountFilled
                timestamp
              }}
            }}
            """
            data = await self.query(query)
            fills_raw = data.get("orderFilledEvents", [])
            if not fills_raw:
                break

            for f in fills_raw:
                all_fills.append(
                    TraderFill(
                        maker=f["maker"],
                        taker=f["taker"],
                        maker_amount=int(f["makerAmountFilled"]) / 1e6,
                        taker_amount=int(f["takerAmountFilled"]) / 1e6,
                        timestamp=int(f["timestamp"]),
                        tx_hash=f.get("id", "").split("_")[0] if "_" in f.get("id", "") else "",
                    )
                )

            last_timestamp = int(fills_raw[-1]["timestamp"])
            logger.info("Fetched %d fills so far (oldest: %s)", len(all_fills), last_timestamp)

        return all_fills


def build_leaderboard(fills: list[TraderFill], *, top_n: int = 50) -> Leaderboard:
    """Aggregate fills into trader profiles and rank them.

    Args:
        fills: Raw fill events from the subgraph.
        top_n: Number of top traders to include.

    Returns:
        Leaderboard with ranked trader profiles.
    """
    wallets: dict[str, dict] = {}

    for fill in fills:
        for role, addr, amount in [
            ("maker", fill.maker, fill.maker_amount),
            ("taker", fill.taker, fill.taker_amount),
        ]:
            if addr in KNOWN_CONTRACTS:
                continue

            if addr not in wallets:
                wallets[addr] = {
                    "address": addr,
                    "trade_count": 0,
                    "total_volume": 0.0,
                    "maker_count": 0,
                    "taker_count": 0,
                    "timestamps": [],
                    "recent_fills": [],
                }

            w = wallets[addr]
            w["trade_count"] += 1
            w["total_volume"] += amount
            w[f"{role}_count"] += 1
            w["timestamps"].append(fill.timestamp)

            # Keep most recent fills for this wallet
            if len(w["recent_fills"]) < 20:
                w["recent_fills"].append(fill)

    # Build profiles
    profiles = []
    for addr, w in wallets.items():
        timestamps = sorted(w["timestamps"])
        if not timestamps:
            continue

        first_ts = timestamps[0]
        last_ts = timestamps[-1]
        span_days = max(1, (last_ts - first_ts) / 86400)

        profile = TraderProfile(
            address=addr,
            trade_count=w["trade_count"],
            total_volume_usd=w["total_volume"],
            maker_count=w["maker_count"],
            taker_count=w["taker_count"],
            first_trade=datetime.fromtimestamp(first_ts, tz=timezone.utc),
            last_trade=datetime.fromtimestamp(last_ts, tz=timezone.utc),
            avg_trade_size=w["total_volume"] / max(w["trade_count"], 1),
            activity_days=int(span_days),
            trades_per_day=w["trade_count"] / span_days,
            maker_ratio=w["maker_count"] / max(w["trade_count"], 1),
            recent_fills=w["recent_fills"][:10],
        )
        profiles.append(profile)

    # Rank by volume
    profiles.sort(key=lambda p: p.total_volume_usd, reverse=True)
    top_profiles = profiles[:top_n]

    # Calculate time window
    all_timestamps = [f.timestamp for f in fills]
    window_hours = (max(all_timestamps) - min(all_timestamps)) / 3600 if all_timestamps else 0

    return Leaderboard(
        traders=top_profiles,
        total_fills_analyzed=len(fills),
        time_window_hours=window_hours,
    )
