"""Tests for the Kelly Criterion calculator and portfolio management."""

from polyclaw.analysis.kelly import kelly_criterion, kelly_for_polymarket, KellyResult
from polyclaw.simulator.portfolio import Portfolio, Side, TradeStatus
from polyclaw.simulator.risk import RiskManager


class TestKellyCriterion:
    def test_positive_edge(self):
        """When you have an edge, Kelly fraction should be positive."""
        result = kelly_criterion(win_probability=0.6, win_payout=1.0, loss_amount=1.0)
        assert result.should_bet is True
        assert result.full_kelly > 0
        assert result.half_kelly == result.full_kelly / 2

    def test_no_edge(self):
        """Fair coin flip with even payout → zero Kelly."""
        result = kelly_criterion(win_probability=0.5, win_payout=1.0)
        assert result.full_kelly == 0.0
        assert result.should_bet is False

    def test_negative_edge(self):
        """When the odds are against you, Kelly says don't bet."""
        result = kelly_criterion(win_probability=0.3, win_payout=1.0)
        assert result.should_bet is False
        assert result.full_kelly == 0.0

    def test_polymarket_convenience(self):
        """Test the Polymarket-specific wrapper."""
        result = kelly_for_polymarket(
            estimated_probability=0.70,
            market_price=0.55,
        )
        assert result.should_bet is True
        assert result.full_kelly > 0
        assert result.position_size(bankroll=1000, aggressiveness=0.5) > 0

    def test_extreme_edge(self):
        """Very high probability → large Kelly fraction."""
        result = kelly_for_polymarket(
            estimated_probability=0.95,
            market_price=0.50,
        )
        assert result.full_kelly > 0.5

    def test_invalid_market_price(self):
        """Edge cases for invalid prices."""
        result = kelly_for_polymarket(0.5, 0.0)
        assert result.should_bet is False
        result = kelly_for_polymarket(0.5, 1.0)
        assert result.should_bet is False


class TestPortfolio:
    def test_initial_state(self):
        p = Portfolio(starting_balance=1000)
        assert p.cash_balance == 1000
        assert p.total_equity == 1000
        assert p.total_pnl == 0
        assert len(p.open_positions) == 0

    def test_open_trade(self):
        p = Portfolio(starting_balance=1000)
        trade = p.open_trade(
            market_question="Will BTC be above 70k?",
            side=Side.YES,
            entry_price=0.55,
            size_usd=100,
            strategy="test",
        )
        assert trade is not None
        assert trade.trade_id == 1
        assert p.cash_balance == 900
        assert len(p.open_positions) == 1

    def test_close_trade_win(self):
        p = Portfolio(starting_balance=1000)
        trade = p.open_trade(
            market_question="Test",
            side=Side.YES,
            entry_price=0.50,
            size_usd=100,
            strategy="test",
        )
        # 100 USD at $0.50 = 200 shares. Win → 200 × $1.00 = $200
        p.close_trade(trade.trade_id, exit_price=1.0)
        assert trade.status == TradeStatus.CLOSED_WIN
        assert trade.pnl == 100.0  # 200 - 100
        assert p.cash_balance == 1100  # 900 + 200
        assert p.total_equity == 1100

    def test_close_trade_loss(self):
        p = Portfolio(starting_balance=1000)
        trade = p.open_trade(
            market_question="Test",
            side=Side.YES,
            entry_price=0.50,
            size_usd=100,
            strategy="test",
        )
        # Loss → 200 shares × $0.00 = $0
        p.close_trade(trade.trade_id, exit_price=0.0)
        assert trade.status == TradeStatus.CLOSED_LOSS
        assert trade.pnl == -100.0
        assert p.cash_balance == 900
        assert p.total_equity == 900

    def test_win_rate(self):
        p = Portfolio(starting_balance=10000)
        for i in range(10):
            t = p.open_trade(
                market_question=f"Q{i}",
                side=Side.YES,
                entry_price=0.50,
                size_usd=100,
                strategy="test",
            )
            # 7 wins, 3 losses
            p.close_trade(t.trade_id, exit_price=1.0 if i < 7 else 0.0)
        assert p.win_rate == 0.7

    def test_insufficient_balance(self):
        p = Portfolio(starting_balance=50)
        trade = p.open_trade(
            market_question="Too expensive",
            side=Side.YES,
            entry_price=0.50,
            size_usd=100,
            strategy="test",
        )
        assert trade is None
        assert p.cash_balance == 50

    def test_snapshot(self):
        p = Portfolio(starting_balance=1000)
        snap = p.take_snapshot()
        assert snap.total_equity == 1000
        assert snap.total_trades == 0
        assert len(p.snapshots) == 1


class TestRiskManager:
    def test_trade_allowed(self):
        p = Portfolio(starting_balance=1000)
        rm = RiskManager(p, max_position_pct=0.10)
        check = rm.check_trade(50)
        assert check.allowed is True

    def test_position_too_large(self):
        p = Portfolio(starting_balance=1000)
        rm = RiskManager(p, max_position_pct=0.10)
        check = rm.check_trade(200)  # 20% > 10% limit
        assert check.allowed is False
        assert "too large" in check.reason.lower()

    def test_max_open_positions(self):
        p = Portfolio(starting_balance=10000)
        rm = RiskManager(p, max_position_pct=0.10, max_open_positions=2)

        p.open_trade(market_question="Q1", side=Side.YES, entry_price=0.5, size_usd=50, strategy="t")
        p.open_trade(market_question="Q2", side=Side.YES, entry_price=0.5, size_usd=50, strategy="t")

        check = rm.check_trade(50)
        assert check.allowed is False
        assert "max open positions" in check.reason.lower()

    def test_insufficient_cash(self):
        p = Portfolio(starting_balance=100)
        rm = RiskManager(p, max_position_pct=1.0)  # no position limit
        p.open_trade(market_question="Q1", side=Side.YES, entry_price=0.5, size_usd=80, strategy="t")
        check = rm.check_trade(50)  # only $20 left
        assert check.allowed is False

    def test_kill_switch(self):
        p = Portfolio(starting_balance=1000)
        rm = RiskManager(p, max_position_pct=1.0, kill_switch_pct=0.40)

        # Simulate a big loss
        t = p.open_trade(market_question="Bad trade", side=Side.YES, entry_price=0.5, size_usd=500, strategy="t")
        p.close_trade(t.trade_id, exit_price=0.0)
        # Now equity is $500, which is 50% drawdown from peak of $1000

        check = rm.check_trade(10)
        assert check.allowed is False
        assert rm.is_halted is True
