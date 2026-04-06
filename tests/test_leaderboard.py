"""Tests for leaderboard, subgraph client, and copy-trade monitor."""

import asyncio
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest

from polyclaw.api.subgraph import (
    KNOWN_CONTRACTS,
    Leaderboard,
    SubgraphClient,
    TraderFill,
    TraderProfile,
    build_leaderboard,
)
from polyclaw.analysis.leaderboard import (
    EnrichedProfile,
    LeaderboardBuilder,
    _assign_tier,
    _score_trader,
)
from polyclaw.analysis.copytrade import CopyTradeMonitor, CopyEvent, TrackedWallet


# ---- TraderFill / TraderProfile -------------------------------------------

class TestTraderFill:
    def test_dt_property(self):
        fill = TraderFill(
            maker="0xaaa",
            taker="0xbbb",
            maker_amount=100.0,
            taker_amount=50.0,
            timestamp=1700000000,
        )
        assert isinstance(fill.dt, datetime)
        assert fill.dt.tzinfo == timezone.utc

    def test_basic_fields(self):
        fill = TraderFill(
            maker="0xmaker",
            taker="0xtaker",
            maker_amount=250.50,
            taker_amount=125.25,
            timestamp=1700000000,
            tx_hash="0xhash",
        )
        assert fill.maker == "0xmaker"
        assert fill.taker_amount == 125.25


class TestTraderProfile:
    def test_bot_detection_high_freq_maker(self):
        """High freq + high maker ratio = likely bot."""
        p = TraderProfile(
            address="0xbot",
            trade_count=500,
            trades_per_day=50,
            maker_ratio=0.85,
        )
        assert p.is_likely_bot is True

    def test_human_detection_low_freq(self):
        """Low frequency = likely human."""
        p = TraderProfile(
            address="0xhuman",
            trade_count=10,
            trades_per_day=2,
            maker_ratio=0.3,
        )
        assert p.is_likely_bot is False

    def test_profile_url(self):
        p = TraderProfile(address="0xabc123")
        assert p.profile_url == "https://polymarket.com/profile/0xabc123"


# ---- build_leaderboard -----------------------------------------------------

class TestBuildLeaderboard:
    def _make_fills(self, n: int = 100) -> list[TraderFill]:
        fills = []
        for i in range(n):
            fills.append(
                TraderFill(
                    maker=f"0xmaker{i % 5:02d}",
                    taker=f"0xtaker{i % 8:02d}",
                    maker_amount=float(100 + i * 10),
                    taker_amount=float(50 + i * 5),
                    timestamp=1700000000 + i * 60,
                )
            )
        return fills

    def test_builds_leaderboard(self):
        fills = self._make_fills(50)
        board = build_leaderboard(fills, top_n=10)
        assert isinstance(board, Leaderboard)
        assert board.total_fills_analyzed == 50
        assert len(board.traders) <= 10
        assert board.time_window_hours > 0

    def test_filters_known_contracts(self):
        """Known contract addresses should not appear as traders."""
        contract = list(KNOWN_CONTRACTS)[0]
        fills = [
            TraderFill(
                maker=contract,
                taker="0xreal_trader",
                maker_amount=1000,
                taker_amount=500,
                timestamp=1700000000,
            ),
        ]
        board = build_leaderboard(fills, top_n=10)
        addresses = {t.address for t in board.traders}
        assert contract not in addresses
        assert "0xreal_trader" in addresses

    def test_volume_sorting(self):
        """Leaderboard should be sorted by volume descending."""
        fills = self._make_fills(100)
        board = build_leaderboard(fills, top_n=50)
        for i in range(len(board.traders) - 1):
            assert board.traders[i].total_volume_usd >= board.traders[i + 1].total_volume_usd

    def test_empty_fills(self):
        board = build_leaderboard([], top_n=10)
        assert board.total_fills_analyzed == 0
        assert len(board.traders) == 0


# ---- Scoring and Tiers -----------------------------------------------------

class TestScoring:
    def test_score_positive(self):
        p = TraderProfile(
            address="0xtest",
            trade_count=50,
            total_volume_usd=5000,
            maker_ratio=0.5,
            trades_per_day=5,
            avg_trade_size=100,
        )
        score = _score_trader(p)
        assert score > 0

    def test_bot_penalty(self):
        """Bots should get penalized."""
        human = TraderProfile(
            address="0xhuman",
            trade_count=50,
            total_volume_usd=5000,
            maker_ratio=0.3,
            trades_per_day=5,
            avg_trade_size=100,
        )
        bot = TraderProfile(
            address="0xbot",
            trade_count=500,
            total_volume_usd=5000,
            maker_ratio=0.8,
            trades_per_day=50,
            avg_trade_size=100,
        )
        assert _score_trader(human) > _score_trader(bot)

    def test_whale_tier(self):
        ep = EnrichedProfile(address="0x", total_volume_usd=50_000)
        assert _assign_tier(ep) == "whale"

    def test_shark_tier(self):
        ep = EnrichedProfile(address="0x", total_volume_usd=5_000)
        assert _assign_tier(ep) == "shark"

    def test_dolphin_tier(self):
        ep = EnrichedProfile(address="0x", total_volume_usd=500)
        assert _assign_tier(ep) == "dolphin"

    def test_fish_tier(self):
        ep = EnrichedProfile(address="0x", total_volume_usd=10)
        assert _assign_tier(ep) == "fish"


class TestEnrichedProfile:
    def test_from_base(self):
        base = TraderProfile(
            address="0xtest",
            trade_count=20,
            total_volume_usd=3000,
            maker_ratio=0.4,
        )
        ep = EnrichedProfile.from_base(base, score=42.5)
        assert ep.address == "0xtest"
        assert ep.trade_count == 20
        assert ep.score == 42.5


# ---- CopyTradeMonitor ------------------------------------------------------

class TestCopyTradeMonitor:
    def test_track_wallet(self):
        monitor = CopyTradeMonitor()
        w = monitor.track("0xABC123", label="Whale")
        assert w.address == "0xabc123"  # lowercased
        assert w.label == "Whale"
        assert len(monitor.tracked_wallets) == 1

    def test_track_deduplicates(self):
        monitor = CopyTradeMonitor()
        monitor.track("0xABC")
        monitor.track("0xabc")  # same address different case
        assert len(monitor.tracked_wallets) == 1

    def test_untrack(self):
        monitor = CopyTradeMonitor()
        monitor.track("0xABC")
        monitor.untrack("0xabc")
        assert len(monitor.tracked_wallets) == 0

    def test_match_fills_maker(self):
        monitor = CopyTradeMonitor()
        monitor.track("0xAAA")

        fills = [
            TraderFill(
                maker="0xaaa",
                taker="0xbbb",
                maker_amount=100,
                taker_amount=50,
                timestamp=1700000000,
            ),
        ]
        events = monitor._match_fills(fills)
        assert len(events) == 1
        assert events[0].role == "maker"
        assert events[0].amount_usd == 100

    def test_match_fills_taker(self):
        monitor = CopyTradeMonitor()
        monitor.track("0xBBB")

        fills = [
            TraderFill(
                maker="0xaaa",
                taker="0xbbb",
                maker_amount=100,
                taker_amount=50,
                timestamp=1700000000,
            ),
        ]
        events = monitor._match_fills(fills)
        assert len(events) == 1
        assert events[0].role == "taker"
        assert events[0].amount_usd == 50

    def test_match_fills_both_tracked(self):
        """If both maker and taker are tracked, both should generate events."""
        monitor = CopyTradeMonitor()
        monitor.track("0xAAA")
        monitor.track("0xBBB")

        fills = [
            TraderFill(
                maker="0xaaa",
                taker="0xbbb",
                maker_amount=100,
                taker_amount=50,
                timestamp=1700000000,
            ),
        ]
        events = monitor._match_fills(fills)
        assert len(events) == 2

    def test_no_match_untracked(self):
        monitor = CopyTradeMonitor()
        monitor.track("0xCCC")

        fills = [
            TraderFill(
                maker="0xaaa",
                taker="0xbbb",
                maker_amount=100,
                taker_amount=50,
                timestamp=1700000000,
            ),
        ]
        events = monitor._match_fills(fills)
        assert len(events) == 0

    def test_run_requires_tracked_wallets(self):
        monitor = CopyTradeMonitor()
        with pytest.raises(ValueError, match="No wallets tracked"):
            asyncio.run(monitor.run(duration_seconds=1))
