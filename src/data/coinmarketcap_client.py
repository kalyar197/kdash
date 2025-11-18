# data/coinmarketcap_client.py
"""
Shared CoinMarketCap API client for fetching crypto market data.

Provides helper functions for:
- Global market metrics (total market cap, BTC dominance, etc.)
- Individual coin quotes (market cap, price, volume, etc.)

API Documentation: https://coinmarketcap.com/api/documentation/v1/
Free Tier: 10,000 calls/month (333 calls/day)
"""

import requests
from datetime import datetime, timezone

CMC_BASE_URL = 'https://pro-api.coinmarketcap.com'


def get_headers():
    """
    Returns standard CoinMarketCap API headers with authentication.

    Returns:
        dict: Headers dictionary with API key

    Raises:
        ValueError: If API key is not configured
    """
    # Import key dynamically to ensure .env is loaded first
    try:
        from config import COINMARKETCAP_API_KEY
    except ImportError:
        raise ValueError("CoinMarketCap API key not found in config.py. Add COINMARKETCAP_API_KEY to .env")

    if not COINMARKETCAP_API_KEY:
        raise ValueError("CoinMarketCap API key is empty. Add COINMARKETCAP_API_KEY to .env")

    return {
        'X-CMC_PRO_API_KEY': COINMARKETCAP_API_KEY,
        'Accept': 'application/json'
    }


def fetch_global_metrics():
    """
    Fetch current global crypto market metrics.

    Returns data including:
    - total_market_cap: Total crypto market capitalization (USD)
    - btc_dominance: Bitcoin's percentage of total market cap
    - active_cryptocurrencies: Number of active coins
    - total_volume_24h: 24-hour trading volume

    Returns:
        dict: Parsed JSON response containing global metrics

    Example response structure:
        {
            'data': {
                'quote': {
                    'USD': {
                        'total_market_cap': 3360000000000,
                        'btc_dominance': 58.5,
                        'total_volume_24h': 156000000000,
                        ...
                    }
                },
                'active_cryptocurrencies': 12345,
                'last_updated': '2025-11-05T...'
            }
        }

    Raises:
        requests.exceptions.HTTPError: If API request fails
        ValueError: If API key not configured
    """
    url = f'{CMC_BASE_URL}/v1/global-metrics/quotes/latest'

    response = requests.get(url, headers=get_headers(), timeout=30)
    response.raise_for_status()

    return response.json()


def fetch_coin_quote(symbol):
    """
    Fetch current quote data for a specific cryptocurrency.

    Returns data including:
    - price: Current USD price
    - market_cap: Market capitalization (price × circulating supply)
    - volume_24h: 24-hour trading volume
    - circulating_supply: Coins currently in circulation
    - percent_change_24h/7d/30d: Price change percentages

    Args:
        symbol (str): Cryptocurrency symbol (e.g., 'BTC', 'ETH', 'USDT')

    Returns:
        dict: Parsed JSON response containing coin quote data

    Example response structure:
        {
            'data': {
                'BTC': {
                    'id': 1,
                    'name': 'Bitcoin',
                    'symbol': 'BTC',
                    'quote': {
                        'USD': {
                            'price': 110540.68,
                            'market_cap': 2190000000000,
                            'volume_24h': 45000000000,
                            'circulating_supply': 19800000,
                            ...
                        }
                    },
                    'last_updated': '2025-11-05T...'
                }
            }
        }

    Raises:
        requests.exceptions.HTTPError: If API request fails
        ValueError: If API key not configured
    """
    url = f'{CMC_BASE_URL}/v1/cryptocurrency/quotes/latest'
    params = {'symbol': symbol.upper()}

    response = requests.get(url, headers=get_headers(), params=params, timeout=30)
    response.raise_for_status()

    return response.json()


def extract_global_metric(response, metric_name):
    """
    Helper to extract a specific metric from global metrics response.

    Args:
        response (dict): Response from fetch_global_metrics()
        metric_name (str): Name of metric (e.g., 'total_market_cap', 'btc_dominance')

    Returns:
        float: Metric value

    Raises:
        KeyError: If metric not found in response
    """
    return response['data']['quote']['USD'][metric_name]


def extract_coin_metric(response, symbol, metric_name):
    """
    Helper to extract a specific metric from coin quote response.

    Args:
        response (dict): Response from fetch_coin_quote()
        symbol (str): Cryptocurrency symbol
        metric_name (str): Name of metric (e.g., 'market_cap', 'price', 'volume_24h')

    Returns:
        float: Metric value

    Raises:
        KeyError: If symbol or metric not found in response
    """
    return response['data'][symbol.upper()]['quote']['USD'][metric_name]


def get_current_timestamp():
    """
    Get current timestamp in milliseconds (UTC).

    Returns:
        int: Current timestamp in milliseconds
    """
    return int(datetime.now(timezone.utc).timestamp() * 1000)
