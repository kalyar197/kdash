# data/incremental_data_manager.py
"""
Incremental data fetching and storage system for persistent historical data.
This module provides a reusable system that all plugins can use to:
- Store historical data persistently (survives server restarts)
- Fetch only new data on refreshes (reduces API calls)
- Merge new data with existing data intelligently
- Handle overlaps and deduplication
"""

import json
import os
from datetime import datetime, timedelta, timezone

# Create directory for historical data storage
HISTORICAL_DATA_DIR = os.path.join(os.path.dirname(__file__), '..', '..', 'storage', 'data')
if not os.path.exists(HISTORICAL_DATA_DIR):
    os.makedirs(HISTORICAL_DATA_DIR)
    print(f"[Incremental Manager] Created historical_data directory at {HISTORICAL_DATA_DIR}")

def load_historical_data(dataset_name):
    """
    Load existing historical data for a dataset from its JSON file.

    Args:
        dataset_name (str): Name of the dataset (e.g., 'eth_price', 'btc_price')

    Returns:
        list: Existing historical data, or empty list if no file exists
    """
    filepath = os.path.join(HISTORICAL_DATA_DIR, f"{dataset_name}.json")

    if not os.path.exists(filepath):
        print(f"[Incremental Manager] No historical data found for {dataset_name}")
        return []

    try:
        with open(filepath, 'r') as f:
            data = json.load(f)
            print(f"[Incremental Manager] Loaded {len(data)} historical records for {dataset_name}")
            return data
    except json.JSONDecodeError as e:
        print(f"[Incremental Manager] Error loading {dataset_name}: {e}")
        return []
    except Exception as e:
        print(f"[Incremental Manager] Unexpected error loading {dataset_name}: {e}")
        return []

def save_historical_data(dataset_name, data):
    """
    Save complete historical dataset to its JSON file.

    Args:
        dataset_name (str): Name of the dataset
        data (list): Complete dataset to save
    """
    filepath = os.path.join(HISTORICAL_DATA_DIR, f"{dataset_name}.json")

    try:
        with open(filepath, 'w') as f:
            json.dump(data, f)
        print(f"[Incremental Manager] Saved {len(data)} records to {dataset_name}.json")
    except Exception as e:
        print(f"[Incremental Manager] Error saving {dataset_name}: {e}")

def get_last_timestamp(dataset_name):
    """
    Get the most recent timestamp from historical data.

    Args:
        dataset_name (str): Name of the dataset

    Returns:
        int: Most recent timestamp in milliseconds, or None if no data exists
    """
    historical_data = load_historical_data(dataset_name)

    if not historical_data:
        return None

    # Data should be sorted, but ensure we get the max timestamp
    try:
        last_timestamp = max(record[0] for record in historical_data if isinstance(record, (list, tuple)) and len(record) >= 2)
        print(f"[Incremental Manager] Last timestamp for {dataset_name}: {last_timestamp} ({datetime.fromtimestamp(last_timestamp/1000, tz=timezone.utc).date()})")
        return last_timestamp
    except (ValueError, IndexError) as e:
        print(f"[Incremental Manager] Error getting last timestamp for {dataset_name}: {e}")
        return None

def merge_and_deduplicate(existing_data, new_data, overlap_days=3):
    """
    Intelligently merge new data with existing historical data.

    Strategy:
    - Identify overlap period (last N days of existing data)
    - Replace overlapping data with fresh data (handles corrections/adjustments)
    - Append truly new data
    - Sort by timestamp
    - Remove exact duplicates

    Args:
        existing_data (list): Historical data already stored
        new_data (list): Fresh data from API
        overlap_days (int): Number of days to treat as overlap/replacement zone

    Returns:
        list: Merged and deduplicated dataset, sorted chronologically
    """
    if not existing_data:
        print(f"[Incremental Manager] No existing data, returning new data as-is")
        return sorted(new_data, key=lambda x: x[0]) if new_data else []

    if not new_data:
        print(f"[Incremental Manager] No new data, returning existing data as-is")
        return existing_data

    print(f"[Incremental Manager] Merging {len(existing_data)} existing + {len(new_data)} new records")

    # Calculate overlap cutoff timestamp
    last_timestamp = max(record[0] for record in existing_data if isinstance(record, (list, tuple)))
    last_date = datetime.fromtimestamp(last_timestamp / 1000, tz=timezone.utc)
    overlap_cutoff_date = last_date - timedelta(days=overlap_days)
    overlap_cutoff_ms = int(overlap_cutoff_date.timestamp() * 1000)

    print(f"[Incremental Manager] Overlap cutoff: {overlap_cutoff_date.date()} (replacing data from this date forward)")

    # Keep only data BEFORE the overlap cutoff from existing data
    retained_existing = [record for record in existing_data if record[0] < overlap_cutoff_ms]
    print(f"[Incremental Manager] Retained {len(retained_existing)} records before overlap cutoff")

    # Combine retained existing data with ALL new data
    combined_data = retained_existing + new_data

    # Sort by timestamp
    combined_data.sort(key=lambda x: x[0])

    # Remove exact duplicates based on timestamp
    deduplicated = []
    seen_timestamps = set()

    for record in combined_data:
        timestamp = record[0]
        if timestamp not in seen_timestamps:
            deduplicated.append(record)
            seen_timestamps.add(timestamp)
        else:
            # If duplicate timestamp exists, keep the newer record (last occurrence)
            # Find and replace the existing record
            for i, existing_record in enumerate(deduplicated):
                if existing_record[0] == timestamp:
                    deduplicated[i] = record
                    break

    print(f"[Incremental Manager] Final merged dataset: {len(deduplicated)} records")

    # Validate chronological order
    for i in range(1, len(deduplicated)):
        if deduplicated[i][0] <= deduplicated[i-1][0]:
            print(f"[Incremental Manager] Warning: Non-chronological data detected at index {i}")

    return deduplicated

def get_fetch_start_date(dataset_name, overlap_days=3, default_days=365):
    """
    Determine the start date for fetching new data.

    Args:
        dataset_name (str): Name of the dataset
        overlap_days (int): Number of days to overlap for corrections
        default_days (int): Number of days to fetch if no historical data exists

    Returns:
        datetime: Start date for API fetch
    """
    last_timestamp = get_last_timestamp(dataset_name)

    if last_timestamp is None:
        # No historical data, fetch default amount
        start_date = datetime.now(tz=timezone.utc) - timedelta(days=default_days)
        print(f"[Incremental Manager] No historical data for {dataset_name}, fetching last {default_days} days")
        return start_date

    # Historical data exists, fetch from (last_timestamp - overlap) to now
    last_date = datetime.fromtimestamp(last_timestamp / 1000, tz=timezone.utc)
    start_date = last_date - timedelta(days=overlap_days)
    print(f"[Incremental Manager] Historical data exists for {dataset_name}, fetching from {start_date.date()}")

    return start_date

def get_oldest_timestamp(dataset_name):
    """
    Get the oldest (first) timestamp from historical data.

    Args:
        dataset_name (str): Name of the dataset

    Returns:
        int: Oldest timestamp in milliseconds, or None if no data exists
    """
    historical_data = load_historical_data(dataset_name)

    if not historical_data:
        return None

    try:
        oldest_timestamp = min(record[0] for record in historical_data if isinstance(record, (list, tuple)) and len(record) >= 2)
        oldest_date = datetime.fromtimestamp(oldest_timestamp/1000, tz=timezone.utc)
        print(f"[Incremental Manager] Oldest timestamp for {dataset_name}: {oldest_timestamp} ({oldest_date.date()})")
        return oldest_timestamp
    except (ValueError, IndexError) as e:
        print(f"[Incremental Manager] Error getting oldest timestamp for {dataset_name}: {e}")
        return None

def needs_older_data(dataset_name, requested_days):
    """
    Check if we need to fetch older historical data to satisfy the requested time range.

    Args:
        dataset_name (str): Name of the dataset
        requested_days (int): Number of days requested by user

    Returns:
        tuple: (needs_older, fetch_from_date) - whether we need older data and from which date
    """
    historical_data = load_historical_data(dataset_name)

    if not historical_data:
        # No historical data, definitely need to fetch
        fetch_from = datetime.now(tz=timezone.utc) - timedelta(days=requested_days)
        print(f"[Incremental Manager] No historical data, need to fetch from {fetch_from.date()}")
        return (True, fetch_from)

    oldest_timestamp = get_oldest_timestamp(dataset_name)
    if oldest_timestamp is None:
        fetch_from = datetime.now(tz=timezone.utc) - timedelta(days=requested_days)
        return (True, fetch_from)

    oldest_date = datetime.fromtimestamp(oldest_timestamp / 1000, tz=timezone.utc)
    required_start_date = datetime.now(tz=timezone.utc) - timedelta(days=requested_days)

    # Check if oldest data is recent enough
    if oldest_date > required_start_date:
        # Need older data
        days_missing = (oldest_date - required_start_date).days
        print(f"[Incremental Manager] Need {days_missing} more days of historical data for {dataset_name}")
        print(f"[Incremental Manager] Will fetch from {required_start_date.date()} to {oldest_date.date()}")
        return (True, required_start_date)
    else:
        # Have enough historical data
        print(f"[Incremental Manager] Have sufficient historical data for {requested_days} days")
        return (False, None)

def validate_data_structure(data):
    """
    Validate that data is in the correct format.

    Args:
        data (list): Data to validate

    Returns:
        tuple: (is_valid, structure_type, error_message)
    """
    if not data:
        return False, None, "Empty data"

    if not isinstance(data, list):
        return False, None, "Data must be a list"

    # Check first record structure
    first_record = data[0]
    if not isinstance(first_record, (list, tuple)):
        return False, None, "Records must be lists or tuples"

    record_length = len(first_record)

    if record_length == 2:
        structure_type = "simple"  # [timestamp, value]
    elif record_length == 6:
        structure_type = "OHLCV"  # [timestamp, open, high, low, close, volume]
    else:
        return False, None, f"Invalid record length: {record_length} (expected 2 or 6)"

    # Validate all records have consistent structure
    for i, record in enumerate(data):
        if len(record) != record_length:
            return False, structure_type, f"Inconsistent record length at index {i}"

        # Validate timestamp is a number
        if not isinstance(record[0], (int, float)):
            return False, structure_type, f"Invalid timestamp at index {i}"

    return True, structure_type, None
