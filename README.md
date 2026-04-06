# 🐾 PolyClaw

**Polymarket Research & Paper Trading Platform**

A Python-based research tool for analyzing Polymarket prediction markets, tracking wallet performance, detecting market inefficiencies, and running paper trade simulations — all without risking real money.

## Features

### 📊 Market Research & Analysis
- Real-time Polymarket market data fetching via CLOB API
- Historical odds tracking and visualization
- Market liquidity analysis
- Event category breakdowns (crypto, politics, sports, etc.)

### 🔍 Wallet Analyzer
- Public on-chain wallet performance tracking
- Win rate, PnL, and trade frequency analysis
- Wallet leaderboard generation from public data
- Trade pattern detection (bot vs. human behavior signatures)

### 📈 Inefficiency Scanner
- Compares Polymarket odds against external data sources
- Tracks Binance/Coinbase crypto prices vs. Polymarket crypto contracts
- Measures the "lag" between CEX price moves and Polymarket odds updates
- Logs and visualizes arbitrage windows (size & duration)

### 🧪 Paper Trading Simulator
- Simulated trading engine with virtual balance
- Configurable strategies (latency arb, mean reversion, news-driven)
- Full position sizing with Kelly Criterion calculator
- Risk management (drawdown limits, position caps)
- Performance tracking dashboard with equity curves

## Project Structure

```
polyclaw/
├── polyclaw/                  # Main package
│   ├── __init__.py
│   ├── config.py              # Configuration & environment
│   ├── api/                   # API clients
│   │   ├── __init__.py
│   │   ├── polymarket.py      # Polymarket CLOB API client
│   │   ├── binance.py         # Binance WebSocket price feed
│   │   └── polygon.py         # Polygon on-chain data
│   ├── analysis/              # Research & analysis tools
│   │   ├── __init__.py
│   │   ├── markets.py         # Market data analysis
│   │   ├── wallets.py         # Wallet performance tracking
│   │   ├── inefficiency.py    # Lag/inefficiency detection
│   │   └── kelly.py           # Kelly Criterion calculator
│   ├── simulator/             # Paper trading engine
│   │   ├── __init__.py
│   │   ├── engine.py          # Core simulation engine
│   │   ├── strategies.py      # Trading strategy implementations
│   │   ├── portfolio.py       # Virtual portfolio manager
│   │   └── risk.py            # Risk management module
│   ├── dashboard/             # Visualization & reporting
│   │   ├── __init__.py
│   │   ├── charts.py          # Plotly/matplotlib charts
│   │   ├── terminal_ui.py     # Rich terminal dashboard
│   │   └── report.py          # PDF/HTML report generator
│   └── data/                  # Data persistence
│       ├── __init__.py
│       ├── store.py           # SQLite data store
│       └── models.py          # Data models
├── notebooks/                 # Jupyter notebooks for exploration
│   └── 01_market_explorer.ipynb
├── tests/                     # Test suite
│   ├── __init__.py
│   ├── test_api.py
│   ├── test_simulator.py
│   └── test_analysis.py
├── .env.example               # Environment variable template
├── .gitignore
├── pyproject.toml             # Project config & dependencies
├── requirements.txt           # Pip dependencies
└── README.md
```

## Quick Start

```bash
# Clone the repo
git clone https://github.com/ZRosserMcIntosh/polyclaw.git
cd polyclaw

# Create virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Copy env template and configure
cp .env.example .env

# Run the market scanner
python -m polyclaw scan-markets

# Run the paper trading simulator
python -m polyclaw simulate --strategy latency-arb --balance 1000 --duration 24h

# Launch the terminal dashboard
python -m polyclaw dashboard
```

## Configuration

Copy `.env.example` to `.env` and fill in your API keys:

```env
# Optional - Polymarket API (public endpoints work without keys)
POLYMARKET_API_KEY=

# Optional - for enhanced crypto price feeds
BINANCE_API_KEY=
BINANCE_API_SECRET=

# Optional - for on-chain wallet analysis
POLYGONSCAN_API_KEY=
```

Most features work without any API keys using public endpoints.

## Disclaimer

This is a **research and educational tool**. It does not place real trades or manage real money. The paper trading simulator uses virtual balances only. Prediction market trading carries significant financial risk. This tool is designed to help you understand market mechanics, not to generate profit.

## License

MIT
