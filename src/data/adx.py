# data/adx.py
"""
ADX (Average Directional Index) Indicator

Calculates ADX from asset OHLC data with incremental fetching.
ADX measures trend strength (not direction) on a 0-100 scale.

Formula:
- +DM = max(high[t] - high[t-1], 0) if high[t] - high[t-1] > low[t-1] - low[t], else 0
- -DM = max(low[t-1] - low[t], 0) if low[t-1] - low[t] > high[t] - high[t-1], else 0
- True Range = max(high - low, abs(high - prev_close), abs(low - prev_close))
- +DI = (smooth +DM / ATR) × 100
- -DI = (smooth -DM / ATR) × 100
- DX = |+DI - -DI| / (+DI + -DI) × 100
- ADX = Wilder's smooth of DX over period (default: 14)

Standard period: 14

Interpretation:
- ADX < 25: Weak or absent trend
- ADX 25-50: Strong trend
- ADX > 50: Very strong trend
- ADX > 75: Extremely strong trend (rare)
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
        'label': f'ADX ({asset_name})',
        'oscillator': True,
        'yAxisId': 'oscillator',
        'yAxisLabel': 'ADX (Trend Strength)',
        'unit': '',
        'chartType': 'line',
        'color': '#673AB7',  # Deep Purple
        'strokeWidth': 2,
        'description': f'Average Directional Index for {asset_name} - Measures trend strength (0-100)',
        'data_structure': 'simple',
        'components': ['timestamp', 'adx_value'],
        'referenceLines': [
            {'value': 25, 'label': 'Trend Threshold', 'color': '#888'}
        ]
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


def calculate_adx(high, low, close, period=14):
    """
    Calculate ADX (Average Directional Index).

    Args:
        high (list): List of high prices
        low (list): List of low prices
        close (list): List of closing prices
        period (int): ADX period (default: 14)

    Returns:
        list: ADX values (first period*2-1 values will be None)
    """
    if len(high) < period + 1 or len(low) < period + 1 or len(close) < period + 1:
        return [None] * len(high)

    n = len(high)

    # Step 1: Calculate directional movements (+DM, -DM) and True Range
    plus_dm = []
    minus_dm = []
    true_range = []

    for i in range(1, n):
        # Directional movements
        up_move = high[i] - high[i-1]
        down_move = low[i-1] - low[i]

        # +DM: upward movement if greater than downward movement, else 0
        if up_move > down_move and up_move > 0:
            plus_dm.append(up_move)
        else:
            plus_dm.append(0)

        # -DM: downward movement if greater than upward movement, else 0
        if down_move > up_move and down_move > 0:
            minus_dm.append(down_move)
        else:
            minus_dm.append(0)

        # True Range
        tr = max(
            high[i] - low[i],
            abs(high[i] - close[i-1]),
            abs(low[i] - close[i-1])
        )
        true_range.append(tr)

    # Step 2: Smooth +DM, -DM, and TR using Wilder's smoothing
    smooth_plus_dm = wilder_smooth(plus_dm, period)
    smooth_minus_dm = wilder_smooth(minus_dm, period)
    smooth_tr = wilder_smooth(true_range, period)  # This is ATR

    # Step 3: Calculate +DI and -DI
    plus_di = []
    minus_di = []

    for i in range(len(smooth_tr)):
        if smooth_tr[i] is not None and smooth_tr[i] > 0:
            plus_di.append((smooth_plus_dm[i] / smooth_tr[i]) * 100)
            minus_di.append((smooth_minus_dm[i] / smooth_tr[i]) * 100)
        else:
            plus_di.append(None)
            minus_di.append(None)

    # Step 4: Calculate DX (Directional Index)
    dx = []

    for i in range(len(plus_di)):
        if plus_di[i] is not None and minus_di[i] is not None:
            di_sum = plus_di[i] + minus_di[i]
            if di_sum > 0:
                dx_value = (abs(plus_di[i] - minus_di[i]) / di_sum) * 100
                dx.append(dx_value)
            else:
                dx.append(None)
        else:
            dx.append(None)

    # Step 5: Smooth DX to get ADX
    # Extract non-None DX values for smoothing
    dx_values_clean = [v for v in dx if v is not None]

    if len(dx_values_clean) < period:
        # Not enough data for ADX
        return [None] * n

    adx_smooth = wilder_smooth(dx_values_clean, period)

    # Map ADX back to original timeline (accounting for initial None at start)
    adx = [None] * (n - len(dx))  # Account for first bar not having DM/TR

    adx_idx = 0
    for i in range(len(dx)):
        if dx[i] is not None:
            adx.append(adx_smooth[adx_idx])
            adx_idx += 1
        else:
            adx.append(None)

    return adx


def calculate_adx_from_ohlcv(ohlcv_data, period=14):
    """
    Calculate ADX from OHLCV data.

    Args:
        ohlcv_data (list): [[timestamp, open, high, low, close, volume], ...]
        period (int): ADX period (default: 14)

    Returns:
        list: [[timestamp, adx_value], ...] (skips None values)
    """
    if not ohlcv_data or len(ohlcv_data) < period * 2:
        return []

    # Extract OHLC components
    high = [item[2] for item in ohlcv_data]
    low = [item[3] for item in ohlcv_data]
    close = [item[4] for item in ohlcv_data]

    # Calculate ADX
    adx_values = calculate_adx(high, low, close, period)

    # Pair timestamps with ADX values, skip None values
    result = []
    for i, item in enumerate(ohlcv_data):
        timestamp = item[0]
        adx_value = adx_values[i]

        if adx_value is not None:
            result.append([timestamp, adx_value])

    return result


def get_data(days='365', asset='btc', period=14):
    """
    Fetches ADX data using incremental fetching strategy.

    Args:
        days (str): Number of days to return ('7', '30', '180', '1095', 'max')
        asset (str): Asset name ('btc', 'eth', 'gold')
        period (int): ADX period (default: 14)

    Returns:
        dict: {
            'metadata': metadata dict,
            'data': [[timestamp, adx_value], ...],
            'structure': 'simple'
        }
    """
    metadata = get_metadata(asset)
    dataset_name = f'adx_{asset}'

    try:
        requested_days = int(days) if days != 'max' else 1095

        # Need extra days for ADX calculation (period for smoothing × 2 + buffer)
        fetch_days = requested_days + (period * 2) + 20

        # Load existing historical ADX data
        historical_data = load_historical_data(dataset_name)

        # Import the asset price module dynamically
        if asset == 'btc':
            from . import btc_price as asset_module
        elif asset == 'eth':
            from . import eth_price as asset_module
        elif asset == 'gold':
            from . import gold_price as asset_module
        else:
            raise ValueError(f"Unsupported asset: {asset}")

        # Fetch asset OHLCV data
        print(f"[ADX {asset.upper()}] Fetching {asset.upper()} price data for ADX calculation...")
        asset_data_result = asset_module.get_data(str(fetch_days))
        asset_ohlcv_data = asset_data_result['data']

        if not asset_ohlcv_data:
            raise ValueError(f"No {asset.upper()} price data available for ADX calculation")

        print(f"[ADX {asset.upper()}] Calculating ADX from {len(asset_ohlcv_data)} price data points...")

        # Calculate ADX from OHLCV data
        calculated_adx = calculate_adx_from_ohlcv(asset_ohlcv_data, period)

        if not calculated_adx:
            raise ValueError("ADX calculation returned no data")

        print(f"[ADX {asset.upper()}] Calculated {len(calculated_adx)} ADX values")

        # Merge with historical data
        merged_data = merge_and_deduplicate(
            existing_data=historical_data,
            new_data=calculated_adx,
            overlap_days=fetch_days
        )

        # Validate data structure
        is_valid, structure_type, error_msg = validate_data_structure(merged_data)
        if not is_valid:
            print(f"[ADX {asset.upper()}] Warning: Data validation failed: {error_msg}")

        # Save complete historical dataset
        save_historical_data(dataset_name, merged_data)

        # Filter to requested days
        if days != 'max':
            cutoff_date = datetime.now(tz=timezone.utc) - timedelta(days=int(days))
            cutoff_ms = int(cutoff_date.timestamp() * 1000)
            filtered_data = [d for d in merged_data if d[0] >= cutoff_ms]
        else:
            filtered_data = merged_data

        print(f"[ADX {asset.upper()}] Returning {len(filtered_data)} ADX data points")
        if filtered_data:
            print(f"[ADX {asset.upper()}] Date range: {datetime.fromtimestamp(filtered_data[0][0]/1000, tz=timezone.utc).date()} to {datetime.fromtimestamp(filtered_data[-1][0]/1000, tz=timezone.utc).date()}")
            values = [d[1] for d in filtered_data]
            print(f"[ADX {asset.upper()}] ADX range: {min(values):.2f} to {max(values):.2f}")

        return {
            'metadata': metadata,
            'data': filtered_data,
            'structure': 'simple'
        }

    except Exception as e:
        print(f"[ADX {asset.upper()}] Error in get_data: {e}")

        # Fallback to historical data if available
        historical_data = load_historical_data(dataset_name)
        if historical_data:
            print(f"[ADX {asset.upper()}] Falling back to historical data ({len(historical_data)} records)")

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
                'structure': 'simple'
            }

        # No data available at all
        print(f"[ADX {asset.upper()}] No historical data available for fallback")
        return {
            'metadata': metadata,
            'data': [],
            'structure': 'simple'
        }
