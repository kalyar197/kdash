# data/spx_price_alpaca.py
"""
S&P 500 Index (SPX) price data fetcher using Alpaca API
Returns simple format: [timestamp, close_price] for oscillator calculations
Uses incremental data manager for caching and efficient fetching

Note: Alpaca Paper Trading API keys are free and don't require credit card.
Get keys at: https://alpaca.markets/
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from datetime import datetime, timedelta, timezone
from .incremental_data_manager import (
    load_historical_data,
    save_historical_data,
    merge_and_deduplicate
)

# Alpaca API configuration
try:
    from config import ALPACA_API_KEY, ALPACA_SECRET_KEY
    ALPACA_CONFIGURED = True
except ImportError:
    print("[SPX Price Alpaca] Warning: Alpaca API keys not configured in config.py")
    ALPACA_CONFIGURED = False

def get_metadata():
    """Returns metadata describing how this data should be displayed"""
    return {
        'label': 'SPX Price (vs BTC)',
        'yAxisId': 'indicator',
        'yAxisLabel': 'Normalized Divergence (σ)',
        'unit': 'σ',
        'chartType': 'line',
        'color': '#FF6B6B',  # Coral red color for S&P 500
        'strokeWidth': 2,
        'description': 'S&P 500 Index price oscillator',
        'data_structure': 'simple'
    }

def fetch_from_alpaca(start_date, end_date):
    """
    Fetch SPX (S&P 500) OHLCV data from Alpaca API for a specific date range.
    Converts OHLCV to simple [timestamp, close_price] format.

    Args:
        start_date (datetime): Start date for data fetch
        end_date (datetime): End date for data fetch

    Returns:
        list: Simple format [[timestamp, close_price], ...]
    """
    if not ALPACA_CONFIGURED:
        raise ValueError("Alpaca API keys not configured")

    print(f"[SPX Price Alpaca] Fetching SPX from Alpaca: {start_date.date()} to {end_date.date()}")

    try:
        # Import Alpaca SDK
        from alpaca.data.historical import StockHistoricalDataClient
        from alpaca.data.requests import StockBarsRequest
        from alpaca.data.timeframe import TimeFrame

        # Initialize Alpaca stock client
        client = StockHistoricalDataClient(ALPACA_API_KEY, ALPACA_SECRET_KEY)

        # Create request for SPX bars
        # Note: Alpaca uses SPY as proxy for S&P 500, or we can use ^GSPC symbol
        request_params = StockBarsRequest(
            symbol_or_symbols=['SPY'],  # SPY ETF tracks S&P 500
            timeframe=TimeFrame.Day,
            start=start_date,
            end=end_date
        )

        # Fetch bars
        bars = client.get_stock_bars(request_params)

        # Extract data
        raw_data = []

        if 'SPY' in bars.data:
            for bar in bars.data['SPY']:
                # Get timestamp in milliseconds
                timestamp_ms = int(bar.timestamp.timestamp() * 1000)

                # Get close price
                close_price = float(bar.close)

                # Store as simple [timestamp, close_price]
                raw_data.append([timestamp_ms, close_price])

        if not raw_data:
            raise ValueError("No valid data extracted from Alpaca response")

        # Sort by timestamp (oldest first)
        raw_data.sort(key=lambda x: x[0])

        print(f"[SPX Price Alpaca] Successfully fetched {len(raw_data)} data points")
        if raw_data:
            print(f"[SPX Price Alpaca] Sample: timestamp={raw_data[0][0]}, close=${raw_data[0][1]:.2f}")

        return raw_data

    except Exception as e:
        print(f"[SPX Price Alpaca] Error fetching from Alpaca: {e}")
        raise

def get_data(days='1095', asset='btc'):
    """
    Fetches SPX price data using incremental fetching strategy.
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
    dataset_name = 'spx_price_alpaca'

    try:
        requested_days = int(days) if days != 'max' else 1095  # Max 3 years

        # Load existing historical data
        historical_data = load_historical_data(dataset_name)

        # Determine fetch strategy
        end_date = datetime.now(tz=timezone.utc)

        if historical_data:
            # Incremental fetch: get last 5 days + new data (overlap for safety)
            last_timestamp = historical_data[-1][0]
            last_date = datetime.fromtimestamp(last_timestamp / 1000, tz=timezone.utc)
            start_date = last_date - timedelta(days=5)

            print(f"[SPX Price Alpaca] Incremental fetch from {start_date.date()} to {end_date.date()}")
            new_data = fetch_from_alpaca(start_date, end_date)
        else:
            # Full fetch: get all requested days
            start_date = end_date - timedelta(days=requested_days)

            print(f"[SPX Price Alpaca] Full fetch from {start_date.date()} to {end_date.date()}")
            new_data = fetch_from_alpaca(start_date, end_date)

        # Merge with historical data
        merged_data = merge_and_deduplicate(
            existing_data=historical_data,
            new_data=new_data,
            overlap_days=5
        )

        # Save complete historical dataset
        save_historical_data(dataset_name, merged_data)

        # Filter to requested days
        if days != 'max':
            cutoff_date = datetime.now(tz=timezone.utc) - timedelta(days=int(days))
            cutoff_ms = int(cutoff_date.timestamp() * 1000)
            filtered_data = [d for d in merged_data if d[0] >= cutoff_ms]
        else:
            filtered_data = merged_data

        print(f"[SPX Price Alpaca] Returning {len(filtered_data)} records")
        if filtered_data:
            start_dt = datetime.fromtimestamp(filtered_data[0][0]/1000, tz=timezone.utc).date()
            end_dt = datetime.fromtimestamp(filtered_data[-1][0]/1000, tz=timezone.utc).date()
            print(f"[SPX Price Alpaca] Date range: {start_dt} to {end_dt}")

        return {
            'metadata': metadata,
            'data': filtered_data
        }

    except Exception as e:
        print(f"[SPX Price Alpaca] Error in get_data: {e}")

        # Fallback to historical data
        historical_data = load_historical_data(dataset_name)
        if historical_data:
            print(f"[SPX Price Alpaca] Falling back to historical data ({len(historical_data)} records)")

            # Filter by requested days
            if days != 'max':
                cutoff_date = datetime.now(tz=timezone.utc) - timedelta(days=int(days))
                cutoff_ms = int(cutoff_date.timestamp() * 1000)
                filtered_data = [d for d in historical_data if d[0] >= cutoff_ms]
            else:
                filtered_data = historical_data

            return {
                'metadata': metadata,
                'data': filtered_data
            }

        # No data available
        print(f"[SPX Price Alpaca] No historical data available for fallback")
        return {
            'metadata': metadata,
            'data': []
        }
