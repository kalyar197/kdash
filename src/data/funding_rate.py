# data/funding_rate.py
"""
Funding Rate Data Plugin
Fetches BTC perpetual funding rate history from Binance
"""

import requests
import json
import os
import math
from datetime import datetime, timedelta, timezone
from config import CACHE_DURATION, RATE_LIMIT_DELAY
import time

# Binance Futures API base URL
BINANCE_BASE_URL = "https://fapi.binance.com"

# Historical data cache file
CACHE_FILE = os.path.join('historical_data', 'funding_rate_btc.json')


def get_metadata(asset='btc'):
    """
    Returns metadata for funding rate data
    """
    asset_name = {
        'btc': 'Bitcoin',
        'eth': 'Ethereum'
    }.get(asset.lower(), 'BTC')

    return {
        'label': f'Funding Rate ({asset_name} Perpetual)',
        'yAxisId': 'percentage',
        'yAxisLabel': 'Funding Rate (%)',
        'unit': '%',
        'chartType': 'area',
        'color': '#FF9500',  # Base orange
        'colorRanges': {
            'positive': '#26a69a',  # Green (>0.01%)
            'neutral': '#888888',   # Gray (-0.01% to +0.01%)
            'negative': '#ef5350'   # Red (<-0.01%)
        },
        'referenceLines': [
            {'value': 0.01, 'label': '+0.01% (High)', 'color': '#26a69a'},
            {'value': 0, 'label': 'Neutral', 'color': '#888'},
            {'value': -0.01, 'label': '-0.01% (Low)', 'color': '#ef5350'}
        ],
        'data_structure': 'simple',
        'components': ['timestamp', 'funding_rate_percentage']
    }


def fetch_from_binance(symbol='BTCUSDT', limit=1000, start_time=None, end_time=None):
    """
    Fetch funding rate history from Binance Futures API

    Args:
        symbol: Trading pair symbol (default: BTCUSDT)
        limit: Number of records to fetch (max 1000)
        start_time: Start timestamp in milliseconds (optional)
        end_time: End timestamp in milliseconds (optional)

    Returns:
        List of [timestamp, funding_rate] pairs
    """
    try:
        endpoint = f"{BINANCE_BASE_URL}/fapi/v1/fundingRate"
        params = {
            'symbol': symbol,
            'limit': limit
        }

        if start_time is not None:
            params['startTime'] = int(start_time)
        if end_time is not None:
            params['endTime'] = int(end_time)

        print(f"[Funding Rate] Fetching from Binance API: {endpoint}")
        if start_time and end_time:
            print(f"[Funding Rate] Time range: {datetime.fromtimestamp(start_time/1000, tz=timezone.utc).date()} to {datetime.fromtimestamp(end_time/1000, tz=timezone.utc).date()}")

        response = requests.get(endpoint, params=params, timeout=10)
        response.raise_for_status()

        data = response.json()
        print(f"[Funding Rate] Received {len(data)} records from Binance")

        # Convert to [[timestamp, rate_percentage], ...] format
        # Binance returns decimal (e.g., 0.0001), convert to percentage (0.01%)
        standardized = []
        for record in data:
            timestamp = record['fundingTime']  # Already in milliseconds
            funding_rate = float(record['fundingRate']) * 100  # Convert to percentage
            standardized.append([timestamp, funding_rate])

        # Sort by timestamp ascending
        standardized.sort(key=lambda x: x[0])

        return standardized

    except requests.exceptions.RequestException as e:
        print(f"[Funding Rate] Error fetching from Binance: {e}")
        return []
    except Exception as e:
        print(f"[Funding Rate] Unexpected error: {e}")
        return []


def fetch_historical_batches(symbol='BTCUSDT', days=1095):
    """
    Fetch historical funding rate data in batches for extended time periods

    Args:
        symbol: Trading pair symbol (default: BTCUSDT)
        days: Number of days to fetch (default: 1095 = 3 years)

    Returns:
        List of [timestamp, funding_rate] pairs
    """
    print(f"\n[Funding Rate] Batch fetching {days} days of historical data...")

    # Calculate time range
    end_time = datetime.now(tz=timezone.utc)
    start_time = end_time - timedelta(days=days)

    end_ms = int(end_time.timestamp() * 1000)
    start_ms = int(start_time.timestamp() * 1000)

    print(f"[Funding Rate] Date range: {start_time.date()} to {end_time.date()}")

    # Calculate number of batches needed
    # Funding rate updates every 8 hours = 3 times per day
    # Max records per batch = 1000
    # Days per batch = 1000 / 3 ≈ 333 days
    records_needed = days * 3
    batches_needed = math.ceil(records_needed / 1000)

    print(f"[Funding Rate] Records needed: {records_needed}, Batches: {batches_needed}")

    all_data = []
    batch_size_ms = 333 * 24 * 60 * 60 * 1000  # ~333 days in milliseconds

    for i in range(batches_needed):
        batch_start = start_ms + (i * batch_size_ms)
        batch_end = min(batch_start + batch_size_ms, end_ms)

        print(f"[Funding Rate] Batch {i+1}/{batches_needed}: Fetching...")

        # Fetch batch with rate limiting
        if i > 0:
            time.sleep(RATE_LIMIT_DELAY)

        batch_data = fetch_from_binance(
            symbol=symbol,
            limit=1000,
            start_time=batch_start,
            end_time=batch_end
        )

        if batch_data:
            all_data.extend(batch_data)
            print(f"[Funding Rate] Batch {i+1} complete: {len(batch_data)} records")
        else:
            print(f"[Funding Rate] Batch {i+1} failed or returned no data")

    # Remove duplicates and sort
    seen_timestamps = set()
    unique_data = []
    for record in all_data:
        if record[0] not in seen_timestamps:
            seen_timestamps.add(record[0])
            unique_data.append(record)

    unique_data.sort(key=lambda x: x[0])

    print(f"[Funding Rate] Batch fetching complete: {len(unique_data)} total records")
    if unique_data:
        print(f"[Funding Rate] First: {datetime.fromtimestamp(unique_data[0][0]/1000, tz=timezone.utc).date()}")
        print(f"[Funding Rate] Last: {datetime.fromtimestamp(unique_data[-1][0]/1000, tz=timezone.utc).date()}")

    return unique_data


def load_historical_cache():
    """
    Load historical funding rate data from disk cache

    Returns:
        List of [timestamp, funding_rate] pairs, or empty list if no cache
    """
    try:
        if os.path.exists(CACHE_FILE):
            with open(CACHE_FILE, 'r') as f:
                data = json.load(f)
                print(f"[Funding Rate] Loaded {len(data)} historical records from cache")
                return data
        else:
            print(f"[Funding Rate] No historical cache found at {CACHE_FILE}")
            return []
    except Exception as e:
        print(f"[Funding Rate] Error loading cache: {e}")
        return []


def save_historical_cache(data):
    """
    Save funding rate data to disk cache

    Args:
        data: List of [timestamp, funding_rate] pairs
    """
    try:
        # Ensure directory exists
        os.makedirs(os.path.dirname(CACHE_FILE), exist_ok=True)

        with open(CACHE_FILE, 'w') as f:
            json.dump(data, f, indent=2)

        print(f"[Funding Rate] Saved {len(data)} records to cache")
    except Exception as e:
        print(f"[Funding Rate] Error saving cache: {e}")


def merge_and_deduplicate(historical, fresh):
    """
    Merge historical and fresh data, removing duplicates

    Args:
        historical: List of [timestamp, value] pairs from cache
        fresh: List of [timestamp, value] pairs from API

    Returns:
        Merged list sorted by timestamp
    """
    # Create dict with timestamp as key (automatically deduplicates)
    merged_dict = {}

    # Add historical data
    for record in historical:
        timestamp = record[0]
        merged_dict[timestamp] = record

    # Add fresh data (overwrites duplicates with fresh values)
    for record in fresh:
        timestamp = record[0]
        merged_dict[timestamp] = record

    # Convert back to list and sort
    merged = list(merged_dict.values())
    merged.sort(key=lambda x: x[0])

    return merged


def get_data(days='365', asset='btc'):
    """
    Get funding rate data with incremental caching and 3-year historical support

    Args:
        days: Number of days to return ('7', '30', '90', '365', '1095', 'max')
        asset: Asset symbol (currently only 'btc' supported)

    Returns:
        Dict with metadata and data
    """
    print(f"\n[Funding Rate] Fetching data for {asset}, {days} days")

    # Step 1: Load historical cache
    historical_data = load_historical_cache()

    # Step 2: Determine fetch strategy
    if not historical_data or len(historical_data) < 100:
        # No cache or insufficient data: Fetch 3 years of historical data in batches
        print("[Funding Rate] No cache found or insufficient data. Fetching 3 years...")
        fresh_data = fetch_historical_batches(symbol='BTCUSDT', days=1095)
        merged_data = fresh_data
        if merged_data:
            save_historical_cache(merged_data)
    else:
        # Cache exists: Incremental update (fetch latest ~333 days)
        print(f"[Funding Rate] Cache exists with {len(historical_data)} records")
        time.sleep(RATE_LIMIT_DELAY)  # Rate limiting
        fresh_data = fetch_from_binance(symbol='BTCUSDT', limit=1000)

        # Merge and deduplicate
        if fresh_data:
            merged_data = merge_and_deduplicate(historical_data, fresh_data)
            # Save updated cache
            save_historical_cache(merged_data)
        else:
            # API failed, use cached data only
            print("[Funding Rate] API failed, using cached data only")
            merged_data = historical_data

    # Step 4: Filter by requested time range
    if days != 'max':
        try:
            days_int = int(days)
            cutoff_date = datetime.now(tz=timezone.utc) - timedelta(days=days_int)
            cutoff_ms = int(cutoff_date.timestamp() * 1000)
            filtered_data = [d for d in merged_data if d[0] >= cutoff_ms]
            print(f"[Funding Rate] Filtered to {len(filtered_data)} records for {days} days")
        except ValueError:
            print(f"[Funding Rate] Invalid days parameter: {days}, using all data")
            filtered_data = merged_data
    else:
        filtered_data = merged_data

    # Step 5: Return in standard format
    result = {
        'metadata': get_metadata(asset),
        'data': filtered_data,
        'structure': 'simple'
    }

    print(f"[Funding Rate] Returning {len(filtered_data)} data points")
    return result


# Test function
if __name__ == '__main__':
    print("Testing Funding Rate Data Plugin\n")

    # Test fetching 30 days of data
    result = get_data(days='30', asset='btc')

    print(f"\nMetadata: {result['metadata']['label']}")
    print(f"Data points: {len(result['data'])}")

    if result['data']:
        print(f"\nFirst record: {result['data'][0]}")
        print(f"Last record: {result['data'][-1]}")

        # Show some statistics
        rates = [r[1] for r in result['data']]
        print(f"\nFunding Rate Statistics:")
        print(f"  Min: {min(rates):.4f}%")
        print(f"  Max: {max(rates):.4f}%")
        print(f"  Avg: {sum(rates)/len(rates):.4f}%")
