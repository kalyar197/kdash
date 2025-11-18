#!/usr/bin/env python3
"""
Binance Daily Updater: Fetch latest BTC 1-minute bars and append to dataset
Run this daily via cron/task scheduler to maintain continuity

Usage:
  python binance_daily_update.py          # Fetch last 24 hours
  python binance_daily_update.py --hours 48  # Fetch last 48 hours
"""

import requests
import json
import time
import argparse
from datetime import datetime, timezone, timedelta
from pathlib import Path

# Configuration
BINANCE_BASE = 'https://api.binance.com'
SYMBOL = 'BTCUSDT'
INTERVAL = '1m'
LIMIT = 1000

DATA_FILE = Path('historical_data/btc_price_1min_complete.json')
BACKUP_FILE = Path('historical_data/btc_price_1min_complete.backup.json')


def backup_data():
    """Create backup before updating."""
    if DATA_FILE.exists():
        import shutil
        shutil.copy(DATA_FILE, BACKUP_FILE)
        print(f"[Backup] Created: {BACKUP_FILE}")


def get_last_timestamp():
    """Get last timestamp from dataset."""
    try:
        with open(DATA_FILE, 'r') as f:
            data = json.load(f)
        if data:
            last_ts = data[-1][0]
            return last_ts, len(data)
        return None, 0
    except FileNotFoundError:
        print(f"[WARNING] File not found: {DATA_FILE}")
        print("[INFO] Will create new file")
        return None, 0
    except Exception as e:
        print(f"[ERROR] Failed to read data: {e}")
        return None, 0


def fetch_recent_data(hours=24):
    """Fetch recent data from Binance."""
    end_ts = int(datetime.now(tz=timezone.utc).timestamp() * 1000)
    start_ts = end_ts - (hours * 3600 * 1000)

    url = f"{BINANCE_BASE}/api/v3/klines"
    params = {
        'symbol': SYMBOL,
        'interval': INTERVAL,
        'startTime': start_ts,
        'endTime': end_ts,
        'limit': min(hours * 60, LIMIT)
    }

    try:
        response = requests.get(url, params=params, timeout=30)
        response.raise_for_status()

        klines = response.json()
        ohlcv = []

        for k in klines:
            ohlcv.append([
                int(k[0]),
                float(k[1]),
                float(k[2]),
                float(k[3]),
                float(k[4]),
                float(k[5])
            ])

        return ohlcv

    except Exception as e:
        print(f"[ERROR] Failed to fetch data: {e}")
        return []


def update_dataset(hours=24):
    """Update dataset with recent data."""
    print("="*80)
    print(f"BINANCE DAILY UPDATE: BTC 1-MINUTE DATA")
    print("="*80)
    print(f"[Fetch] Last {hours} hours\n")

    # Backup
    backup_data()

    # Get current dataset
    last_ts, existing_count = get_last_timestamp()

    if last_ts:
        last_dt = datetime.fromtimestamp(last_ts / 1000, tz=timezone.utc)
        print(f"[Current] {existing_count:,} records (last: {last_dt})")
    else:
        print(f"[Current] No existing data")

    # Fetch new data
    print(f"[Fetching] Latest {hours} hours from Binance...")
    new_data = fetch_recent_data(hours)

    if not new_data:
        print("[ERROR] No new data fetched")
        return

    print(f"[Fetched] {len(new_data)} bars")

    # Load existing data
    try:
        with open(DATA_FILE, 'r') as f:
            existing_data = json.load(f)
    except FileNotFoundError:
        existing_data = []

    # Merge and deduplicate
    combined = existing_data + new_data

    seen = set()
    unique_data = []

    for record in combined:
        ts = record[0]
        if ts not in seen:
            seen.add(ts)
            unique_data.append(record)

    unique_data.sort(key=lambda x: x[0])

    added = len(unique_data) - existing_count

    print(f"[Added] {added} new unique bars")
    print(f"[Total] {len(unique_data):,} bars")

    # Save
    with open(DATA_FILE, 'w') as f:
        json.dump(unique_data, f)

    print(f"[SAVED] {DATA_FILE}")

    # Stats
    if unique_data:
        first_dt = datetime.fromtimestamp(unique_data[0][0]/1000, tz=timezone.utc)
        last_dt = datetime.fromtimestamp(unique_data[-1][0]/1000, tz=timezone.utc)

        print(f"\n[Dataset Info]")
        print(f"  Range: {first_dt.date()} to {last_dt.date()}")
        print(f"  Records: {len(unique_data):,}")
        print(f"  File Size: {DATA_FILE.stat().st_size / 1024 / 1024:.1f} MB")
        print(f"  Last Update: {last_dt}")

    print(f"\n{'='*80}")
    print("UPDATE COMPLETE!")
    print(f"{'='*80}")


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Update BTC 1-minute data from Binance')
    parser.add_argument('--hours', type=int, default=24, help='Hours of data to fetch (default: 24)')
    args = parser.parse_args()

    try:
        update_dataset(hours=args.hours)
    except KeyboardInterrupt:
        print("\n\n[ABORTED]")
    except Exception as e:
        print(f"\n[FATAL ERROR] {e}")
        import traceback
        traceback.print_exc()
