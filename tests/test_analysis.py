"""Tests for market analysis and Kelly criterion."""

import pytest
from polyclaw.analysis.kelly import kelly_criterion, kelly_for_polymarket


class TestKellyEdgeCases:
    def test_zero_payout(self):
        result = kelly_criterion(win_probability=0.6, win_payout=0.0)
        assert result.should_bet is False

    def test_certain_win(self):
        result = kelly_criterion(win_probability=1.0, win_payout=1.0)
        assert result.should_bet is True
        assert result.full_kelly == 1.0

    def test_certain_loss(self):
        result = kelly_criterion(win_probability=0.0, win_payout=1.0)
        assert result.should_bet is False

    def test_clamps_probability(self):
        """Probabilities outside [0,1] should be clamped."""
        result = kelly_criterion(win_probability=1.5, win_payout=1.0)
        assert result.full_kelly == 1.0

    def test_polymarket_no_edge(self):
        """Buying at fair value → no edge."""
        result = kelly_for_polymarket(
            estimated_probability=0.50,
            market_price=0.50,
        )
        assert result.full_kelly == 0.0
        assert result.should_bet is False

    def test_polymarket_small_edge(self):
        """Small edge → small Kelly fraction."""
        result = kelly_for_polymarket(
            estimated_probability=0.55,
            market_price=0.50,
        )
        assert result.should_bet is True
        assert 0 < result.full_kelly < 0.2
