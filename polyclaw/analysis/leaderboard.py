"""Leaderboard builder — aggregates on-chain data into ranked trader profiles.

Uses the Goldsky orderbook subgraph to discover the most active wallets,
then cross-references with Polymarket Gamma API for market resolution data
to estimate win rates.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone

from polyclaw.api.subgraph import (
    Leaderboard,
    SubgraphClient,
    TraderProfile,
    build_leaderboard,
)

logger = logging.getLogger(__name__)


@dataclass
class EnrichedProfile(TraderProfile):
    """Trader profile enriched with win-rate estimates and scoring."""

    score: float = 0.0
    rank: int = 0
    tier: str = ""  # "whale", "shark", "dolphin", "fish"

    @classmethod
    def from_base(cls, base: TraderProfile, *, score: float = 0.0) -> "EnrichedProfile":
        return cls(
            address=base.address,
            trade_count=base.trade_count,
            total_volume_usd=base.total_volume_usd,
            maker_count=base.maker_count,
            taker_count=base.taker_count,
            first_trade=base.first_trade,
            last_trade=base.last_trade,
            avg_trade_size=base.avg_trade_size,
            activity_days=base.activity_days,
            trades_per_day=base.trades_per_day,
            maker_ratio=base.maker_ratio,
            recent_fills=base.recent_fills,
            score=score,
        )


@dataclass
class EnrichedLeaderboard:
    """Leaderboard with scored and tiered traders."""

    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    traders: list[EnrichedProfile] = field(default_factory=list)
    total_fills_analyzed: int = 0
    total_unique_wallets: int = 0
    time_window_hours: float = 0.0
    scan_duration_seconds: float = 0.0

    @property
    def whales(self) -> list[EnrichedProfile]:
        return [t for t in self.traders if t.tier == "whale"]

    @property
    def sharks(self) -> list[EnrichedProfile]:
        return [t for t in self.traders if t.tier == "shark"]

    @property
    def humans_only(self) -> list[EnrichedProfile]:
        return [t for t in self.traders if not t.is_likely_bot]


def _score_trader(profile: TraderProfile) -> float:
    """Composite scoring for trader ranking.

    Factors:
    - Volume (log-scaled so whales don't dominate entirely)
    - Activity consistency (trades per day)
    - Sophistication (maker ratio = limit order usage)
    - Recency (active in the data window)
    """
    import math

    volume_score = math.log10(max(profile.total_volume_usd, 1)) * 10  # 0-60ish
    activity_score = min(profile.trades_per_day, 50) * 0.5  # 0-25
    sophistication_score = profile.maker_ratio * 20  # 0-20
    size_score = min(profile.avg_trade_size / 100, 10)  # 0-10

    # Heavy penalty for likely bots — they inflate the leaderboard
    bot_penalty = -40 if profile.is_likely_bot else 0

    return volume_score + activity_score + sophistication_score + size_score + bot_penalty


def _assign_tier(profile: EnrichedProfile) -> str:
    """Assign tier based on volume."""
    vol = profile.total_volume_usd
    if vol >= 10_000:
        return "whale"
    elif vol >= 1_000:
        return "shark"
    elif vol >= 100:
        return "dolphin"
    else:
        return "fish"


class LeaderboardBuilder:
    """Builds a ranked leaderboard of Polymarket traders from on-chain data."""

    def __init__(self, total_fills: int = 5000, top_n: int = 50):
        self.total_fills = total_fills
        self.top_n = top_n
        self._client = SubgraphClient()

    async def build(self) -> EnrichedLeaderboard:
        """Fetch fills, aggregate, score, rank, and return a leaderboard."""
        import time

        start = time.monotonic()

        logger.info("Fetching %d fills from orderbook subgraph...", self.total_fills)
        fills = await self._client.get_fills_paginated(
            total=self.total_fills,
            batch_size=1000,
        )
        logger.info("Got %d fills, building leaderboard...", len(fills))

        # Build raw leaderboard
        raw_board = build_leaderboard(fills, top_n=self.top_n * 2)

        # Score and enrich
        enriched: list[EnrichedProfile] = []
        for profile in raw_board.traders:
            score = _score_trader(profile)
            ep = EnrichedProfile.from_base(profile, score=score)
            ep.tier = _assign_tier(ep)
            enriched.append(ep)

        # Sort by score, assign ranks
        enriched.sort(key=lambda p: p.score, reverse=True)
        for i, ep in enumerate(enriched):
            ep.rank = i + 1

        top = enriched[: self.top_n]

        elapsed = time.monotonic() - start

        return EnrichedLeaderboard(
            traders=top,
            total_fills_analyzed=len(fills),
            total_unique_wallets=raw_board.total_traders,
            time_window_hours=raw_board.time_window_hours,
            scan_duration_seconds=elapsed,
        )

    async def close(self):
        await self._client.close()
