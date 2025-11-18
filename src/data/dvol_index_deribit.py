"""
DVOL Index (Deribit Volatility Index) data module.

Provides BTC and ETH DVOL data from Deribit API with disk caching and incremental updates.
DVOL represents the market's expectation of 30-day future volatility calculated from option prices.

Data Source: Deribit API (free, no API key required)
Cache: historical_data/dvol_{currency}.json
Update Strategy: Incremental daily updates appended to cache
"""

import json
import os
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, List, Any
from data.deribit_utils import get_latest_dvol
from data.derivatives_config import CACHE_DIR


def get_metadata(currency: str = 'BTC') -> Dict[str, Any]:
    """
    Returns display metadata for DVOL oscillator.

    Args:
        currency: 'BTC' or 'ETH'

    Returns:
        Metadata dictionary for frontend rendering
    """
    return {
        'label': f'{currency} DVOL Index',
        'yAxisId': 'indicator',
        'yAxisLabel': 'DVOL Value',
        'unit': '',
        'color': '#9D4EDD',  # Purple for volatility
        'chartType': 'line',
        'description': f'Deribit {currency} Volatility Index - 30-day implied volatility from options'
    }


def load_cache(currency: str = 'BTC') -> List[List]:
    """
    Load DVOL data from disk cache.

    Args:
        currency: 'BTC' or 'ETH'

    Returns:
        List of [timestamp_ms, dvol_value] tuples, sorted by timestamp
    """
    cache_file = Path(CACHE_DIR) / f"dvol_{currency.lower()}.json"

    if not cache_file.exists():
        print(f"Warning: {cache_file} not found. Run scripts/backfill_dvol.py first.")
        return []

    with open(cache_file, 'r') as f:
        data = json.load(f)

    return sorted(data, key=lambda x: x[0])


def update_cache(currency: str = 'BTC') -> None:
    """
    Fetch latest DVOL value and append to cache if new.

    Args:
        currency: 'BTC' or 'ETH'
    """
    cache_file = Path(CACHE_DIR) / f"dvol_{currency.lower()}.json"

    # Load existing data
    existing_data = load_cache(currency)

    if not existing_data:
        print(f"No cached data for {currency} DVOL. Run backfill script first.")
        return

    # Get latest timestamp in cache
    latest_cached_ts = existing_data[-1][0]
    latest_cached_date = datetime.fromtimestamp(latest_cached_ts / 1000)

    # Check if we need an update (more than 23 hours old)
    now = datetime.now()
    if (now - latest_cached_date).total_seconds() < 23 * 3600:
        # Data is recent, no update needed
        return

    # Fetch latest DVOL
    print(f"Fetching latest {currency} DVOL...")
    latest_point = get_latest_dvol(currency)

    if not latest_point:
        print(f"Failed to fetch latest {currency} DVOL")
        return

    latest_ts, latest_value = latest_point

    # Only append if timestamp is newer than cache
    if latest_ts > latest_cached_ts:
        existing_data.append([latest_ts, latest_value])

        # Save updated cache
        cache_file.parent.mkdir(parents=True, exist_ok=True)
        with open(cache_file, 'w') as f:
            json.dump(existing_data, f, indent=2)

        print(f"Updated {currency} DVOL cache with latest value: {latest_value}")
    else:
        print(f"{currency} DVOL cache is up to date")


def filter_by_days(data: List[List], days: str) -> List[List]:
    """
    Filter data by number of days or return all.

    Args:
        data: List of [timestamp_ms, value] tuples
        days: Number of days ('7', '30', '90', '365') or 'max'

    Returns:
        Filtered data
    """
    if days == 'max':
        return data

    try:
        num_days = int(days)
        cutoff_ts = (datetime.now() - timedelta(days=num_days)).timestamp() * 1000
        return [point for point in data if point[0] >= cutoff_ts]
    except ValueError:
        return data


def get_data(days: str = '365', asset: str = 'btc') -> Dict[str, Any]:
    """
    Get DVOL data with automatic cache updates.

    Args:
        days: Number of days ('7', '30', '90', '365') or 'max'
        asset: 'btc' or 'eth' (converted to uppercase for API)

    Returns:
        Dictionary with metadata and data
    """
    currency = asset.upper()

    # Update cache with latest data (if needed)
    update_cache(currency)

    # Load from cache
    data = load_cache(currency)

    if not data:
        return {
            'metadata': get_metadata(currency),
            'data': [],
            'error': f'No cached {currency} DVOL data. Run scripts/backfill_dvol.py first.'
        }

    # Filter by time range
    filtered_data = filter_by_days(data, days)

    return {
        'metadata': get_metadata(currency),
        'data': filtered_data,
        'structure': 'simple'
    }


if __name__ == '__main__':
    # Test the module
    print("Testing DVOL Index module...")

    result = get_data('btc', '30')
    print(f"\nBTC DVOL (last 30 days):")
    print(f"  Metadata: {result['metadata']['label']}")
    print(f"  Data points: {len(result['data'])}")

    if result['data']:
        latest = result['data'][-1]
        latest_date = datetime.fromtimestamp(latest[0] / 1000)
        print(f"  Latest: {latest[1]:.2f} on {latest_date.date()}")
