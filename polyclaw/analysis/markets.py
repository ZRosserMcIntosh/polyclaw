"""Market data analysis tools.

Fetches and analyzes Polymarket markets to find interesting
opportunities, high-volume events, and spread anomalies.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

import pandas as pd

from polyclaw.api.polymarket import PolymarketClient, Market, Event

logger = logging.getLogger(__name__)


@dataclass
class MarketScanResult:
    """Results from a market scan."""

    total_markets: int = 0
    total_volume: float = 0.0
    avg_spread: float = 0.0
    widest_spreads: list[dict] = None
    highest_volume: list[dict] = None
    crypto_markets: list[dict] = None
    low_liquidity: list[dict] = None

    def __post_init__(self):
        self.widest_spreads = self.widest_spreads or []
        self.highest_volume = self.highest_volume or []
        self.crypto_markets = self.crypto_markets or []
        self.low_liquidity = self.low_liquidity or []


class MarketAnalyzer:
    """Analyzes Polymarket data for research insights."""

    def __init__(self, client: PolymarketClient | None = None):
        self.client = client or PolymarketClient()

    async def scan_markets(self, *, limit: int = 200) -> MarketScanResult:
        """Perform a comprehensive scan of active markets.

        Returns analysis including:
        - Markets with widest bid/ask spreads (potential inefficiency)
        - Highest volume markets (most liquid)
        - Crypto-specific markets (relevant for latency analysis)
        - Low liquidity markets (potential spread opportunities)
        """
        logger.info("Scanning up to %d active markets...", limit)

        # Fetch in batches
        all_markets: list[Market] = []
        offset = 0
        batch_size = min(limit, 100)
        while offset < limit:
            batch = await self.client.get_markets(
                active=True, limit=batch_size, offset=offset
            )
            if not batch:
                break
            all_markets.extend(batch)
            offset += batch_size

        if not all_markets:
            logger.warning("No markets found!")
            return MarketScanResult()

        logger.info("Fetched %d markets. Analyzing...", len(all_markets))

        # Convert to dicts for analysis
        records = []
        for m in all_markets:
            records.append({
                "condition_id": m.condition_id,
                "question": m.question[:80],
                "volume": m.volume,
                "volume_24h": m.volume_24h,
                "liquidity": m.liquidity,
                "best_bid": m.best_bid,
                "best_ask": m.best_ask,
                "spread": m.spread if m.spread else (m.best_ask - m.best_bid if m.best_ask and m.best_bid else 0),
                "last_price": m.last_price,
                "category": m.category,
            })

        df = pd.DataFrame(records)

        # Widest spreads (potential mispricing / inefficiency)
        df_spreads = df[df["spread"] > 0].sort_values("spread", ascending=False)
        widest_spreads = df_spreads.head(10).to_dict("records")

        # Highest 24h volume
        highest_volume = df.sort_values("volume_24h", ascending=False).head(10).to_dict("records")

        # Crypto-related markets
        crypto_keywords = ["bitcoin", "btc", "ethereum", "eth", "crypto", "solana", "sol"]
        crypto_mask = df["question"].str.lower().apply(
            lambda q: any(kw in q for kw in crypto_keywords)
        )
        crypto_markets = df[crypto_mask].sort_values("volume_24h", ascending=False).head(20).to_dict("records")

        # Low liquidity (thin order books, easier to move)
        df_low_liq = df[(df["liquidity"] > 0) & (df["liquidity"] < 5000)]
        low_liquidity = df_low_liq.sort_values("liquidity").head(10).to_dict("records")

        total_volume = df["volume"].sum()
        avg_spread = df[df["spread"] > 0]["spread"].mean() if len(df[df["spread"] > 0]) else 0

        return MarketScanResult(
            total_markets=len(all_markets),
            total_volume=total_volume,
            avg_spread=avg_spread,
            widest_spreads=widest_spreads,
            highest_volume=highest_volume,
            crypto_markets=crypto_markets,
            low_liquidity=low_liquidity,
        )

    async def get_market_detail(self, condition_id: str) -> dict:
        """Get detailed info for a single market including order book."""
        markets = await self.client.get_markets(limit=1)
        # Fetch order book if we have token IDs
        # For now, return market metadata
        for m in markets:
            if m.condition_id == condition_id:
                return {
                    "question": m.question,
                    "volume": m.volume,
                    "liquidity": m.liquidity,
                    "spread": m.spread,
                    "best_bid": m.best_bid,
                    "best_ask": m.best_ask,
                    "implied_prob": m.implied_probability,
                }
        return {}

    async def close(self):
        await self.client.close()
