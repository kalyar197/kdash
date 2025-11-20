"""
Tension² Pairs Analyzer

This module calculates two-level tension analysis for sentiment vs mechanics pairs:
- Tension₁ (Raw Divergence): Sentiment_z - Mechanics_z
- Tension₂ (Context-Aware Abnormality): Actual Tension₁ - Expected Tension₁

Tension₂ measures how abnormal the current divergence is relative to what
historically happens at this sentiment level. This provides context-aware
divergence detection for contrarian trading strategies.

Used by System 3: Tension² Pairs Oscillator Dashboard
"""

import numpy as np
from typing import List, Tuple, Dict, Optional
from . import zscore


def calculate_tensions(
    sentiment_data: List[List],
    mechanics_data: List[List],
    btc_price_data: List[List],
    window: int = 30
) -> Dict[str, List[List]]:
    """
    Calculate Tension₁ and Tension₂ for a sentiment vs mechanics pair.

    Process:
    1. Normalize both sentiment and mechanics using zscore.normalize()
       (price-anchored residual z-scores)
    2. Calculate Tension₁ = Sentiment_z - Mechanics_z (raw divergence)
    3. Calculate Tension₂ = Actual Tension₁ - Expected Tension₁
       where Expected Tension₁ is the historical average divergence at
       the current sentiment level (context-aware abnormality)

    Args:
        sentiment_data: Time series data [[timestamp, value], ...]
        mechanics_data: Time series data [[timestamp, value], ...]
        btc_price_data: BTC price data for normalization [[timestamp, value], ...]
        window: Rolling window size for z-score and expectation calculations (default: 30)

    Returns:
        {
            'tension1': [[timestamp, value], ...],  # Raw divergence
            'tension2': [[timestamp, value], ...]   # Context-aware abnormality
        }

    Example:
        >>> sentiment = [[1609459200, 50.5], [1609545600, 52.3], ...]
        >>> mechanics = [[1609459200, 0.8], [1609545600, 0.9], ...]
        >>> btc_price = [[1609459200, 29000], [1609545600, 29500], ...]
        >>> tensions = calculate_tensions(sentiment, mechanics, btc_price, window=30)
        >>> tensions['tension1']  # Sentiment_z - Mechanics_z
        [[1609459200, 1.2], [1609545600, -0.5], ...]
        >>> tensions['tension2']  # Actual - Expected Tension₁
        [[1609459200, 0.8], [1609545600, -0.3], ...]
    """

    # Step 1: Normalize sentiment and mechanics to z-scores
    sentiment_z = zscore.normalize(sentiment_data, btc_price_data, window)
    mechanics_z = zscore.normalize(mechanics_data, btc_price_data, window)

    # Step 2: Align timestamps (use intersection of both datasets)
    tension1_data = _calculate_tension1(sentiment_z, mechanics_z)

    # Step 3: Calculate Tension₂ (context-aware divergence abnormality)
    tension2_data = _calculate_tension2(sentiment_z, tension1_data, window)

    return {
        'tension1': tension1_data,
        'tension2': tension2_data
    }


def _calculate_tension1(
    sentiment_z: List[List],
    mechanics_z: List[List]
) -> List[List]:
    """
    Calculate Tension₁ = Sentiment_z - Mechanics_z

    Only includes timestamps present in BOTH datasets.

    Args:
        sentiment_z: Normalized sentiment [[timestamp, z_score], ...]
        mechanics_z: Normalized mechanics [[timestamp, z_score], ...]

    Returns:
        [[timestamp, tension1_value], ...]
    """
    # Convert to dictionaries for fast lookup
    sentiment_dict = {int(ts): val for ts, val in sentiment_z}
    mechanics_dict = {int(ts): val for ts, val in mechanics_z}

    # Find common timestamps
    common_timestamps = sorted(set(sentiment_dict.keys()) & set(mechanics_dict.keys()))

    # Calculate Tension₁ = Sentiment_z - Mechanics_z
    tension1 = []
    for ts in common_timestamps:
        sent_z = sentiment_dict[ts]
        mech_z = mechanics_dict[ts]

        # Skip if either value is None/NaN
        if sent_z is None or mech_z is None:
            continue
        if np.isnan(sent_z) or np.isnan(mech_z):
            continue

        divergence = sent_z - mech_z
        tension1.append([ts, divergence])

    return tension1


def _calculate_tension2(
    sentiment_z: List[List],
    tension1_data: List[List],
    window: int = 30,
    bucket_size: float = 0.3
) -> List[List]:
    """
    Calculate Tension₂ = Actual Tension₁ - Expected Tension₁

    This measures context-aware divergence abnormality by comparing current
    divergence to what historically happens at this sentiment level.

    Process:
    1. For each timestamp t, get current Sentiment_z value
    2. Look back {window} days in history
    3. Find all historical points where Sentiment_z was similar (within bucket)
    4. Average their Tension₁ values → Expected_Tension₁(t)
    5. Tension₂(t) = Actual_Tension₁(t) - Expected_Tension₁(t)

    Args:
        sentiment_z: Normalized sentiment [[timestamp, z_score], ...]
        tension1_data: Tension₁ time series [[timestamp, value], ...]
        window: Rolling window size for historical lookback (default: 30)
        bucket_size: Sentiment similarity threshold in σ units (default: 0.3)

    Returns:
        [[timestamp, tension2_value], ...]

    Example:
        If current Sentiment_z = +2.0 and historically when Sentiment was ~+2.0,
        Tension₁ averaged +0.5, but current Tension₁ = +1.5, then:
        Tension₂ = +1.5 - (+0.5) = +1.0 (abnormally high divergence for this sentiment)
    """
    if len(tension1_data) < window:
        # Not enough data for rolling window
        return []

    # Convert to dicts for fast lookup
    sentiment_dict = {int(ts): val for ts, val in sentiment_z}
    tension1_dict = {int(ts): val for ts, val in tension1_data}

    # Get common timestamps (sorted)
    common_timestamps = sorted(set(sentiment_dict.keys()) & set(tension1_dict.keys()))

    tension2 = []

    for i, current_ts in enumerate(common_timestamps):
        current_sentiment = sentiment_dict[current_ts]
        current_tension1 = tension1_dict[current_ts]

        # Skip if either value is None/NaN
        if current_sentiment is None or current_tension1 is None:
            continue
        if np.isnan(current_sentiment) or np.isnan(current_tension1):
            continue

        # Define rolling window (look back {window} timestamps, excluding current)
        start_idx = max(0, i - window)
        end_idx = i  # Exclude current point from historical average

        # Skip if insufficient historical data
        if end_idx - start_idx < 10:  # Minimum 10 points for meaningful statistics
            continue

        # Find historical points with similar sentiment levels
        historical_tension1_values = []

        for hist_idx in range(start_idx, end_idx):
            hist_ts = common_timestamps[hist_idx]
            hist_sentiment = sentiment_dict[hist_ts]
            hist_tension1 = tension1_dict[hist_ts]

            # Skip None/NaN
            if hist_sentiment is None or hist_tension1 is None:
                continue
            if np.isnan(hist_sentiment) or np.isnan(hist_tension1):
                continue

            # Check if historical sentiment is within bucket of current sentiment
            if abs(hist_sentiment - current_sentiment) <= bucket_size:
                historical_tension1_values.append(hist_tension1)

        # Skip if no matching historical points found
        if len(historical_tension1_values) < 3:  # Minimum 3 matches for meaningful average
            continue

        # Calculate Expected Tension₁ (average of historical values at this sentiment level)
        expected_tension1 = np.mean(historical_tension1_values)

        # Calculate Tension₂ = Actual - Expected
        tension2_value = current_tension1 - expected_tension1

        tension2.append([current_ts, tension2_value])

    return tension2


def identify_signals(
    tension1_data: List[List],
    tension2_data: List[List],
    threshold: float = 2.0
) -> Dict[str, List[List]]:
    """
    Identify BUY and SELL signals based on Tension₁ and Tension₂.

    Signal Rules:
    - SELL: Tension₂ > +threshold AND Tension₁ > 0
    - BUY:  Tension₂ > +threshold AND Tension₁ < 0

    (Threshold represents statistical significance, typically 2σ)

    Args:
        tension1_data: Tension₁ time series [[timestamp, value], ...]
        tension2_data: Tension₂ time series [[timestamp, value], ...]
        threshold: Statistical threshold (default: 2.0 for 2σ)

    Returns:
        {
            'sell_signals': [[timestamp, tension2_value], ...],
            'buy_signals': [[timestamp, tension2_value], ...]
        }
    """
    # Convert Tension₁ to dict for fast lookup
    tension1_dict = {int(ts): val for ts, val in tension1_data}

    sell_signals = []
    buy_signals = []

    for ts, tension2_val in tension2_data:
        # Check if Tension₂ exceeds threshold
        if abs(tension2_val) > threshold:
            # Get corresponding Tension₁ value
            tension1_val = tension1_dict.get(int(ts))

            if tension1_val is None:
                continue

            # Determine signal type based on Tension₁ sign
            if tension2_val > threshold and tension1_val > 0:
                # SELL signal: High abnormality + sentiment > mechanics
                sell_signals.append([ts, tension2_val])
            elif tension2_val > threshold and tension1_val < 0:
                # BUY signal: High abnormality + sentiment < mechanics
                buy_signals.append([ts, tension2_val])

    return {
        'sell_signals': sell_signals,
        'buy_signals': buy_signals
    }
