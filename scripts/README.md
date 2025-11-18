# Production Scripts

This directory contains operational scripts for the BTC Trading Dashboard. All one-time migration and backfill scripts have been moved to the `archive/migration-scripts` branch.

## Daily Operations (Automated)

These scripts should be run daily via cron jobs to keep data up-to-date:

### binance_daily_update.py
**Purpose:** Updates BTC price data from Binance
**Schedule:** Daily at 00:05 UTC
**Runtime:** ~30 seconds
**Requirements:** None (uses Binance public API)
**Command:**
```bash
python scripts/binance_daily_update.py
```

### tradingview_daily_update.py
**Purpose:** Updates 27 TradingView metrics (technical indicators, market data)
**Schedule:** Daily at 00:10 UTC
**Runtime:** ~2-5 minutes
**Requirements:** TRADINGVIEW_USERNAME, TRADINGVIEW_PASSWORD in .env
**Command:**
```bash
python scripts/tradingview_daily_update.py
```

### binance_taker_ratio_update.py
**Purpose:** Updates taker buy/sell ratio data from Binance
**Schedule:** Every 6 hours
**Runtime:** ~15 seconds
**Requirements:** None (uses Binance public API)
**Command:**
```bash
python scripts/binance_taker_ratio_update.py
```

## Utility Scripts (Manual)

These scripts are run manually for maintenance and monitoring:

### inventory_datasets.py
**Purpose:** List all datasets in PostgreSQL database
**When to run:** When you need to see what data is available
**Runtime:** <1 second
**Command:**
```bash
python scripts/inventory_datasets.py
```

Example output:
```
Dataset Inventory (PostgreSQL)
================================
- btc_price_binance (1min)
- rsi_btc (1hour)
- funding_rate_btc (8hour)
... (36 total datasets)
```

### benchmark_performance.py
**Purpose:** Benchmark API response times and database query performance
**When to run:** After deployment or when investigating performance issues
**Runtime:** ~30 seconds
**Command:**
```bash
python scripts/benchmark_performance.py
```

### spot_check_data.py
**Purpose:** Quick data quality check - verify recent data points exist
**When to run:** After daily updates or when troubleshooting data gaps
**Runtime:** ~5 seconds
**Command:**
```bash
python scripts/spot_check_data.py
```

Example output:
```
Spot Check Results
===================
✓ btc_price: Latest = 2024-11-17 00:00:00 (3 hours ago)
✓ rsi_btc: Latest = 2024-11-17 00:00:00 (3 hours ago)
✗ funding_rate_btc: Latest = 2024-11-16 16:00:00 (11 hours ago) - STALE!
```

## Setup: Cron Jobs for Daily Updates

Add these entries to your crontab (`crontab -e`):

```bash
# BTC Trading Dashboard - Daily Data Updates
# Run at 00:05 UTC daily - Binance BTC price update
5 0 * * * cd /opt/dash && /opt/dash/venv/bin/python scripts/binance_daily_update.py >> /opt/dash/logs/binance_daily.log 2>&1

# Run at 00:10 UTC daily - TradingView metrics update
10 0 * * * cd /opt/dash && /opt/dash/venv/bin/python scripts/tradingview_daily_update.py >> /opt/dash/logs/tradingview_daily.log 2>&1

# Run every 6 hours - Taker ratio update
0 */6 * * * cd /opt/dash && /opt/dash/venv/bin/python scripts/binance_taker_ratio_update.py >> /opt/dash/logs/taker_ratio.log 2>&1
```

**Note:** Adjust paths (`/opt/dash`) to match your actual deployment directory.

## Archived Scripts

All migration, backfill, and one-time setup scripts (47 total) have been moved to the `archive/migration-scripts` branch for historical reference.

To access archived scripts:
```bash
git checkout archive/migration-scripts
cd scripts/
```

See `scripts/ARCHIVE_README.md` in that branch for full documentation.

## Environment Variables Required

Make sure these are set in your `.env` file:

**For TradingView updates:**
- `TRADINGVIEW_USERNAME`
- `TRADINGVIEW_PASSWORD`

**For database access (all scripts):**
- `DATABASE_URL`

## Troubleshooting

**Script fails with "ModuleNotFoundError":**
- Ensure you're running from the project root directory
- Activate virtual environment: `source venv/bin/activate` (Linux/Mac) or `venv\Scripts\activate` (Windows)
- Install dependencies: `pip install -r requirements.txt`

**Daily updates not running:**
- Check cron logs: `grep CRON /var/log/syslog` (Linux)
- Verify cron service is running: `systemctl status cron`
- Test script manually first: `python scripts/binance_daily_update.py`

**Data is stale:**
- Run `spot_check_data.py` to identify which datasets are outdated
- Check logs in `/opt/dash/logs/` for error messages
- Manually run the relevant update script to backfill

## Support

For issues or questions about these scripts, see:
- **Main Documentation:** `docs/CLAUDE.md`
- **Deployment Guide:** `docs/DEPLOYMENT.md`
- **Dataset Inventory:** `docs/plans/DATASET_INVENTORY.json`
