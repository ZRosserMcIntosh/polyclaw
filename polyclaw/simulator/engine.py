"""Core simulation engine for paper trading.

Orchestrates the full loop:
1. Fetch market data + price feeds
2. Run strategy to produce signals
3. Apply risk management checks
4. Execute paper trades
5. Monitor + close positions on resolution
6. Track performance over time
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any

from polyclaw.api.binance import BinanceClient
from polyclaw.api.polymarket import PolymarketClient
from polyclaw.config import config
from polyclaw.simulator.portfolio import Portfolio, Side
from polyclaw.simulator.risk import RiskManager
from polyclaw.simulator.strategies import Strategy, TradeSignal, get_strategy

logger = logging.getLogger(__name__)


class SimulationEngine:
    """Runs a paper trading simulation loop.

    Connects real-time data feeds to a strategy, applies risk management,
    and tracks all simulated trades in a virtual portfolio.
    """

    def __init__(
        self,
        strategy: Strategy | str = "latency-arb",
        starting_balance: float | None = None,
        polymarket: PolymarketClient | None = None,
        binance: BinanceClient | None = None,
    ):
        if isinstance(strategy, str):
            self.strategy = get_strategy(strategy)
        else:
            self.strategy = strategy

        balance = starting_balance or config.simulator.starting_balance
        self.portfolio = Portfolio(starting_balance=balance)
        self.risk_manager = RiskManager(self.portfolio)
        self.polymarket = polymarket or PolymarketClient()
        self.binance = binance or BinanceClient()
        self._running = False
        self._tick_count = 0
        self._signal_count = 0

    async def run(
        self,
        duration_seconds: float = 3600,
        poll_interval: float = 10.0,
    ) -> dict[str, Any]:
        """Run the simulation for a specified duration.

        Args:
            duration_seconds: How long to run (default: 1 hour).
            poll_interval: How often to poll Polymarket (seconds).

        Returns:
            Summary dict with performance metrics.
        """
        self._running = True
        start = datetime.now(timezone.utc)

        logger.info(
            "🚀 Starting paper simulation | Strategy=%s | Balance=$%.2f | Duration=%ds",
            self.strategy.name,
            self.portfolio.starting_balance,
            duration_seconds,
        )

        # Initial market fetch
        markets = await self.polymarket.get_markets(limit=50)
        logger.info("Loaded %d markets", len(markets))

        # Collect initial price snapshot
        prices = await self.binance.get_prices()
        logger.info("Initial prices: %s", {k: f"${v.price:,.2f}" for k, v in prices.items()})

        # Take initial snapshot
        self.portfolio.take_snapshot()

        # Main loop
        elapsed = 0.0
        cycle = 0
        while self._running and elapsed < duration_seconds:
            cycle += 1
            try:
                # Refresh data
                prices = await self.binance.get_prices()
                if cycle % 6 == 0:  # Refresh markets every ~minute
                    markets = await self.polymarket.get_markets(limit=50)

                # Run strategy
                signals = await self.strategy.evaluate(markets, prices)
                self._signal_count += len(signals)

                # Process signals
                for signal in signals:
                    await self._process_signal(signal)

                # Simulate position resolution (simplified)
                await self._simulate_resolutions()

                # Periodic snapshot
                if cycle % 12 == 0:
                    snap = self.portfolio.take_snapshot()
                    logger.info(
                        "📊 Snapshot | Equity=$%.2f | PnL=$%.2f | Win Rate=%.0f%% | Trades=%d",
                        snap.total_equity,
                        snap.total_pnl,
                        snap.win_rate * 100,
                        snap.total_trades,
                    )

            except Exception:
                logger.exception("Simulation cycle error")

            await asyncio.sleep(poll_interval)
            elapsed = (datetime.now(timezone.utc) - start).total_seconds()

        self._running = False

        # Final snapshot
        self.portfolio.take_snapshot()

        summary = self._build_summary(duration_seconds)
        logger.info("✅ Simulation complete. Results: %s", summary)
        return summary

    async def _process_signal(self, signal: TradeSignal):
        """Process a trade signal through risk management and execute."""
        equity = self.portfolio.total_equity
        size_usd = equity * signal.suggested_size_fraction

        # Minimum trade size
        if size_usd < 1.0:
            return

        # Risk check
        check = self.risk_manager.check_trade(size_usd)
        if not check.allowed:
            logger.debug("Trade rejected: %s", check.reason)
            return

        # Cap at max allowed
        size_usd = min(size_usd, check.max_allowed_size)

        # Execute paper trade
        self.portfolio.open_trade(
            market_question=signal.market_question,
            condition_id=signal.condition_id,
            side=signal.side,
            entry_price=signal.entry_price,
            size_usd=size_usd,
            strategy=signal.strategy_name,
            metadata={
                "edge_pct": signal.edge_pct,
                "confidence": signal.confidence,
                "estimated_prob": signal.estimated_probability,
                **signal.metadata,
            },
        )

    async def _simulate_resolutions(self):
        """Simulate market resolution for open positions.

        In a real system, you'd check if markets have resolved.
        For simulation, we use a simplified model based on the
        strategy's estimated probability.
        """
        import random

        for trade in self.portfolio.open_positions:
            # Simulate resolution after a random delay
            age = (datetime.now(timezone.utc) - trade.timestamp).total_seconds()
            if age < 60:  # Don't resolve trades younger than 1 minute
                continue

            # Resolution probability increases with age
            resolve_chance = min(0.1, age / 6000)
            if random.random() > resolve_chance:
                continue

            # Use the strategy's estimated probability to simulate outcome
            est_prob = trade.metadata.get("estimated_prob", 0.5)
            if trade.side == Side.YES:
                won = random.random() < est_prob
            else:
                won = random.random() < (1 - est_prob)

            exit_price = 1.0 if won else 0.0
            self.portfolio.close_trade(trade.trade_id, exit_price)

    def _build_summary(self, duration_seconds: float) -> dict[str, Any]:
        """Build final simulation summary."""
        return {
            **self.portfolio.summary_dict(),
            "Strategy": self.strategy.name,
            "Duration": f"{duration_seconds / 3600:.1f} hours",
            "Signals Generated": self._signal_count,
            "Risk Status": self.risk_manager.status_dict(),
        }

    async def stop(self):
        """Stop the simulation."""
        self._running = False
        await self.polymarket.close()
        await self.binance.close()
