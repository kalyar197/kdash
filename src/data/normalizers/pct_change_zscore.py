# data/normalizers/pct_change_zscore.py
"""
Velocity-Anchored Regression Divergence Normalizer (System 2)

Detects divergence by measuring when indicator velocity deviates from its expected
relationship with BTC velocity (percentage changes).

Formula: residual from rolling OLS regression of % changes, standardized

Mathematical Foundation:
- Uses rolling window OLS regression: ΔX_t% = α + β·ΔP_t% + ε_t
- Percentage changes calculated as log returns: ln(P_t / P_t-1)
- Measures residual ε_t normalized by rolling standard error
- Detects when historical velocity correlation structure breaks down

Use case:
- BEST for detecting when indicator momentum diverges from BTC momentum
- Captures non-linear momentum divergences and velocity regime changes
- Shows standardized prediction errors in velocity space
- The "0" line represents expected velocity relationship holds
"""

import numpy as np


def calculate_pct_change(values):
    """
    Calculate percentage changes using log returns.

    Formula: pct_change = ln(value_t / value_t-1)

    Args:
        values (np.array): Array of price/indicator values

    Returns:
        np.array: Array of percentage changes (length = len(values) - 1)
                  Returns np.nan for invalid calculations (division by zero, negative values)

    Note:
        - First element has no previous value, so output has length n-1
        - Returns np.nan if value_t-1 <= 0 (can't take log of zero/negative)
        - Returns np.nan if value_t <= 0
    """
    if len(values) < 2:
        return np.array([])

    pct_changes = []
    for i in range(1, len(values)):
        prev_val = values[i-1]
        curr_val = values[i]

        # Skip if either value is invalid (NaN, zero, or negative)
        if np.isnan(prev_val) or np.isnan(curr_val) or prev_val <= 0 or curr_val <= 0:
            pct_changes.append(np.nan)
        else:
            # Log return: ln(current / previous)
            try:
                pct_change = np.log(curr_val / prev_val)
                pct_changes.append(pct_change)
            except:
                pct_changes.append(np.nan)

    return np.array(pct_changes)


def normalize(dataset_data, asset_price_data, window=30):
    """
    Normalize using rolling regression of percentage changes (velocity-anchored approach).

    Mathematical Method:
    1. Calculate % changes for indicator: ΔX_t% = ln(X_t / X_t-1)
    2. Calculate % changes for price: ΔP_t% = ln(P_t / P_t-1)
    3. Rolling OLS regression over window: ΔX_t% = α + β·ΔP_t% + ε_t
    4. Calculate expected indicator % change: ΔX_expected% = α + β·ΔP_t%
    5. Calculate residual: ε_t = ΔX_actual% - ΔX_expected%
    6. Standardize: z_t = ε_t / std(ε_{t-window:t})

    Why This Is Correct:
    - Properly handles velocity correlation between indicator and price
    - Detects when momentum relationship breaks down (velocity regime change)
    - Residuals are approximately IID under correct model
    - Standard regression diagnostics apply

    Args:
        dataset_data (list): [[timestamp, value], ...] - The indicator/oscillator data
        asset_price_data (list): [[timestamp, open, high, low, close, volume], ...] - Asset OHLCV data
        window (int): Rolling window for regression (default: 30 days)

    Returns:
        list: [[timestamp, normalized_value], ...] where 0 = expected velocity relationship holds

    Interpretation:
        Positive values: Indicator momentum higher than expected from BTC momentum (bullish divergence)
        Negative values: Indicator momentum lower than expected from BTC momentum (bearish divergence)
        ±1: Prediction error within 1 standard error (normal)
        ±2: Significant velocity divergence (2 sigma prediction error)
        ±3: Extreme velocity divergence (model breakdown, regime change)
    """
    if not dataset_data or not asset_price_data:
        return []

    if len(dataset_data) < window + 1 or len(asset_price_data) < window + 1:
        # Need extra point for % change calculation
        return []

    # Create price lookup (closing prices)
    # Handle both OHLCV format (6 elements) and simple format (2 elements)
    try:
        if len(asset_price_data[0]) == 6:
            # OHLCV format: [timestamp, open, high, low, close, volume]
            price_lookup = {item[0]: item[4] for item in asset_price_data}
        elif len(asset_price_data[0]) == 2:
            # Simple format: [timestamp, close_price]
            price_lookup = {item[0]: item[1] for item in asset_price_data}
        else:
            raise ValueError(f"Unexpected asset_price_data format: {len(asset_price_data[0])} elements")
    except Exception as e:
        print(f"[Pct-Change Z-Score Normalizer] ERROR creating price lookup: {e}")
        return []

    # Extract indicator values, replacing None with np.nan
    indicator_values = np.array([item[1] if item[1] is not None else np.nan for item in dataset_data])

    # Build price array aligned with indicator timestamps
    aligned_prices = []
    for item in dataset_data:
        timestamp = item[0]
        if timestamp in price_lookup:
            aligned_prices.append(price_lookup[timestamp])
        else:
            # If no matching price, use forward fill
            if aligned_prices:
                aligned_prices.append(aligned_prices[-1])
            else:
                aligned_prices.append(np.nan)

    price_values = np.array(aligned_prices)

    # Calculate percentage changes for full arrays
    indicator_pct_changes = calculate_pct_change(indicator_values)
    price_pct_changes = calculate_pct_change(price_values)

    # Note: pct_changes arrays are 1 element shorter than original arrays
    # pct_changes[i] corresponds to dataset_data[i+1]

    # Calculate rolling regression residuals on percentage changes
    normalized_data = []

    # Start from window+1 because:
    # - We need window points for regression
    # - pct_changes[i] corresponds to dataset_data[i+1]
    for i in range(window, len(indicator_pct_changes)):
        # Current timestamp corresponds to dataset_data[i+1]
        timestamp = dataset_data[i+1][0]

        # Get rolling window data for % changes
        indicator_pct_window = indicator_pct_changes[i-window:i]
        price_pct_window = price_pct_changes[i-window:i]

        # Filter out NaN values
        valid_mask = ~(np.isnan(indicator_pct_window) | np.isnan(price_pct_window))
        valid_indicator_pct = indicator_pct_window[valid_mask]
        valid_price_pct = price_pct_window[valid_mask]

        # Skip if insufficient valid data (need at least 10 points for regression)
        if len(valid_indicator_pct) < 10:
            continue  # Skip timestamp - insufficient data for meaningful calculation

        # Skip if current % change values are NaN
        current_price_pct = price_pct_changes[i]
        current_indicator_pct = indicator_pct_changes[i]
        if np.isnan(current_price_pct) or np.isnan(current_indicator_pct):
            continue  # Skip null timestamps entirely (weekends/holidays)

        # Skip if no variance (flat data can't establish relationship)
        if np.std(valid_price_pct) == 0 or np.std(valid_indicator_pct) == 0:
            continue  # Skip timestamp - zero variance prevents regression

        # Perform OLS regression: indicator_pct = alpha + beta * price_pct
        # Using numpy polyfit (degree 1 = linear regression)
        try:
            # polyfit returns [beta, alpha] for degree 1
            coefficients = np.polyfit(valid_price_pct, valid_indicator_pct, deg=1)
            beta = coefficients[0]
            alpha = coefficients[1]

            # Expected indicator % change from regression
            expected_indicator_pct = alpha + beta * current_price_pct

            # Residual (prediction error in velocity space)
            residual = current_indicator_pct - expected_indicator_pct

            # Calculate standard error of residuals in window
            predicted_window = alpha + beta * valid_price_pct
            residuals_window = valid_indicator_pct - predicted_window
            std_error = np.std(residuals_window)

            # Standardize residual
            if std_error > 0:
                standardized_residual = residual / std_error
                normalized_data.append([timestamp, standardized_residual])
            else:
                # Skip if zero std_error (perfect prediction - can't standardize)
                continue

        except Exception:
            # If regression fails, skip timestamp
            continue

    return normalized_data


def normalize_with_thresholds(dataset_data, asset_price_data):
    """
    Normalize as z-scores and also return statistical thresholds.

    Returns:
        tuple: (normalized_data, thresholds_dict)
        where thresholds_dict = {
            'mean': mean_value,
            'std_dev': std_dev_value,
            'threshold_1_sigma': ±1,
            'threshold_2_sigma': ±2,
            'threshold_3_sigma': ±3
        }
    """
    normalized_data = normalize(dataset_data, asset_price_data)

    if not normalized_data:
        return normalized_data, {}

    values = np.array([item[1] for item in normalized_data])
    mean = np.mean(values)
    std_dev = np.std(values)

    thresholds = {
        'mean': float(mean),
        'std_dev': float(std_dev),
        'threshold_1_sigma': 1.0,
        'threshold_2_sigma': 2.0,
        'threshold_3_sigma': 3.0,
        'percentile_68': '±1 sigma',
        'percentile_95': '±2 sigma',
        'percentile_997': '±3 sigma'
    }

    return normalized_data, thresholds


def detect_outliers(dataset_data, asset_price_data, threshold=2.0):
    """
    Detect outliers using z-score threshold.

    Args:
        dataset_data (list): [[timestamp, value], ...]
        asset_price_data (list): Asset OHLCV data
        threshold (float): Z-score threshold (default: 2.0)

    Returns:
        list: [[timestamp, original_value, z_score], ...] for outliers only
    """
    normalized_data = normalize(dataset_data, asset_price_data)

    if not normalized_data:
        return []

    # Create timestamp to z-score lookup
    z_score_lookup = {item[0]: item[1] for item in normalized_data}

    outliers = []
    for item in dataset_data:
        timestamp = item[0]
        original_value = item[1]

        if timestamp in z_score_lookup:
            z_score = z_score_lookup[timestamp]

            # Check if absolute z-score exceeds threshold
            if abs(z_score) >= threshold:
                outliers.append([timestamp, original_value, z_score])

    return outliers


def get_info():
    """Return information about this normalizer"""
    return {
        'name': 'Velocity-Anchored Regression Divergence',
        'short_name': 'pct_change_zscore',
        'description': 'Detects when indicator momentum deviates from expected relationship with BTC momentum (velocity-based)',
        'formula': 'Standardized residual from rolling OLS of log returns: ε_t / std(ε)',
        'zero_line_meaning': 'Expected velocity relationship holds',
        'positive_meaning': 'Indicator momentum higher than predicted from BTC momentum',
        'negative_meaning': 'Indicator momentum lower than predicted from BTC momentum',
        'mathematical_properties': [
            'Uses log returns for percentage changes',
            'Properly handles velocity correlation between indicator and BTC',
            'Detects structural breaks in momentum relationship',
            'Residuals approximately IID under correct model',
            'Standard regression diagnostics apply'
        ],
        'interpretation': {
            '±1': 'Velocity prediction error within 1 standard error (normal)',
            '±2': 'Significant momentum divergence (2 sigma prediction error)',
            '±3': 'Extreme velocity divergence (model breakdown, regime change)'
        },
        'use_cases': [
            'Detecting momentum relationship breakdowns',
            'Identifying velocity regime changes',
            'Structural break detection in percentage changes',
            'Non-linear momentum divergence analysis',
            'Velocity mean reversion opportunities'
        ],
        'note': 'Default window=30 days for rolling regression. Best for System 2: Velocity-Anchored Oscillators'
    }
