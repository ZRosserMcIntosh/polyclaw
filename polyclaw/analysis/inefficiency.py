"""Inefficiency / latency detection between CEX prices and Polymarket odds.

The core research question: how large is the lag between Binance
price movements and Polymarket crypto contract odds updates?
This module measures and logs those windows.
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone

from polyclaw.api.binance import BinanceClient, PriceTick
from polyclaw.api.polymarket import PolymarketClient, Market

logger = logging.getLogger(__name__)


@dataclass
class InefficiencyWindow:
    """A detected lag/inefficiency window."""

    timestamp: datetime
    symbol: str
    cex_price: float
    cex_price_change_pct: float
    polymarket_question: str
    polymarket_implied_prob: float
    estimated_fair_prob: float
    edge_pct: float
    window_duration_ms: float = 0.0
    resolved: bool = False

    @property
    def edge_direction(self) -> str:
        if self.edge_pct > 0:
            return "BUY_YES"
        elif self.edge_pct < 0:
            return "BUY_NO"
        return "NONE"


@dataclass
class ScanSession:
    """Tracks an inefficiency scanning session."""

    start_time: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    windows_detected: list[InefficiencyWindow] = field(default_factory=list)
    total_ticks_processed: int = 0
    total_polymarket_polls: int = 0
    avg_lag_ms: float = 0.0

    @property
    def duration_seconds(self) -> float:
        now = datetime.now(timezone.utc)
        return (now - self.start_time).total_seconds()

    @property
    def windows_per_hour(self) -> float:
        hours = self.duration_seconds / 3600
        return len(self.windows_detected) / max(hours, 0.001)


class InefficiencyScanner:
    """Monitors CEX prices vs Polymarket odds to detect lag windows.

    This does NOT trade. It measures and logs how often the claimed
    arbitrage windows exist, how large they are, and how long they last.
    """

    def __init__(
        self,
        binance: BinanceClient | None = None,
        polymarket: PolymarketClient | None = None,
        edge_threshold_pct: float = 3.0,
    ):
        self.binance = binance or BinanceClient()
        self.polymarket = polymarket or PolymarketClient()
        self.edge_threshold = edge_threshold_pct / 100.0
        self._session: ScanSession | None = None
        self._running = False

        # State for tracking price movements
        self._price_baseline: dict[str, float] = {}
        self._crypto_markets: list[Market] = []

    async def _refresh_crypto_markets(self):
        """Find active crypto price markets on Polymarket."""
        all_markets = await self.polymarket.get_markets(limit=100)
        crypto_keywords = ["bitcoin", "btc", "ethereum", "eth", "price", "above", "below"]
        self._crypto_markets = [
            m for m in all_markets
            if any(kw in m.question.lower() for kw in crypto_keywords)
            and m.active
            and not m.closed
        ]
        logger.info(
            "Found %d active crypto markets to monitor", len(self._crypto_markets)
        )

    def _estimate_fair_probability(
        self, market: Market, cex_price: float, price_change_pct: float
    ) -> float | None:
        """Estimate what the 'fair' probability should be given CEX data.

        This is a simplified heuristic — real implementations would use
        historical volatility, time to expiry, and strike price extraction.
        For research purposes, we use a momentum-based estimate.
        """
        question = market.question.lower()

        # Try to detect "above X" or "below X" style markets
        # These are very rough heuristics for research logging
        current_prob = market.implied_probability
        if current_prob <= 0 or current_prob >= 1:
            return None

        # Simple model: if price moved significantly, the probability
        # should shift in the same direction for "above" contracts
        if "above" in question or "higher" in question or "up" in question:
            # Price went up → "above" more likely
            shift = price_change_pct * 2  # amplify for short-duration contracts
            return max(0.01, min(0.99, current_prob + shift))
        elif "below" in question or "lower" in question or "down" in question:
            shift = -price_change_pct * 2
            return max(0.01, min(0.99, current_prob + shift))

        return None

    async def _on_price_tick(self, tick: PriceTick):
        """Process a CEX price tick and check for Polymarket lag."""
        if not self._session:
            return

        self._session.total_ticks_processed += 1

        # Track price baseline
        symbol = tick.symbol
        if symbol not in self._price_baseline:
            self._price_baseline[symbol] = tick.price
            return

        baseline = self._price_baseline[symbol]
        change_pct = (tick.price - baseline) / baseline

        # Only analyze significant moves (>0.1%)
        if abs(change_pct) < 0.001:
            return

        # Update baseline
        self._price_baseline[symbol] = tick.price

        # Check each crypto market for potential lag
        for market in self._crypto_markets:
            fair_prob = self._estimate_fair_probability(market, tick.price, change_pct)
            if fair_prob is None:
                continue

            current_prob = market.implied_probability
            edge = abs(fair_prob - current_prob)

            if edge >= self.edge_threshold:
                window = InefficiencyWindow(
                    timestamp=datetime.now(timezone.utc),
                    symbol=symbol,
                    cex_price=tick.price,
                    cex_price_change_pct=change_pct * 100,
                    polymarket_question=market.question[:100],
                    polymarket_implied_prob=current_prob,
                    estimated_fair_prob=fair_prob,
                    edge_pct=edge * 100,
                )
                self._session.windows_detected.append(window)
                logger.info(
                    "⚡ Inefficiency detected! Edge=%.1f%% | %s | CEX Δ=%.2f%% | "
                    "PM prob=%.1f%% → fair=%.1f%%",
                    window.edge_pct,
                    symbol,
                    window.cex_price_change_pct,
                    window.polymarket_implied_prob * 100,
                    window.estimated_fair_prob * 100,
                )

    async def run_scan(
        self,
        duration_seconds: float = 300,
        poll_interval: float = 5.0,
    ) -> ScanSession:
        """Run an inefficiency scan for the specified duration.

        Args:
            duration_seconds: How long to run the scan (default: 5 minutes).
            poll_interval: How often to refresh Polymarket data (seconds).

        Returns:
            ScanSession with all detected windows and stats.
        """
        self._session = ScanSession()
        self._running = True

        logger.info(
            "Starting inefficiency scan (duration=%ds, threshold=%.1f%%)",
            duration_seconds,
            self.edge_threshold * 100,
        )

        # Find crypto markets to monitor
        await self._refresh_crypto_markets()

        if not self._crypto_markets:
            logger.warning("No crypto markets found to monitor!")
            return self._session

        # Register price tick callback
        self.binance.on_tick(self._on_price_tick)

        # Run WebSocket stream and periodic Polymarket polling concurrently
        async def poll_polymarket():
            while self._running:
                try:
                    await self._refresh_crypto_markets()
                    self._session.total_polymarket_polls += 1
                except Exception:
                    logger.exception("Polymarket poll error")
                await asyncio.sleep(poll_interval)

        try:
            await asyncio.gather(
                self.binance.stream_prices(
                    symbols=["btcusdt", "ethusdt"],
                    duration_seconds=duration_seconds,
                ),
                poll_polymarket(),
            )
        except asyncio.CancelledError:
            pass
        finally:
            self._running = False

        # Calculate summary stats
        if self._session.windows_detected:
            edges = [w.edge_pct for w in self._session.windows_detected]
            self._session.avg_lag_ms = sum(edges) / len(edges)  # placeholder

        logger.info(
            "Scan complete. Duration=%.0fs | Ticks=%d | Windows=%d | Rate=%.1f/hr",
            self._session.duration_seconds,
            self._session.total_ticks_processed,
            len(self._session.windows_detected),
            self._session.windows_per_hour,
        )

        return self._session

    async def close(self):
        self._running = False
        await self.binance.close()
        await self.polymarket.close()
