"""Polygon (PoS) chain explorer client for on-chain wallet analysis.

Uses the PolygonScan API to fetch wallet transaction history,
token transfers, and trading activity on Polymarket contracts.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

import httpx
from pydantic import BaseModel, Field

from polyclaw.config import config

logger = logging.getLogger(__name__)


class WalletTransaction(BaseModel):
    """A single on-chain transaction."""

    hash: str = ""
    block_number: int = 0
    timestamp: int = 0
    from_address: str = ""
    to_address: str = ""
    value: str = "0"
    gas_used: int = 0
    is_error: bool = False
    method_id: str = ""
    function_name: str = ""

    @property
    def dt(self) -> datetime:
        return datetime.fromtimestamp(self.timestamp, tz=timezone.utc)

    @property
    def value_matic(self) -> float:
        """Value in MATIC (18 decimals)."""
        return int(self.value) / 1e18 if self.value else 0.0


class TokenTransfer(BaseModel):
    """An ERC-20 token transfer event."""

    hash: str = ""
    block_number: int = 0
    timestamp: int = 0
    from_address: str = ""
    to_address: str = ""
    value: str = "0"
    token_name: str = ""
    token_symbol: str = ""
    token_decimal: int = 18
    contract_address: str = ""

    @property
    def dt(self) -> datetime:
        return datetime.fromtimestamp(self.timestamp, tz=timezone.utc)

    @property
    def token_value(self) -> float:
        return int(self.value) / (10 ** self.token_decimal) if self.value else 0.0


class WalletSummary(BaseModel):
    """Aggregated wallet stats."""

    address: str = ""
    total_transactions: int = 0
    first_seen: datetime | None = None
    last_seen: datetime | None = None
    total_token_transfers: int = 0
    unique_contracts_interacted: int = 0
    matic_balance: float = 0.0


class PolygonClient:
    """Async client for PolygonScan API."""

    def __init__(self):
        self.base_url = config.api.polygonscan_base_url
        self.api_key = config.api.polygonscan_api_key
        self._client: httpx.AsyncClient | None = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(timeout=httpx.Timeout(30.0))
        return self._client

    async def close(self):
        if self._client and not self._client.is_closed:
            await self._client.aclose()

    async def _request(self, params: dict[str, Any]) -> list[dict]:
        """Make a request to the PolygonScan API."""
        if not self.api_key:
            logger.warning("No PolygonScan API key configured. On-chain features limited.")
            return []

        client = await self._get_client()
        params["apikey"] = self.api_key
        resp = await client.get(self.base_url, params=params)
        resp.raise_for_status()
        data = resp.json()

        if data.get("status") != "1":
            msg = data.get("message", "Unknown error")
            if "No transactions found" in msg:
                return []
            logger.warning("PolygonScan API error: %s", msg)
            return []

        return data.get("result", [])

    # -- Wallet Queries -----------------------------------------------------

    async def get_transactions(
        self,
        address: str,
        *,
        start_block: int = 0,
        end_block: int = 99999999,
        page: int = 1,
        offset: int = 100,
        sort: str = "desc",
    ) -> list[WalletTransaction]:
        """Get normal transactions for a wallet address."""
        raw = await self._request({
            "module": "account",
            "action": "txlist",
            "address": address,
            "startblock": start_block,
            "endblock": end_block,
            "page": page,
            "offset": offset,
            "sort": sort,
        })
        return [
            WalletTransaction(
                hash=tx.get("hash", ""),
                block_number=int(tx.get("blockNumber", 0)),
                timestamp=int(tx.get("timeStamp", 0)),
                from_address=tx.get("from", ""),
                to_address=tx.get("to", ""),
                value=tx.get("value", "0"),
                gas_used=int(tx.get("gasUsed", 0)),
                is_error=tx.get("isError", "0") == "1",
                method_id=tx.get("methodId", ""),
                function_name=tx.get("functionName", ""),
            )
            for tx in raw
        ]

    async def get_token_transfers(
        self,
        address: str,
        *,
        contract_address: str | None = None,
        page: int = 1,
        offset: int = 100,
        sort: str = "desc",
    ) -> list[TokenTransfer]:
        """Get ERC-20 token transfer events for a wallet."""
        params: dict[str, Any] = {
            "module": "account",
            "action": "tokentx",
            "address": address,
            "page": page,
            "offset": offset,
            "sort": sort,
        }
        if contract_address:
            params["contractaddress"] = contract_address

        raw = await self._request(params)
        return [
            TokenTransfer(
                hash=tx.get("hash", ""),
                block_number=int(tx.get("blockNumber", 0)),
                timestamp=int(tx.get("timeStamp", 0)),
                from_address=tx.get("from", ""),
                to_address=tx.get("to", ""),
                value=tx.get("value", "0"),
                token_name=tx.get("tokenName", ""),
                token_symbol=tx.get("tokenSymbol", ""),
                token_decimal=int(tx.get("tokenDecimal", 18)),
                contract_address=tx.get("contractAddress", ""),
            )
            for tx in raw
        ]

    async def get_matic_balance(self, address: str) -> float:
        """Get MATIC balance for a wallet."""
        raw = await self._request({
            "module": "account",
            "action": "balance",
            "address": address,
            "tag": "latest",
        })
        if isinstance(raw, str):
            return int(raw) / 1e18
        return 0.0

    async def get_wallet_summary(self, address: str) -> WalletSummary:
        """Build a summary profile of a wallet's on-chain activity."""
        txns = await self.get_transactions(address, offset=500)
        transfers = await self.get_token_transfers(address, offset=500)

        unique_contracts = set()
        for tx in txns:
            if tx.to_address:
                unique_contracts.add(tx.to_address.lower())

        first_seen = min((tx.dt for tx in txns), default=None) if txns else None
        last_seen = max((tx.dt for tx in txns), default=None) if txns else None

        return WalletSummary(
            address=address,
            total_transactions=len(txns),
            first_seen=first_seen,
            last_seen=last_seen,
            total_token_transfers=len(transfers),
            unique_contracts_interacted=len(unique_contracts),
        )
