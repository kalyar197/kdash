#!/usr/bin/env python3
"""
Binance Taker Ratio Daily Updater
Fetches latest taker buy/sell ratio and appends to dataset
Run daily via cron/task scheduler to maintain continuity

Data Granularity: 1-day periods
Source: Binance Futures API (FREE)
"""

import requests
import json
import argparse
from datetime import datetime, timezone
from pathlib import Path

# Configuration
BINANCE_FUTURES_BASE = 'https://fapi.binance.com'
SYMBOL = 'BTCUSDT'
PERIOD = '1d'
LIMIT = 30  # Fetch last 30 days for redundancy

DATA_FILE = Path('historical_data/options_pcr_cvd/taker_ratio_3m.json')
BACKUP_FILE = Path('historical_data/options_pcr_cvd/taker_ratio_3m.backup.json')


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


def fetch_recent_taker_ratio(days=30):
    """Fetch recent taker ratio from Binance."""
    url = f"{BINANCE_FUTURES_BASE}/futures/data/takerlongshortRatio"

    params = {
        'symbol': SYMBOL,
        'period': PERIOD,
        'limit': days
    }

    try:
        print(f"[Fetching] Last {days} days from Binance Futures API...")
        response = requests.get(url, params=params, timeout=30)
        response.raise_for_status()

        data = response.json()

        if not data:
            print("[ERROR] No data returned from API")
            return []

        taker_data = []
        for point in data:
            # Convert to millisecond timestamp
            timestamp = int(point['timestamp'])
            ratio = float(point['buySellRatio'])
            taker_data.append([timestamp, ratio])

        taker_data.sort(key=lambda x: x[0])
        print(f"[Fetched] {len(taker_data)} records")

        return taker_data

    except Exception as e:
        print(f"[ERROR] Failed to fetch data: {e}")
        return []


def update_dataset(days=30):
    """Update dataset with recent data."""
    print("="*80)
    print(f"BINANCE TAKER RATIO DAILY UPDATE")
    print("="*80)
    print(f"[Fetch] Last {days} days\n")

    # Backup
    backup_data()

    # Get current dataset
    last_ts, existing_count = get_last_timestamp()

    if last_ts:
        last_dt = datetime.fromtimestamp(last_ts / 1000, tz=timezone.utc)
        print(f"[Current] {existing_count} records (last: {last_dt.date()})")
    else:
        print(f"[Current] No existing data")

    # Fetch new data
    new_data = fetch_recent_taker_ratio(days)

    if not new_data:
        print("[ERROR] No new data fetched")
        return

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

    print(f"[Added] {added} new unique records")
    print(f"[Total] {len(unique_data)} records")

    # Save
    DATA_FILE.parent.mkdir(parents=True, exist_ok=True)

    with open(DATA_FILE, 'w') as f:
        json.dump(unique_data, f)

    print(f"[SAVED] {DATA_FILE}")

    # Stats
    if unique_data:
        first_dt = datetime.fromtimestamp(unique_data[0][0]/1000, tz=timezone.utc)
        last_dt = datetime.fromtimestamp(unique_data[-1][0]/1000, tz=timezone.utc)

        print(f"\n[Dataset Info]")
        print(f"  Range: {first_dt.date()} to {last_dt.date()}")
        print(f"  Records: {len(unique_data)}")
        print(f"  Granularity: 1 day")
        print(f"  Last Update: {last_dt.date()}")

    print(f"\n{'='*80}")
    print("UPDATE COMPLETE!")
    print(f"{'='*80}")


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Update taker ratio data from Binance')
    parser.add_argument('--days', type=int, default=30, help='Days of data to fetch (default: 30)')
    args = parser.parse_args()

    try:
        update_dataset(days=args.days)
    except KeyboardInterrupt:
        print("\n\n[ABORTED]")
    except Exception as e:
        print(f"\n[FATAL ERROR] {e}")
        import traceback
        traceback.print_exc()
