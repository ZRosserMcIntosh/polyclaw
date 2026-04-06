"""Kelly Criterion calculator for optimal position sizing.

The Kelly Criterion determines the optimal fraction of capital to risk
on a bet given the probability of winning and the payout ratio.
This is used by the paper trading simulator for position sizing.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class KellyResult:
    """Result of a Kelly Criterion calculation."""

    full_kelly: float  # Optimal fraction (can be > 1)
    half_kelly: float  # Conservative: half Kelly
    quarter_kelly: float  # Very conservative: quarter Kelly
    edge: float  # Expected edge as percentage
    should_bet: bool  # Whether the Kelly fraction is positive
    expected_value: float  # EV per dollar risked

    def recommended_fraction(self, aggressiveness: float = 0.5) -> float:
        """Get recommended bet fraction.

        Args:
            aggressiveness: 0.0 = quarter Kelly, 0.5 = half Kelly, 1.0 = full Kelly
        """
        if not self.should_bet:
            return 0.0
        if aggressiveness <= 0.25:
            return self.quarter_kelly
        elif aggressiveness <= 0.75:
            return self.half_kelly
        return self.full_kelly

    def position_size(self, bankroll: float, aggressiveness: float = 0.5) -> float:
        """Calculate the dollar amount to wager.

        Args:
            bankroll: Total available capital.
            aggressiveness: Kelly fraction scaling (0.0–1.0).
        """
        fraction = self.recommended_fraction(aggressiveness)
        return bankroll * fraction


def kelly_criterion(
    win_probability: float,
    win_payout: float = 1.0,
    loss_amount: float = 1.0,
) -> KellyResult:
    """Calculate the Kelly Criterion for a binary outcome bet.

    Args:
        win_probability: Probability of winning (0.0 to 1.0).
        win_payout: Amount won per dollar risked if you win.
            For Polymarket: if you buy at $0.55 and it resolves to $1.00,
            win_payout = (1.00 - 0.55) / 0.55 ≈ 0.818
        loss_amount: Amount lost per dollar risked if you lose (usually 1.0).

    Returns:
        KellyResult with optimal fractions.

    Example:
        >>> # Buy YES at $0.55 when you think true prob is 70%
        >>> result = kelly_criterion(
        ...     win_probability=0.70,
        ...     win_payout=(1.0 - 0.55) / 0.55,  # ≈ 0.818
        ...     loss_amount=1.0,
        ... )
        >>> result.half_kelly
        0.195  # Risk ~19.5% of bankroll
    """
    p = max(0.0, min(1.0, win_probability))
    q = 1.0 - p
    b = win_payout

    # Kelly formula: f* = (bp - q) / b
    if b <= 0:
        return KellyResult(
            full_kelly=0.0,
            half_kelly=0.0,
            quarter_kelly=0.0,
            edge=0.0,
            should_bet=False,
            expected_value=0.0,
        )

    full = (b * p - q) / b
    edge = b * p - q  # Expected value per unit risked
    ev = p * win_payout - q * loss_amount

    should_bet = full > 0

    return KellyResult(
        full_kelly=max(0.0, full),
        half_kelly=max(0.0, full / 2),
        quarter_kelly=max(0.0, full / 4),
        edge=edge * 100,
        should_bet=should_bet,
        expected_value=ev,
    )


def kelly_for_polymarket(
    estimated_probability: float,
    market_price: float,
) -> KellyResult:
    """Convenience wrapper for Polymarket-style binary contracts.

    Args:
        estimated_probability: Your estimated true probability (0.0–1.0).
        market_price: Current market price of YES share (0.0–1.0).

    Returns:
        KellyResult for the optimal position.

    Example:
        >>> # Market says 55%, you think it's 70%
        >>> result = kelly_for_polymarket(0.70, 0.55)
        >>> result.position_size(bankroll=1000, aggressiveness=0.5)
        195.0
    """
    if market_price <= 0 or market_price >= 1:
        return KellyResult(
            full_kelly=0.0, half_kelly=0.0, quarter_kelly=0.0,
            edge=0.0, should_bet=False, expected_value=0.0,
        )

    win_payout = (1.0 - market_price) / market_price
    return kelly_criterion(
        win_probability=estimated_probability,
        win_payout=win_payout,
        loss_amount=1.0,
    )
