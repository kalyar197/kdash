"""
Utility functions for fetching data from Deribit API.

Handles DVOL (Deribit Volatility Index) historical data fetching with proper
error handling, retries, and timestamp normalization.
"""

import requests
import time
from datetime import datetime, timedelta
from typing import List, Tuple, Optional
from data.derivatives_config import (
    DERIBIT_BASE,
    DERIBIT_ENDPOINTS,
    REQUEST_DELAY,
    MAX_RETRIES,
    RETRY_BACKOFF_BASE,
    DERIBIT_DVOL_LIMIT,
    DVOL_VALID_RANGE
)
from data.time_transformer import standardize_to_daily_utc


def fetch_dvol_history(
    currency: str,
    start_date: datetime,
    end_date: datetime,
    resolution: str = '1D'
) -> List[Tuple[int, float]]:
    """
    Fetch DVOL (Deribit Volatility Index) historical data for a currency.

    Args:
        currency: 'BTC' or 'ETH'
        start_date: Start date for historical data
        end_date: End date for historical data
        resolution: Data resolution ('1D' for daily)

    Returns:
        List of [timestamp_ms, dvol_value] tuples

    Raises:
        requests.RequestException: If API request fails after retries
        ValueError: If response format is invalid
    """
    start_ts = int(start_date.timestamp() * 1000)
    end_ts = int(end_date.timestamp() * 1000)

    params = {
        'currency': currency,
        'resolution': resolution,
        'start_timestamp': start_ts,
        'end_timestamp': end_ts
    }

    url = f"{DERIBIT_BASE}{DERIBIT_ENDPOINTS['dvol_history']}"

    for attempt in range(MAX_RETRIES):
        try:
            response = requests.get(url, params=params, timeout=30)
            response.raise_for_status()
            data = response.json()

            if not data.get('result'):
                raise ValueError(f"No result in Deribit response: {data}")

            result = data['result']
            if 'data' not in result:
                raise ValueError(f"No data field in result: {result}")

            raw_data = result['data']

            # Deribit returns 5-element OHLC structure: [timestamp, open, high, low, close]
            # Extract [timestamp, close] for our purposes
            simplified_data = []
            for point in raw_data:
                timestamp = point[0]
                dvol_close = point[4]  # Use closing DVOL value

                # Validate DVOL values
                if not (DVOL_VALID_RANGE[0] <= dvol_close <= DVOL_VALID_RANGE[1]):
                    print(f"Warning: DVOL value {dvol_close} outside valid range {DVOL_VALID_RANGE}")

                simplified_data.append([timestamp, dvol_close])

            # Standardize timestamps to midnight UTC (handles deduplication)
            standardized_data = standardize_to_daily_utc(simplified_data)

            print(f"Fetched {len(standardized_data)} DVOL data points for {currency}")
            return standardized_data

        except requests.exceptions.RequestException as e:
            if attempt < MAX_RETRIES - 1:
                wait_time = RETRY_BACKOFF_BASE * (2 ** attempt)
                print(f"Deribit API error (attempt {attempt + 1}/{MAX_RETRIES}): {e}")
                print(f"Retrying in {wait_time}s...")
                time.sleep(wait_time)
            else:
                raise

        except (ValueError, KeyError, IndexError) as e:
            raise ValueError(f"Invalid Deribit API response format: {e}")

    raise requests.RequestException(f"Failed to fetch DVOL after {MAX_RETRIES} attempts")


def fetch_dvol_with_stitching(
    currency: str,
    days_back: int = 1095
) -> List[Tuple[int, float]]:
    """
    Fetch DVOL data with automatic stitching for date ranges exceeding API limits.

    Deribit DVOL limit is 1000 data points (~33 months). For 36 months, we need 1-2 requests.

    Args:
        currency: 'BTC' or 'ETH'
        days_back: Number of days to fetch (default: 1095 = 36 months)

    Returns:
        Combined list of [timestamp_ms, dvol_value] tuples
    """
    end_date = datetime.now()
    start_date = end_date - timedelta(days=days_back)

    all_data = []
    current_start = start_date

    # Calculate how many chunks we need
    # DVOL limit is ~1000 points (33 months), so for 36 months we need 2 requests
    chunk_days = int(DERIBIT_DVOL_LIMIT * 0.95)  # Use 95% of limit for safety

    while current_start < end_date:
        current_end = min(current_start + timedelta(days=chunk_days), end_date)

        print(f"\nFetching DVOL for {currency}: {current_start.date()} to {current_end.date()}")

        chunk_data = fetch_dvol_history(currency, current_start, current_end)
        all_data.extend(chunk_data)

        current_start = current_end
        time.sleep(REQUEST_DELAY)  # Rate limit protection

    # Remove duplicates and sort by timestamp
    unique_data = {}
    for ts, value in all_data:
        unique_data[ts] = value  # Later values overwrite earlier ones

    sorted_data = sorted([[ts, val] for ts, val in unique_data.items()])

    print(f"\nTotal {currency} DVOL data points: {len(sorted_data)}")
    if sorted_data:
        first_date = datetime.fromtimestamp(sorted_data[0][0] / 1000)
        last_date = datetime.fromtimestamp(sorted_data[-1][0] / 1000)
        print(f"Date range: {first_date.date()} to {last_date.date()}")

    return sorted_data


def get_latest_dvol(currency: str) -> Optional[Tuple[int, float]]:
    """
    Fetch the most recent DVOL value for a currency.

    Args:
        currency: 'BTC' or 'ETH'

    Returns:
        [timestamp_ms, dvol_value] tuple or None if fetch fails
    """
    try:
        # Fetch last 2 days to ensure we get latest
        end_date = datetime.now()
        start_date = end_date - timedelta(days=2)

        data = fetch_dvol_history(currency, start_date, end_date)

        if data:
            return data[-1]  # Return most recent point
        return None

    except Exception as e:
        print(f"Error fetching latest DVOL for {currency}: {e}")
        return None
