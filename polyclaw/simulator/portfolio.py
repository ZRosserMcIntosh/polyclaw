"""Virtual portfolio manager for paper trading.

Tracks virtual balance, open positions, trade history,
and performance metrics without any real money.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


class Side(str, Enum):
    YES = "YES"
    NO = "NO"


class TradeStatus(str, Enum):
    OPEN = "OPEN"
    CLOSED_WIN = "CLOSED_WIN"
    CLOSED_LOSS = "CLOSED_LOSS"
    EXPIRED = "EXPIRED"


@dataclass
class PaperTrade:
    """A single simulated trade."""

    trade_id: int = 0
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    market_question: str = ""
    condition_id: str = ""
    side: Side = Side.YES
    entry_price: float = 0.0
    size_usd: float = 0.0
    shares: float = 0.0
    exit_price: float | None = None
    exit_timestamp: datetime | None = None
    status: TradeStatus = TradeStatus.OPEN
    pnl: float = 0.0
    strategy: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def is_open(self) -> bool:
        return self.status == TradeStatus.OPEN

    @property
    def return_pct(self) -> float:
        if self.size_usd <= 0:
            return 0.0
        return (self.pnl / self.size_usd) * 100


@dataclass
class PortfolioSnapshot:
    """Point-in-time portfolio state."""

    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    cash_balance: float = 0.0
    open_position_value: float = 0.0
    total_equity: float = 0.0
    total_trades: int = 0
    winning_trades: int = 0
    losing_trades: int = 0
    total_pnl: float = 0.0
    max_drawdown_pct: float = 0.0
    win_rate: float = 0.0


class Portfolio:
    """Virtual portfolio tracking all paper trades."""

    def __init__(self, starting_balance: float = 1000.0):
        self.starting_balance = starting_balance
        self.cash_balance = starting_balance
        self.trades: list[PaperTrade] = []
        self.snapshots: list[PortfolioSnapshot] = []
        self._next_trade_id = 1
        self._peak_equity = starting_balance

    @property
    def open_positions(self) -> list[PaperTrade]:
        return [t for t in self.trades if t.is_open]

    @property
    def closed_trades(self) -> list[PaperTrade]:
        return [t for t in self.trades if not t.is_open]

    @property
    def total_pnl(self) -> float:
        return sum(t.pnl for t in self.closed_trades)

    @property
    def total_equity(self) -> float:
        open_value = sum(t.size_usd for t in self.open_positions)
        return self.cash_balance + open_value

    @property
    def win_rate(self) -> float:
        closed = self.closed_trades
        if not closed:
            return 0.0
        wins = sum(1 for t in closed if t.status == TradeStatus.CLOSED_WIN)
        return wins / len(closed)

    @property
    def max_drawdown_pct(self) -> float:
        if self._peak_equity <= 0:
            return 0.0
        current = self.total_equity
        if current > self._peak_equity:
            self._peak_equity = current
        drawdown = (self._peak_equity - current) / self._peak_equity
        return drawdown * 100

    @property
    def return_pct(self) -> float:
        if self.starting_balance <= 0:
            return 0.0
        return ((self.total_equity - self.starting_balance) / self.starting_balance) * 100

    def open_trade(
        self,
        *,
        market_question: str,
        condition_id: str = "",
        side: Side,
        entry_price: float,
        size_usd: float,
        strategy: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> PaperTrade | None:
        """Open a new paper trade.

        Returns None if insufficient balance.
        """
        if size_usd > self.cash_balance:
            logger.warning(
                "Insufficient balance: need $%.2f, have $%.2f",
                size_usd, self.cash_balance,
            )
            return None

        if entry_price <= 0 or entry_price >= 1:
            logger.warning("Invalid entry price: %.4f (must be between 0 and 1)", entry_price)
            return None

        shares = size_usd / entry_price

        trade = PaperTrade(
            trade_id=self._next_trade_id,
            market_question=market_question,
            condition_id=condition_id,
            side=side,
            entry_price=entry_price,
            size_usd=size_usd,
            shares=shares,
            strategy=strategy,
            metadata=metadata or {},
        )

        self._next_trade_id += 1
        self.cash_balance -= size_usd
        self.trades.append(trade)

        logger.info(
            "📝 PAPER TRADE #%d: %s %s @ $%.4f ($%.2f) | %s",
            trade.trade_id, side.value, market_question[:50],
            entry_price, size_usd, strategy,
        )

        return trade

    def close_trade(
        self,
        trade_id: int,
        exit_price: float,
        *,
        resolved: bool = True,
    ) -> PaperTrade | None:
        """Close an open paper trade.

        Args:
            trade_id: The trade to close.
            exit_price: Settlement price (1.0 for win, 0.0 for loss,
                        or intermediate for early exit).
            resolved: Whether the market has resolved (vs. early exit).
        """
        trade = None
        for t in self.trades:
            if t.trade_id == trade_id and t.is_open:
                trade = t
                break

        if trade is None:
            logger.warning("Trade #%d not found or already closed", trade_id)
            return None

        trade.exit_price = exit_price
        trade.exit_timestamp = datetime.now(timezone.utc)

        # Calculate PnL
        exit_value = trade.shares * exit_price
        trade.pnl = exit_value - trade.size_usd

        if trade.pnl > 0:
            trade.status = TradeStatus.CLOSED_WIN
        else:
            trade.status = TradeStatus.CLOSED_LOSS

        # Return funds to cash
        self.cash_balance += exit_value

        # Update peak equity
        if self.total_equity > self._peak_equity:
            self._peak_equity = self.total_equity

        logger.info(
            "%s PAPER TRADE #%d closed: PnL=$%.2f (%.1f%%) | Balance=$%.2f",
            "✅" if trade.pnl > 0 else "❌",
            trade.trade_id, trade.pnl, trade.return_pct, self.total_equity,
        )

        return trade

    def take_snapshot(self) -> PortfolioSnapshot:
        """Record current portfolio state."""
        closed = self.closed_trades
        wins = sum(1 for t in closed if t.status == TradeStatus.CLOSED_WIN)
        losses = sum(1 for t in closed if t.status == TradeStatus.CLOSED_LOSS)

        snapshot = PortfolioSnapshot(
            cash_balance=self.cash_balance,
            open_position_value=sum(t.size_usd for t in self.open_positions),
            total_equity=self.total_equity,
            total_trades=len(closed),
            winning_trades=wins,
            losing_trades=losses,
            total_pnl=self.total_pnl,
            max_drawdown_pct=self.max_drawdown_pct,
            win_rate=self.win_rate,
        )
        self.snapshots.append(snapshot)
        return snapshot

    def summary_dict(self) -> dict[str, Any]:
        """Return a summary dictionary for display."""
        return {
            "Starting Balance": f"${self.starting_balance:,.2f}",
            "Current Equity": f"${self.total_equity:,.2f}",
            "Cash Balance": f"${self.cash_balance:,.2f}",
            "Total PnL": f"${self.total_pnl:,.2f}",
            "Return": f"{self.return_pct:+.1f}%",
            "Total Trades": len(self.closed_trades),
            "Open Positions": len(self.open_positions),
            "Win Rate": f"{self.win_rate * 100:.1f}%",
            "Max Drawdown": f"{self.max_drawdown_pct:.1f}%",
        }
