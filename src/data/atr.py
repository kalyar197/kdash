# data/atr.py
"""
ATR (Average True Range) Indicator

Calculates ATR from asset OHLC data with incremental fetching.
ATR measures market volatility on an absolute price scale.

Formula:
- True Range (TR) = max(high - low, |high - prev_close|, |low - prev_close|)
- ATR = Wilder's smooth of TR over period (default: 14)

Standard period: 14

Interpretation:
- Higher ATR: Increased volatility, larger price movements
- Lower ATR: Decreased volatility, smaller price movements
- ATR trends with price (higher price assets have higher ATR in absolute terms)
- Use ATR% (ATR/Price) for cross-asset comparisons
"""

import numpy as np
from datetime import datetime, timedelta, timezone
from .incremental_data_manager import (
    load_historical_data,
    save_historical_data,
    merge_and_deduplicate,
    validate_data_structure
)


def get_metadata(asset='btc'):
    """Returns metadata describing how this data should be displayed"""
    asset_names = {
        'btc': 'Bitcoin',
        'eth': 'Ethereum',
        'gold': 'Gold'
    }
    asset_name = asset_names.get(asset, asset.upper())

    return {
        'label': f'ATR ({asset_name})',
        'oscillator': True,
        'yAxisId': 'oscillator',
        'yAxisLabel': 'ATR (Volatility)',
        'unit': '$',
        'chartType': 'line',
        'color': '#FF5722',  # Deep Orange-Red
        'strokeWidth': 2,
        'description': f'Average True Range for {asset_name} - Measures volatility',
        'data_structure': 'simple',
        'components': ['timestamp', 'atr_value']
    }


def wilder_smooth(values, period):
    """
    Apply Wilder's smoothing (modified EMA).

    Formula: smooth[t] = (smooth[t-1] * (period - 1) + value[t]) / period

    Args:
        values (list): List of values to smooth
        period (int): Smoothing period

    Returns:
        list: Smoothed values (first 'period' values will be None, then SMA, then Wilder smooth)
    """
    if len(values) < period:
        return [None] * len(values)

    smoothed = [None] * (period - 1)

    # First smoothed value is simple average
    first_smooth = np.mean(values[:period])
    smoothed.append(first_smooth)

    # Subsequent values use Wilder's smoothing
    for i in range(period, len(values)):
        smooth = (smoothed[-1] * (period - 1) + values[i]) / period
        smoothed.append(smooth)

    return smoothed


def calculate_atr(high, low, close, period=14):
    """
    Calculate ATR (Average True Range).

    Args:
        high (list): List of high prices
        low (list): List of low prices
        close (list): List of closing prices
        period (int): ATR period (default: 14)

    Returns:
        list: ATR values (first period values will be None)
    """
    if len(high) < period + 1 or len(low) < period + 1 or len(close) < period + 1:
        return [None] * len(high)

    n = len(high)
    true_range = []

    # Calculate True Range for each bar (starting from index 1)
    for i in range(1, n):
        tr = max(
            high[i] - low[i],                # High - Low
            abs(high[i] - close[i-1]),       # |High - Previous Close|
            abs(low[i] - close[i-1])         # |Low - Previous Close|
        )
        true_range.append(tr)

    # Apply Wilder's smoothing to get ATR
    atr_smooth = wilder_smooth(true_range, period)

    # Add initial None to account for first bar not having TR
    atr = [None] + atr_smooth

    return atr


def calculate_atr_from_ohlcv(ohlcv_data, period=14):
    """
    Calculate ATR from OHLCV data.

    Args:
        ohlcv_data (list): [[timestamp, open, high, low, close, volume], ...]
        period (int): ATR period (default: 14)

    Returns:
        list: [[timestamp, atr_value], ...] (skips None values)
    """
    if not ohlcv_data or len(ohlcv_data) < period + 1:
        return []

    # Extract OHLC components
    high = [item[2] for item in ohlcv_data]
    low = [item[3] for item in ohlcv_data]
    close = [item[4] for item in ohlcv_data]

    # Calculate ATR
    atr_values = calculate_atr(high, low, close, period)

    # Pair timestamps with ATR values, skip None values
    result = []
    for i, item in enumerate(ohlcv_data):
        timestamp = item[0]
        atr_value = atr_values[i]

        if atr_value is not None:
            result.append([timestamp, atr_value])

    return result


def get_data(days='365', asset='btc', period=14):
    """
    Fetches ATR data using incremental fetching strategy.

    Args:
        days (str): Number of days to return ('7', '30', '180', '1095', 'max')
        asset (str): Asset name ('btc', 'eth', 'gold')
        period (int): ATR period (default: 14)

    Returns:
        dict: {
            'metadata': metadata dict,
            'data': [[timestamp, atr_value], ...],
            'structure': 'simple'
        }
    """
    metadata = get_metadata(asset)
    dataset_name = f'atr_{asset}'

    try:
        # Load historical ATR data from disk
        historical_data = load_historical_data(dataset_name)

        # Determine required price data days
        # Need extra days for ATR calculation (period + buffer)
        if days == 'max':
            price_days = 'max'
        else:
            price_days = str(int(days) + period + 10)

        # Import asset price module dynamically
        if asset == 'btc':
            from . import btc_price
            price_module = btc_price
        elif asset == 'eth':
            from . import eth_price
            price_module = eth_price
        elif asset == 'gold':
            from . import gold_price
            price_module = gold_price
        else:
            raise ValueError(f"Unknown asset: {asset}")

        print(f"[ATR {asset.upper()}] Fetching {asset.upper()} price data for ATR calculation...")
        price_result = price_module.get_data(price_days)
        ohlcv_data = price_result['data']

        if not ohlcv_data:
            raise ValueError(f"No {asset.upper()} price data available")

        print(f"[ATR {asset.upper()}] Calculating ATR from {len(ohlcv_data)} price data points...")

        # Calculate ATR from OHLCV data
        new_atr_data = calculate_atr_from_ohlcv(ohlcv_data, period)

        if not new_atr_data:
            raise ValueError("ATR calculation failed")

        print(f"[ATR {asset.upper()}] Calculated {len(new_atr_data)} ATR values")

        # Merge with historical data
        # Use keyword arguments to avoid passing dataset_name as overlap_days
        merged_data = merge_and_deduplicate(
            existing_data=historical_data,
            new_data=new_atr_data
        )

        # Validate and save
        is_valid, structure_type, error_msg = validate_data_structure(merged_data)
        if not is_valid:
            raise ValueError(f"Invalid data structure: {error_msg}")
        save_historical_data(dataset_name, merged_data)

        # Return requested number of days
        if days == 'max':
            final_data = merged_data
        else:
            days_int = int(days)
            cutoff_timestamp = merged_data[-1][0] - (days_int * 24 * 60 * 60 * 1000)
            final_data = [d for d in merged_data if d[0] >= cutoff_timestamp]

        print(f"[ATR {asset.upper()}] Returning {len(final_data)} ATR data points")

        if final_data:
            start_date = datetime.fromtimestamp(final_data[0][0] / 1000, tz=timezone.utc).strftime('%Y-%m-%d')
            end_date = datetime.fromtimestamp(final_data[-1][0] / 1000, tz=timezone.utc).strftime('%Y-%m-%d')
            print(f"[ATR {asset.upper()}] Date range: {start_date} to {end_date}")
            print(f"[ATR {asset.upper()}] ATR range: {min(d[1] for d in final_data):.2f} to {max(d[1] for d in final_data):.2f}")

        return {
            'metadata': metadata,
            'data': final_data,
            'structure': 'simple'
        }

    except Exception as e:
        print(f"[ATR {asset.upper()}] Error in get_data: {e}")
        import traceback
        traceback.print_exc()
        return {
            'metadata': metadata,
            'data': [],
            'structure': 'simple'
        }
