"""Risk management module for the paper trading simulator.

Implements position limits, drawdown protection, and kill switches.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta

from polyclaw.simulator.portfolio import Portfolio
from polyclaw.config import config

logger = logging.getLogger(__name__)


@dataclass
class RiskCheck:
    """Result of a risk check."""

    allowed: bool
    reason: str = ""
    max_allowed_size: float = 0.0


class RiskManager:
    """Enforces risk management rules on the paper portfolio."""

    def __init__(
        self,
        portfolio: Portfolio,
        max_position_pct: float | None = None,
        daily_loss_limit_pct: float | None = None,
        kill_switch_pct: float | None = None,
        max_open_positions: int = 10,
    ):
        self.portfolio = portfolio
        self.max_position_pct = max_position_pct or config.simulator.max_position_pct
        self.daily_loss_limit_pct = daily_loss_limit_pct or config.simulator.daily_loss_limit_pct
        self.kill_switch_pct = kill_switch_pct or config.simulator.kill_switch_pct
        self.max_open_positions = max_open_positions
        self._halted = False
        self._halt_reason = ""

    @property
    def is_halted(self) -> bool:
        return self._halted

    @property
    def halt_reason(self) -> str:
        return self._halt_reason

    def check_trade(self, proposed_size_usd: float) -> RiskCheck:
        """Check if a proposed trade passes all risk rules.

        Returns a RiskCheck indicating whether the trade is allowed.
        """
        # Kill switch check
        if self._halted:
            return RiskCheck(
                allowed=False,
                reason=f"Trading halted: {self._halt_reason}",
            )

        equity = self.portfolio.total_equity

        # Total drawdown kill switch
        drawdown_pct = self.portfolio.max_drawdown_pct / 100
        if drawdown_pct >= self.kill_switch_pct:
            self._halted = True
            self._halt_reason = (
                f"Kill switch triggered: {drawdown_pct * 100:.1f}% drawdown "
                f"exceeds {self.kill_switch_pct * 100:.1f}% limit"
            )
            logger.critical("🛑 %s", self._halt_reason)
            return RiskCheck(allowed=False, reason=self._halt_reason)

        # Daily loss limit
        daily_pnl = self._calculate_daily_pnl()
        daily_loss_pct = abs(min(0, daily_pnl)) / max(self.portfolio.starting_balance, 1)
        if daily_loss_pct >= self.daily_loss_limit_pct:
            self._halted = True
            self._halt_reason = (
                f"Daily loss limit: ${daily_pnl:.2f} "
                f"({daily_loss_pct * 100:.1f}% > {self.daily_loss_limit_pct * 100:.1f}%)"
            )
            logger.warning("⚠️ %s", self._halt_reason)
            return RiskCheck(allowed=False, reason=self._halt_reason)

        # Max position size
        max_size = equity * self.max_position_pct
        if proposed_size_usd > max_size:
            return RiskCheck(
                allowed=False,
                reason=(
                    f"Position too large: ${proposed_size_usd:.2f} > "
                    f"${max_size:.2f} ({self.max_position_pct * 100:.0f}% of equity)"
                ),
                max_allowed_size=max_size,
            )

        # Max open positions
        if len(self.portfolio.open_positions) >= self.max_open_positions:
            return RiskCheck(
                allowed=False,
                reason=f"Max open positions reached: {self.max_open_positions}",
            )

        # Sufficient cash
        if proposed_size_usd > self.portfolio.cash_balance:
            return RiskCheck(
                allowed=False,
                reason=(
                    f"Insufficient cash: need ${proposed_size_usd:.2f}, "
                    f"have ${self.portfolio.cash_balance:.2f}"
                ),
                max_allowed_size=self.portfolio.cash_balance,
            )

        return RiskCheck(
            allowed=True,
            reason="Trade approved",
            max_allowed_size=max_size,
        )

    def _calculate_daily_pnl(self) -> float:
        """Calculate PnL for trades closed today."""
        today = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
        return sum(
            t.pnl
            for t in self.portfolio.closed_trades
            if t.exit_timestamp and t.exit_timestamp >= today
        )

    def reset_halt(self):
        """Manually reset the trading halt (e.g., for a new day)."""
        self._halted = False
        self._halt_reason = ""
        logger.info("Trading halt reset.")

    def status_dict(self) -> dict:
        """Return current risk status."""
        equity = self.portfolio.total_equity
        return {
            "Halted": self._halted,
            "Halt Reason": self._halt_reason or "N/A",
            "Current Drawdown": f"{self.portfolio.max_drawdown_pct:.1f}%",
            "Kill Switch At": f"{self.kill_switch_pct * 100:.1f}%",
            "Daily PnL": f"${self._calculate_daily_pnl():.2f}",
            "Daily Loss Limit": f"{self.daily_loss_limit_pct * 100:.1f}%",
            "Max Position Size": f"${equity * self.max_position_pct:.2f}",
            "Open Positions": f"{len(self.portfolio.open_positions)}/{self.max_open_positions}",
        }
