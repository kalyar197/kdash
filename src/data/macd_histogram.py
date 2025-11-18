# data/macd_histogram.py
"""
MACD Histogram (Moving Average Convergence Divergence Histogram) Indicator

Calculates MACD Histogram from asset price data with incremental fetching.
MACD Histogram shows momentum acceleration/deceleration.

Formula:
- MACD Line = 12-period EMA - 26-period EMA
- Signal Line = 9-period EMA of MACD Line
- Histogram = MACD Line - Signal Line

Returns the Histogram (MACD - Signal) for momentum divergence detection.
Histogram crossing zero indicates MACD/Signal crossover (potential trade signal).
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
        'label': f'MACD Histogram ({asset_name})',
        'oscillator': True,
        'yAxisId': 'oscillator',
        'yAxisLabel': 'MACD Histogram',
        'unit': '',
        'chartType': 'line',
        'color': '#2196F3',  # Blue color
        'strokeWidth': 2,
        'description': f'MACD Histogram for {asset_name} (12,26,9) - Momentum acceleration indicator',
        'data_structure': 'simple',
        'components': ['timestamp', 'histogram_value'],
        'referenceLines': [
            {'value': 0, 'label': 'Zero Line', 'color': '#888'}
        ]
    }


def calculate_ema(prices, period):
    """
    Calculate Exponential Moving Average.

    Args:
        prices (list): List of closing prices
        period (int): EMA period

    Returns:
        list: EMA values (first 'period-1' values will be None)
    """
    if len(prices) < period:
        return [None] * len(prices)

    ema_values = [None] * (period - 1)

    # Calculate initial SMA as the first EMA value
    sma = np.mean(prices[:period])
    ema_values.append(sma)

    # Calculate EMA multiplier
    multiplier = 2 / (period + 1)

    # Calculate subsequent EMA values
    for i in range(period, len(prices)):
        ema = (prices[i] - ema_values[-1]) * multiplier + ema_values[-1]
        ema_values.append(ema)

    return ema_values


def calculate_macd(prices, fast_period=12, slow_period=26, signal_period=9):
    """
    Calculate MACD, Signal Line, and Histogram.

    Args:
        prices (list): List of closing prices
        fast_period (int): Fast EMA period (default: 12)
        slow_period (int): Slow EMA period (default: 26)
        signal_period (int): Signal line EMA period (default: 9)

    Returns:
        tuple: (macd_line, signal_line, histogram)
            Each is a list with same length as prices, with None for insufficient data
    """
    if len(prices) < slow_period:
        return [None] * len(prices), [None] * len(prices), [None] * len(prices)

    # Calculate fast and slow EMAs
    fast_ema = calculate_ema(prices, fast_period)
    slow_ema = calculate_ema(prices, slow_period)

    # Calculate MACD Line
    macd_line = []
    for i in range(len(prices)):
        if fast_ema[i] is not None and slow_ema[i] is not None:
            macd_line.append(fast_ema[i] - slow_ema[i])
        else:
            macd_line.append(None)

    # Extract non-None MACD values for signal line calculation
    macd_values_clean = [v for v in macd_line if v is not None]

    # Calculate Signal Line (EMA of MACD Line)
    if len(macd_values_clean) >= signal_period:
        signal_ema = calculate_ema(macd_values_clean, signal_period)

        # Map signal EMA back to original timeline
        signal_line = [None] * len(prices)
        signal_idx = 0
        for i in range(len(prices)):
            if macd_line[i] is not None:
                signal_line[i] = signal_ema[signal_idx]
                signal_idx += 1
    else:
        signal_line = [None] * len(prices)

    # Calculate Histogram
    histogram = []
    for i in range(len(prices)):
        if macd_line[i] is not None and signal_line[i] is not None:
            histogram.append(macd_line[i] - signal_line[i])
        else:
            histogram.append(None)

    return macd_line, signal_line, histogram


def calculate_macd_histogram_from_ohlcv(ohlcv_data, fast_period=12, slow_period=26, signal_period=9):
    """
    Calculate MACD Histogram from OHLCV data.

    Args:
        ohlcv_data (list): [[timestamp, open, high, low, close, volume], ...]
        fast_period (int): Fast EMA period
        slow_period (int): Slow EMA period
        signal_period (int): Signal line period

    Returns:
        list: [[timestamp, histogram_value], ...] (returns Histogram, skips None values)
    """
    if not ohlcv_data or len(ohlcv_data) < slow_period:
        return []

    # Extract closing prices
    close_prices = [item[4] for item in ohlcv_data]

    # Calculate MACD
    macd_line, signal_line, histogram = calculate_macd(close_prices, fast_period, slow_period, signal_period)

    # Pair timestamps with Histogram values, skip None values
    result = []
    for i, item in enumerate(ohlcv_data):
        timestamp = item[0]
        histogram_value = histogram[i]

        if histogram_value is not None:
            result.append([timestamp, histogram_value])

    return result


def get_data(days='365', asset='btc', fast_period=12, slow_period=26, signal_period=9):
    """
    Fetches MACD Histogram data using incremental fetching strategy.

    Args:
        days (str): Number of days to return
        asset (str): Asset name ('btc', 'eth', 'gold')
        fast_period (int): Fast EMA period (default: 12)
        slow_period (int): Slow EMA period (default: 26)
        signal_period (int): Signal line period (default: 9)

    Returns:
        dict: {
            'metadata': metadata dict,
            'data': [[timestamp, histogram_value], ...],
            'structure': 'simple'
        }
    """
    metadata = get_metadata(asset)
    dataset_name = f'macd_histogram_{asset}'

    try:
        requested_days = int(days) if days != 'max' else 1095

        # Need extra days for MACD calculation
        fetch_days = requested_days + slow_period + signal_period + 10

        # Load existing historical MACD Histogram data
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
        print(f"[MACD Histogram {asset.upper()}] Fetching {asset.upper()} price data for MACD Histogram calculation...")
        asset_data_result = asset_module.get_data(str(fetch_days))
        asset_ohlcv_data = asset_data_result['data']

        if not asset_ohlcv_data:
            raise ValueError(f"No {asset.upper()} price data available for MACD Histogram calculation")

        print(f"[MACD Histogram {asset.upper()}] Calculating MACD Histogram from {len(asset_ohlcv_data)} price data points...")

        # Calculate MACD Histogram from OHLCV data
        calculated_histogram = calculate_macd_histogram_from_ohlcv(asset_ohlcv_data, fast_period, slow_period, signal_period)

        if not calculated_histogram:
            raise ValueError("MACD Histogram calculation returned no data")

        print(f"[MACD Histogram {asset.upper()}] Calculated {len(calculated_histogram)} Histogram values")

        # Merge with historical data
        merged_data = merge_and_deduplicate(
            existing_data=historical_data,
            new_data=calculated_histogram,
            overlap_days=fetch_days
        )

        # Validate data structure
        is_valid, structure_type, error_msg = validate_data_structure(merged_data)
        if not is_valid:
            print(f"[MACD Histogram {asset.upper()}] Warning: Data validation failed: {error_msg}")

        # Save complete historical dataset
        save_historical_data(dataset_name, merged_data)

        # Filter to requested days
        if days != 'max':
            cutoff_date = datetime.now(tz=timezone.utc) - timedelta(days=int(days))
            cutoff_ms = int(cutoff_date.timestamp() * 1000)
            filtered_data = [d for d in merged_data if d[0] >= cutoff_ms]
        else:
            filtered_data = merged_data

        print(f"[MACD Histogram {asset.upper()}] Returning {len(filtered_data)} Histogram data points")
        if filtered_data:
            print(f"[MACD Histogram {asset.upper()}] Date range: {datetime.fromtimestamp(filtered_data[0][0]/1000, tz=timezone.utc).date()} to {datetime.fromtimestamp(filtered_data[-1][0]/1000, tz=timezone.utc).date()}")
            values = [d[1] for d in filtered_data]
            print(f"[MACD Histogram {asset.upper()}] Histogram range: {min(values):.2f} to {max(values):.2f}")

        return {
            'metadata': metadata,
            'data': filtered_data,
            'structure': 'simple'
        }

    except Exception as e:
        print(f"[MACD Histogram {asset.upper()}] Error in get_data: {e}")

        # Fallback to historical data
        historical_data = load_historical_data(dataset_name)
        if historical_data:
            print(f"[MACD Histogram {asset.upper()}] Falling back to historical data ({len(historical_data)} records)")

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

        print(f"[MACD Histogram {asset.upper()}] No historical data available for fallback")
        return {
            'metadata': metadata,
            'data': [],
            'structure': 'simple'
        }
