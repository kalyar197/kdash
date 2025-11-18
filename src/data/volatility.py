"""
Garman-Klass Volatility Estimator

Calculates historical volatility using the Garman-Klass estimator,
which is more efficient than close-to-close volatility as it uses
the full OHLC range information.

Formula: σ_GK = sqrt(0.5 * ln(H/L)² - (2*ln(2)-1) * ln(C/O)²)

This module is used by the Markov regime detector to classify
market volatility states (low-vol vs high-vol).
"""

import numpy as np
import math


def get_metadata():
    """Returns display metadata for the Garman-Klass volatility indicator."""
    return {
        'label': 'Garman-Klass Volatility',
        'yAxisId': 'percentage',
        'yAxisLabel': 'Volatility (%)',
        'unit': '%',
        'color': '#FF9500',  # Orange
        'chartType': 'line'
    }


def calculate_gk_volatility(ohlc_data):
    """
    Calculate Garman-Klass volatility from OHLC data.

    Args:
        ohlc_data: List of [timestamp, open, high, low, close, volume]

    Returns:
        List of [timestamp, volatility] pairs

    Formula:
        σ_GK = sqrt(0.5 * ln(H/L)² - (2*ln(2)-1) * ln(C/O)²)

    Note: Returns annualized volatility (multiplied by sqrt(252) for daily data)
    """
    if not ohlc_data or len(ohlc_data) == 0:
        return []

    volatility_data = []
    ln2_factor = 2 * math.log(2) - 1  # ≈ 0.386

    for candle in ohlc_data:
        timestamp = candle[0]
        open_price = candle[1]
        high_price = candle[2]
        low_price = candle[3]
        close_price = candle[4]

        # Skip invalid data
        if any(price <= 0 for price in [open_price, high_price, low_price, close_price]):
            continue

        if high_price < low_price:
            continue

        try:
            # Calculate components
            hl_ratio = high_price / low_price
            co_ratio = close_price / open_price

            # Garman-Klass formula
            term1 = 0.5 * (math.log(hl_ratio) ** 2)
            term2 = ln2_factor * (math.log(co_ratio) ** 2)

            # Daily volatility
            daily_vol = math.sqrt(term1 - term2)

            # Annualize (252 trading days)
            annualized_vol = daily_vol * math.sqrt(252)

            # Convert to percentage
            volatility_pct = annualized_vol * 100

            volatility_data.append([timestamp, volatility_pct])

        except (ValueError, ZeroDivisionError) as e:
            # Skip problematic data points
            continue

    return volatility_data


def get_data(days='365', asset='btc'):
    """
    Fetch Garman-Klass volatility data for a given asset.

    Args:
        days: Number of days of historical data
        asset: Asset symbol ('btc', 'eth', 'gold')

    Returns:
        Dictionary with metadata and volatility time series
    """
    # Import asset price module dynamically
    if asset == 'btc':
        from . import btc_price
        price_data = btc_price.get_data(days=days)
    elif asset == 'eth':
        from . import eth_price
        price_data = eth_price.get_data(days=days)
    else:
        # Default to BTC
        from . import btc_price
        price_data = btc_price.get_data(days=days)

    # Extract OHLCV data
    ohlcv_data = price_data.get('data', [])

    if not ohlcv_data:
        return {
            'metadata': get_metadata(),
            'data': [],
            'structure': 'simple'
        }

    # Calculate GK volatility
    volatility_data = calculate_gk_volatility(ohlcv_data)

    return {
        'metadata': get_metadata(),
        'data': volatility_data,
        'structure': 'simple'
    }


if __name__ == '__main__':
    # Test the volatility calculator
    import sys
    import os
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

    from data import btc_price

    print("Testing Garman-Klass Volatility Estimator...")

    # Get BTC price data
    price_data = btc_price.get_data(days='90')
    ohlcv_data = price_data.get('data', [])

    # Calculate volatility
    volatility_data = calculate_gk_volatility(ohlcv_data)

    print(f"\nCalculated {len(volatility_data)} volatility points")

    if volatility_data:
        # Show first and last values
        first = volatility_data[0]
        last = volatility_data[-1]

        print(f"\nFirst point: {first[1]:.2f}%")
        print(f"Last point:  {last[1]:.2f}%")

        # Calculate statistics
        volatilities = [v[1] for v in volatility_data]
        print(f"\nStatistics:")
        print(f"  Mean:   {np.mean(volatilities):.2f}%")
        print(f"  Median: {np.median(volatilities):.2f}%")
        print(f"  Min:    {np.min(volatilities):.2f}%")
        print(f"  Max:    {np.max(volatilities):.2f}%")
