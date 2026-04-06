"""Tests for Kalshi client and cross-exchange comparison."""

import pytest

from polyclaw.api.kalshi import (
    KalshiBalance,
    KalshiClient,
    KalshiMarket,
    KalshiOrderBook,
    KALSHI_DEMO_URL,
    KALSHI_PROD_URL,
)
from polyclaw.analysis.compare import (
    MarketPair,
    _fuzzy_match,
    _keyword_overlap,
    match_markets,
)


class TestKalshiMarket:
    def test_yes_bid_property(self):
        m = KalshiMarket(yes_bid_dollars="0.4200")
        assert m.yes_bid == 0.42

    def test_yes_ask_property(self):
        m = KalshiMarket(yes_ask_dollars="0.5800")
        assert m.yes_ask == 0.58

    def test_spread(self):
        m = KalshiMarket(yes_bid_dollars="0.40", yes_ask_dollars="0.60")
        assert m.spread == pytest.approx(0.20)

    def test_spread_no_bids(self):
        m = KalshiMarket(yes_bid_dollars="0.0000", yes_ask_dollars="0.0000")
        assert m.spread == 0.0

    def test_midpoint(self):
        m = KalshiMarket(yes_bid_dollars="0.40", yes_ask_dollars="0.60")
        assert m.midpoint == pytest.approx(0.50)

    def test_midpoint_fallback_to_last_price(self):
        m = KalshiMarket(
            yes_bid_dollars="0.0000",
            yes_ask_dollars="0.0000",
            last_price_dollars="0.55",
        )
        assert m.midpoint == 0.55

    def test_volume(self):
        m = KalshiMarket(volume_fp="12345")
        assert m.volume == 12345.0

    def test_volume_empty(self):
        m = KalshiMarket(volume_fp="")
        assert m.volume == 0.0


class TestKalshiOrderBook:
    def test_best_yes_bid(self):
        ob = KalshiOrderBook(yes_bids=[(0.50, 100), (0.45, 200)])
        assert ob.best_yes_bid == 0.50

    def test_best_yes_bid_empty(self):
        ob = KalshiOrderBook(yes_bids=[])
        assert ob.best_yes_bid == 0.0

    def test_best_no_bid(self):
        ob = KalshiOrderBook(no_bids=[(0.60, 50)])
        assert ob.best_no_bid == 0.60


class TestKalshiBalance:
    def test_balance_conversion(self):
        b = KalshiBalance(balance_cents=5042)
        assert b.balance == 50.42

    def test_payout_conversion(self):
        b = KalshiBalance(payout_cents=1000)
        assert b.payout == 10.0


class TestKalshiClient:
    def test_demo_url(self):
        c = KalshiClient(demo=True)
        assert c.base_url == KALSHI_DEMO_URL
        assert c.demo is True
        assert c.environment == "demo"

    def test_prod_url(self):
        c = KalshiClient(demo=False)
        assert c.base_url == KALSHI_PROD_URL
        assert c.environment == "production"

    def test_not_authenticated_without_keys(self):
        c = KalshiClient(demo=True)
        assert c.is_authenticated is False


# ---- Cross-Exchange Comparison Tests ----------------------------------------

class TestFuzzyMatch:
    def test_exact_match(self):
        assert _fuzzy_match("hello world", "hello world") == 1.0

    def test_case_insensitive(self):
        assert _fuzzy_match("Hello World", "hello world") == 1.0

    def test_partial_match(self):
        score = _fuzzy_match(
            "Will Bitcoin reach $100k by end of 2025?",
            "Bitcoin price above $100,000 by December 2025",
        )
        assert 0.0 < score < 1.0

    def test_no_match(self):
        score = _fuzzy_match("cats and dogs", "quantum physics equations")
        assert score < 0.3


class TestKeywordOverlap:
    def test_identical_titles(self):
        score = _keyword_overlap("bitcoin price above 100k", "bitcoin price above 100k")
        assert score == 1.0

    def test_overlapping_titles(self):
        score = _keyword_overlap(
            "Will Bitcoin reach $100k?",
            "Bitcoin price above $100,000",
        )
        assert score > 0.0

    def test_no_overlap(self):
        score = _keyword_overlap("presidential election results", "soccer world cup winner")
        assert score == 0.0

    def test_empty_title(self):
        assert _keyword_overlap("", "some title") == 0.0


class TestMatchMarkets:
    def test_basic_match(self):
        pm = [
            {"question": "Will Bitcoin reach $100k by end of 2025?", "best_bid": 0.6, "best_ask": 0.65},
        ]
        km = [
            {"title": "Bitcoin price above $100,000 by December 2025?", "yes_bid_dollars": "0.55", "yes_ask_dollars": "0.62"},
        ]
        pairs = match_markets(pm, km, min_score=0.3)
        assert len(pairs) >= 1
        assert pairs[0].polymarket_question == pm[0]["question"]
        assert pairs[0].kalshi_title == km[0]["title"]
        assert pairs[0].match_score > 0.3

    def test_no_match(self):
        pm = [{"question": "Who will win the Super Bowl?"}]
        km = [{"title": "Average temperature in NYC tomorrow?"}]
        pairs = match_markets(pm, km, min_score=0.5)
        assert len(pairs) == 0

    def test_empty_inputs(self):
        assert match_markets([], []) == []
        assert match_markets([{"question": "test"}], []) == []
        assert match_markets([], [{"title": "test"}]) == []

    def test_price_diff_calculation(self):
        pm = [{"question": "test market", "best_bid": 0.5, "best_ask": 0.5}]
        km = [{"title": "test market", "yes_bid_dollars": "0.6", "yes_ask_dollars": "0.6"}]
        pairs = match_markets(pm, km, min_score=0.3)
        if pairs:
            assert pairs[0].price_diff > 0  # Kalshi is higher
            assert pairs[0].cheaper_on == "polymarket"


class TestMarketPair:
    def test_arb_opportunity(self):
        p = MarketPair(price_diff_pct=8.0)
        assert p.has_arb_opportunity is True

    def test_no_arb(self):
        p = MarketPair(price_diff_pct=2.0)
        assert p.has_arb_opportunity is False

    def test_cheaper_on_polymarket(self):
        p = MarketPair(price_diff=0.05)
        assert p.cheaper_on == "polymarket"

    def test_cheaper_on_kalshi(self):
        p = MarketPair(price_diff=-0.05)
        assert p.cheaper_on == "kalshi"

    def test_equal_price(self):
        p = MarketPair(price_diff=0.0)
        assert p.cheaper_on == "equal"
