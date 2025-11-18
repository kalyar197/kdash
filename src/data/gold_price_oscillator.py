# data/gold_price_oscillator.py
"""
Gold (XAU/USD) price oscillator wrapper
Extracts closing prices from existing FMP gold module for oscillator calculations
Returns simple format: [timestamp, close_price]
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from datetime import datetime, timezone
from . import gold_price

def get_metadata():
    """Returns metadata describing how this data should be displayed"""
    return {
        'label': 'Gold Price (vs BTC)',
        'yAxisId': 'indicator',
        'yAxisLabel': 'Normalized Divergence (σ)',
        'unit': 'σ',
        'chartType': 'line',
        'color': '#FFD700',  # Gold color
        'strokeWidth': 2,
        'description': 'Gold spot price oscillator',
        'data_structure': 'simple'
    }

def get_data(days='1095', asset='btc'):
    """
    Fetches Gold price data via existing FMP module and extracts closing prices.
    Returns simple format [timestamp, close_price] for oscillator calculations.

    Args:
        days (str): Number of days to return ('30', '365', '1095', 'max')
        asset (str): Asset parameter (for compatibility, not used)

    Returns:
        dict: {
            'metadata': metadata dict,
            'data': [[timestamp, close_price], ...]
        }
    """
    metadata = get_metadata()

    try:
        # Fetch OHLCV data from existing gold_price module
        result = gold_price.get_data(days=days)
        ohlcv_data = result.get('data', [])

        if not ohlcv_data:
            print(f"[Gold Price Oscillator] No data returned from gold_price module")
            return {
                'metadata': metadata,
                'data': []
            }

        # Extract closing prices (index [4] in OHLCV structure)
        # OHLCV: [timestamp, open, high, low, close, volume]
        simple_data = []
        for candle in ohlcv_data:
            if len(candle) >= 5:
                timestamp = candle[0]
                close_price = candle[4]  # Extract close price
                simple_data.append([timestamp, close_price])

        print(f"[Gold Price Oscillator] Converted {len(simple_data)} OHLCV records to simple format")
        if simple_data:
            start_dt = datetime.fromtimestamp(simple_data[0][0]/1000, tz=timezone.utc).date()
            end_dt = datetime.fromtimestamp(simple_data[-1][0]/1000, tz=timezone.utc).date()
            print(f"[Gold Price Oscillator] Date range: {start_dt} to {end_dt}")
            print(f"[Gold Price Oscillator] Sample: timestamp={simple_data[0][0]}, close=${simple_data[0][1]:.2f}")

        return {
            'metadata': metadata,
            'data': simple_data
        }

    except Exception as e:
        print(f"[Gold Price Oscillator] Error in get_data: {e}")
        return {
            'metadata': metadata,
            'data': []
        }
