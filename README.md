# 🐾 PolyClaw

**Multi-Exchange Prediction Market Research & Paper Trading Platform**

A Python-based research tool for analyzing prediction markets across **Polymarket** and **Kalshi**, tracking wallet performance, discovering top traders, detecting market inefficiencies, and running paper trade simulations.

## Features

### 📊 Market Research & Analysis
- Real-time market data from **Polymarket** (CLOB + Gamma API) and **Kalshi** (REST API)
- Cross-exchange comparison with fuzzy market matching
- Market liquidity, spread, and volume analysis
- Event category breakdowns (crypto, politics, sports, economics, etc.)

### 🏆 Trader Leaderboard & Copy-Trading
- On-chain wallet discovery via Goldsky orderbook subgraph
- Composite scoring: volume, activity, sophistication, bot detection
- Tiered ranking (🐋 whale, 🦈 shark, 🐬 dolphin, 🐟 fish)
- Real-time copy-trade monitor — watches top wallets and paper-copies trades

### ⚖️ Cross-Exchange Comparison (Polymarket vs Kalshi)
- Fuzzy title matching + keyword overlap to find same markets across exchanges
- Side-by-side pricing, spreads, liquidity comparison
- Cross-platform arbitrage opportunity detection
- Platform advantage analysis

### 🔍 Wallet Analyzer
- Public on-chain wallet performance tracking
- Win rate, PnL, and trade frequency analysis
- Trade pattern detection (bot vs. human behavior signatures)

### 📈 Inefficiency Scanner
- Compares Polymarket odds against Binance/Coinbase crypto prices
- Measures the "lag" between CEX price moves and prediction market odds
- Logs and visualizes potential arbitrage windows

### 🧪 Paper Trading Simulator
- Simulated trading engine with virtual balance
- Configurable strategies (latency arb, mean reversion, random baseline)
- Full position sizing with Kelly Criterion calculator
- Risk management (drawdown limits, position caps, kill switch)

## Project Structure

```
polyclaw/
├── polyclaw/
│   ├── __init__.py
│   ├── config.py              # Configuration & environment
│   ├── cli.py                 # Click CLI with 11 commands
│   ├── api/                   # API clients
│   │   ├── polymarket.py      # Polymarket CLOB + Gamma API
│   │   ├── kalshi.py          # Kalshi Exchange API (+ RSA auth)
│   │   ├── subgraph.py        # Goldsky orderbook subgraph
│   │   ├── binance.py         # Binance WebSocket price feed
│   │   └── polygon.py         # Polygon on-chain data
│   ├── analysis/              # Research & analysis tools
│   │   ├── markets.py         # Market data analysis
│   │   ├── leaderboard.py     # Trader leaderboard builder
│   │   ├── copytrade.py       # Copy-trade monitor
│   │   ├── compare.py         # Cross-exchange comparison
│   │   ├── wallets.py         # Wallet performance tracking
│   │   ├── inefficiency.py    # CEX vs prediction market lag detection
│   │   └── kelly.py           # Kelly Criterion calculator
│   ├── simulator/             # Paper trading engine
│   │   ├── engine.py          # Core simulation engine
│   │   ├── strategies.py      # Trading strategy implementations
│   │   ├── portfolio.py       # Virtual portfolio manager
│   │   └── risk.py            # Risk management module
│   ├── dashboard/             # Visualization & reporting
│   │   ├── charts.py          # Plotly charts
│   │   └── terminal_ui.py     # Rich terminal dashboard
│   └── data/                  # Data persistence
│       ├── store.py           # SQLite data store
│       └── models.py          # Data models
├── tests/                     # 85 tests, all passing
│   ├── test_api.py
│   ├── test_analysis.py
│   ├── test_kalshi.py
│   ├── test_leaderboard.py
│   └── test_simulator.py
├── scripts/
│   └── discover_apis.py       # API discovery utility
├── .env.example               # Environment variable template
├── pyproject.toml
└── requirements.txt
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
```

## CLI Commands

```bash
# Market Research
polyclaw scan-markets              # Scan Polymarket markets
polyclaw kalshi-markets            # Browse Kalshi markets
polyclaw kalshi-markets --series KXFED  # Filter by series
polyclaw compare                   # Compare Polymarket vs Kalshi side-by-side

# Trader Discovery
polyclaw leaderboard               # Build ranked trader leaderboard
polyclaw copy-trade 0xABC... 0xDEF...  # Monitor wallets in real time
polyclaw discover-and-copy         # Full pipeline: find top traders → copy them

# Analysis
polyclaw scan-inefficiency         # Monitor CEX vs Polymarket lag
polyclaw analyze-wallet 0x...      # Analyze a wallet's trading patterns
polyclaw prices                    # Quick BTC/ETH price check

# Paper Trading
polyclaw simulate --strategy latency-arb --balance 1000

# Kalshi Account (requires API keys)
polyclaw kalshi-balance            # Check account balance
polyclaw kalshi-balance --demo     # Use demo environment
```

## Exchange Comparison

| Feature | Polymarket | Kalshi |
|---|---|---|
| **Regulation** | Unregulated (crypto-native) | CFTC-regulated |
| **Auth** | Wallet-based | RSA key pairs |
| **Market Data** | Public, no auth needed | Public, no auth needed |
| **Trading API** | On-chain via CLOB | REST API with proper auth |
| **Demo Environment** | ❌ | ✅ demo.kalshi.co |
| **Volume** | Higher on crypto/politics | Higher on economics/weather |
| **Fees** | Lower | Standard |
| **Settlement** | USDC on Polygon | USD |
| **KYC** | Optional for basic | Required |
| **On-chain Data** | Full (Goldsky subgraph) | None (centralized) |

## Configuration

Copy `.env.example` to `.env` and fill in your API keys:

```env
# Kalshi Exchange (get keys at kalshi.com → Account & Security → API Keys)
KALSHI_API_KEY_ID=your-key-id
KALSHI_PRIVATE_KEY_PATH=/path/to/kalshi-key.key
KALSHI_DEMO=true  # Start with demo!

# Polymarket (public endpoints work without keys)
POLYMARKET_API_KEY=

# Binance (public WebSocket works without keys)
BINANCE_API_KEY=

# PolygonScan (for on-chain wallet analysis)
POLYGONSCAN_API_KEY=
```

Most features work without any API keys using public endpoints.

## Running Tests

```bash
python -m pytest tests/ -v
```

## Disclaimer

This is a **research and educational tool**. It does not place real trades or manage real money unless you explicitly configure exchange API keys and use the trading commands. The paper trading simulator uses virtual balances only. Prediction market trading carries significant financial risk. This tool is designed to help you understand market mechanics, not to generate profit.

## License

MIT
