"""Cross-exchange comparison — Polymarket vs Kalshi side-by-side analysis.

Finds overlapping markets between exchanges, compares pricing,
liquidity, and identifies cross-platform arbitrage opportunities.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from difflib import SequenceMatcher

logger = logging.getLogger(__name__)


@dataclass
class MarketPair:
    """A matched pair of markets across Polymarket and Kalshi."""

    polymarket_question: str = ""
    kalshi_title: str = ""
    polymarket_yes_price: float = 0.0
    kalshi_yes_price: float = 0.0
    price_diff: float = 0.0  # kalshi - polymarket
    price_diff_pct: float = 0.0
    polymarket_volume: float = 0.0
    kalshi_volume: float = 0.0
    polymarket_spread: float = 0.0
    kalshi_spread: float = 0.0
    polymarket_liquidity: float = 0.0
    kalshi_liquidity: float = 0.0
    match_score: float = 0.0  # How confident we are these are the same market
    category: str = ""

    @property
    def has_arb_opportunity(self) -> bool:
        """Is there a potential cross-exchange arb (>5% price diff)?"""
        return abs(self.price_diff_pct) > 5.0

    @property
    def cheaper_on(self) -> str:
        if self.price_diff > 0:
            return "polymarket"
        elif self.price_diff < 0:
            return "kalshi"
        return "equal"


@dataclass
class ExchangeComparison:
    """Side-by-side comparison of two prediction market exchanges."""

    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    matched_pairs: list[MarketPair] = field(default_factory=list)
    polymarket_only: int = 0
    kalshi_only: int = 0
    total_polymarket: int = 0
    total_kalshi: int = 0

    # Aggregate stats
    avg_price_diff: float = 0.0
    avg_polymarket_spread: float = 0.0
    avg_kalshi_spread: float = 0.0
    total_polymarket_volume: float = 0.0
    total_kalshi_volume: float = 0.0
    arb_opportunities: int = 0

    @property
    def match_rate(self) -> float:
        total = self.total_polymarket + self.total_kalshi
        if total == 0:
            return 0.0
        return len(self.matched_pairs) * 2 / total


def _fuzzy_match(s1: str, s2: str) -> float:
    """Fuzzy match score between two market titles (0-1)."""
    # Normalize
    s1 = s1.lower().strip()
    s2 = s2.lower().strip()

    # Exact match
    if s1 == s2:
        return 1.0

    # SequenceMatcher
    return SequenceMatcher(None, s1, s2).ratio()


def _extract_keywords(title: str) -> set[str]:
    """Extract meaningful keywords from a market title."""
    # Common stop words to skip
    stop = {
        "will", "the", "a", "an", "in", "on", "at", "to", "of", "be",
        "is", "by", "for", "or", "and", "this", "that", "it", "with",
        "before", "after", "above", "below", "over", "under", "between",
    }
    words = set()
    for w in title.lower().split():
        w = w.strip("?.,!:;\"'()[]{}$%")
        if len(w) > 2 and w not in stop:
            words.add(w)
    return words


def _keyword_overlap(title1: str, title2: str) -> float:
    """Keyword-based overlap score (0-1)."""
    kw1 = _extract_keywords(title1)
    kw2 = _extract_keywords(title2)
    if not kw1 or not kw2:
        return 0.0
    intersection = kw1 & kw2
    union = kw1 | kw2
    return len(intersection) / len(union)  # Jaccard similarity


def match_markets(
    polymarket_markets: list[dict],
    kalshi_markets: list[dict],
    *,
    min_score: float = 0.45,
) -> list[MarketPair]:
    """Find matching markets across Polymarket and Kalshi.

    Uses a combination of fuzzy string matching and keyword overlap.

    Args:
        polymarket_markets: List of dicts with 'question', 'best_bid', 'best_ask', etc.
        kalshi_markets: List of KalshiMarket-like dicts.
        min_score: Minimum match confidence to include.

    Returns:
        List of matched MarketPairs, sorted by match confidence.
    """
    pairs: list[MarketPair] = []
    used_kalshi: set[int] = set()

    for pm in polymarket_markets:
        pm_q = pm.get("question", "")
        if not pm_q:
            continue

        best_match: MarketPair | None = None
        best_score = 0.0
        best_idx = -1

        for j, km in enumerate(kalshi_markets):
            if j in used_kalshi:
                continue

            km_title = km.get("title", "")
            if not km_title:
                continue

            # Combined score: 60% fuzzy, 40% keyword overlap
            fuzzy = _fuzzy_match(pm_q, km_title)
            keyword = _keyword_overlap(pm_q, km_title)
            score = 0.6 * fuzzy + 0.4 * keyword

            if score > best_score and score >= min_score:
                best_score = score
                best_idx = j

                pm_bid = float(pm.get("best_bid", 0) or 0)
                pm_ask = float(pm.get("best_ask", 0) or 0)
                pm_mid = (pm_bid + pm_ask) / 2 if pm_bid and pm_ask else pm_bid or pm_ask

                km_bid = float(km.get("yes_bid_dollars", "0") or "0")
                km_ask = float(km.get("yes_ask_dollars", "0") or "0")
                km_mid = (km_bid + km_ask) / 2 if km_bid and km_ask else km_bid or km_ask

                price_diff = km_mid - pm_mid
                avg_price = (km_mid + pm_mid) / 2 if (km_mid + pm_mid) else 1.0

                best_match = MarketPair(
                    polymarket_question=pm_q,
                    kalshi_title=km_title,
                    polymarket_yes_price=pm_mid,
                    kalshi_yes_price=km_mid,
                    price_diff=price_diff,
                    price_diff_pct=(price_diff / avg_price * 100) if avg_price else 0,
                    polymarket_volume=float(pm.get("volume_24h", 0) or 0),
                    kalshi_volume=float(km.get("volume_fp", "0") or "0"),
                    polymarket_spread=float(pm.get("spread", 0) or 0),
                    kalshi_spread=km_ask - km_bid if km_ask and km_bid else 0,
                    polymarket_liquidity=float(pm.get("liquidity", 0) or 0),
                    kalshi_liquidity=float(km.get("liquidity_dollars", "0") or "0"),
                    match_score=best_score,
                    category=km.get("category", pm.get("category", "")),
                )

        if best_match and best_idx >= 0:
            used_kalshi.add(best_idx)
            pairs.append(best_match)

    pairs.sort(key=lambda p: p.match_score, reverse=True)
    return pairs


class CrossExchangeAnalyzer:
    """Compares Polymarket and Kalshi markets side-by-side."""

    def __init__(self, *, kalshi_demo: bool = False):
        self._pm_client = None
        self._kalshi_client = None
        self._kalshi_demo = kalshi_demo

    async def _get_pm_client(self):
        if self._pm_client is None:
            from polyclaw.api.polymarket import PolymarketClient
            self._pm_client = PolymarketClient()
        return self._pm_client

    async def _get_kalshi_client(self):
        if self._kalshi_client is None:
            from polyclaw.api.kalshi import KalshiClient
            self._kalshi_client = KalshiClient(demo=self._kalshi_demo)
        return self._kalshi_client

    async def compare(self, *, max_markets: int = 200) -> ExchangeComparison:
        """Run a full cross-exchange comparison."""
        pm_client = await self._get_pm_client()
        kalshi_client = await self._get_kalshi_client()

        # Fetch from both
        logger.info("Fetching Polymarket markets...")
        pm_raw = await pm_client.get_markets(limit=max_markets, active=True)
        pm_markets = [
            {
                "question": m.question,
                "best_bid": m.best_bid,
                "best_ask": m.best_ask,
                "spread": m.spread,
                "volume_24h": m.volume_24h,
                "liquidity": m.liquidity,
                "category": getattr(m, "category", ""),
            }
            for m in pm_raw
        ]

        logger.info("Fetching Kalshi markets...")
        kalshi_raw = await kalshi_client.get_all_markets(status="open")
        kalshi_dicts = [m.model_dump() for m in kalshi_raw]

        logger.info(
            "Matching %d Polymarket vs %d Kalshi markets...",
            len(pm_markets),
            len(kalshi_dicts),
        )

        # Match
        pairs = match_markets(pm_markets, kalshi_dicts)

        # Build comparison
        comp = ExchangeComparison(
            matched_pairs=pairs,
            total_polymarket=len(pm_markets),
            total_kalshi=len(kalshi_dicts),
            polymarket_only=len(pm_markets) - len(pairs),
            kalshi_only=len(kalshi_dicts) - len(pairs),
        )

        if pairs:
            comp.avg_price_diff = sum(p.price_diff for p in pairs) / len(pairs)
            comp.avg_polymarket_spread = sum(p.polymarket_spread for p in pairs) / len(pairs)
            comp.avg_kalshi_spread = sum(p.kalshi_spread for p in pairs) / len(pairs)
            comp.arb_opportunities = sum(1 for p in pairs if p.has_arb_opportunity)

        comp.total_polymarket_volume = sum(
            float(m.get("volume_24h", 0) or 0) for m in pm_markets
        )
        comp.total_kalshi_volume = sum(
            float(m.get("volume_fp", "0") or "0") for m in kalshi_dicts
        )

        return comp

    async def close(self):
        if self._pm_client:
            await self._pm_client.close()
        if self._kalshi_client:
            await self._kalshi_client.close()
