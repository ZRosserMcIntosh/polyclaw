"""Configuration management for PolyClaw."""

from __future__ import annotations

import os
from pathlib import Path
from dataclasses import dataclass, field
from dotenv import load_dotenv

# Load .env from project root
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(_PROJECT_ROOT / ".env")


@dataclass
class APIConfig:
    """API connection settings."""

    polymarket_base_url: str = "https://clob.polymarket.com"
    polymarket_gamma_url: str = "https://gamma-api.polymarket.com"
    polymarket_api_key: str = ""
    polymarket_api_secret: str = ""

    binance_ws_url: str = "wss://stream.binance.com:9443/ws"
    binance_rest_url: str = "https://api.binance.com/api/v3"
    binance_api_key: str = ""
    binance_api_secret: str = ""

    polygonscan_api_key: str = ""
    polygonscan_base_url: str = "https://api.polygonscan.com/api"

    # Kalshi
    kalshi_api_key_id: str = ""
    kalshi_private_key_path: str = ""
    kalshi_demo: bool = True  # Default to demo for safety

    def __post_init__(self):
        self.polymarket_api_key = os.getenv("POLYMARKET_API_KEY", "")
        self.polymarket_api_secret = os.getenv("POLYMARKET_API_SECRET", "")
        self.binance_api_key = os.getenv("BINANCE_API_KEY", "")
        self.binance_api_secret = os.getenv("BINANCE_API_SECRET", "")
        self.polygonscan_api_key = os.getenv("POLYGONSCAN_API_KEY", "")
        self.kalshi_api_key_id = os.getenv("KALSHI_API_KEY_ID", "")
        self.kalshi_private_key_path = os.getenv("KALSHI_PRIVATE_KEY_PATH", "")
        self.kalshi_demo = os.getenv("KALSHI_DEMO", "true").lower() in ("true", "1", "yes")


@dataclass
class SimulatorConfig:
    """Paper trading simulator settings."""

    starting_balance: float = 1000.0
    max_position_pct: float = 0.08  # 8% of portfolio per trade
    daily_loss_limit_pct: float = 0.20  # -20% daily loss halt
    kill_switch_pct: float = 0.40  # -40% total drawdown kill
    default_strategy: str = "latency-arb"

    def __post_init__(self):
        self.starting_balance = float(
            os.getenv("PAPER_TRADE_STARTING_BALANCE", self.starting_balance)
        )
        self.max_position_pct = float(
            os.getenv("PAPER_TRADE_MAX_POSITION_PCT", self.max_position_pct)
        )
        self.daily_loss_limit_pct = float(
            os.getenv("PAPER_TRADE_DAILY_LOSS_LIMIT_PCT", self.daily_loss_limit_pct)
        )
        self.kill_switch_pct = float(
            os.getenv("PAPER_TRADE_KILL_SWITCH_PCT", self.kill_switch_pct)
        )


@dataclass
class AppConfig:
    """Top-level application configuration."""

    api: APIConfig = field(default_factory=APIConfig)
    simulator: SimulatorConfig = field(default_factory=SimulatorConfig)
    database_path: str = ""
    log_level: str = "INFO"
    project_root: Path = _PROJECT_ROOT

    def __post_init__(self):
        self.database_path = os.getenv(
            "DATABASE_PATH",
            str(self.project_root / "polyclaw_data.db"),
        )
        self.log_level = os.getenv("LOG_LEVEL", "INFO")


# Global config singleton
config = AppConfig()
