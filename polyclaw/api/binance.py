"""Binance WebSocket and REST client for real-time crypto price feeds.

Used to compare CEX prices against Polymarket crypto contract odds
to detect latency/inefficiency windows.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from datetime import datetime, timezone
from typing import Any, Callable

import httpx
import websockets

from polyclaw.config import config

logger = logging.getLogger(__name__)


class PriceTick:
    """A single price update from Binance."""

    __slots__ = ("symbol", "price", "timestamp", "source")

    def __init__(self, symbol: str, price: float, timestamp: float, source: str = "binance"):
        self.symbol = symbol
        self.price = price
        self.timestamp = timestamp
        self.source = source

    @property
    def dt(self) -> datetime:
        return datetime.fromtimestamp(self.timestamp, tz=timezone.utc)

    def __repr__(self) -> str:
        return f"PriceTick({self.symbol}={self.price:.2f} @ {self.dt.isoformat()})"


class BinanceClient:
    """Async client for Binance price data (public endpoints only)."""

    def __init__(self):
        self.ws_url = config.api.binance_ws_url
        self.rest_url = config.api.binance_rest_url
        self._http: httpx.AsyncClient | None = None
        self._ws_connection = None
        self._running = False
        self._callbacks: list[Callable[[PriceTick], Any]] = []
        self._latest_prices: dict[str, PriceTick] = {}

    async def _get_http(self) -> httpx.AsyncClient:
        if self._http is None or self._http.is_closed:
            self._http = httpx.AsyncClient(timeout=httpx.Timeout(15.0))
        return self._http

    async def close(self):
        self._running = False
        if self._http and not self._http.is_closed:
            await self._http.aclose()

    # -- REST API -----------------------------------------------------------

    async def get_price(self, symbol: str = "BTCUSDT") -> PriceTick:
        """Get current price for a symbol via REST."""
        client = await self._get_http()
        resp = await client.get(f"{self.rest_url}/ticker/price", params={"symbol": symbol})
        resp.raise_for_status()
        data = resp.json()
        tick = PriceTick(
            symbol=symbol,
            price=float(data["price"]),
            timestamp=time.time(),
        )
        self._latest_prices[symbol] = tick
        return tick

    async def get_prices(self, symbols: list[str] | None = None) -> dict[str, PriceTick]:
        """Get prices for multiple symbols. Defaults to BTC and ETH."""
        symbols = symbols or ["BTCUSDT", "ETHUSDT"]
        tasks = [self.get_price(s) for s in symbols]
        ticks = await asyncio.gather(*tasks, return_exceptions=True)
        result = {}
        for tick in ticks:
            if isinstance(tick, PriceTick):
                result[tick.symbol] = tick
        return result

    async def get_klines(
        self,
        symbol: str = "BTCUSDT",
        interval: str = "1m",
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """Get historical kline/candlestick data."""
        client = await self._get_http()
        resp = await client.get(
            f"{self.rest_url}/klines",
            params={"symbol": symbol, "interval": interval, "limit": limit},
        )
        resp.raise_for_status()
        raw = resp.json()
        return [
            {
                "open_time": k[0],
                "open": float(k[1]),
                "high": float(k[2]),
                "low": float(k[3]),
                "close": float(k[4]),
                "volume": float(k[5]),
                "close_time": k[6],
            }
            for k in raw
        ]

    # -- WebSocket Stream ---------------------------------------------------

    def on_tick(self, callback: Callable[[PriceTick], Any]):
        """Register a callback for price ticks."""
        self._callbacks.append(callback)

    @property
    def latest(self) -> dict[str, PriceTick]:
        """Most recent price for each subscribed symbol."""
        return dict(self._latest_prices)

    async def stream_prices(
        self,
        symbols: list[str] | None = None,
        duration_seconds: float | None = None,
    ):
        """Connect to Binance WebSocket and stream real-time prices.

        Args:
            symbols: List of symbols to subscribe to. Defaults to BTC and ETH.
            duration_seconds: If set, stop after this many seconds.
        """
        symbols = symbols or ["btcusdt", "ethusdt"]
        streams = "/".join(f"{s.lower()}@trade" for s in symbols)
        url = f"{self.ws_url}/{streams}" if len(symbols) > 1 else f"{self.ws_url}/{streams}"

        self._running = True
        start_time = time.time()
        logger.info("Connecting to Binance WebSocket: %s", streams)

        try:
            async with websockets.connect(url) as ws:
                self._ws_connection = ws
                async for raw_msg in ws:
                    if not self._running:
                        break
                    if duration_seconds and (time.time() - start_time) > duration_seconds:
                        break

                    try:
                        data = json.loads(raw_msg)
                        tick = PriceTick(
                            symbol=data.get("s", ""),
                            price=float(data.get("p", 0)),
                            timestamp=float(data.get("T", 0)) / 1000.0,
                        )
                        self._latest_prices[tick.symbol] = tick

                        for cb in self._callbacks:
                            try:
                                result = cb(tick)
                                if asyncio.iscoroutine(result):
                                    await result
                            except Exception:
                                logger.exception("Tick callback error")
                    except (json.JSONDecodeError, KeyError, ValueError):
                        logger.warning("Malformed WS message: %s", raw_msg[:200])
        except Exception:
            logger.exception("WebSocket connection error")
        finally:
            self._ws_connection = None
            self._running = False

    async def stop_stream(self):
        """Signal the WebSocket stream to stop."""
        self._running = False
