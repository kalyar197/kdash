# data/dxy_price_yfinance.py
"""
DXY (US Dollar Index) price data fetcher using Yahoo Finance.

The DXY measures the value of the USD against a basket of foreign currencies:
- Euro (EUR) - 57.6% weight
- Japanese Yen (JPY) - 13.6%
- British Pound (GBP) - 11.9%
- Canadian Dollar (CAD) - 9.1%
- Swedish Krona (SEK) - 4.2%
- Swiss Franc (CHF) - 3.6%

Returns simple format: [[timestamp, close_price], ...] for oscillator calculations.

Data Characteristics:
- Daily OHLC data (no intraday)
- Updates after market close (~4 PM ET)
- Historical data: 10+ years available
- No API key required (free Yahoo Finance data)

Use Case:
- Dollar strength indicator (inverse to crypto/gold prices)
- Macro sentiment gauge
- Risk-on/risk-off signal

Ticker Symbol: DX-Y.NYB
"""

import yfinance as yf
from datetime import datetime, timedelta, timezone
from .incremental_data_manager import (
    load_historical_data,
    save_historical_data,
    merge_and_deduplicate
)
from .time_transformer import standardize_to_daily_utc


def get_metadata():
    """
    Returns metadata describing how this data should be displayed.

    Returns:
        dict: Display metadata for frontend rendering
    """
    return {
        'label': 'DXY (vs BTC)',
        'yAxisId': 'indicator',
        'yAxisLabel': 'Normalized Divergence (σ)',
        'unit': 'σ',
        'chartType': 'line',
        'color': '#00FF00',  # Green for dollar strength
        'strokeWidth': 2,
        'description': 'US Dollar Index oscillator - measures USD strength vs basket of currencies',
        'data_structure': 'simple',  # [[timestamp, close_price], ...]
        'source': 'Yahoo Finance',
        'update_frequency': 'daily'
    }


def fetch_from_yfinance(start_date, end_date):
    """
    Fetch DXY OHLCV data from Yahoo Finance for specified date range.

    Args:
        start_date (str): Start date in 'YYYY-MM-DD' format
        end_date (str): End date in 'YYYY-MM-DD' format

    Returns:
        list: [[timestamp_ms, close_price], ...] sorted by timestamp ascending

    Raises:
        Exception: If yfinance fails to fetch data
    """
    print(f"[DXY YFinance] Fetching DXY from Yahoo Finance: {start_date} to {end_date}")

    # Create ticker object for DXY
    ticker = yf.Ticker("DX-Y.NYB")

    # Fetch historical data
    hist = ticker.history(start=start_date, end=end_date)

    if hist.empty:
        print(f"[DXY YFinance] No data returned from Yahoo Finance")
        return []

    # Convert DataFrame to simple format [[timestamp_ms, close_price], ...]
    # Filter out weekends (DXY is market hours only: Mon-Fri)
    raw_data = []
    for index, row in hist.iterrows():
        # Skip weekends (Saturday=5, Sunday=6)
        if index.weekday() in [5, 6]:
            continue

        # Convert pandas Timestamp to milliseconds
        timestamp_ms = int(index.timestamp() * 1000)
        close_price = float(row['Close'])
        raw_data.append([timestamp_ms, close_price])

    # Sort by timestamp (should already be sorted, but ensure)
    raw_data.sort(key=lambda x: x[0])

    print(f"[DXY YFinance] Successfully fetched {len(raw_data)} data points")
    if raw_data:
        print(f"[DXY YFinance] Sample: timestamp={raw_data[0][0]}, close={raw_data[0][1]}")

    return raw_data


def get_data(days='1095', asset='btc'):
    """
    Fetches DXY price data using incremental fetching strategy.

    Strategy:
    1. Load existing historical data from cache
    2. Determine date range to fetch (newer data only)
    3. Fetch from Yahoo Finance
    4. Merge with historical data
    5. Save updated cache
    6. Return requested days

    Args:
        days (str): Number of days to return ('7', '30', '365', '1095', 'max')
        asset (str): Asset parameter (unused for DXY, but required by interface)

    Returns:
        dict: {
            'metadata': metadata dict,
            'data': [[timestamp, close_price], ...] for requested period
        }

    Example:
        >>> result = get_data('30', 'btc')
        >>> len(result['data'])
        30
        >>> result['metadata']['label']
        'DXY (vs BTC)'
    """
    dataset_name = 'dxy_price'

    # Step 1: Load existing historical data
    historical_data = load_historical_data(dataset_name)

    # Step 2: Determine date range for fetching
    # Always try to fetch recent data to stay current
    end_date = datetime.now(timezone.utc)
    end_date_str = end_date.strftime('%Y-%m-%d')

    if historical_data:
        # Incremental fetch: get data from last cached timestamp onwards
        last_timestamp = historical_data[-1][0]
        last_date = datetime.fromtimestamp(last_timestamp / 1000, tz=timezone.utc)
        start_date = last_date - timedelta(days=5)  # 5-day overlap for safety
        start_date_str = start_date.strftime('%Y-%m-%d')

        print(f"[DXY YFinance] Incremental fetch from {start_date_str} to {end_date_str}")
    else:
        # First fetch: get requested days + buffer for rolling window
        if days == 'max':
            # Yahoo Finance has 10+ years of DXY data
            start_date = end_date - timedelta(days=3650)  # 10 years
        else:
            days_int = int(days)
            # Add 210 days buffer for noise_level=200 + overlap
            start_date = end_date - timedelta(days=days_int + 210)

        start_date_str = start_date.strftime('%Y-%m-%d')
        print(f"[DXY YFinance] Initial fetch from {start_date_str} to {end_date_str}")

    # Step 3: Fetch from Yahoo Finance
    try:
        new_data = fetch_from_yfinance(start_date_str, end_date_str)
    except Exception as e:
        print(f"[DXY YFinance] Error fetching from Yahoo Finance: {e}")
        # Fallback to historical data if fetch fails
        if historical_data:
            print(f"[DXY YFinance] Falling back to cached data")
            new_data = []
        else:
            raise

    # Step 4: Merge with historical data
    if new_data:
        merged_data = merge_and_deduplicate(historical_data, new_data)
        print(f"[DXY YFinance] Merged {len(historical_data)} historical + {len(new_data)} new = {len(merged_data)} total")
    else:
        merged_data = historical_data
        print(f"[DXY YFinance] No new data, using {len(merged_data)} cached records")

    # Step 5: Standardize timestamps and save updated cache
    if merged_data:
        # Standardize timestamps to daily UTC (00:00:00) for alignment with BTC
        standardized_data = standardize_to_daily_utc(merged_data)
        save_historical_data(dataset_name, standardized_data)
        print(f"[DXY YFinance] Standardized timestamps to midnight UTC for BTC alignment")
    else:
        standardized_data = []

    # Step 6: Return requested days
    if not standardized_data:
        print(f"[DXY YFinance] Warning: No data available")
        return {
            'metadata': get_metadata(),
            'data': []
        }

    if days == 'max':
        result_data = standardized_data
    else:
        days_int = int(days)
        # Return last N days (DXY is daily data, so 30 days = ~30 data points)
        result_data = standardized_data[-days_int:] if len(standardized_data) >= days_int else standardized_data

    print(f"[DXY YFinance] Returning {len(result_data)} records")
    if result_data:
        start_ts = result_data[0][0]
        end_ts = result_data[-1][0]
        start_date_obj = datetime.fromtimestamp(start_ts / 1000, tz=timezone.utc)
        end_date_obj = datetime.fromtimestamp(end_ts / 1000, tz=timezone.utc)
        print(f"[DXY YFinance] Date range: {start_date_obj.strftime('%Y-%m-%d')} to {end_date_obj.strftime('%Y-%m-%d')}")

    return {
        'metadata': get_metadata(),
        'data': result_data
    }
