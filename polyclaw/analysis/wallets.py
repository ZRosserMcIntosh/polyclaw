"""Wallet performance tracking and analysis.

Analyzes on-chain wallet activity to build performance profiles:
win rates, PnL estimates, trading patterns, and bot detection.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone

from polyclaw.api.polygon import PolygonClient, WalletSummary

logger = logging.getLogger(__name__)


@dataclass
class WalletProfile:
    """Enriched wallet analysis profile."""

    address: str = ""
    summary: WalletSummary | None = None
    estimated_trade_count: int = 0
    activity_days: int = 0
    avg_trades_per_day: float = 0.0
    is_likely_bot: bool = False
    bot_confidence: float = 0.0
    bot_signals: list[str] = field(default_factory=list)


class WalletAnalyzer:
    """Analyzes wallet on-chain activity for trading patterns."""

    # Known Polymarket contract addresses on Polygon
    POLYMARKET_CTF_EXCHANGE = "0x4bfb41d5b3570defd03c39a9a4d8de6bd8b8982e"
    POLYMARKET_NEG_RISK_EXCHANGE = "0xc5d563a36ae78145c45a50134d48a1215220f80a"

    def __init__(self, client: PolygonClient | None = None):
        self.client = client or PolygonClient()

    async def analyze_wallet(self, address: str) -> WalletProfile:
        """Build a comprehensive profile of a wallet's trading activity."""
        address = address.lower().strip()
        logger.info("Analyzing wallet: %s", address)

        summary = await self.client.get_wallet_summary(address)

        # Estimate Polymarket-specific trading
        txns = await self.client.get_transactions(address, offset=500)
        polymarket_txns = [
            tx for tx in txns
            if tx.to_address.lower() in (
                self.POLYMARKET_CTF_EXCHANGE,
                self.POLYMARKET_NEG_RISK_EXCHANGE,
            )
        ]

        # Calculate activity span
        if txns:
            first = min(tx.timestamp for tx in txns)
            last = max(tx.timestamp for tx in txns)
            activity_days = max(1, (last - first) // 86400)
        else:
            activity_days = 0

        estimated_trades = len(polymarket_txns)
        avg_per_day = estimated_trades / max(1, activity_days)

        # Bot detection heuristics
        bot_signals = []
        bot_score = 0.0

        if avg_per_day > 50:
            bot_signals.append(f"High frequency: {avg_per_day:.0f} trades/day")
            bot_score += 0.3

        if estimated_trades > 100:
            # Check for regularity in timing
            if polymarket_txns:
                intervals = []
                sorted_txns = sorted(polymarket_txns, key=lambda t: t.timestamp)
                for i in range(1, min(len(sorted_txns), 100)):
                    dt = sorted_txns[i].timestamp - sorted_txns[i - 1].timestamp
                    intervals.append(dt)

                if intervals:
                    avg_interval = sum(intervals) / len(intervals)
                    variance = sum((x - avg_interval) ** 2 for x in intervals) / len(intervals)
                    cv = (variance ** 0.5) / max(avg_interval, 1)  # coefficient of variation

                    if cv < 0.5:  # very regular intervals
                        bot_signals.append(f"Regular timing pattern (CV={cv:.2f})")
                        bot_score += 0.3

        # Check for interaction with known bot infrastructure
        unique_tos = set(tx.to_address.lower() for tx in txns if tx.to_address)
        polymarket_only = unique_tos.issubset({
            self.POLYMARKET_CTF_EXCHANGE,
            self.POLYMARKET_NEG_RISK_EXCHANGE,
            "",
        })
        if polymarket_only and estimated_trades > 20:
            bot_signals.append("Interacts only with Polymarket contracts")
            bot_score += 0.2

        # 24/7 activity check
        if txns:
            hours = set()
            for tx in txns[:200]:
                hours.add(tx.dt.hour)
            if len(hours) >= 20:
                bot_signals.append(f"Active across {len(hours)}/24 hours")
                bot_score += 0.2

        is_bot = bot_score >= 0.5

        return WalletProfile(
            address=address,
            summary=summary,
            estimated_trade_count=estimated_trades,
            activity_days=activity_days,
            avg_trades_per_day=avg_per_day,
            is_likely_bot=is_bot,
            bot_confidence=min(bot_score, 1.0),
            bot_signals=bot_signals,
        )

    async def close(self):
        await self.client.close()
