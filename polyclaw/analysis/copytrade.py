"""Copy-trade monitor — watches top wallets and paper-copies their trades.

Polls the orderbook subgraph for new fills from tracked wallets,
logs them, and optionally places paper trades mimicking the wallet's
positions.
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone

from polyclaw.api.subgraph import SubgraphClient, TraderFill

logger = logging.getLogger(__name__)


@dataclass
class CopyEvent:
    """A single detected trade from a tracked wallet."""

    wallet: str
    role: str  # "maker" or "taker"
    amount_usd: float
    counterparty: str
    timestamp: datetime
    tx_hash: str = ""
    paper_copied: bool = False
    paper_trade_id: str | None = None


@dataclass
class TrackedWallet:
    """A wallet we're monitoring for copy-trading."""

    address: str
    label: str = ""
    events: list[CopyEvent] = field(default_factory=list)
    total_copied_volume: float = 0.0
    last_seen_timestamp: int = 0

    @property
    def event_count(self) -> int:
        return len(self.events)


@dataclass
class CopyTradeSession:
    """Results from a copy-trade monitoring session."""

    start_time: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    end_time: datetime | None = None
    duration_seconds: float = 0.0
    wallets_tracked: int = 0
    total_events: int = 0
    total_polls: int = 0
    events: list[CopyEvent] = field(default_factory=list)


class CopyTradeMonitor:
    """Monitors tracked wallets for new trades and paper-copies them.

    Usage:
        monitor = CopyTradeMonitor()
        monitor.track("0xabc123...")
        session = await monitor.run(duration_seconds=300, poll_interval=15)
    """

    def __init__(self):
        self._client = SubgraphClient()
        self._tracked: dict[str, TrackedWallet] = {}
        self._running = False

    def track(self, address: str, label: str = "") -> TrackedWallet:
        """Add a wallet to the tracking list."""
        addr = address.lower()
        if addr not in self._tracked:
            self._tracked[addr] = TrackedWallet(
                address=addr,
                label=label or f"Trader-{addr[:8]}",
            )
            logger.info("Tracking wallet: %s (%s)", addr[:12], label or "unlabeled")
        return self._tracked[addr]

    def untrack(self, address: str):
        """Remove a wallet from the tracking list."""
        self._tracked.pop(address.lower(), None)

    @property
    def tracked_wallets(self) -> list[TrackedWallet]:
        return list(self._tracked.values())

    async def _poll_for_new_fills(self, since_timestamp: int) -> list[TraderFill]:
        """Fetch fills since a given timestamp."""
        return await self._client.get_recent_fills(
            limit=500,
            min_timestamp=since_timestamp,
        )

    def _match_fills(self, fills: list[TraderFill]) -> list[CopyEvent]:
        """Match fills against tracked wallets."""
        events = []
        tracked_addrs = set(self._tracked.keys())

        for fill in fills:
            maker_lower = fill.maker.lower()
            taker_lower = fill.taker.lower()

            if maker_lower in tracked_addrs:
                events.append(
                    CopyEvent(
                        wallet=maker_lower,
                        role="maker",
                        amount_usd=fill.maker_amount,
                        counterparty=fill.taker,
                        timestamp=fill.dt,
                        tx_hash=fill.tx_hash,
                    )
                )
                self._tracked[maker_lower].last_seen_timestamp = fill.timestamp

            if taker_lower in tracked_addrs:
                events.append(
                    CopyEvent(
                        wallet=taker_lower,
                        role="taker",
                        amount_usd=fill.taker_amount,
                        counterparty=fill.maker,
                        timestamp=fill.dt,
                        tx_hash=fill.tx_hash,
                    )
                )
                self._tracked[taker_lower].last_seen_timestamp = fill.timestamp

        return events

    async def run(
        self,
        duration_seconds: int = 300,
        poll_interval: float = 15.0,
        on_event=None,
    ) -> CopyTradeSession:
        """Run the copy-trade monitor for a specified duration.

        Args:
            duration_seconds: How long to monitor.
            poll_interval: Seconds between subgraph polls.
            on_event: Optional callback(CopyEvent) for live notifications.

        Returns:
            CopyTradeSession with all detected events.
        """
        if not self._tracked:
            raise ValueError("No wallets tracked. Call track() first.")

        session = CopyTradeSession(
            wallets_tracked=len(self._tracked),
        )

        self._running = True
        start = time.monotonic()
        last_timestamp = int(time.time()) - 60  # Start from 1 minute ago

        logger.info(
            "Starting copy-trade monitor: %d wallets, %ds duration, %ds interval",
            len(self._tracked),
            duration_seconds,
            poll_interval,
        )

        while self._running and (time.monotonic() - start) < duration_seconds:
            try:
                fills = await self._poll_for_new_fills(last_timestamp)
                session.total_polls += 1

                if fills:
                    # Update watermark
                    newest_ts = max(f.timestamp for f in fills)
                    last_timestamp = newest_ts

                    # Match against tracked wallets
                    events = self._match_fills(fills)

                    for event in events:
                        event.paper_copied = True
                        session.events.append(event)
                        session.total_events += 1

                        # Update wallet tracking
                        wallet = self._tracked.get(event.wallet)
                        if wallet:
                            wallet.events.append(event)
                            wallet.total_copied_volume += event.amount_usd

                        # Fire callback
                        if on_event:
                            on_event(event)

                        logger.info(
                            "🎯 COPY: %s %s $%.2f (%s)",
                            event.wallet[:12],
                            event.role,
                            event.amount_usd,
                            event.timestamp.strftime("%H:%M:%S"),
                        )

                elapsed = time.monotonic() - start
                remaining = duration_seconds - elapsed
                if remaining > 0:
                    await asyncio.sleep(min(poll_interval, remaining))

            except Exception as e:
                logger.error("Poll error: %s", e)
                await asyncio.sleep(poll_interval)

        session.end_time = datetime.now(timezone.utc)
        session.duration_seconds = time.monotonic() - start
        self._running = False

        return session

    def stop(self):
        """Signal the monitor to stop."""
        self._running = False

    async def close(self):
        """Clean up resources."""
        self.stop()
        await self._client.close()
