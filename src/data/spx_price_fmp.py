# data/spx_price_fmp.py
"""
S&P 500 Index (SPX) price data fetcher using FMP API
Returns simple format: [timestamp, close_price] for oscillator calculations
Uses incremental data manager for caching and efficient fetching

Symbol: ^GSPC (S&P 500 index symbol in FMP)
API Endpoint: https://financialmodelingprep.com/stable/historical-price-eod/full
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from datetime import datetime, timedelta, timezone
from .incremental_data_manager import (
    load_historical_data,
    save_historical_data,
    merge_and_deduplicate
)

# FMP API configuration
try:
    from config import FMP_API_KEY
    FMP_CONFIGURED = bool(FMP_API_KEY)
except ImportError:
    print("[SPX Price FMP] Warning: FMP API key not configured in config.py")
    FMP_CONFIGURED = False

def get_metadata():
    """Returns metadata describing how this data should be displayed"""
    return {
        'label': 'SPX Price (vs BTC)',
        'yAxisId': 'indicator',
        'yAxisLabel': 'Normalized Divergence (σ)',
        'unit': 'σ',
        'chartType': 'line',
        'color': '#FF6B6B',  # Coral red color for S&P 500
        'strokeWidth': 2,
        'description': 'S&P 500 Index price oscillator',
        'data_structure': 'simple'
    }

def fetch_from_fmp(start_date, end_date):
    """
    Fetch S&P 500 (^GSPC) OHLCV data from FMP API for a specific date range.
    Converts OHLCV to simple [timestamp, close_price] format.

    Args:
        start_date (datetime): Start date for data fetch
        end_date (datetime): End date for data fetch

    Returns:
        list: Simple format [[timestamp, close_price], ...]
    """
    if not FMP_CONFIGURED:
        raise ValueError("FMP API key not configured")

    print(f"[SPX Price FMP] Fetching ^GSPC from FMP: {start_date.date()} to {end_date.date()}")

    try:
        import requests

        # FMP endpoint for S&P 500 index historical data
        # Symbol: ^GSPC (S&P 500 Index)
        url = f"https://financialmodelingprep.com/stable/historical-price-eod/full"

        params = {
            'symbol': '^GSPC',
            'apikey': FMP_API_KEY
        }

        response = requests.get(url, params=params, timeout=30)
        response.raise_for_status()

        data = response.json()

        # Extract historical data array (FMP format)
        if isinstance(data, dict) and 'historical' in data:
            historical_data = data['historical']
        elif isinstance(data, list):
            historical_data = data
        else:
            raise ValueError(f"Unexpected FMP response structure: {type(data)}")

        if not historical_data:
            raise ValueError("Empty historical data from FMP")

        # Extract OHLCV data and convert to simple format
        raw_data = []

        for item in historical_data:
            # Parse date (format: YYYY-MM-DD)
            date_str = item.get('date')
            if not date_str:
                continue

            # Convert to timestamp in milliseconds
            dt = datetime.strptime(date_str, '%Y-%m-%d')
            dt = dt.replace(tzinfo=timezone.utc)
            timestamp_ms = int(dt.timestamp() * 1000)

            # Get close price
            close_price = item.get('close')
            if close_price is None:
                continue

            # Store as simple [timestamp, close_price]
            raw_data.append([timestamp_ms, float(close_price)])

        if not raw_data:
            raise ValueError("No valid data extracted from FMP response")

        # Sort by timestamp (oldest first)
        raw_data.sort(key=lambda x: x[0])

        print(f"[SPX Price FMP] Successfully fetched {len(raw_data)} data points")
        if raw_data:
            print(f"[SPX Price FMP] Sample: timestamp={raw_data[0][0]}, close=${raw_data[0][1]:.2f}")

        return raw_data

    except Exception as e:
        print(f"[SPX Price FMP] Error fetching from FMP: {e}")
        raise

def get_data(days='1095', asset='btc'):
    """
    Fetches S&P 500 price data using incremental fetching strategy.
    Returns simple format [timestamp, close_price] for oscillator calculations.

    Args:
        days (str): Number of days to return ('30', '365', '1095', 'max')
        asset (str): Asset parameter (for compatibility, not used)

    Returns:
        dict: {
            'metadata': metadata dict,
            'data': [[timestamp, close_price], ...]
        }
    """
    metadata = get_metadata()
    dataset_name = 'spx_price_fmp'

    try:
        requested_days = int(days) if days != 'max' else 1095  # Max 3 years

        # Load existing historical data
        historical_data = load_historical_data(dataset_name)

        # Determine fetch strategy
        end_date = datetime.now(tz=timezone.utc)

        if historical_data:
            # Incremental fetch: get last 5 days + new data (overlap for safety)
            last_timestamp = historical_data[-1][0]
            last_date = datetime.fromtimestamp(last_timestamp / 1000, tz=timezone.utc)
            start_date = last_date - timedelta(days=5)

            print(f"[SPX Price FMP] Incremental fetch from {start_date.date()} to {end_date.date()}")
            new_data = fetch_from_fmp(start_date, end_date)
        else:
            # Full fetch: get all requested days
            start_date = end_date - timedelta(days=requested_days)

            print(f"[SPX Price FMP] Full fetch from {start_date.date()} to {end_date.date()}")
            new_data = fetch_from_fmp(start_date, end_date)

        # Merge with historical data
        merged_data = merge_and_deduplicate(
            existing_data=historical_data,
            new_data=new_data,
            overlap_days=5
        )

        # Save complete historical dataset
        save_historical_data(dataset_name, merged_data)

        # Filter to requested days
        if days != 'max':
            cutoff_date = datetime.now(tz=timezone.utc) - timedelta(days=int(days))
            cutoff_ms = int(cutoff_date.timestamp() * 1000)
            filtered_data = [d for d in merged_data if d[0] >= cutoff_ms]
        else:
            filtered_data = merged_data

        print(f"[SPX Price FMP] Returning {len(filtered_data)} records")
        if filtered_data:
            start_dt = datetime.fromtimestamp(filtered_data[0][0]/1000, tz=timezone.utc).date()
            end_dt = datetime.fromtimestamp(filtered_data[-1][0]/1000, tz=timezone.utc).date()
            print(f"[SPX Price FMP] Date range: {start_dt} to {end_dt}")

        return {
            'metadata': metadata,
            'data': filtered_data
        }

    except Exception as e:
        print(f"[SPX Price FMP] Error in get_data: {e}")

        # Fallback to historical data
        historical_data = load_historical_data(dataset_name)
        if historical_data:
            print(f"[SPX Price FMP] Falling back to historical data ({len(historical_data)} records)")

            # Filter by requested days
            if days != 'max':
                cutoff_date = datetime.now(tz=timezone.utc) - timedelta(days=int(days))
                cutoff_ms = int(cutoff_date.timestamp() * 1000)
                filtered_data = [d for d in historical_data if d[0] >= cutoff_ms]
            else:
                filtered_data = historical_data

            return {
                'metadata': metadata,
                'data': filtered_data
            }

        # No data available
        print(f"[SPX Price FMP] No historical data available for fallback")
        return {
            'metadata': metadata,
            'data': []
        }
