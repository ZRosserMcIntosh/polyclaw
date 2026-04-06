"""Paper trading strategies.

Each strategy consumes market data and produces trade signals
that the simulation engine executes against the virtual portfolio.
"""

from __future__ import annotations

import logging
import random
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime, timezone

from polyclaw.analysis.kelly import kelly_for_polymarket
from polyclaw.api.binance import PriceTick
from polyclaw.api.polymarket import Market
from polyclaw.simulator.portfolio import Side

logger = logging.getLogger(__name__)


@dataclass
class TradeSignal:
    """A signal produced by a strategy."""

    timestamp: datetime
    market_question: str
    condition_id: str
    side: Side
    entry_price: float
    estimated_probability: float
    edge_pct: float
    suggested_size_fraction: float  # Kelly-derived fraction of bankroll
    strategy_name: str
    confidence: float = 0.0  # 0.0–1.0
    metadata: dict = None

    def __post_init__(self):
        self.metadata = self.metadata or {}


class Strategy(ABC):
    """Base class for paper trading strategies."""

    name: str = "base"

    @abstractmethod
    async def evaluate(
        self,
        markets: list[Market],
        price_ticks: dict[str, PriceTick],
    ) -> list[TradeSignal]:
        """Evaluate current market state and return trade signals."""
        ...


class LatencyArbStrategy(Strategy):
    """Simulated latency arbitrage strategy.

    Detects when CEX price moves suggest Polymarket odds are stale,
    and generates signals for the expected correct direction.

    NOTE: This is a simulation — in reality, this strategy requires
    sub-second execution that a Python script cannot achieve competitively.
    The simulation helps measure how often opportunities appear and
    what theoretical returns would look like.
    """

    name = "latency-arb"

    def __init__(
        self,
        edge_threshold_pct: float = 3.0,
        kelly_aggressiveness: float = 0.5,
    ):
        self.edge_threshold = edge_threshold_pct / 100.0
        self.kelly_aggressiveness = kelly_aggressiveness
        self._price_baselines: dict[str, float] = {}

    async def evaluate(
        self,
        markets: list[Market],
        price_ticks: dict[str, PriceTick],
    ) -> list[TradeSignal]:
        signals = []

        for symbol, tick in price_ticks.items():
            if symbol not in self._price_baselines:
                self._price_baselines[symbol] = tick.price
                continue

            baseline = self._price_baselines[symbol]
            change_pct = (tick.price - baseline) / baseline
            self._price_baselines[symbol] = tick.price

            # Only significant moves
            if abs(change_pct) < 0.001:
                continue

            # Check each crypto market
            for market in markets:
                q = market.question.lower()
                is_crypto = any(
                    kw in q
                    for kw in ["bitcoin", "btc", "ethereum", "eth", "crypto"]
                )
                if not is_crypto or not market.active:
                    continue

                current_prob = market.implied_probability
                if current_prob <= 0.05 or current_prob >= 0.95:
                    continue

                # Estimate fair probability shift
                if "above" in q or "higher" in q or "up" in q:
                    fair_prob = min(0.95, max(0.05, current_prob + change_pct * 2))
                elif "below" in q or "lower" in q or "down" in q:
                    fair_prob = min(0.95, max(0.05, current_prob - change_pct * 2))
                else:
                    continue

                edge = abs(fair_prob - current_prob)
                if edge < self.edge_threshold:
                    continue

                # Determine direction
                if fair_prob > current_prob:
                    side = Side.YES
                    entry_price = current_prob
                else:
                    side = Side.NO
                    entry_price = 1.0 - current_prob

                # Kelly sizing
                kelly = kelly_for_polymarket(fair_prob if side == Side.YES else 1 - fair_prob, entry_price)

                if kelly.should_bet:
                    signals.append(
                        TradeSignal(
                            timestamp=datetime.now(timezone.utc),
                            market_question=market.question,
                            condition_id=market.condition_id,
                            side=side,
                            entry_price=entry_price,
                            estimated_probability=fair_prob,
                            edge_pct=edge * 100,
                            suggested_size_fraction=kelly.recommended_fraction(
                                self.kelly_aggressiveness
                            ),
                            strategy_name=self.name,
                            confidence=min(edge / 0.10, 1.0),
                            metadata={
                                "symbol": symbol,
                                "cex_price": tick.price,
                                "price_change_pct": change_pct * 100,
                                "kelly_full": kelly.full_kelly,
                            },
                        )
                    )

        return signals


class MeanReversionStrategy(Strategy):
    """Mean reversion strategy for markets with wide spreads.

    Identifies markets where the odds have moved far from their
    recent average and bets on reversion.
    """

    name = "mean-reversion"

    def __init__(
        self,
        lookback_period: int = 20,
        deviation_threshold: float = 0.10,
        kelly_aggressiveness: float = 0.25,
    ):
        self.lookback = lookback_period
        self.deviation_threshold = deviation_threshold
        self.kelly_aggressiveness = kelly_aggressiveness
        self._price_history: dict[str, list[float]] = {}

    async def evaluate(
        self,
        markets: list[Market],
        price_ticks: dict[str, PriceTick],
    ) -> list[TradeSignal]:
        signals = []

        for market in markets:
            if not market.active or market.closed:
                continue

            cid = market.condition_id
            price = market.implied_probability
            if price <= 0.05 or price >= 0.95:
                continue

            # Track price history
            if cid not in self._price_history:
                self._price_history[cid] = []
            self._price_history[cid].append(price)

            # Keep only lookback window
            if len(self._price_history[cid]) > self.lookback:
                self._price_history[cid] = self._price_history[cid][-self.lookback:]

            history = self._price_history[cid]
            if len(history) < self.lookback // 2:
                continue

            mean_price = sum(history) / len(history)
            deviation = price - mean_price

            if abs(deviation) < self.deviation_threshold:
                continue

            # Bet on reversion to mean
            if deviation > 0:
                # Price is above mean → expect it to come down → buy NO
                side = Side.NO
                entry_price = 1.0 - price
                fair_prob = 1.0 - mean_price
            else:
                # Price is below mean → expect it to go up → buy YES
                side = Side.YES
                entry_price = price
                fair_prob = mean_price

            kelly = kelly_for_polymarket(fair_prob, entry_price)
            if kelly.should_bet:
                signals.append(
                    TradeSignal(
                        timestamp=datetime.now(timezone.utc),
                        market_question=market.question,
                        condition_id=market.condition_id,
                        side=side,
                        entry_price=entry_price,
                        estimated_probability=fair_prob,
                        edge_pct=abs(deviation) * 100,
                        suggested_size_fraction=kelly.recommended_fraction(
                            self.kelly_aggressiveness
                        ),
                        strategy_name=self.name,
                        confidence=min(abs(deviation) / 0.20, 1.0),
                        metadata={
                            "mean_price": mean_price,
                            "deviation": deviation,
                            "history_length": len(history),
                        },
                    )
                )

        return signals


class RandomStrategy(Strategy):
    """Random strategy — used as a benchmark/control.

    Makes random trades to establish a baseline for comparison.
    Expected return: negative (due to spreads).
    """

    name = "random-baseline"

    def __init__(self, trade_probability: float = 0.05):
        self.trade_probability = trade_probability

    async def evaluate(
        self,
        markets: list[Market],
        price_ticks: dict[str, PriceTick],
    ) -> list[TradeSignal]:
        signals = []

        for market in markets:
            if not market.active or market.closed:
                continue
            if market.implied_probability <= 0.1 or market.implied_probability >= 0.9:
                continue

            if random.random() > self.trade_probability:
                continue

            side = random.choice([Side.YES, Side.NO])
            entry_price = market.implied_probability if side == Side.YES else (1.0 - market.implied_probability)

            signals.append(
                TradeSignal(
                    timestamp=datetime.now(timezone.utc),
                    market_question=market.question,
                    condition_id=market.condition_id,
                    side=side,
                    entry_price=max(0.05, min(0.95, entry_price)),
                    estimated_probability=0.5,
                    edge_pct=0.0,
                    suggested_size_fraction=0.02,
                    strategy_name=self.name,
                    confidence=0.0,
                )
            )

        return signals


# Strategy registry
STRATEGIES: dict[str, type[Strategy]] = {
    "latency-arb": LatencyArbStrategy,
    "mean-reversion": MeanReversionStrategy,
    "random-baseline": RandomStrategy,
}


def get_strategy(name: str, **kwargs) -> Strategy:
    """Get a strategy instance by name."""
    cls = STRATEGIES.get(name)
    if cls is None:
        raise ValueError(f"Unknown strategy: {name}. Available: {list(STRATEGIES.keys())}")
    return cls(**kwargs)
