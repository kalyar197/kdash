# data/btc_dominance_cmc.py
"""
Bitcoin Dominance (BTC.D) data fetcher using CoinMarketCap API.

Bitcoin Dominance = (BTC Market Cap / Total Crypto Market Cap) × 100

Interpretation:
- High dominance (>60%): Bitcoin leading, altcoins lagging (defensive market)
- Low dominance (<40%): Altcoins outperforming, risk-on environment
- Trending up: Capital flowing into BTC from altcoins
- Trending down: Alt season, capital rotating out of BTC

Historical Range: ~35% (alt season 2021) to ~70% (bear market 2018-2019)
Current Typical Range: 45-65%

Returns simple format: [[timestamp, dominance_pct], ...] for oscillator calculations.

API: CoinMarketCap /v1/global-metrics/quotes/latest
Rate Limit: 10,000 calls/month (333 calls/day) - Free Tier
Cache: 15-minute intervals (slower moving than price)
"""

import requests
from datetime import datetime, timedelta, timezone
from .coinmarketcap_client import (
    fetch_global_metrics,
    extract_global_metric,
    get_current_timestamp
)
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
        'label': 'BTC.D (vs BTC)',
        'yAxisId': 'indicator',
        'yAxisLabel': 'Normalized Divergence (σ)',
        'unit': 'σ',
        'chartType': 'line',
        'color': '#FF6B35',  # Orange for Bitcoin dominance
        'strokeWidth': 2,
        'description': 'Bitcoin Dominance (% of total crypto market cap) - higher = defensive market',
        'data_structure': 'simple',  # [[timestamp, dominance_pct], ...]
        'source': 'CoinMarketCap',
        'update_frequency': '15 minutes'
    }


def fetch_current_btc_dominance():
    """
    Fetch current Bitcoin dominance percentage from CoinMarketCap API.

    Returns:
        list: [[timestamp_ms, dominance_pct]] with single current data point

    Example:
        [[1762305610000, 58.45]]

    Raises:
        Exception: If CoinMarketCap API request fails
    """
    print(f"[BTC Dominance CMC] Fetching current BTC dominance from CoinMarketCap")

    try:
        # Fetch global metrics
        response = fetch_global_metrics()

        # Extract BTC dominance percentage (it's at root data level, not in quote/USD)
        btc_dominance = response['data']['btc_dominance']

        # Get current timestamp
        timestamp_ms = get_current_timestamp()

        print(f"[BTC Dominance CMC] Successfully fetched: {btc_dominance:.2f}%")

        return [[timestamp_ms, btc_dominance]]

    except requests.exceptions.HTTPError as e:
        print(f"[BTC Dominance CMC] HTTP Error: {e}")
        if e.response.status_code == 401:
            raise ValueError("CoinMarketCap API authentication failed. Check COINMARKETCAP_API_KEY in .env")
        elif e.response.status_code == 429:
            raise ValueError("CoinMarketCap API rate limit exceeded. Wait before retrying")
        else:
            raise

    except Exception as e:
        print(f"[BTC Dominance CMC] Error fetching from CoinMarketCap: {e}")
        raise


def get_data(days='1095', asset='btc'):
    """
    Fetches BTC dominance data using incremental fetching strategy.

    Strategy:
    1. Load existing historical data from cache
    2. Fetch current dominance from CoinMarketCap
    3. Merge with historical data
    4. Save updated cache
    5. Return requested days

    Note: CoinMarketCap free tier doesn't provide historical global metrics,
    so we build history incrementally by fetching current value periodically.

    Args:
        days (str): Number of days to return ('7', '30', '365', '1095', 'max')
        asset (str): Asset parameter (unused for BTC.D, but required by interface)

    Returns:
        dict: {
            'metadata': metadata dict,
            'data': [[timestamp, dominance_pct], ...] for requested period
        }

    Example:
        >>> result = get_data('30', 'btc')
        >>> len(result['data'])
        ~2880  # 30 days × 96 samples/day (15-min intervals)
        >>> result['data'][0]
        [1759795200000, 58.45]
    """
    dataset_name = 'btc_dominance'

    # Step 1: Load existing historical data
    historical_data = load_historical_data(dataset_name)

    # Step 2: Fetch current dominance
    try:
        new_data = fetch_current_btc_dominance()
    except Exception as e:
        print(f"[BTC Dominance CMC] Error fetching current data: {e}")
        # Fallback to historical data if fetch fails
        if historical_data:
            print(f"[BTC Dominance CMC] Falling back to cached data ({len(historical_data)} records)")
            new_data = []
        else:
            raise

    # Step 3: Merge with historical data
    if new_data:
        merged_data = merge_and_deduplicate(historical_data, new_data)
        print(f"[BTC Dominance CMC] Merged {len(historical_data)} historical + {len(new_data)} new = {len(merged_data)} total")
    else:
        merged_data = historical_data
        print(f"[BTC Dominance CMC] No new data, using {len(merged_data)} cached records")

    # Step 4: Standardize timestamps and save updated cache
    if merged_data:
        # Standardize timestamps to daily UTC (00:00:00) for alignment with BTC
        standardized_data = standardize_to_daily_utc(merged_data)
        save_historical_data(dataset_name, standardized_data)
        print(f"[BTC Dominance CMC] Standardized timestamps to midnight UTC for BTC alignment")
    else:
        standardized_data = []

    # Step 5: Return requested days
    if not standardized_data:
        print(f"[BTC Dominance CMC] Warning: No data available")
        return {
            'metadata': get_metadata(),
            'data': []
        }

    if days == 'max':
        result_data = standardized_data
    else:
        days_int = int(days)
        # Calculate cutoff timestamp (days ago)
        cutoff_timestamp = standardized_data[-1][0] - (days_int * 24 * 60 * 60 * 1000)
        # Filter data >= cutoff
        result_data = [d for d in standardized_data if d[0] >= cutoff_timestamp]

        # If not enough data, return all available
        if len(result_data) < 10:
            print(f"[BTC Dominance CMC] Warning: Only {len(result_data)} points for {days} days (insufficient history)")
            result_data = standardized_data

    print(f"[BTC Dominance CMC] Returning {len(result_data)} records")
    if result_data:
        start_ts = result_data[0][0]
        end_ts = result_data[-1][0]
        start_date_obj = datetime.fromtimestamp(start_ts / 1000, tz=timezone.utc)
        end_date_obj = datetime.fromtimestamp(end_ts / 1000, tz=timezone.utc)
        print(f"[BTC Dominance CMC] Date range: {start_date_obj.strftime('%Y-%m-%d')} to {end_date_obj.strftime('%Y-%m-%d')}")
        valid_values = [d[1] for d in result_data if d[1] is not None]
        if valid_values:
            print(f"[BTC Dominance CMC] BTC.D range: {min(valid_values):.2f}% to {max(valid_values):.2f}%")

    # CRITICAL: Filter out None values before returning (prevents Z-score calculation errors)
    result_data = [[ts, val] for ts, val in result_data if val is not None]
    if len(result_data) < len([d for d in standardized_data if d[1] is not None]):
        print(f"[BTC Dominance CMC] Warning: Filtered out {len(standardized_data) - len(result_data)} None values")

    return {
        'metadata': get_metadata(),
        'data': result_data
    }
