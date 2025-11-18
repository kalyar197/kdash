"""
Basis Spread data module (Binance Futures).

Provides BTC basis spread data from Binance Futures API with disk caching and incremental updates.
Basis Spread = Spot Price - Futures Price
Positive values indicate backwardation (spot > futures).
Negative values indicate contango (futures > spot).

Data Source: Binance Futures API (free, no API key required)
Cache: historical_data/basis_spread_btc.json
Update Strategy: Incremental daily updates appended to cache
"""

import json
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, List, Any
from data.binance_utils import fetch_recent_data, fetch_basis_spread
from data.derivatives_config import CACHE_DIR, DEFAULT_SYMBOL


def get_metadata(symbol: str = DEFAULT_SYMBOL) -> Dict[str, Any]:
    """
    Returns display metadata for basis spread oscillator.

    Args:
        symbol: Trading pair symbol (default: BTCUSDT)

    Returns:
        Metadata dictionary for frontend rendering
    """
    return {
        'label': f'{symbol} Basis Spread',
        'yAxisId': 'indicator',
        'yAxisLabel': 'Basis Spread (USD)',
        'unit': '',
        'color': '#FF6B35',  # Orange for derivatives data
        'chartType': 'line',
        'description': f'Spot vs Futures price differential for {symbol} perpetual'
    }


def load_cache(symbol: str = DEFAULT_SYMBOL) -> List[List]:
    """
    Load basis spread data from disk cache.

    Args:
        symbol: Trading pair symbol (default: BTCUSDT)

    Returns:
        List of [timestamp_ms, basis_value] tuples, sorted by timestamp
    """
    # For now, only BTC is supported
    if symbol != DEFAULT_SYMBOL:
        print(f"Warning: Only {DEFAULT_SYMBOL} basis spread is currently cached")
        return []

    cache_file = Path(CACHE_DIR) / "basis_spread_btc.json"

    if not cache_file.exists():
        print(f"Warning: {cache_file} not found. Run scripts/backfill_basis.py first.")
        return []

    with open(cache_file, 'r') as f:
        data = json.load(f)

    return sorted(data, key=lambda x: x[0])


def update_cache(symbol: str = DEFAULT_SYMBOL) -> None:
    """
    Fetch recent basis spread data and append to cache if new.

    Args:
        symbol: Trading pair symbol (default: BTCUSDT)
    """
    if symbol != DEFAULT_SYMBOL:
        return

    cache_file = Path(CACHE_DIR) / "basis_spread_btc.json"

    # Load existing data
    existing_data = load_cache(symbol)

    if not existing_data:
        print(f"No cached data for {symbol} basis spread. Run backfill script first.")
        return

    # Get latest timestamp in cache
    latest_cached_ts = existing_data[-1][0]
    latest_cached_date = datetime.fromtimestamp(latest_cached_ts / 1000)

    # Check if we need an update (more than 23 hours old)
    now = datetime.now()
    if (now - latest_cached_date).total_seconds() < 23 * 3600:
        # Data is recent, no update needed
        return

    # Fetch recent data (last 30 days to ensure we capture latest)
    print(f"Fetching latest {symbol} basis spread...")
    recent_data = fetch_recent_data(
        fetch_function=fetch_basis_spread,
        days=30,
        symbol=symbol
    )

    if not recent_data:
        print(f"Failed to fetch latest {symbol} basis spread")
        return

    # Find new data points (timestamps newer than cache)
    new_points = [point for point in recent_data if point[0] > latest_cached_ts]

    if new_points:
        # Append new points to existing data
        existing_data.extend(new_points)

        # Sort by timestamp (should already be sorted, but ensure it)
        existing_data.sort(key=lambda x: x[0])

        # Save updated cache
        cache_file.parent.mkdir(parents=True, exist_ok=True)
        with open(cache_file, 'w') as f:
            json.dump(existing_data, f, indent=2)

        print(f"Updated {symbol} basis spread cache with {len(new_points)} new points")
    else:
        print(f"{symbol} basis spread cache is up to date")


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
    Get basis spread data with automatic cache updates.

    Args:
        days: Number of days ('7', '30', '90', '365') or 'max'
        asset: 'btc' (only BTC supported currently)

    Returns:
        Dictionary with metadata and data
    """
    symbol = DEFAULT_SYMBOL  # Currently only BTCUSDT

    # Update cache with latest data (if needed)
    update_cache(symbol)

    # Load from cache
    data = load_cache(symbol)

    if not data:
        return {
            'metadata': get_metadata(symbol),
            'data': [],
            'error': f'No cached {symbol} basis spread data. Run scripts/backfill_basis.py first.'
        }

    # Filter by time range
    filtered_data = filter_by_days(data, days)

    return {
        'metadata': get_metadata(symbol),
        'data': filtered_data,
        'structure': 'simple'
    }


if __name__ == '__main__':
    # Test the module
    print("Testing Basis Spread module...")

    result = get_data('btc', '30')
    print(f"\nBTC Basis Spread (last 30 days):")
    print(f"  Metadata: {result['metadata']['label']}")
    print(f"  Data points: {len(result['data'])}")

    if result['data']:
        latest = result['data'][-1]
        latest_date = datetime.fromtimestamp(latest[0] / 1000)
        print(f"  Latest: {latest[1]:.2f} on {latest_date.date()}")

        values = [point[1] for point in result['data']]
        contango_pct = sum(1 for v in values if v < 0) / len(values) * 100
        print(f"  Contango: {contango_pct:.1f}% of the time")
