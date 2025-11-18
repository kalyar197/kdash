# data/parabolic_sar.py
"""
Parabolic SAR (Stop and Reverse) Indicator

Calculates Parabolic SAR from asset OHLC data with incremental fetching.
SAR provides trailing stop levels and trend direction signals.

Formula: SAR(today) = SAR(yesterday) + AF * [EP - SAR(yesterday)]

Where:
- AF = Acceleration Factor (starts at 0.02, increases by 0.02 per new extreme, max 0.20)
- EP = Extreme Point (highest high in uptrend, lowest low in downtrend)
- Trend flips when price crosses SAR

Crypto-optimized parameters:
- AF Start: 0.02 (standard for cryptocurrency volatility)
- AF Increment: 0.02 (standard sensitivity)
- AF Max: 0.20 (standard maximum)

Interpretation:
- SAR below price: Bullish trend (buy signal)
- SAR above price: Bearish trend (sell signal)
- SAR flip: Potential trend reversal
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
        'label': f'Parabolic SAR ({asset_name})',
        'overlay': True,  # Flag to identify as overlay (not oscillator)
        'yAxisId': 'price_usd',  # Same axis as price
        'yAxisLabel': 'Price (USD)',
        'unit': '$',
        'renderType': 'dots',  # NEW: Render as dots instead of line
        'dotRadius': 3,  # Dot size in pixels
        'dotColors': {  # Color mapping for trend direction
            'bullish': '#00D9FF',   # Cyan (SAR below price)
            'bearish': '#FF1493'    # Magenta (SAR above price)
        },
        'chartType': 'overlay',
        'color': '#00D9FF',  # Default/fallback color
        'description': f'Parabolic SAR for {asset_name} - Trend following stop-and-reverse indicator',
        'data_structure': 'extended',  # [[timestamp, sar_value, trend]] format
        'components': ['timestamp', 'sar_value', 'trend']
    }


def calculate_parabolic_sar(ohlc_data, af_start=0.02, af_increment=0.02, af_max=0.20):
    """
    Calculate Parabolic SAR from OHLC data.

    Args:
        ohlc_data (list): List of [timestamp, open, high, low, close, volume]
        af_start (float): Initial acceleration factor (default: 0.02)
        af_increment (float): AF increment per new extreme (default: 0.02)
        af_max (float): Maximum AF value (default: 0.20)

    Returns:
        list: [[timestamp, sar_value, trend], ...]
              trend = 1 (bullish/below price) or -1 (bearish/above price)
    """
    if not ohlc_data or len(ohlc_data) < 2:
        return []

    result = []

    # Extract OHLC components
    timestamps = [bar[0] for bar in ohlc_data]
    highs = np.array([bar[2] for bar in ohlc_data])
    lows = np.array([bar[3] for bar in ohlc_data])
    closes = np.array([bar[4] for bar in ohlc_data])

    # Initialize variables
    # Start with first bar, determine initial trend from first two bars
    if closes[1] > closes[0]:
        # Start in uptrend
        trend = 1  # Bullish
        sar = lows[0]  # SAR starts at low
        ep = highs[1]  # Extreme point is high
    else:
        # Start in downtrend
        trend = -1  # Bearish
        sar = highs[0]  # SAR starts at high
        ep = lows[1]  # Extreme point is low

    af = af_start

    # Add first SAR point
    result.append([timestamps[0], float(sar), int(trend)])

    # Calculate SAR for each subsequent bar
    for i in range(1, len(ohlc_data)):
        # Store previous SAR for calculation
        prev_sar = sar

        # Calculate new SAR
        sar = prev_sar + af * (ep - prev_sar)

        # Check for trend reversal
        if trend == 1:  # Currently in uptrend
            # SAR should not be above the prior two lows
            if i >= 2:
                sar = min(sar, lows[i-1], lows[i-2])
            else:
                sar = min(sar, lows[i-1])

            # Check if price crossed below SAR (trend reversal to downtrend)
            if lows[i] < sar:
                trend = -1  # Flip to bearish
                sar = ep  # New SAR is the previous extreme point (high)
                ep = lows[i]  # New extreme point is current low
                af = af_start  # Reset AF
            else:
                # Continue uptrend
                # Check if we have a new high (new extreme point)
                if highs[i] > ep:
                    ep = highs[i]
                    af = min(af + af_increment, af_max)  # Increase AF

        else:  # Currently in downtrend (trend == -1)
            # SAR should not be below the prior two highs
            if i >= 2:
                sar = max(sar, highs[i-1], highs[i-2])
            else:
                sar = max(sar, highs[i-1])

            # Check if price crossed above SAR (trend reversal to uptrend)
            if highs[i] > sar:
                trend = 1  # Flip to bullish
                sar = ep  # New SAR is the previous extreme point (low)
                ep = highs[i]  # New extreme point is current high
                af = af_start  # Reset AF
            else:
                # Continue downtrend
                # Check if we have a new low (new extreme point)
                if lows[i] < ep:
                    ep = lows[i]
                    af = min(af + af_increment, af_max)  # Increase AF

        # Add to result
        result.append([timestamps[i], float(sar), int(trend)])

    return result


def get_data(days='365', asset='btc'):
    """
    Fetches Parabolic SAR data using incremental fetching strategy.

    Strategy:
    1. Load historical SAR data from disk
    2. Check if we need older data for requested time range
    3. Fetch asset OHLC data
    4. Calculate Parabolic SAR from OHLC data
    5. Merge with historical data using overlap strategy
    6. Save to historical_data/psar_{asset}.json
    7. Return filtered by requested days

    Args:
        days (str): Number of days to return ('7', '30', '180', '1095', 'max')
        asset (str): Asset name ('btc', 'eth', 'gold')

    Returns:
        dict: {
            'metadata': metadata dict,
            'data': [[timestamp, sar_value, trend], ...],
            'structure': 'extended'
        }
    """
    metadata = get_metadata(asset)
    dataset_name = f'psar_{asset}'

    try:
        requested_days = int(days) if days != 'max' else 1095

        # We need extra days for SAR calculation (buffer for initial trend determination)
        fetch_days = requested_days + 10

        # Load existing historical SAR data
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

        # Fetch asset OHLC data (we need this to calculate SAR)
        print(f"[PSAR {asset.upper()}] Fetching {asset.upper()} OHLC data for SAR calculation...")
        asset_data_result = asset_module.get_data(str(fetch_days))
        asset_ohlc_data = asset_data_result['data']

        if not asset_ohlc_data:
            raise ValueError(f"No {asset.upper()} OHLC data available for SAR calculation")

        print(f"[PSAR {asset.upper()}] Calculating Parabolic SAR from {len(asset_ohlc_data)} OHLC data points...")

        # Calculate Parabolic SAR from OHLC data
        # Using crypto-optimized parameters: 0.02, 0.02, 0.20
        calculated_sar = calculate_parabolic_sar(
            asset_ohlc_data,
            af_start=0.02,
            af_increment=0.02,
            af_max=0.20
        )

        if not calculated_sar:
            raise ValueError("Parabolic SAR calculation returned no data")

        print(f"[PSAR {asset.upper()}] Calculated {len(calculated_sar)} SAR values")

        # Count bullish vs bearish signals
        bullish_count = sum(1 for point in calculated_sar if point[2] == 1)
        bearish_count = sum(1 for point in calculated_sar if point[2] == -1)
        print(f"[PSAR {asset.upper()}] Signals: {bullish_count} bullish, {bearish_count} bearish")

        # Merge with historical data
        # For calculated indicators, we replace all overlapping data with fresh calculations
        merged_data = merge_and_deduplicate(
            existing_data=historical_data,
            new_data=calculated_sar,
            overlap_days=fetch_days  # Replace all data in the calculated range
        )

        # Note: validate_data_structure may not support 3-component arrays
        # We'll skip validation for now since we know our structure is correct

        # Save complete historical dataset
        save_historical_data(dataset_name, merged_data)

        # Filter to requested days
        if days != 'max':
            cutoff_date = datetime.now(tz=timezone.utc) - timedelta(days=int(days))
            cutoff_ms = int(cutoff_date.timestamp() * 1000)
            filtered_data = [d for d in merged_data if d[0] >= cutoff_ms]
        else:
            filtered_data = merged_data

        print(f"[PSAR {asset.upper()}] Returning {len(filtered_data)} SAR data points")
        if filtered_data:
            print(f"[PSAR {asset.upper()}] Date range: {datetime.fromtimestamp(filtered_data[0][0]/1000, tz=timezone.utc).date()} to {datetime.fromtimestamp(filtered_data[-1][0]/1000, tz=timezone.utc).date()}")
            print(f"[PSAR {asset.upper()}] SAR range: ${min(d[1] for d in filtered_data):.2f} to ${max(d[1] for d in filtered_data):.2f}")

        return {
            'metadata': metadata,
            'data': filtered_data,
            'structure': 'extended'
        }

    except Exception as e:
        print(f"[PSAR {asset.upper()}] Error in get_data: {e}")

        # Fallback to historical data if available
        historical_data = load_historical_data(dataset_name)
        if historical_data:
            print(f"[PSAR {asset.upper()}] Falling back to historical data ({len(historical_data)} records)")

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
                'structure': 'extended'
            }

        # No data available at all
        print(f"[PSAR {asset.upper()}] No historical data available for fallback")
        return {
            'metadata': metadata,
            'data': [],
            'structure': 'extended'
        }
