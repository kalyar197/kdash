# data/sma.py
"""
SMA (Simple Moving Average) Indicator

Calculates Simple Moving Averages from asset price data with incremental fetching.
SMA smooths price data by calculating the average price over a specified period.

Formula: SMA = sum(prices[-period:]) / period

Standard usage:
- SMA-14: Fast-moving average for short-term trends
- SMA-60: Slow-moving average for medium-term trends
- Price above SMA: Bullish signal
- Price below SMA: Bearish signal
- SMA crossovers: Trend change signals
"""

import numpy as np
from datetime import datetime, timedelta, timezone
from .incremental_data_manager import (
    load_historical_data,
    save_historical_data,
    merge_and_deduplicate,
    validate_data_structure
)


def get_metadata(asset='btc', period=14):
    """Returns metadata describing how this data should be displayed"""
    asset_names = {
        'btc': 'Bitcoin',
        'eth': 'Ethereum',
        'gold': 'Gold'
    }
    asset_name = asset_names.get(asset, asset.upper())

    # Color coding based on period
    colors = {
        7: '#FF6B6B',   # Red/orange for fast MA
        21: '#FFA500',  # Orange for medium MA
        60: '#4ECDC4'   # Cyan/teal for slow MA
    }
    color = colors.get(period, '#888888')

    return {
        'label': f'SMA-{period} ({asset_name})',
        'overlay': True,  # Flag to identify as overlay (not oscillator)
        'yAxisId': 'price_usd',  # Same axis as price
        'yAxisLabel': 'Price (USD)',
        'unit': '$',
        'chartType': 'line',
        'color': color,
        'strokeWidth': 2 if period <= 30 else 2.5,  # Thicker line for slower MAs
        'description': f'{period}-period Simple Moving Average for {asset_name}',
        'data_structure': 'simple',
        'components': ['timestamp', 'sma_value']
    }


def calculate_sma(prices, period=14):
    """
    Calculate Simple Moving Average from price data.

    Args:
        prices (list): List of closing prices
        period (int): SMA period (default: 14)

    Returns:
        list: SMA values (same length as prices, first 'period-1' values will be None)
    """
    if len(prices) < period:
        return [None] * len(prices)

    sma_values = [None] * (period - 1)  # First 'period-1' values can't be calculated

    # Calculate SMA for each valid window
    for i in range(period - 1, len(prices)):
        window = prices[i - period + 1:i + 1]
        sma = np.mean(window)
        sma_values.append(sma)

    return sma_values


def calculate_sma_from_ohlcv(ohlcv_data, period=14):
    """
    Calculate SMA from OHLCV data.

    Args:
        ohlcv_data (list): [[timestamp, open, high, low, close, volume], ...]
        period (int): SMA period (default: 14)

    Returns:
        list: [[timestamp, sma_value], ...] (first 'period-1' points will be None)
    """
    if not ohlcv_data or len(ohlcv_data) < period:
        return []

    # Extract closing prices
    close_prices = [item[4] for item in ohlcv_data]  # Index 4 is close price

    # Calculate SMA
    sma_values = calculate_sma(close_prices, period)

    # Pair timestamps with SMA values, skip None values
    result = []
    for i, item in enumerate(ohlcv_data):
        timestamp = item[0]
        sma_value = sma_values[i]

        if sma_value is not None:
            result.append([timestamp, sma_value])

    return result


def get_data(days='365', asset='btc', period=14):
    """
    Fetches SMA data using incremental fetching strategy.

    Strategy:
    1. Load historical SMA data from disk
    2. Check if we need older data for requested time range
    3. Fetch asset price data (OHLCV)
    4. Calculate SMA from price data
    5. Merge with historical data using overlap strategy
    6. Save to historical_data/sma_{period}_{asset}.json
    7. Return filtered by requested days

    Args:
        days (str): Number of days to return ('7', '30', '180', '1095', 'max')
        asset (str): Asset name ('btc', 'eth', 'gold')
        period (int): SMA period (default: 14)

    Returns:
        dict: {
            'metadata': metadata dict,
            'data': [[timestamp, sma_value], ...],
            'structure': 'simple'
        }
    """
    metadata = get_metadata(asset, period)
    dataset_name = f'sma_{period}_{asset}'

    try:
        requested_days = int(days) if days != 'max' else 1095

        # We need extra days for SMA calculation (period + buffer)
        fetch_days = requested_days + period + 10

        # Load existing historical SMA data
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

        # Fetch asset OHLCV data (we need this to calculate SMA)
        print(f"[SMA-{period} {asset.upper()}] Fetching {asset.upper()} price data for SMA calculation...")
        asset_data_result = asset_module.get_data(str(fetch_days))
        asset_ohlcv_data = asset_data_result['data']

        if not asset_ohlcv_data:
            raise ValueError(f"No {asset.upper()} price data available for SMA calculation")

        print(f"[SMA-{period} {asset.upper()}] Calculating SMA from {len(asset_ohlcv_data)} price data points...")

        # Calculate SMA from OHLCV data
        calculated_sma = calculate_sma_from_ohlcv(asset_ohlcv_data, period)

        if not calculated_sma:
            raise ValueError("SMA calculation returned no data")

        print(f"[SMA-{period} {asset.upper()}] Calculated {len(calculated_sma)} SMA values")

        # Merge with historical data
        # For calculated indicators, we replace all overlapping data with fresh calculations
        merged_data = merge_and_deduplicate(
            existing_data=historical_data,
            new_data=calculated_sma,
            overlap_days=fetch_days  # Replace all data in the calculated range
        )

        # Validate data structure
        is_valid, structure_type, error_msg = validate_data_structure(merged_data)
        if not is_valid:
            print(f"[SMA-{period} {asset.upper()}] Warning: Data validation failed: {error_msg}")

        # Save complete historical dataset
        save_historical_data(dataset_name, merged_data)

        # Filter to requested days
        if days != 'max':
            cutoff_date = datetime.now(tz=timezone.utc) - timedelta(days=int(days))
            cutoff_ms = int(cutoff_date.timestamp() * 1000)
            filtered_data = [d for d in merged_data if d[0] >= cutoff_ms]
        else:
            filtered_data = merged_data

        print(f"[SMA-{period} {asset.upper()}] Returning {len(filtered_data)} SMA data points")
        if filtered_data:
            print(f"[SMA-{period} {asset.upper()}] Date range: {datetime.fromtimestamp(filtered_data[0][0]/1000, tz=timezone.utc).date()} to {datetime.fromtimestamp(filtered_data[-1][0]/1000, tz=timezone.utc).date()}")
            print(f"[SMA-{period} {asset.upper()}] SMA range: ${min(d[1] for d in filtered_data):.2f} to ${max(d[1] for d in filtered_data):.2f}")

        return {
            'metadata': metadata,
            'data': filtered_data,
            'structure': 'simple'
        }

    except Exception as e:
        print(f"[SMA-{period} {asset.upper()}] Error in get_data: {e}")

        # Fallback to historical data if available
        historical_data = load_historical_data(dataset_name)
        if historical_data:
            print(f"[SMA-{period} {asset.upper()}] Falling back to historical data ({len(historical_data)} records)")

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
        print(f"[SMA-{period} {asset.upper()}] No historical data available for fallback")
        return {
            'metadata': metadata,
            'data': [],
            'structure': 'simple'
        }
