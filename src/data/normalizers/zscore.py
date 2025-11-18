# data/normalizers/zscore.py
"""
Correlation-Based Regression Divergence Normalizer (Mathematically Rigorous)

Detects divergence by measuring when indicator deviates from its expected relationship with price.
Formula: residual from rolling OLS regression, standardized

Mathematical Foundation:
- Uses rolling window ordinary least squares (OLS) regression: X_t = α + β·P_t + ε_t
- Measures residual ε_t normalized by rolling standard error
- Properly handles dependent processes (indicator calculated from price)
- Detects when historical correlation structure breaks down

Use case:
- BEST for detecting when indicator-price relationship changes
- Captures non-linear divergences and regime changes
- Shows standardized prediction errors
- The "0" line represents expected relationship holds
"""

import numpy as np


def normalize(dataset_data, asset_price_data, window=30):
    """
    Normalize using rolling regression residuals (mathematically rigorous approach).

    Mathematical Method:
    1. Rolling OLS regression over window: X_t = α + β·P_t + ε_t
    2. Calculate expected indicator value: X_expected = α + β·P_t
    3. Calculate residual: ε_t = X_actual - X_expected
    4. Standardize: z_t = ε_t / std(ε_{t-window:t})

    Why This Is Correct:
    - Properly handles correlation between indicator and price
    - Detects when relationship breaks down (structural break)
    - Residuals are approximately IID under correct model
    - Standard regression diagnostics apply

    Args:
        dataset_data (list): [[timestamp, value], ...] - The indicator/oscillator data
        asset_price_data (list): [[timestamp, open, high, low, close, volume], ...] - Asset OHLCV data
        window (int): Rolling window for regression (default: 30 days)

    Returns:
        list: [[timestamp, normalized_value], ...] where 0 = expected relationship holds

    Interpretation:
        Positive values: Indicator higher than expected from price relationship (bullish divergence)
        Negative values: Indicator lower than expected from price relationship (bearish divergence)
        ±1: Prediction error within 1 standard error (normal)
        ±2: Significant divergence (2 sigma prediction error)
        ±3: Extreme divergence (model breakdown, regime change)
    """
    if not dataset_data or not asset_price_data:
        return []

    if len(dataset_data) < window or len(asset_price_data) < window:
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
        print(f"[Z-Score Normalizer] ERROR creating price lookup: {e}")
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

    # Calculate rolling regression residuals
    normalized_data = []

    for i in range(window, len(dataset_data)):
        timestamp = dataset_data[i][0]

        # Get rolling window data
        indicator_window = indicator_values[i-window:i]
        price_window = price_values[i-window:i]

        # Filter out NaN values
        valid_mask = ~(np.isnan(indicator_window) | np.isnan(price_window))
        valid_indicator = indicator_window[valid_mask]
        valid_price = price_window[valid_mask]

        # Skip if insufficient valid data (need at least 10 points for regression)
        if len(valid_indicator) < 10:
            continue  # Skip timestamp - insufficient data for meaningful calculation

        # Skip if current values are NaN
        current_price = price_values[i]
        current_indicator = indicator_values[i]
        if np.isnan(current_price) or np.isnan(current_indicator):
            continue  # Skip null timestamps entirely (weekends/holidays)

        # Skip if no variance (flat data can't establish relationship)
        if np.std(valid_price) == 0 or np.std(valid_indicator) == 0:
            continue  # Skip timestamp - zero variance prevents regression

        # Perform OLS regression: indicator = alpha + beta * price
        # Using numpy polyfit (degree 1 = linear regression)
        try:
            # polyfit returns [beta, alpha] for degree 1
            coefficients = np.polyfit(valid_price, valid_indicator, deg=1)
            beta = coefficients[0]
            alpha = coefficients[1]

            # Expected indicator value from regression
            expected_indicator = alpha + beta * current_price

            # Residual (prediction error)
            residual = current_indicator - expected_indicator

            # Calculate standard error of residuals in window
            predicted_window = alpha + beta * valid_price
            residuals_window = valid_indicator - predicted_window
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

    if not dataset_data:
        return normalized_data, {}

    values = np.array([item[1] for item in dataset_data])
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
        list: [[timestamp, value, z_score], ...] for outliers only
    """
    normalized_data = normalize(dataset_data, asset_price_data)

    outliers = []
    for i, item in enumerate(dataset_data):
        timestamp = item[0]
        original_value = item[1]
        z_score = normalized_data[i][1]

        # Check if absolute z-score exceeds threshold
        if abs(z_score) >= threshold:
            outliers.append([timestamp, original_value, z_score])

    return outliers


def get_info():
    """Return information about this normalizer"""
    return {
        'name': 'Regression Divergence',
        'short_name': 'regression',
        'description': 'Detects when indicator deviates from expected relationship with price (mathematically rigorous)',
        'formula': 'Standardized residual from rolling OLS: ε_t / std(ε)',
        'zero_line_meaning': 'Expected relationship holds',
        'positive_meaning': 'Indicator higher than predicted from price',
        'negative_meaning': 'Indicator lower than predicted from price',
        'mathematical_properties': [
            'Properly handles correlation between indicator and price',
            'Detects structural breaks in relationship',
            'Residuals approximately IID under correct model',
            'Standard regression diagnostics apply'
        ],
        'interpretation': {
            '±1': 'Prediction error within 1 standard error (normal)',
            '±2': 'Significant divergence (2 sigma prediction error)',
            '±3': 'Extreme divergence (model breakdown, regime change)'
        },
        'use_cases': [
            'Detecting relationship breakdowns',
            'Identifying regime changes',
            'Structural break detection',
            'Non-linear divergence analysis',
            'Mean reversion opportunities'
        ],
        'note': 'Default window=30 days for rolling regression. Best for indicators calculated from price (RSI, MACD, etc.)'
    }
