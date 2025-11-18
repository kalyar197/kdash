# data/time_transformer.py
"""
Time standardization module for OHLCV data
Handles both 2-element [timestamp, value] and 6-element [timestamp, O, H, L, C, V] structures
Ensures all timestamps are normalized to daily UTC boundaries
PRESERVES ALL DATA COMPONENTS - No data loss

CRITICAL POLICY: NO MOCK VALUES OR ESTIMATES
- Missing days are included in the timeline with NaN (null in JSON) values
- Frontend visualization renders gaps, NOT interpolated/estimated lines
- This ensures data integrity and prevents misleading visualizations
"""

from datetime import datetime, timezone, timedelta

def standardize_to_daily_utc(raw_data):
    """
    Takes raw data and standardizes timestamps to UTC daily boundaries.
    
    CRITICAL: Now handles two data structures:
    - 2-element: [timestamp, value] - for simple price/dominance data
    - 6-element: [timestamp, open, high, low, close, volume] - for OHLCV data
    
    The timestamp is normalized to 00:00:00 UTC.
    ALL OTHER COMPONENTS ARE PRESERVED UNCHANGED.
    
    Args:
        raw_data (list): A list of lists, where each inner list is either:
                         [unix_millisecond_timestamp, value] OR
                         [unix_millisecond_timestamp, open, high, low, close, volume]
    
    Returns:
        list: A standardized list with same structure as input.
    """
    if not raw_data:
        return []
    
    # Detect data structure from first valid element
    data_structure = None
    for item in raw_data:
        if isinstance(item, (list, tuple)) and len(item) >= 2:
            data_structure = len(item)
            print(f"Detected data structure: {data_structure} elements per record")
            break
    
    if not data_structure:
        print("Error: Could not determine data structure")
        return []
    
    standardized_data = []
    seen_dates = set()
    
    for item in raw_data:
        # Validate structure consistency
        if not isinstance(item, (list, tuple)) or len(item) != data_structure:
            print(f"Warning: Skipping invalid/inconsistent data point: {item}")
            continue
        
        # Extract timestamp (always first element)
        ms_timestamp = item[0]
        
        # Validate timestamp
        if not isinstance(ms_timestamp, (int, float)):
            print(f"Warning: Invalid timestamp: {ms_timestamp}")
            continue
        
        # Convert timestamp to datetime
        try:
            # Handle both millisecond and second timestamps
            if ms_timestamp > 1000000000000:  # Milliseconds
                dt_object = datetime.fromtimestamp(ms_timestamp / 1000, tz=timezone.utc)
            else:  # Seconds
                dt_object = datetime.fromtimestamp(ms_timestamp, tz=timezone.utc)
        except (ValueError, OSError) as e:
            print(f"Warning: Could not parse timestamp {ms_timestamp}: {e}")
            continue
        
        # CRITICAL: Normalize timestamp to beginning of UTC day
        normalized_dt = dt_object.replace(hour=0, minute=0, second=0, microsecond=0)
        
        # Check for duplicates on the same day
        if normalized_dt in seen_dates:
            continue
        seen_dates.add(normalized_dt)
        
        # Convert normalized datetime back to millisecond timestamp
        standardized_ms_timestamp = int(normalized_dt.timestamp() * 1000)
        
        # Build standardized record based on structure
        if data_structure == 2:
            # Simple [timestamp, value] structure
            value = item[1]
            
            # Validate value
            if value is None or (isinstance(value, str) and not value.strip()):
                print(f"Warning: Invalid value for date {normalized_dt.date()}: {value}")
                continue
            
            try:
                numeric_value = float(value)
            except (ValueError, TypeError):
                print(f"Warning: Could not convert value to number: {value}")
                continue
            
            standardized_data.append([standardized_ms_timestamp, numeric_value])
            
        elif data_structure == 6:
            # OHLCV structure [timestamp, open, high, low, close, volume]
            # PRESERVE ALL COMPONENTS
            try:
                standardized_record = [
                    standardized_ms_timestamp,
                    float(item[1]),  # open
                    float(item[2]),  # high
                    float(item[3]),  # low
                    float(item[4]),  # close
                    float(item[5])   # volume
                ]
                
                # Validate OHLCV logic (high >= low, high >= open/close, etc.)
                if standardized_record[2] < standardized_record[3]:  # high < low
                    print(f"Warning: Invalid OHLCV data (high < low) for {normalized_dt.date()}")
                    continue
                
                standardized_data.append(standardized_record)
                
            except (ValueError, TypeError) as e:
                print(f"Warning: Could not process OHLCV data: {e}")
                continue
        else:
            print(f"Warning: Unsupported data structure with {data_structure} elements")
            continue
    
    # Sort by timestamp to ensure chronological order
    standardized_data.sort(key=lambda x: x[0])

    # Create continuous daily index with NaN for missing data (NO MOCK VALUES)
    # This ensures visualization shows gaps instead of interpolated/estimated data
    if len(standardized_data) > 1:
        continuous_data = create_continuous_index_with_nan(standardized_data, data_structure)
        return continuous_data

    return standardized_data

def create_continuous_index_with_nan(data, data_structure):
    """
    Create a continuous daily index with NaN values for missing days.

    CRITICAL: NO MOCK VALUES OR ESTIMATES - missing days contain NaN (null in JSON)
    to ensure the frontend visualization renders gaps, not interpolated lines.

    Args:
        data: Sorted list of data points (either 2-element or 6-element)
        data_structure: 2 for [timestamp, value], 6 for OHLCV

    Returns:
        List with continuous daily timestamps, NaN for missing data
    """
    if len(data) < 2:
        return data

    # Get date range
    start_date = datetime.fromtimestamp(data[0][0] / 1000, tz=timezone.utc)
    end_date = datetime.fromtimestamp(data[-1][0] / 1000, tz=timezone.utc)

    # Create lookup dictionary for existing data
    data_dict = {point[0]: point for point in data}

    # Generate continuous daily range
    continuous_data = []
    current_date = start_date
    gap_count = 0

    while current_date <= end_date:
        current_timestamp = int(current_date.timestamp() * 1000)

        if current_timestamp in data_dict:
            # Real data exists for this day
            continuous_data.append(data_dict[current_timestamp])
        else:
            # Missing data - insert NaN values (NO MOCK VALUES)
            gap_count += 1
            if data_structure == 2:
                # Simple structure: [timestamp, NaN]
                continuous_data.append([current_timestamp, None])
            elif data_structure == 6:
                # OHLCV structure: [timestamp, NaN, NaN, NaN, NaN, NaN]
                continuous_data.append([current_timestamp, None, None, None, None, None])

        # Move to next day
        current_date += timedelta(days=1)

    if gap_count > 0:
        print(f"Info: Created continuous index with {gap_count} gap days (NaN values) between {start_date.date()} and {end_date.date()}")

    return continuous_data

def validate_daily_alignment(data):
    """
    Validate that all data points are properly aligned to daily boundaries.
    Works with both 2-element and 6-element structures.
    """
    for point in data:
        timestamp_ms = point[0]
        dt = datetime.fromtimestamp(timestamp_ms / 1000, tz=timezone.utc)
        
        if dt.hour != 0 or dt.minute != 0 or dt.second != 0 or dt.microsecond != 0:
            print(f"Warning: Timestamp not aligned to daily boundary: {dt}")
            return False
    
    return True

def get_date_range(data):
    """
    Get the date range of the dataset.
    Works with both 2-element and 6-element structures.
    """
    if not data:
        return None, None
    
    start_timestamp = data[0][0]
    end_timestamp = data[-1][0]
    
    start_date = datetime.fromtimestamp(start_timestamp / 1000, tz=timezone.utc)
    end_date = datetime.fromtimestamp(end_timestamp / 1000, tz=timezone.utc)
    
    return start_date, end_date

def extract_component(ohlcv_data, component='close'):
    """
    Extract a specific component from OHLCV data.
    Useful for indicators that only need closing prices.
    
    Args:
        ohlcv_data: List of [timestamp, open, high, low, close, volume]
        component: 'open', 'high', 'low', 'close', or 'volume'
    
    Returns:
        List of [timestamp, value] pairs
    """
    component_map = {
        'open': 1,
        'high': 2,
        'low': 3,
        'close': 4,
        'volume': 5
    }
    
    if component not in component_map:
        raise ValueError(f"Invalid component: {component}")
    
    index = component_map[component]
    
    extracted_data = []
    for point in ohlcv_data:
        if len(point) == 6:  # OHLCV structure
            extracted_data.append([point[0], point[index]])
        elif len(point) == 2 and component == 'close':
            # Fallback for simple price data
            extracted_data.append(point)
    
    return extracted_data