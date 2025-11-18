# BTC Trading Dashboard

Production-ready Bitcoin trading dashboard with technical indicators, price analysis, and macroeconomic metrics. Features 36 data plugins, PostgreSQL/TimescaleDB backend, and real-time visualization with D3.js.

## Quick Start (Development)

```bash
# 1. Clone the repository
git clone https://github.com/yourusername/btc-trading-dashboard.git
cd btc-trading-dashboard

# 2. Create virtual environment
python3.11 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Configure environment variables
cp .env.example .env
# Edit .env and add your API keys

# 5. Initialize database (PostgreSQL required)
# See docs/DEPLOYMENT.md for database setup

# 6. Run the application
python app.py

# 7. Open in browser
http://localhost:5000
```

## Production Deployment

For production deployment to a VPS/server, see the comprehensive guide:

**📖 [Production Deployment Guide](docs/DEPLOYMENT.md)**

Includes:
- Server setup & requirements
- PostgreSQL + TimescaleDB installation
- Systemd service configuration
- Nginx reverse proxy setup
- SSL certificate installation
- Daily data updates via cron
- Monitoring & troubleshooting

## Project Structure

```
Dash/
├── app.py              # Flask application entry point
├── config.py           # API keys and configuration
├── index.html          # Dashboard UI
├── requirements.txt    # Python dependencies
│
├── src/                # Application code
│   ├── data/          # Data plugins (price feeds, indicators)
│   └── static/        # Frontend assets (JavaScript, CSS)
│
├── database/          # Database schema and migrations
│   ├── alembic/       # Database migrations
│   ├── alembic.ini    # Alembic configuration
│   ├── models/        # SQLAlchemy ORM models
│   └── schema/        # SQL schema files
│
├── storage/           # Runtime data (not committed)
│   ├── cache/         # In-memory cache files
│   ├── data/          # Historical time-series data
│   ├── logs/          # Application logs
│   └── backups/       # Data backups
│
├── scripts/           # Utility scripts
│   ├── binance_daily_update.py
│   ├── tradingview_daily_update.py
│   └── archive/       # Old/deprecated scripts
│
├── docs/              # Documentation
│   ├── CLAUDE.md      # Development guide
│   ├── plans/         # Implementation plans
│   └── archive/       # Historical documentation
│
├── tests/             # Test suite
│   ├── test_api_endpoints.py  # Smoke tests
│   └── integration/            # Integration tests
│
├── deployment/         # Production deployment files
│   ├── dash-app.service       # Systemd service file
│   └── init_database.sh       # Database initialization
│
└── .config/           # Development config (not committed)
    ├── .serena/       # Serena MCP memory
    └── .claude/       # Claude Code settings
```

## Features

- **Oscillators**: RSI, MACD, ADX, ATR with Z-score normalization
- **Price Charts**: BTC, ETH, Gold, SPX, DXY with OHLCV candlesticks
- **Macro Indicators**: BTC.D, USDT.D, DVOL Index, Basis Spread
- **Markov Regime Detection**: Visual volatility regime backgrounds
- **PostgreSQL + TimescaleDB**: High-performance time-series database
- **Caching**: Two-tier (disk + in-memory) for fast loads
- **Minimalist UI**: Clean, expert-focused design

## Configuration

### Environment Variables

Create a `.env` file from the template:

```bash
cp .env.example .env
```

**Required API Keys:**

- **CoinAPI** - Cryptocurrency price data
  - Get key at: https://www.coinapi.io/
- **FMP (Financial Modeling Prep)** - Stock market data
  - Get key at: https://financialmodelingprep.com/
- **CoinMarketCap** - Cryptocurrency dominance metrics
  - Get key at: https://pro.coinmarketcap.com/
- **TradingView** - Technical indicators (27 metrics)
  - Username/password for data fetching
- **Alpaca Markets** - Additional market data (optional)
  - Get keys at: https://alpaca.markets/

### Database Setup

**Required:** PostgreSQL 14+ with TimescaleDB extension

For detailed database setup instructions, see:
- [Production Deployment Guide](docs/DEPLOYMENT.md) - Section: Database Setup
- Quick start: Run `./deployment/init_database.sh`

## Daily Updates

**Automated via Cron (Production):**

See [scripts/README.md](scripts/README.md) for cron job setup.

**Manual Execution (Development):**

```bash
# Update BTC price data
python scripts/binance_daily_update.py

# Update TradingView metrics (27 indicators)
python scripts/tradingview_daily_update.py

# Update taker ratio data
python scripts/binance_taker_ratio_update.py
```

## Testing

Run smoke tests to verify the application is working:

```bash
# Ensure Flask app is running first (python app.py)

# Run smoke tests
python tests/test_api_endpoints.py
```

Expected output:
```
✓ Server is running
✓ index.html loads successfully
✓ /api/data_sources returns 36 sources
✓ /api/data/btc returns 1440 data points
✓ /api/oscillator returns 1440 oscillator points
✓ All 5 static JS files are accessible

Passed: 6/6
```

## Documentation

- **📖 Deployment Guide**: [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md) - Production deployment instructions
- **💻 Development Guide**: [docs/CLAUDE.md](docs/CLAUDE.md) - Architecture, data plugins, development notes
- **🔧 Scripts Documentation**: [scripts/README.md](scripts/README.md) - Operational scripts guide
- **📊 Dataset Inventory**: [docs/plans/DATASET_INVENTORY.json](docs/plans/DATASET_INVENTORY.json) - Complete dataset listing

## Tech Stack

- **Backend**: Flask (Python), PostgreSQL, TimescaleDB
- **Frontend**: D3.js, vanilla JavaScript
- **Data**: Binance, TradingView, Alpaca, CoinMarketCap, FMP
- **Indicators**: Custom Z-score normalization, Markov regime detection

## License

Private use only.
