# data/eth_price.py
"""
Ethereum OHLCV data fetcher using CoinAPI with incremental fetching
Returns FULL OHLCV data structure: [timestamp, open, high, low, close, volume]
Uses incremental data manager to fetch only new data after initial load
"""

import requests
from .time_transformer import standardize_to_daily_utc
from .incremental_data_manager import (
    load_historical_data,
    save_historical_data,
    get_fetch_start_date,
    merge_and_deduplicate,
    validate_data_structure,
    needs_older_data,
    get_oldest_timestamp
)
from datetime import datetime, timedelta, timezone
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import COINAPI_KEY

def get_metadata():
    """Returns metadata describing how this data should be displayed"""
    return {
        'label': 'Ethereum (ETH)',
        'yAxisId': 'price_usd',
        'yAxisLabel': 'Price (USD)',
        'unit': '$',
        'chartType': 'line',
        'color': '#627EEA',  # Ethereum purple
        'strokeWidth': 2,
        'description': 'Ethereum OHLCV data with incremental fetching',
        'data_structure': 'OHLCV',
        'components': ['timestamp', 'open', 'high', 'low', 'close', 'volume']
    }

def fetch_from_coinapi(start_date, end_date):
    """
    Fetch ETH OHLCV data from CoinAPI for a specific date range.

    Args:
        start_date (datetime): Start date for data fetch
        end_date (datetime): End date for data fetch

    Returns:
        list: Raw OHLCV data [[timestamp, open, high, low, close, volume], ...]
    """
    print(f"[ETH Price] Fetching ETH OHLCV from CoinAPI: {start_date.date()} to {end_date.date()}")

    # CoinAPI OHLCV History endpoint configuration
    base_url = 'https://rest.coinapi.io/v1/ohlcv'
    symbol_id = 'BINANCE_SPOT_ETH_USDT'  # High-volume reliable symbol

    # Format dates for CoinAPI (ISO 8601)
    time_start = start_date.strftime('%Y-%m-%dT00:00:00')
    time_end = end_date.strftime('%Y-%m-%dT23:59:59')

    # Construct the API URL
    url = f'{base_url}/{symbol_id}/history'

    # API parameters
    params = {
        'period_id': '1DAY',  # Daily candles
        'time_start': time_start,
        'time_end': time_end,
        'limit': 100000  # Max limit to get all available data
    }

    # Headers with API key
    headers = {
        'X-CoinAPI-Key': COINAPI_KEY
    }

    try:
        # Make the API request
        response = requests.get(url, params=params, headers=headers, timeout=30)
        response.raise_for_status()

        data = response.json()

        if not data:
            raise ValueError("No data returned from CoinAPI")

        # Process the FULL OHLCV data - ALL 6 COMPONENTS
        raw_data = []
        for candle in data:
            # Extract ALL OHLCV components
            timestamp_str = candle.get('time_period_start')

            # CRITICAL: Extract all 6 components
            open_price = candle.get('price_open')
            high_price = candle.get('price_high')
            low_price = candle.get('price_low')
            close_price = candle.get('price_close')
            volume_traded = candle.get('volume_traded')

            # Validate all components exist
            if (timestamp_str and
                open_price is not None and
                high_price is not None and
                low_price is not None and
                close_price is not None and
                volume_traded is not None):

                # Parse the ISO timestamp
                dt = datetime.fromisoformat(timestamp_str.replace('Z', '+00:00'))
                timestamp_ms = int(dt.timestamp() * 1000)

                # CRITICAL: Store all 6 components
                raw_data.append([
                    timestamp_ms,
                    float(open_price),
                    float(high_price),
                    float(low_price),
                    float(close_price),
                    float(volume_traded)
                ])
            else:
                print(f"[ETH Price] Warning: Incomplete OHLCV data for {timestamp_str}, skipping...")

        if not raw_data:
            raise ValueError("No valid OHLCV data extracted from CoinAPI response")

        # Sort by timestamp (oldest first)
        raw_data.sort(key=lambda x: x[0])

        print(f"[ETH Price] Successfully fetched {len(raw_data)} OHLCV data points from CoinAPI")
        if raw_data:
            print(f"[ETH Price] Sample data: timestamp={raw_data[0][0]}, O=${raw_data[0][1]:.2f}, H=${raw_data[0][2]:.2f}, L=${raw_data[0][3]:.2f}, C=${raw_data[0][4]:.2f}, V={raw_data[0][5]:.2f}")

        return raw_data

    except requests.exceptions.RequestException as e:
        print(f"[ETH Price] API request failed: {e}")
        raise
    except Exception as e:
        print(f"[ETH Price] Error fetching from CoinAPI: {e}")
        raise

def get_data(days='365'):
    """
    Fetches Ethereum FULL OHLCV data using incremental fetching strategy.

    Strategy:
    1. Check if historical data exists
    2. If exists: Fetch only from (last_timestamp - 3 days) to now
    3. If not: Fetch full history (e.g., 365 days)
    4. Merge new data with existing historical data
    5. Save merged result to historical_data/eth_price.json
    6. Return data filtered by requested days parameter

    Args:
        days (str): Number of days to return ('30', '365', 'max')

    Returns:
        dict: {
            'metadata': metadata dict,
            'data': [[timestamp, open, high, low, close, volume], ...],
            'structure': 'OHLCV'
        }
    """
    metadata = get_metadata()
    dataset_name = 'eth_price'

    try:
        requested_days = int(days) if days != 'max' else 1095  # Max 3 years for 'max'

        # Load existing historical data
        historical_data = load_historical_data(dataset_name)

        # Check if we need to fetch older data
        needs_older, older_start_date = needs_older_data(dataset_name, requested_days)

        all_new_data = []

        # Fetch older historical data if needed
        if needs_older:
            oldest_timestamp = get_oldest_timestamp(dataset_name)
            if oldest_timestamp:
                # Fetch from required_start to oldest_date
                oldest_date = datetime.fromtimestamp(oldest_timestamp / 1000, tz=timezone.utc)
                print(f"[ETH Price] Fetching OLDER data from {older_start_date.date()} to {oldest_date.date()}")
                older_data = fetch_from_coinapi(older_start_date, oldest_date)
                all_new_data.extend(older_data)
            else:
                # No historical data, fetch all
                end_date = datetime.now(tz=timezone.utc)
                print(f"[ETH Price] Fetching ALL data from {older_start_date.date()} to {end_date.date()}")
                all_data = fetch_from_coinapi(older_start_date, end_date)
                all_new_data.extend(all_data)

        # Fetch new data (forward from last timestamp)
        if historical_data:
            start_date = get_fetch_start_date(
                dataset_name=dataset_name,
                overlap_days=3,
                default_days=requested_days
            )
            end_date = datetime.now(tz=timezone.utc)
            print(f"[ETH Price] Fetching NEWER data from {start_date.date()} to {end_date.date()}")
            new_forward_data = fetch_from_coinapi(start_date, end_date)
            all_new_data.extend(new_forward_data)

        # If no new data was fetched (shouldn't happen), but just in case
        if not all_new_data and not historical_data:
            raise ValueError("No data fetched and no historical data available")

        # Merge all fetched data with historical data (with 3-day overlap replacement)
        merged_data = merge_and_deduplicate(
            existing_data=historical_data,
            new_data=all_new_data,
            overlap_days=3
        )

        # Validate merged data structure
        is_valid, structure_type, error_msg = validate_data_structure(merged_data)
        if not is_valid:
            print(f"[ETH Price] Warning: Data structure validation failed: {error_msg}")

        # Standardize the OHLCV data to daily UTC format
        # time_transformer handles 6-element structure
        standardized_data = standardize_to_daily_utc(merged_data)

        # Save complete historical dataset
        save_historical_data(dataset_name, standardized_data)

        # Trim to the exact requested number of days
        if days != 'max':
            cutoff_date = datetime.now(tz=timezone.utc) - timedelta(days=int(days))
            cutoff_ms = int(cutoff_date.timestamp() * 1000)
            filtered_data = [d for d in standardized_data if d[0] >= cutoff_ms]
        else:
            filtered_data = standardized_data

        # Log structure verification
        if filtered_data:
            print(f"[ETH Price] Returning {len(filtered_data)} OHLCV records with 6 components each")
            print(f"[ETH Price] Date range: {datetime.fromtimestamp(filtered_data[0][0]/1000, tz=timezone.utc).date()} to {datetime.fromtimestamp(filtered_data[-1][0]/1000, tz=timezone.utc).date()}")
        else:
            print(f"[ETH Price] Warning: No data to return after filtering")

        return {
            'metadata': metadata,
            'data': filtered_data,
            'structure': 'OHLCV'  # Explicit structure indicator
        }

    except Exception as e:
        print(f"[ETH Price] Error in get_data: {e}")

        # Fallback to historical data if available
        historical_data = load_historical_data(dataset_name)
        if historical_data:
            print(f"[ETH Price] Falling back to historical data ({len(historical_data)} records)")

            # Filter by requested days
            if days != 'max':
                cutoff_date = datetime.now(tz=timezone.utc) - timedelta(days=int(days))
                cutoff_ms = int(cutoff_date.timestamp() * 1000)
                filtered_data = [d for d in historical_data if d[0] >= cutoff_ms]
            else:
                filtered_data = historical_data

            return {
                'metadata': metadata,
                'data': filtered_data,
                'structure': 'OHLCV'
            }

        # No data available at all
        print(f"[ETH Price] No historical data available for fallback")
        return {
            'metadata': metadata,
            'data': [],
            'structure': 'OHLCV'
        }
