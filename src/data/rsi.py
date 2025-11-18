# data/rsi.py
"""
RSI (Relative Strength Index) Indicator

Calculates RSI from asset price data with incremental fetching.
RSI measures the magnitude of recent price changes to evaluate overbought/oversold conditions.

Formula: RSI = 100 - (100 / (1 + RS))
where RS = Average Gain / Average Loss over the period

Standard interpretation:
- RSI > 70: Overbought
- RSI < 30: Oversold
- RSI = 50: Neutral momentum
"""

import numpy as np
from datetime import datetime, timedelta, timezone
from .incremental_data_manager import (
    load_historical_data,
    save_historical_data,
    get_fetch_start_date,
    merge_and_deduplicate,
    validate_data_structure,
    needs_older_data,
    get_oldest_timestamp
)
from .time_transformer import extract_component


def get_metadata(asset='btc'):
    """Returns metadata describing how this data should be displayed"""
    asset_names = {
        'btc': 'Bitcoin',
        'eth': 'Ethereum',
        'gold': 'Gold'
    }
    asset_name = asset_names.get(asset, asset.upper())

    return {
        'label': f'RSI ({asset_name})',
        'oscillator': True,  # Flag to identify as oscillator dataset
        'yAxisId': 'oscillator',
        'yAxisLabel': 'RSI',
        'unit': '',
        'chartType': 'line',
        'color': '#FF9500',  # Orange color
        'strokeWidth': 2,
        'description': f'Relative Strength Index for {asset_name} (14-period)',
        'data_structure': 'simple',
        'components': ['timestamp', 'rsi_value'],
        'yDomain': [0, 100],  # RSI always between 0 and 100
        'referenceLines': [
            {'value': 70, 'label': 'Overbought', 'color': '#ef5350'},
            {'value': 50, 'label': 'Neutral', 'color': '#888'},
            {'value': 30, 'label': 'Oversold', 'color': '#26a69a'}
        ]
    }


def calculate_rsi(prices, period=14):
    """
    Calculate RSI from price data.

    Args:
        prices (list): List of closing prices
        period (int): RSI period (default: 14)

    Returns:
        list: RSI values (same length as prices, first 'period' values will be None)
    """
    if len(prices) < period + 1:
        return [None] * len(prices)

    # Calculate price changes
    deltas = np.diff(prices)

    # Separate gains and losses
    gains = np.where(deltas > 0, deltas, 0)
    losses = np.where(deltas < 0, -deltas, 0)

    # Calculate initial average gain and loss using SMA
    avg_gain = np.mean(gains[:period])
    avg_loss = np.mean(losses[:period])

    rsi_values = [None] * period  # First 'period' values can't be calculated

    # Calculate first RSI
    if avg_loss == 0:
        rsi = 100.0
    else:
        rs = avg_gain / avg_loss
        rsi = 100.0 - (100.0 / (1.0 + rs))

    rsi_values.append(rsi)

    # Calculate subsequent RSI values using Wilder's smoothing
    for i in range(period, len(deltas)):
        gain = gains[i]
        loss = losses[i]

        # Wilder's smoothing
        avg_gain = (avg_gain * (period - 1) + gain) / period
        avg_loss = (avg_loss * (period - 1) + loss) / period

        if avg_loss == 0:
            rsi = 100.0
        else:
            rs = avg_gain / avg_loss
            rsi = 100.0 - (100.0 / (1.0 + rs))

        rsi_values.append(rsi)

    return rsi_values


def calculate_rsi_from_ohlcv(ohlcv_data, period=14):
    """
    Calculate RSI from OHLCV data.

    Args:
        ohlcv_data (list): [[timestamp, open, high, low, close, volume], ...]
        period (int): RSI period (default: 14)

    Returns:
        list: [[timestamp, rsi_value], ...] (first 'period' points will be None)
    """
    if not ohlcv_data or len(ohlcv_data) < period + 1:
        return []

    # Extract closing prices
    close_prices = [item[4] for item in ohlcv_data]  # Index 4 is close price

    # Calculate RSI
    rsi_values = calculate_rsi(close_prices, period)

    # Pair timestamps with RSI values, skip None values
    result = []
    for i, item in enumerate(ohlcv_data):
        timestamp = item[0]
        rsi_value = rsi_values[i]

        if rsi_value is not None:
            result.append([timestamp, rsi_value])

    return result


def get_data(days='365', asset='btc', period=14):
    """
    Fetches RSI data using incremental fetching strategy.

    Strategy:
    1. Load historical RSI data from disk
    2. Check if we need older data for requested time range
    3. Fetch asset price data (OHLCV)
    4. Calculate RSI from price data
    5. Merge with historical data using overlap strategy
    6. Save to historical_data/rsi_{asset}.json
    7. Return filtered by requested days

    Args:
        days (str): Number of days to return ('7', '30', '180', '1095', 'max')
        asset (str): Asset name ('btc', 'eth', 'gold')
        period (int): RSI period (default: 14)

    Returns:
        dict: {
            'metadata': metadata dict,
            'data': [[timestamp, rsi_value], ...],
            'structure': 'simple'
        }
    """
    metadata = get_metadata(asset)
    dataset_name = f'rsi_{asset}'

    try:
        requested_days = int(days) if days != 'max' else 1095

        # We need extra days for RSI calculation (period + buffer)
        fetch_days = requested_days + period + 10

        # Load existing historical RSI data
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

        # Fetch asset OHLCV data (we need this to calculate RSI)
        print(f"[RSI {asset.upper()}] Fetching {asset.upper()} price data for RSI calculation...")
        asset_data_result = asset_module.get_data(str(fetch_days))
        asset_ohlcv_data = asset_data_result['data']

        if not asset_ohlcv_data:
            raise ValueError(f"No {asset.upper()} price data available for RSI calculation")

        print(f"[RSI {asset.upper()}] Calculating RSI from {len(asset_ohlcv_data)} price data points...")

        # Calculate RSI from OHLCV data
        calculated_rsi = calculate_rsi_from_ohlcv(asset_ohlcv_data, period)

        if not calculated_rsi:
            raise ValueError("RSI calculation returned no data")

        print(f"[RSI {asset.upper()}] Calculated {len(calculated_rsi)} RSI values")

        # Merge with historical data
        # For calculated indicators, we replace all overlapping data with fresh calculations
        merged_data = merge_and_deduplicate(
            existing_data=historical_data,
            new_data=calculated_rsi,
            overlap_days=fetch_days  # Replace all data in the calculated range
        )

        # Validate data structure
        is_valid, structure_type, error_msg = validate_data_structure(merged_data)
        if not is_valid:
            print(f"[RSI {asset.upper()}] Warning: Data validation failed: {error_msg}")

        # Save complete historical dataset
        save_historical_data(dataset_name, merged_data)

        # Filter to requested days
        if days != 'max':
            cutoff_date = datetime.now(tz=timezone.utc) - timedelta(days=int(days))
            cutoff_ms = int(cutoff_date.timestamp() * 1000)
            filtered_data = [d for d in merged_data if d[0] >= cutoff_ms]
        else:
            filtered_data = merged_data

        print(f"[RSI {asset.upper()}] Returning {len(filtered_data)} RSI data points")
        if filtered_data:
            print(f"[RSI {asset.upper()}] Date range: {datetime.fromtimestamp(filtered_data[0][0]/1000, tz=timezone.utc).date()} to {datetime.fromtimestamp(filtered_data[-1][0]/1000, tz=timezone.utc).date()}")
            print(f"[RSI {asset.upper()}] RSI range: {min(d[1] for d in filtered_data):.2f} to {max(d[1] for d in filtered_data):.2f}")

        return {
            'metadata': metadata,
            'data': filtered_data,
            'structure': 'simple'
        }

    except Exception as e:
        print(f"[RSI {asset.upper()}] Error in get_data: {e}")

        # Fallback to historical data if available
        historical_data = load_historical_data(dataset_name)
        if historical_data:
            print(f"[RSI {asset.upper()}] Falling back to historical data ({len(historical_data)} records)")

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
        print(f"[RSI {asset.upper()}] No historical data available for fallback")
        return {
            'metadata': metadata,
            'data': [],
            'structure': 'simple'
        }
