"""SQLAlchemy data models for persistent storage."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import Column, Integer, Float, String, Boolean, DateTime, Text
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass


class MarketSnapshot(Base):
    """Historical market data snapshots."""

    __tablename__ = "market_snapshots"

    id = Column(Integer, primary_key=True, autoincrement=True)
    timestamp = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    condition_id = Column(String(128), index=True)
    question = Column(Text)
    best_bid = Column(Float)
    best_ask = Column(Float)
    spread = Column(Float)
    last_price = Column(Float)
    volume_24h = Column(Float)
    liquidity = Column(Float)
    category = Column(String(64))


class PriceFeed(Base):
    """CEX price feed snapshots."""

    __tablename__ = "price_feeds"

    id = Column(Integer, primary_key=True, autoincrement=True)
    timestamp = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    symbol = Column(String(20), index=True)
    price = Column(Float)
    source = Column(String(20), default="binance")


class DetectedWindow(Base):
    """Logged inefficiency windows."""

    __tablename__ = "detected_windows"

    id = Column(Integer, primary_key=True, autoincrement=True)
    timestamp = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    symbol = Column(String(20))
    cex_price = Column(Float)
    cex_change_pct = Column(Float)
    polymarket_question = Column(Text)
    polymarket_prob = Column(Float)
    estimated_fair_prob = Column(Float)
    edge_pct = Column(Float)
    duration_ms = Column(Float, nullable=True)


class PaperTradeRecord(Base):
    """Persisted paper trades."""

    __tablename__ = "paper_trades"

    id = Column(Integer, primary_key=True, autoincrement=True)
    trade_id = Column(Integer, index=True)
    timestamp = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    market_question = Column(Text)
    condition_id = Column(String(128))
    side = Column(String(4))
    entry_price = Column(Float)
    size_usd = Column(Float)
    shares = Column(Float)
    exit_price = Column(Float, nullable=True)
    exit_timestamp = Column(DateTime, nullable=True)
    status = Column(String(20))
    pnl = Column(Float, default=0.0)
    strategy = Column(String(50))


class WalletAnalysisRecord(Base):
    """Cached wallet analysis results."""

    __tablename__ = "wallet_analyses"

    id = Column(Integer, primary_key=True, autoincrement=True)
    timestamp = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    address = Column(String(42), index=True)
    total_transactions = Column(Integer)
    estimated_trade_count = Column(Integer)
    activity_days = Column(Integer)
    avg_trades_per_day = Column(Float)
    is_likely_bot = Column(Boolean)
    bot_confidence = Column(Float)
