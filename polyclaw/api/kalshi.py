"""Kalshi Exchange API client.

Provides access to Kalshi's prediction market data and trading:
- Public: markets, events, series, orderbooks (no auth)
- Authenticated: portfolio, orders, positions, balance (RSA key auth)

Supports both production and demo environments.

Production: https://api.elections.kalshi.com/trade-api/v2
Demo:       https://demo-api.kalshi.co/trade-api/v2

Docs: https://docs.kalshi.com
"""

from __future__ import annotations

import base64
import logging
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import httpx
from pydantic import BaseModel, Field

from polyclaw.config import config

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# URLs
# ---------------------------------------------------------------------------

KALSHI_PROD_URL = "https://api.elections.kalshi.com/trade-api/v2"
KALSHI_DEMO_URL = "https://demo-api.kalshi.co/trade-api/v2"


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------


class KalshiMarket(BaseModel):
    """A single Kalshi binary market."""

    model_config = {"extra": "ignore"}

    ticker: str = ""
    title: str = ""
    event_ticker: str = ""
    status: str = ""
    market_type: str = "binary"

    yes_bid_dollars: str = "0.0000"
    yes_ask_dollars: str = "0.0000"
    no_bid_dollars: str = "0.0000"
    no_ask_dollars: str = "0.0000"
    last_price_dollars: str = "0.0000"
    previous_price_dollars: str = "0.0000"

    volume_fp: str = "0"
    volume_24h_fp: str = "0"
    open_interest_fp: str = "0"
    liquidity_dollars: str = "0.0000"
    notional_value_dollars: str = "1.0000"

    close_time: str = ""
    expiration_time: str = ""
    open_time: str = ""
    result: str = ""

    @property
    def yes_bid(self) -> float:
        return float(self.yes_bid_dollars or "0")

    @property
    def yes_ask(self) -> float:
        return float(self.yes_ask_dollars or "0")

    @property
    def no_bid(self) -> float:
        return float(self.no_bid_dollars or "0")

    @property
    def no_ask(self) -> float:
        return float(self.no_ask_dollars or "0")

    @property
    def last_price(self) -> float:
        return float(self.last_price_dollars or "0")

    @property
    def volume(self) -> float:
        return float(self.volume_fp or "0")

    @property
    def volume_24h(self) -> float:
        return float(self.volume_24h_fp or "0")

    @property
    def open_interest(self) -> float:
        return float(self.open_interest_fp or "0")

    @property
    def liquidity(self) -> float:
        return float(self.liquidity_dollars or "0")

    @property
    def spread(self) -> float:
        """Spread between yes bid and ask."""
        bid = self.yes_bid
        ask = self.yes_ask
        if bid > 0 and ask > 0:
            return ask - bid
        return 0.0

    @property
    def midpoint(self) -> float:
        bid = self.yes_bid
        ask = self.yes_ask
        if bid > 0 and ask > 0:
            return (bid + ask) / 2
        return self.last_price


class KalshiEvent(BaseModel):
    """A Kalshi event (container for related markets)."""

    model_config = {"extra": "ignore"}

    event_ticker: str = ""
    series_ticker: str = ""
    title: str = ""
    sub_title: str = ""
    category: str = ""
    mutually_exclusive: bool = False


class KalshiOrderBook(BaseModel):
    """Orderbook snapshot for a Kalshi market."""

    yes_bids: list[tuple[float, float]] = Field(default_factory=list)  # (price, qty)
    no_bids: list[tuple[float, float]] = Field(default_factory=list)

    @property
    def best_yes_bid(self) -> float:
        return self.yes_bids[0][0] if self.yes_bids else 0.0

    @property
    def best_no_bid(self) -> float:
        return self.no_bids[0][0] if self.no_bids else 0.0


class KalshiOrder(BaseModel):
    """A placed order."""

    model_config = {"extra": "ignore"}

    order_id: str = ""
    client_order_id: str = ""
    ticker: str = ""
    action: str = ""  # buy / sell
    side: str = ""  # yes / no
    type: str = ""  # limit / market
    status: str = ""
    yes_price: float = 0.0
    no_price: float = 0.0
    count: int = 0
    remaining_count: int = 0
    created_time: str = ""


class KalshiPosition(BaseModel):
    """A current position."""

    model_config = {"extra": "ignore"}

    ticker: str = ""
    market_title: str = ""
    yes_count: int = 0
    no_count: int = 0
    avg_yes_price: float = 0.0
    avg_no_price: float = 0.0
    market_result: str = ""


class KalshiBalance(BaseModel):
    """Account balance (in cents, converted to dollars)."""

    balance_cents: int = 0
    payout_cents: int = 0

    @property
    def balance(self) -> float:
        return self.balance_cents / 100

    @property
    def payout(self) -> float:
        return self.payout_cents / 100


# ---------------------------------------------------------------------------
# Auth helper
# ---------------------------------------------------------------------------


class KalshiAuth:
    """RSA-PSS signature authentication for Kalshi API."""

    def __init__(self, api_key_id: str, private_key_path: str):
        self.api_key_id = api_key_id
        self._private_key = self._load_key(private_key_path)

    @staticmethod
    def _load_key(path: str):
        from cryptography.hazmat.backends import default_backend
        from cryptography.hazmat.primitives import serialization

        key_path = Path(path).expanduser()
        if not key_path.exists():
            raise FileNotFoundError(f"Kalshi private key not found: {key_path}")

        with open(key_path, "rb") as f:
            return serialization.load_pem_private_key(
                f.read(), password=None, backend=default_backend()
            )

    def sign(self, timestamp_ms: str, method: str, path: str) -> str:
        """Create RSA-PSS signature for a request."""
        from cryptography.hazmat.primitives import hashes
        from cryptography.hazmat.primitives.asymmetric import padding

        # Strip query parameters
        path_clean = path.split("?")[0]
        message = f"{timestamp_ms}{method}{path_clean}".encode("utf-8")

        signature = self._private_key.sign(
            message,
            padding.PSS(
                mgf=padding.MGF1(hashes.SHA256()),
                salt_length=padding.PSS.DIGEST_LENGTH,
            ),
            hashes.SHA256(),
        )
        return base64.b64encode(signature).decode("utf-8")

    def headers(self, method: str, path: str) -> dict[str, str]:
        """Generate auth headers for a request."""
        timestamp = str(int(time.time() * 1000))
        signature = self.sign(timestamp, method, path)
        return {
            "KALSHI-ACCESS-KEY": self.api_key_id,
            "KALSHI-ACCESS-TIMESTAMP": timestamp,
            "KALSHI-ACCESS-SIGNATURE": signature,
        }


# ---------------------------------------------------------------------------
# Client
# ---------------------------------------------------------------------------


class KalshiClient:
    """Kalshi Exchange API client.

    Public methods (no auth required):
        get_markets, get_market, get_events, get_event,
        get_series, get_orderbook

    Authenticated methods (require API key + private key):
        get_balance, get_positions, get_orders, place_order,
        cancel_order, amend_order
    """

    def __init__(
        self,
        *,
        demo: bool = False,
        api_key_id: str = "",
        private_key_path: str = "",
    ):
        self.base_url = KALSHI_DEMO_URL if demo else KALSHI_PROD_URL
        self.demo = demo
        self._client: httpx.AsyncClient | None = None

        # Auth (optional)
        self._auth: KalshiAuth | None = None
        key_id = api_key_id or config.api.kalshi_api_key_id
        key_path = private_key_path or config.api.kalshi_private_key_path
        if key_id and key_path:
            try:
                self._auth = KalshiAuth(key_id, key_path)
                logger.info("Kalshi auth configured (key: %s...)", key_id[:12])
            except Exception as e:
                logger.warning("Kalshi auth setup failed: %s", e)

    @property
    def is_authenticated(self) -> bool:
        return self._auth is not None

    @property
    def environment(self) -> str:
        return "demo" if self.demo else "production"

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(timeout=httpx.Timeout(30.0))
        return self._client

    async def close(self):
        if self._client and not self._client.is_closed:
            await self._client.aclose()

    async def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict | None = None,
        json_data: dict | None = None,
        auth_required: bool = False,
    ) -> dict[str, Any]:
        """Make an API request."""
        client = await self._get_client()
        url = f"{self.base_url}{path}"

        headers: dict[str, str] = {"Content-Type": "application/json"}

        if auth_required:
            if not self._auth:
                raise PermissionError(
                    "This endpoint requires Kalshi API keys. "
                    "Set KALSHI_API_KEY_ID and KALSHI_PRIVATE_KEY_PATH in .env"
                )
            # Sign the full path from root
            sign_path = urlparse(url).path
            headers.update(self._auth.headers(method.upper(), sign_path))

        resp = await client.request(
            method, url, headers=headers, params=params, json=json_data
        )
        resp.raise_for_status()
        return resp.json()

    # ---- Public: Markets ---------------------------------------------------

    async def get_markets(
        self,
        *,
        limit: int = 100,
        status: str = "open",
        series_ticker: str = "",
        event_ticker: str = "",
        cursor: str = "",
    ) -> tuple[list[KalshiMarket], str]:
        """Get markets. Returns (markets, next_cursor)."""
        params: dict[str, Any] = {"limit": limit, "status": status}
        if series_ticker:
            params["series_ticker"] = series_ticker
        if event_ticker:
            params["event_ticker"] = event_ticker
        if cursor:
            params["cursor"] = cursor

        data = await self._request("GET", "/markets", params=params)
        markets = [KalshiMarket(**m) for m in data.get("markets", [])]
        return markets, data.get("cursor", "")

    async def get_all_markets(
        self,
        *,
        status: str = "open",
        series_ticker: str = "",
        max_pages: int = 10,
    ) -> list[KalshiMarket]:
        """Paginate through all markets."""
        all_markets: list[KalshiMarket] = []
        cursor = ""

        for _ in range(max_pages):
            markets, cursor = await self.get_markets(
                limit=200,
                status=status,
                series_ticker=series_ticker,
                cursor=cursor,
            )
            all_markets.extend(markets)
            if not cursor or not markets:
                break

        return all_markets

    async def get_market(self, ticker: str) -> KalshiMarket:
        """Get a single market by ticker."""
        data = await self._request("GET", f"/markets/{ticker}")
        return KalshiMarket(**data.get("market", {}))

    async def get_orderbook(self, ticker: str) -> KalshiOrderBook:
        """Get orderbook for a market."""
        data = await self._request("GET", f"/markets/{ticker}/orderbook")
        fp = data.get("orderbook_fp", {})

        yes_bids = [
            (float(price), float(qty))
            for price, qty in fp.get("yes_dollars", [])
        ]
        no_bids = [
            (float(price), float(qty))
            for price, qty in fp.get("no_dollars", [])
        ]

        return KalshiOrderBook(yes_bids=yes_bids, no_bids=no_bids)

    # ---- Public: Events & Series -------------------------------------------

    async def get_events(
        self,
        *,
        limit: int = 50,
        status: str = "open",
        series_ticker: str = "",
        cursor: str = "",
    ) -> tuple[list[KalshiEvent], str]:
        """Get events. Returns (events, next_cursor)."""
        params: dict[str, Any] = {"limit": limit, "status": status}
        if series_ticker:
            params["series_ticker"] = series_ticker
        if cursor:
            params["cursor"] = cursor

        data = await self._request("GET", "/events", params=params)
        events = [KalshiEvent(**e) for e in data.get("events", [])]
        return events, data.get("cursor", "")

    async def get_event(self, event_ticker: str) -> KalshiEvent:
        """Get a single event."""
        data = await self._request("GET", f"/events/{event_ticker}")
        return KalshiEvent(**data.get("event", {}))

    async def get_series(self, series_ticker: str) -> dict[str, Any]:
        """Get series info."""
        data = await self._request("GET", f"/series/{series_ticker}")
        return data.get("series", {})

    # ---- Authenticated: Portfolio ------------------------------------------

    async def get_balance(self) -> KalshiBalance:
        """Get account balance. Requires auth."""
        data = await self._request(
            "GET", "/portfolio/balance", auth_required=True
        )
        return KalshiBalance(
            balance_cents=data.get("balance", 0),
            payout_cents=data.get("payout", 0),
        )

    async def get_positions(
        self,
        *,
        limit: int = 100,
        event_ticker: str = "",
        settlement_status: str = "",
    ) -> list[KalshiPosition]:
        """Get current positions. Requires auth."""
        params: dict[str, Any] = {"limit": limit}
        if event_ticker:
            params["event_ticker"] = event_ticker
        if settlement_status:
            params["settlement_status"] = settlement_status

        data = await self._request(
            "GET", "/portfolio/positions", params=params, auth_required=True
        )
        positions = []
        for p in data.get("market_positions", []):
            positions.append(
                KalshiPosition(
                    ticker=p.get("ticker", ""),
                    market_title=p.get("market_title", ""),
                    yes_count=p.get("position", 0),
                    no_count=p.get("total_traded", 0),
                )
            )
        return positions

    # ---- Authenticated: Orders ---------------------------------------------

    async def get_orders(
        self,
        *,
        limit: int = 100,
        ticker: str = "",
        status: str = "",
    ) -> list[KalshiOrder]:
        """Get orders. Requires auth."""
        params: dict[str, Any] = {"limit": limit}
        if ticker:
            params["ticker"] = ticker
        if status:
            params["status"] = status

        data = await self._request(
            "GET", "/portfolio/orders", params=params, auth_required=True
        )
        return [KalshiOrder(**o) for o in data.get("orders", [])]

    async def place_order(
        self,
        *,
        ticker: str,
        action: str = "buy",
        side: str = "yes",
        count: int = 1,
        order_type: str = "limit",
        yes_price: int = 0,
        no_price: int = 0,
        client_order_id: str = "",
    ) -> KalshiOrder:
        """Place an order. Requires auth.

        Args:
            ticker: Market ticker.
            action: "buy" or "sell".
            side: "yes" or "no".
            count: Number of contracts.
            order_type: "limit" or "market".
            yes_price: Limit price in cents (1-99) for yes side.
            no_price: Limit price in cents (1-99) for no side.
            client_order_id: Unique ID for deduplication.
        """
        if not client_order_id:
            client_order_id = str(uuid.uuid4())

        order_data: dict[str, Any] = {
            "ticker": ticker,
            "action": action,
            "side": side,
            "count": count,
            "type": order_type,
            "client_order_id": client_order_id,
        }
        if yes_price:
            order_data["yes_price"] = yes_price
        if no_price:
            order_data["no_price"] = no_price

        data = await self._request(
            "POST",
            "/portfolio/orders",
            json_data=order_data,
            auth_required=True,
        )
        return KalshiOrder(**data.get("order", {}))

    async def cancel_order(self, order_id: str) -> dict[str, Any]:
        """Cancel an order. Requires auth."""
        return await self._request(
            "DELETE",
            f"/portfolio/orders/{order_id}",
            auth_required=True,
        )

    async def amend_order(
        self,
        order_id: str,
        *,
        count: int | None = None,
        yes_price: int | None = None,
        no_price: int | None = None,
    ) -> KalshiOrder:
        """Amend an existing order. Requires auth."""
        amend_data: dict[str, Any] = {}
        if count is not None:
            amend_data["count"] = count
        if yes_price is not None:
            amend_data["yes_price"] = yes_price
        if no_price is not None:
            amend_data["no_price"] = no_price

        data = await self._request(
            "PUT",
            f"/portfolio/orders/{order_id}",
            json_data=amend_data,
            auth_required=True,
        )
        return KalshiOrder(**data.get("order", {}))
