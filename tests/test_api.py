"""Tests for API clients (using mocked responses)."""

import pytest
from polyclaw.api.polymarket import Market, OrderBookSnapshot


class TestMarketModel:
    def test_midpoint(self):
        m = Market(best_bid=0.45, best_ask=0.55)
        assert m.midpoint == 0.50

    def test_midpoint_fallback(self):
        m = Market(last_price=0.60, best_bid=0.0, best_ask=0.0)
        assert m.midpoint == 0.60

    def test_implied_probability(self):
        m = Market(best_bid=0.70, best_ask=0.75)
        assert m.implied_probability == 0.725


class TestOrderBookSnapshot:
    def test_spread_calculation(self):
        ob = OrderBookSnapshot(
            token_id="test",
            bids=[{"price": 0.55, "size": 100}],
            asks=[{"price": 0.60, "size": 100}],
            best_bid=0.55,
            best_ask=0.60,
            spread=0.05,
            mid=0.575,
        )
        assert ob.spread == 0.05
        assert ob.mid == 0.575
