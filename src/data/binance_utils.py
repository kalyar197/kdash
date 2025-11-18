"""
Utility functions for fetching data from Binance Futures API.

Handles basis spread, open interest history, and taker long/short ratio data
with automatic stitching for multi-month historical fetches.
"""

import requests
import time
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional
from data.derivatives_config import (
    BINANCE_FUTURES_BASE,
    BINANCE_ENDPOINTS,
    REQUEST_DELAY,
    MAX_RETRIES,
    RETRY_BACKOFF_BASE,
    BINANCE_BASIS_LIMIT,
    BINANCE_OI_LIMIT,
    BINANCE_TAKER_LIMIT,
    DEFAULT_SYMBOL
)
from data.time_transformer import standardize_to_daily_utc


def fetch_binance_endpoint(
    endpoint: str,
    params: Dict[str, Any],
    timestamp_key: str = 'timestamp'
) -> List[Dict[str, Any]]:
    """
    Generic Binance Futures API fetcher with retry logic.

    Args:
        endpoint: API endpoint path (e.g., '/futures/data/basis')
        params: Query parameters
        timestamp_key: Key name for timestamp field in response

    Returns:
        List of data points from API

    Raises:
        requests.RequestException: If API request fails after retries
    """
    url = f"{BINANCE_FUTURES_BASE}{endpoint}"

    for attempt in range(MAX_RETRIES):
        try:
            response = requests.get(url, params=params, timeout=30)
            response.raise_for_status()
            data = response.json()

            if not isinstance(data, list):
                raise ValueError(f"Expected list response, got: {type(data)}")

            print(f"Fetched {len(data)} data points from {endpoint}")
            return data

        except requests.exceptions.RequestException as e:
            if attempt < MAX_RETRIES - 1:
                wait_time = RETRY_BACKOFF_BASE * (2 ** attempt)
                print(f"Binance API error (attempt {attempt + 1}/{MAX_RETRIES}): {e}")
                print(f"Retrying in {wait_time}s...")
                time.sleep(wait_time)
            else:
                raise

    raise requests.RequestException(f"Failed to fetch from {endpoint} after {MAX_RETRIES} attempts")


def fetch_basis_spread(
    symbol: str = DEFAULT_SYMBOL,
    contract_type: str = 'PERPETUAL',
    period: str = '1d',
    limit: int = BINANCE_BASIS_LIMIT
) -> List[List]:
    """
    Fetch basis spread data (spot vs futures price differential).

    Args:
        symbol: Trading pair symbol (default: BTCUSDT)
        contract_type: Contract type (default: PERPETUAL)
        period: Time period (default: 1d for daily)
        limit: Number of data points to fetch (max 500)

    Returns:
        List of [timestamp_ms, basis_value] tuples
    """
    params = {
        'pair': symbol,
        'contractType': contract_type,
        'period': period,
        'limit': limit
    }

    data = fetch_binance_endpoint(BINANCE_ENDPOINTS['basis'], params)

    # Convert to standard format [timestamp, value]
    raw_data = []
    for point in data:
        raw_data.append([point['timestamp'], float(point['basis'])])

    # Standardize timestamps to midnight UTC
    standardized = standardize_to_daily_utc(raw_data)

    return standardized


def fetch_oi_history(
    symbol: str = DEFAULT_SYMBOL,
    period: str = '1d',
    limit: int = BINANCE_OI_LIMIT
) -> List[List]:
    """
    Fetch open interest history data.

    Args:
        symbol: Trading pair symbol (default: BTCUSDT)
        period: Time period (default: 1d for daily)
        limit: Number of data points to fetch (max 31)

    Returns:
        List of [timestamp_ms, oi_value] tuples
    """
    params = {
        'symbol': symbol,
        'period': period,
        'limit': limit
    }

    data = fetch_binance_endpoint(BINANCE_ENDPOINTS['oi_history'], params)

    # Convert to standard format [timestamp, value]
    raw_data = []
    for point in data:
        raw_data.append([point['timestamp'], float(point['sumOpenInterest'])])

    # Standardize timestamps to midnight UTC
    standardized = standardize_to_daily_utc(raw_data)

    return standardized


def fetch_taker_ratio(
    symbol: str = DEFAULT_SYMBOL,
    period: str = '1d',
    limit: int = BINANCE_TAKER_LIMIT
) -> List[List]:
    """
    Fetch taker buy/sell long/short ratio data (CVD proxy).

    Args:
        symbol: Trading pair symbol (default: BTCUSDT)
        period: Time period (default: 1d for daily)
        limit: Number of data points to fetch (max 31)

    Returns:
        List of [timestamp_ms, ratio_value] tuples
    """
    params = {
        'symbol': symbol,
        'period': period,
        'limit': limit
    }

    data = fetch_binance_endpoint(BINANCE_ENDPOINTS['taker_ratio'], params)

    # Convert to standard format [timestamp, value]
    raw_data = []
    for point in data:
        raw_data.append([point['timestamp'], float(point['buySellRatio'])])

    # Standardize timestamps to midnight UTC
    standardized = standardize_to_daily_utc(raw_data)

    return standardized


def fetch_with_stitching(
    fetch_function,
    days_back: int,
    chunk_size_days: int,
    symbol: str = DEFAULT_SYMBOL,
    **kwargs
) -> List[List]:
    """
    Generic stitching function for any Binance endpoint with date-based pagination.

    Args:
        fetch_function: Function to call for each chunk (e.g., fetch_basis_spread)
        days_back: Total number of days to fetch
        chunk_size_days: Days per chunk (based on API limit)
        symbol: Trading pair symbol
        **kwargs: Additional arguments to pass to fetch_function

    Returns:
        Combined and deduplicated list of [timestamp_ms, value] tuples
    """
    end_date = datetime.now()
    all_data = {}  # Use dict to deduplicate by timestamp

    # Calculate number of chunks needed
    num_chunks = (days_back + chunk_size_days - 1) // chunk_size_days

    print(f"\nFetching {days_back} days of data in {num_chunks} chunks...")

    for chunk_idx in range(num_chunks):
        # Calculate chunk limit (days, not data points)
        # For the last chunk, fetch only remaining days
        remaining_days = days_back - (chunk_idx * chunk_size_days)
        chunk_limit = min(chunk_size_days, remaining_days)

        print(f"Chunk {chunk_idx + 1}/{num_chunks}: Fetching {chunk_limit} days")

        try:
            chunk_data = fetch_function(
                symbol=symbol,
                limit=chunk_limit,
                **kwargs
            )

            # Add to dictionary (automatic deduplication)
            for ts, value in chunk_data:
                all_data[ts] = value

        except Exception as e:
            print(f"Error fetching chunk {chunk_idx + 1}: {e}")
            # Continue with next chunk rather than failing entirely

        # Rate limit protection
        if chunk_idx < num_chunks - 1:
            time.sleep(REQUEST_DELAY)

    # Convert back to sorted list
    sorted_data = sorted([[ts, val] for ts, val in all_data.items()])

    print(f"\nTotal data points collected: {len(sorted_data)}")
    if sorted_data:
        first_date = datetime.fromtimestamp(sorted_data[0][0] / 1000)
        last_date = datetime.fromtimestamp(sorted_data[-1][0] / 1000)
        print(f"Date range: {first_date.date()} to {last_date.date()}")

    return sorted_data


def fetch_recent_data(
    fetch_function,
    days: int = 30,
    symbol: str = DEFAULT_SYMBOL,
    **kwargs
) -> List[List]:
    """
    Fetch recent data for incremental updates (single request).

    Args:
        fetch_function: Function to call (e.g., fetch_basis_spread)
        days: Number of recent days to fetch (default: 30)
        symbol: Trading pair symbol
        **kwargs: Additional arguments to pass to fetch_function

    Returns:
        List of [timestamp_ms, value] tuples
    """
    return fetch_function(symbol=symbol, limit=days, **kwargs)
