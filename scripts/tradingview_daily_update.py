#!/usr/bin/env python3
"""
TradingView Daily Updater: Fetch latest data for all 27 TradingView metrics
Maintains continuity by fetching last 7 days and merging with historical data

Usage:
  python tradingview_daily_update.py           # Update all 27 symbols
  python tradingview_daily_update.py --days 3  # Fetch last 3 days only
  python tradingview_daily_update.py --dry-run # Test without saving

Run this daily via Windows Task Scheduler or cron to keep data fresh.

Requirements:
  - TradingView credentials in .env (TV_USERNAME, TV_PASSWORD)
  - tvdatafeed library installed
"""

import os
import sys
import json
import time
import argparse
from datetime import datetime, timezone, timedelta
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from tvDatafeed import TvDatafeed, Interval
from data.time_transformer import standardize_to_daily_utc
from data.incremental_data_manager import save_historical_data, load_historical_data, merge_and_deduplicate

# Load credentials from environment
from dotenv import load_dotenv
load_dotenv()

TV_USERNAME = os.getenv('TV_USERNAME')
TV_PASSWORD = os.getenv('TV_PASSWORD')

# Rate limiting configuration
BASE_DELAY = 3          # Seconds between each symbol
EXCHANGE_DELAY = 5      # When switching exchanges
ERROR_BACKOFF = 10      # After any error
MAX_RETRIES = 2

# Symbol mappings (all 27 metrics)
SYMBOLS = {
    # GLASSNODE (8 symbols)
    'GLASSNODE': [
        ('BTC_SOPR', 'btc_sopr'),
        ('BTC_MEDIANVOLUME', 'btc_medianvolume'),
        ('BTC_MEANTXFEES', 'btc_meantxfees'),
        ('BTC_SENDINGADDRESSES', 'btc_sendingaddresses'),
        ('BTC_ACTIVE1Y', 'btc_active1y'),
        ('BTC_RECEIVINGADDRESSES', 'btc_receivingaddresses'),
        ('BTC_NEWADDRESSES', 'btc_newaddresses'),
        ('USDT_TFSPS', 'usdt_tfsps'),
    ],
    # COINMETRICS (8 symbols)
    'COINMETRICS': [
        ('BTC_SER', 'btc_ser'),
        ('BTC_AVGTX', 'btc_avgtx'),
        ('BTC_TXCOUNT', 'btc_txcount'),
        ('BTC_SPLYADRBAL1', 'btc_splyadrbal1'),
        ('BTC_ADDRESSESSUPPLY1IN10K', 'btc_addressessupply1in10k'),
        ('BTC_LARGETXCOUNT', 'btc_largetxcount'),
        ('BTC_ACTIVESUPPLY1Y', 'btc_activesupply1y'),
        ('USDT_AVGTX', 'usdt_avgtx'),
    ],
    # KRAKEN (1 symbol)
    'KRAKEN': [
        ('USDTUSD.PM', 'usdtusd_pm'),
    ],
    # LUNARCRUSH (4 symbols)
    'LUNARCRUSH': [
        ('BTC_POSTSCREATED', 'btc_postscreated'),
        ('BTC_CONTRIBUTORSCREATED', 'btc_contributorscreated'),
        ('BTC_SOCIALDOMINANCE', 'btc_socialdominance'),
        ('BTC_CONTRIBUTORSACTIVE', 'btc_contributorsactive'),
    ],
    # DEFILLAMA (1 symbol)
    'DEFILLAMA': [
        ('BTCST_TVL', 'btcst_tvl'),
    ],
    # NASDAQ (1 symbol)
    'NASDAQ': [
        ('IBIT', 'ibit'),
    ],
    # AMEX (1 symbol)
    'AMEX': [
        ('GBTC', 'gbtc'),
    ],
    # CRYPTOCAP (2 symbols)
    'CRYPTOCAP': [
        ('TOTAL3', 'total3'),
        ('STABLE.C.D', 'stable_c_d'),
    ],
}


def get_last_data_timestamp(filename):
    """Get the timestamp of the last data point in file."""
    try:
        data = load_historical_data(filename)
        if data and len(data) > 0:
            last_ts = data[-1][0]  # milliseconds
            return last_ts
        return None
    except Exception as e:
        print(f"  Warning: Could not read {filename}: {e}")
        return None


def fetch_symbol_update(exchange, symbol, filename, n_bars=7, retry_count=0):
    """
    Fetch latest data for a single symbol.

    Args:
        exchange: TradingView exchange name
        symbol: Symbol name
        filename: Filename for saving (without .json)
        n_bars: Number of days to fetch (default: 7 for redundancy)
        retry_count: Current retry attempt

    Returns:
        dict: {'success': bool, 'new_points': int, 'error': str}
    """
    try:
        # Initialize with login
        if TV_USERNAME and TV_PASSWORD:
            tv = TvDatafeed(username=TV_USERNAME, password=TV_PASSWORD)
        else:
            tv = TvDatafeed()
            print(f"  WARNING: No login credentials (some data may be limited)")

        # Fetch data
        df = tv.get_hist(
            symbol=symbol,
            exchange=exchange,
            interval=Interval.in_daily,
            n_bars=n_bars
        )

        if df is None or df.empty:
            return {'success': False, 'new_points': 0, 'error': 'No data returned'}

        # Convert to standard format
        data = []
        for idx, row in df.iterrows():
            timestamp_ms = int(idx.timestamp() * 1000)
            value = float(row['close'])
            data.append([timestamp_ms, value])

        # Standardize timestamps to midnight UTC
        cleaned_data = standardize_to_daily_utc(data)

        if not cleaned_data:
            return {'success': False, 'new_points': 0, 'error': 'No valid data after cleaning'}

        # Load existing data for merging
        existing_data = load_historical_data(filename)

        # Merge new data with existing historical data (prevents data loss)
        merged_data = merge_and_deduplicate(existing_data, cleaned_data, overlap_days=3)

        # Count new points added
        existing_timestamps = set(point[0] for point in existing_data) if existing_data else set()
        new_points = [point for point in cleaned_data if point[0] not in existing_timestamps]

        # Save merged dataset (not just new data)
        save_historical_data(filename, merged_data)

        return {
            'success': True,
            'new_points': len(new_points),
            'total_points': len(merged_data),
            'error': None
        }

    except Exception as e:
        error_msg = str(e)

        # Retry logic
        if retry_count < MAX_RETRIES:
            print(f"  Error: {error_msg}")
            print(f"  Retrying ({retry_count + 1}/{MAX_RETRIES})...")
            time.sleep(ERROR_BACKOFF * (2 ** retry_count))  # Exponential backoff
            return fetch_symbol_update(exchange, symbol, filename, n_bars, retry_count + 1)

        return {'success': False, 'new_points': 0, 'error': error_msg}


def main():
    """Main execution."""
    parser = argparse.ArgumentParser(description='TradingView Daily Updater')
    parser.add_argument('--days', type=int, default=7,
                       help='Number of days to fetch (default: 7 for redundancy)')
    parser.add_argument('--dry-run', action='store_true',
                       help='Test mode - show what would be updated without saving')
    parser.add_argument('--symbols', type=int,
                       help='Only update first N symbols (for testing)')
    args = parser.parse_args()

    print("="*80)
    print("TRADINGVIEW DAILY UPDATER")
    print("="*80)
    print(f"Timestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"Login: {'ENABLED' if TV_USERNAME and TV_PASSWORD else 'DISABLED'}")
    print(f"Fetch period: Last {args.days} days")
    print(f"Mode: {'DRY-RUN (no saves)' if args.dry_run else 'LIVE UPDATE'}")

    # Count total symbols
    total_symbols = sum(len(symbols) for symbols in SYMBOLS.values())
    if args.symbols:
        total_symbols = min(args.symbols, total_symbols)
        print(f"Test mode: Only updating first {total_symbols} symbols")

    print(f"Symbols to update: {total_symbols}")
    print("="*80)

    if not TV_USERNAME or not TV_PASSWORD:
        print("\nWARNING: No TradingView credentials found!")
        print("10 symbols require login. Add to .env:")
        print("  TV_USERNAME=your_username")
        print("  TV_PASSWORD=your_password")
        print("\nContinuing with limited access...\n")

    results = {
        'updated': [],
        'no_new_data': [],
        'failed': []
    }

    symbol_count = 0
    last_exchange = None

    for exchange, symbol_list in SYMBOLS.items():
        # Add delay when switching exchanges
        if last_exchange and last_exchange != exchange:
            print(f"\n[Switching to {exchange}] Waiting {EXCHANGE_DELAY}s...")
            time.sleep(EXCHANGE_DELAY)

        print(f"\n{'='*80}")
        print(f"EXCHANGE: {exchange} ({len(symbol_list)} symbols)")
        print(f"{'='*80}")

        for symbol, filename in symbol_list:
            symbol_count += 1

            # Check if we should stop (for --symbols limit)
            if args.symbols and symbol_count > args.symbols:
                print(f"\nReached symbol limit ({args.symbols}), stopping.")
                break

            print(f"\n[{symbol_count}/{total_symbols}] {exchange}:{symbol}")

            # Get last data timestamp
            last_ts = get_last_data_timestamp(filename)
            if last_ts:
                last_date = datetime.fromtimestamp(last_ts / 1000, tz=timezone.utc)
                age_hours = (datetime.now(tz=timezone.utc) - last_date).total_seconds() / 3600
                print(f"  Last data: {last_date.strftime('%Y-%m-%d %H:%M UTC')} ({age_hours:.1f}h ago)")
            else:
                print(f"  No existing data found")

            # Fetch update
            if args.dry_run:
                print(f"  [DRY-RUN] Would fetch last {args.days} days")
                results['updated'].append({
                    'symbol': f"{exchange}:{symbol}",
                    'new_points': 0,
                    'dry_run': True
                })
            else:
                result = fetch_symbol_update(exchange, symbol, filename, n_bars=args.days)

                if result['success']:
                    if result['new_points'] > 0:
                        print(f"  [SUCCESS] Added {result['new_points']} new points (fetched {result['total_points']})")
                        results['updated'].append({
                            'symbol': f"{exchange}:{symbol}",
                            'new_points': result['new_points']
                        })
                    else:
                        print(f"  [UP-TO-DATE] No new data (fetched {result['total_points']}, all existed)")
                        results['no_new_data'].append(f"{exchange}:{symbol}")
                else:
                    print(f"  [FAILED] {result['error']}")
                    results['failed'].append({
                        'symbol': f"{exchange}:{symbol}",
                        'error': result['error']
                    })

            # Delay between symbols
            if symbol_count < total_symbols:
                time.sleep(BASE_DELAY)

        last_exchange = exchange

        # Break outer loop if reached symbol limit
        if args.symbols and symbol_count >= args.symbols:
            break

    # Final summary
    print("\n\n" + "="*80)
    print("UPDATE SUMMARY")
    print("="*80)
    print(f"Total symbols processed: {symbol_count}")
    print(f"Updated (new data): {len(results['updated'])}")
    print(f"Up-to-date (no new data): {len(results['no_new_data'])}")
    print(f"Failed: {len(results['failed'])}")

    if results['updated']:
        print(f"\nUpdated symbols ({len(results['updated'])}):")
        for r in results['updated']:
            if 'dry_run' in r:
                print(f"  [DRY-RUN] {r['symbol']}")
            else:
                print(f"  [+{r['new_points']:2d}] {r['symbol']}")

    if results['no_new_data']:
        print(f"\nUp-to-date symbols ({len(results['no_new_data'])}):")
        for s in results['no_new_data'][:10]:  # Show first 10
            print(f"  [OK] {s}")
        if len(results['no_new_data']) > 10:
            print(f"  ... and {len(results['no_new_data']) - 10} more")

    if results['failed']:
        print(f"\nFailed symbols ({len(results['failed'])}):")
        for r in results['failed']:
            print(f"  [FAIL] {r['symbol']}: {r['error']}")

    print("="*80)

    # Save results to log file
    if not args.dry_run:
        log_file = Path('historical_data/tradingview_update_log.json')
        log_entry = {
            'timestamp': datetime.now(tz=timezone.utc).isoformat(),
            'updated': len(results['updated']),
            'up_to_date': len(results['no_new_data']),
            'failed': len(results['failed']),
            'details': results
        }

        # Append to log file
        try:
            if log_file.exists():
                with open(log_file, 'r') as f:
                    logs = json.load(f)
            else:
                logs = []

            logs.append(log_entry)

            # Keep only last 30 entries
            logs = logs[-30:]

            with open(log_file, 'w') as f:
                json.dump(logs, f, indent=2)

            print(f"\nLog saved to: {log_file}")
        except Exception as e:
            print(f"\nWarning: Could not save log: {e}")

    # Exit code
    sys.exit(0 if len(results['failed']) == 0 else 1)


if __name__ == '__main__':
    main()
