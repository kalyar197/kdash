# data/gold_price.py
"""
Gold price fetcher using FMP API with incremental fetching
Returns OHLC data structure: [timestamp, open, high, low, close, volume]
Uses incremental data manager to fetch only new data after initial load
Note: Volume is set to 0 for gold spot price (not applicable)
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
from config import FMP_API_KEY

def get_metadata():
    """Returns metadata describing how this data should be displayed"""
    return {
        'label': 'Gold (XAU/USD)',
        'yAxisId': 'price_usd',
        'yAxisLabel': 'Price per Oz (USD)',
        'unit': '$',
        'chartType': 'line',
        'color': '#FFD700',  # Gold color
        'strokeWidth': 2,
        'description': 'Gold spot price per troy ounce with incremental fetching',
        'data_structure': 'OHLCV',
        'components': ['timestamp', 'open', 'high', 'low', 'close', 'volume']
    }

def fetch_from_fmp(start_date, end_date):
    """
    Fetch Gold OHLC data from FMP for a specific date range.

    Args:
        start_date (datetime): Start date for data fetch
        end_date (datetime): End date for data fetch

    Returns:
        list: Raw OHLCV data [[timestamp, open, high, low, close, volume], ...]
    """
    print(f"[Gold Price] Fetching Gold OHLC from FMP: {start_date.date()} to {end_date.date()}")

    # FMP stable endpoint configuration
    base_url = 'https://financialmodelingprep.com/stable/historical-price-eod/full'

    # API parameters
    params = {
        'symbol': 'GCUSD',  # Gold Continuous Contract
        'apikey': FMP_API_KEY
    }

    try:
        # Make the API request
        response = requests.get(base_url, params=params, timeout=30)
        response.raise_for_status()

        data = response.json()

        if not data:
            raise ValueError("No data returned from FMP")

        # Extract historical data array
        if isinstance(data, dict) and 'historical' in data:
            historical_data = data['historical']
        elif isinstance(data, list):
            historical_data = data
        else:
            raise ValueError(f"Unexpected FMP response structure: {type(data)}")

        if not historical_data:
            raise ValueError("Empty historical data from FMP")

        # Process the OHLC data
        raw_data = []
        for item in historical_data:
            # Extract date and OHLC values
            date_str = item.get('date')
            open_price = item.get('open')
            high_price = item.get('high')
            low_price = item.get('low')
            close_price = item.get('close')

            # Validate all components exist
            if (date_str and
                open_price is not None and
                high_price is not None and
                low_price is not None and
                close_price is not None):

                # Parse the date string
                try:
                    dt = datetime.strptime(date_str, '%Y-%m-%d')
                    dt = dt.replace(tzinfo=timezone.utc)
                    timestamp_ms = int(dt.timestamp() * 1000)
                except ValueError:
                    print(f"[Gold Price] Warning: Could not parse date {date_str}, skipping...")
                    continue

                # Filter by date range
                if dt < start_date or dt > end_date:
                    continue

                # Skip weekends (market hours only: Mon-Fri)
                if dt.weekday() in [5, 6]:  # Saturday=5, Sunday=6
                    continue

                # Store as OHLCV (volume = 0 for gold spot)
                raw_data.append([
                    timestamp_ms,
                    float(open_price),
                    float(high_price),
                    float(low_price),
                    float(close_price),
                    0.0  # Gold spot price doesn't have volume
                ])
            else:
                print(f"[Gold Price] Warning: Incomplete OHLC data for {date_str}, skipping...")

        if not raw_data:
            raise ValueError("No valid OHLC data extracted from FMP response")

        # Sort by timestamp (oldest first)
        raw_data.sort(key=lambda x: x[0])

        print(f"[Gold Price] Successfully fetched {len(raw_data)} OHLC data points from FMP")
        if raw_data:
            print(f"[Gold Price] Sample data: timestamp={raw_data[0][0]}, O=${raw_data[0][1]:.2f}, H=${raw_data[0][2]:.2f}, L=${raw_data[0][3]:.2f}, C=${raw_data[0][4]:.2f}")

        return raw_data

    except requests.exceptions.RequestException as e:
        print(f"[Gold Price] API request failed: {e}")
        raise
    except Exception as e:
        print(f"[Gold Price] Error fetching from FMP: {e}")
        raise

def get_data(days='365'):
    """
    Fetches Gold OHLC data using incremental fetching strategy.

    Strategy:
    1. Check if historical data exists
    2. If exists: Fetch only from (last_timestamp - 3 days) to now
    3. If not: Fetch full history (e.g., 365 days)
    4. Check if we need older data for requested time range
    5. Merge new data with existing historical data
    6. Save merged result to historical_data/gold_price.json
    7. Return data filtered by requested days parameter

    Args:
        days (str): Number of days to return ('7', '30', '180', '1095')

    Returns:
        dict: {
            'metadata': metadata dict,
            'data': [[timestamp, open, high, low, close, volume], ...],
            'structure': 'OHLCV'
        }
    """
    metadata = get_metadata()
    dataset_name = 'gold_price'

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
                print(f"[Gold Price] Fetching OLDER data from {older_start_date.date()} to {oldest_date.date()}")
                older_data = fetch_from_fmp(older_start_date, oldest_date)
                all_new_data.extend(older_data)
            else:
                # No historical data, fetch all
                end_date = datetime.now(tz=timezone.utc)
                print(f"[Gold Price] Fetching ALL data from {older_start_date.date()} to {end_date.date()}")
                all_data = fetch_from_fmp(older_start_date, end_date)
                all_new_data.extend(all_data)

        # Fetch new data (forward from last timestamp)
        if historical_data:
            start_date = get_fetch_start_date(
                dataset_name=dataset_name,
                overlap_days=3,
                default_days=requested_days
            )
            end_date = datetime.now(tz=timezone.utc)
            print(f"[Gold Price] Fetching NEWER data from {start_date.date()} to {end_date.date()}")
            new_forward_data = fetch_from_fmp(start_date, end_date)
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
            print(f"[Gold Price] Warning: Data structure validation failed: {error_msg}")

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
            print(f"[Gold Price] Returning {len(filtered_data)} OHLCV records with 6 components each")
            print(f"[Gold Price] Date range: {datetime.fromtimestamp(filtered_data[0][0]/1000, tz=timezone.utc).date()} to {datetime.fromtimestamp(filtered_data[-1][0]/1000, tz=timezone.utc).date()}")
        else:
            print(f"[Gold Price] Warning: No data to return after filtering")

        return {
            'metadata': metadata,
            'data': filtered_data,
            'structure': 'OHLCV'  # Explicit structure indicator
        }

    except Exception as e:
        print(f"[Gold Price] Error in get_data: {e}")

        # Fallback to historical data if available
        historical_data = load_historical_data(dataset_name)
        if historical_data:
            print(f"[Gold Price] Falling back to historical data ({len(historical_data)} records)")

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
        print(f"[Gold Price] No historical data available for fallback")
        return {
            'metadata': metadata,
            'data': [],
            'structure': 'OHLCV'
        }
