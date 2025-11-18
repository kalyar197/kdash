"""
Markov Regime Detector

Uses a 2-state Markov Switching Autoregressive model to classify
market volatility into hidden states:
  - Regime 0: Low Volatility
  - Regime 1: High Volatility

This provides objective market context ("Radar") independent of
the user's oscillator tuning settings ("Pilot").

The model is fitted to Garman-Klass volatility and uses Bayesian
inference to determine the most probable regime for each timestamp.
"""

import numpy as np
import json
import os
from datetime import datetime

# Cache for fitted model and regime classifications
_REGIME_CACHE = {
    'model': None,
    'regimes': None,
    'timestamps': None,
    'asset': None,
    'last_update': None
}


def get_metadata():
    """Returns display metadata for regime classifications."""
    return {
        'label': 'Market Regime',
        'states': {
            0: {
                'label': 'Low Volatility',
                'color': 'rgba(0, 122, 255, 0.1)',  # Blue
                'description': 'Stable, range-bound market conditions'
            },
            1: {
                'label': 'High Volatility',
                'color': 'rgba(255, 59, 48, 0.1)',  # Red
                'description': 'Unstable, trending market conditions'
            }
        }
    }


def fit_markov_model(volatility_data, k_regimes=2, order=1):
    """
    Fit a Markov Switching Autoregressive model to volatility data.

    Args:
        volatility_data: List of [timestamp, volatility] pairs
        k_regimes: Number of regimes (default: 2)
        order: AR order (default: 1 for AR(1))

    Returns:
        Fitted model object or None if fitting fails
    """
    try:
        from statsmodels.tsa.regime_switching import markov_autoregression

        # Extract just the volatility values (strip timestamps)
        volatilities = np.array([v[1] for v in volatility_data])

        # Need at least 50 observations for stable fitting
        if len(volatilities) < 50:
            print(f"[Markov] Insufficient data: {len(volatilities)} points (need 50+)")
            return None

        # Fit Markov Switching AR model
        # - k_regimes=2: Two hidden states (low-vol, high-vol)
        # - order=1: AR(1) - volatility depends on previous volatility
        # - switching_variance=True: Each regime has different variance
        print(f"[Markov] Fitting 2-state AR({order}) model to {len(volatilities)} volatility points...")

        model = markov_autoregression.MarkovAutoregression(
            endog=volatilities,
            k_regimes=k_regimes,
            order=order,
            switching_ar=True,
            switching_variance=True
        )

        # Fit the model (this can take a while)
        fitted_model = model.fit(maxiter=100, disp=False)

        print(f"[Markov] Model fitted successfully")
        print(f"[Markov] Log-likelihood: {fitted_model.llf:.2f}")
        print(f"[Markov] AIC: {fitted_model.aic:.2f}")

        return fitted_model

    except Exception as e:
        print(f"[Markov] Model fitting failed: {str(e)}")
        return None


def classify_regimes(fitted_model, volatility_data):
    """
    Use fitted Markov model to classify each timestamp into a regime.

    Args:
        fitted_model: Fitted MarkovAutoregression model
        volatility_data: List of [timestamp, volatility] pairs

    Returns:
        List of [timestamp, regime_int] pairs where regime_int is 0 or 1
    """
    if fitted_model is None:
        print("[Markov] No fitted model available")
        return []

    try:
        # Get smoothed probabilities (uses all data for inference)
        smoothed_probs = fitted_model.smoothed_marginal_probabilities

        # Extract timestamps
        timestamps = [v[0] for v in volatility_data]

        # AR models lose the first observation(s) due to lag structure
        # smoothed_probs has shape (n_obs - order, k_regimes)
        n_probs = len(smoothed_probs)
        n_timestamps = len(timestamps)

        print(f"[Markov] Model probabilities: {n_probs} points")
        print(f"[Markov] Input timestamps: {n_timestamps} points")

        # Skip the first observations that were used for initialization
        offset = n_timestamps - n_probs
        regime_classifications = []

        for i in range(n_probs):
            timestamp = timestamps[i + offset]
            probs = smoothed_probs[i]

            # Select regime with highest probability
            regime = int(np.argmax(probs))

            regime_classifications.append([timestamp, regime])

        print(f"[Markov] Classified {len(regime_classifications)} observations")

        # Show regime distribution
        regimes = [r[1] for r in regime_classifications]
        regime_0_count = sum(1 for r in regimes if r == 0)
        regime_1_count = sum(1 for r in regimes if r == 1)

        print(f"[Markov] Regime 0 (Low-Vol):  {regime_0_count} observations ({regime_0_count/len(regimes)*100:.1f}%)")
        print(f"[Markov] Regime 1 (High-Vol): {regime_1_count} observations ({regime_1_count/len(regimes)*100:.1f}%)")

        return regime_classifications

    except Exception as e:
        print(f"[Markov] Regime classification failed: {str(e)}")
        import traceback
        traceback.print_exc()
        return []


def simple_threshold_regimes(volatility_data, threshold_percentile=50):
    """
    Fallback: Simple threshold-based regime classification.

    Used when Markov model fitting fails.

    Args:
        volatility_data: List of [timestamp, volatility] pairs
        threshold_percentile: Percentile to use as threshold (default: 50 = median)

    Returns:
        List of [timestamp, regime_int] pairs
    """
    if not volatility_data:
        return []

    volatilities = [v[1] for v in volatility_data]
    threshold = np.percentile(volatilities, threshold_percentile)

    print(f"[Markov] Using simple threshold fallback: {threshold:.2f}% (p{threshold_percentile})")

    regime_classifications = []
    for timestamp, volatility in volatility_data:
        regime = 1 if volatility > threshold else 0
        regime_classifications.append([timestamp, regime])

    return regime_classifications


def get_data(days='365', asset='btc', force_refresh=False):
    """
    Get regime classifications for a given asset.

    This function uses caching to avoid refitting the model on every request.

    Args:
        days: Number of days of historical data
        asset: Asset symbol ('btc', 'eth', 'gold')
        force_refresh: Force model re-fitting even if cache exists

    Returns:
        Dictionary with metadata and regime time series
    """
    global _REGIME_CACHE

    # Check cache
    cache_key = f"{asset}_{days}"
    if not force_refresh and _REGIME_CACHE['asset'] == cache_key and _REGIME_CACHE['regimes'] is not None:
        print(f"[Markov] Using cached regime classifications for {asset}")
        return {
            'metadata': get_metadata(),
            'data': _REGIME_CACHE['regimes'],
            'structure': 'simple'
        }

    # Import volatility module
    from . import volatility

    # Get volatility data
    print(f"[Markov] Fetching volatility data for {asset}...")
    volatility_result = volatility.get_data(days=days, asset=asset)
    volatility_data = volatility_result.get('data', [])

    if not volatility_data:
        print("[Markov] No volatility data available")
        return {
            'metadata': get_metadata(),
            'data': [],
            'structure': 'simple'
        }

    print(f"[Markov] Got {len(volatility_data)} volatility points")

    # Fit Markov model
    fitted_model = fit_markov_model(volatility_data)

    # Classify regimes
    if fitted_model is not None:
        regime_data = classify_regimes(fitted_model, volatility_data)
    else:
        # Fallback to simple threshold
        print("[Markov] Falling back to simple threshold-based classification")
        regime_data = simple_threshold_regimes(volatility_data)

    # Update cache
    _REGIME_CACHE['model'] = fitted_model
    _REGIME_CACHE['regimes'] = regime_data
    _REGIME_CACHE['timestamps'] = [r[0] for r in regime_data]
    _REGIME_CACHE['asset'] = cache_key
    _REGIME_CACHE['last_update'] = datetime.now().isoformat()

    return {
        'metadata': get_metadata(),
        'data': regime_data,
        'structure': 'simple'
    }


if __name__ == '__main__':
    # Test the Markov regime detector
    import sys
    import os
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

    from data import volatility

    print("Testing Markov Regime Detector...")
    print("=" * 60)

    # Get volatility data
    print("Fetching volatility data...")
    volatility_result = volatility.get_data(days='365', asset='btc')
    volatility_data = volatility_result.get('data', [])

    print(f"Got {len(volatility_data)} volatility points")

    # Fit model and classify
    fitted_model = fit_markov_model(volatility_data)

    if fitted_model is not None:
        regime_data = classify_regimes(fitted_model, volatility_data)
    else:
        print("Falling back to simple threshold")
        regime_data = simple_threshold_regimes(volatility_data)

    print("\n" + "=" * 60)
    print(f"Regime classifications: {len(regime_data)} points")

    if regime_data:
        # Show first and last
        first = regime_data[0]
        last = regime_data[-1]

        print(f"\nFirst point: Regime {first[1]}")
        print(f"Last point:  Regime {last[1]}")

        # Show regime transitions
        regimes = [r[1] for r in regime_data]
        transitions = 0
        for i in range(1, len(regimes)):
            if regimes[i] != regimes[i-1]:
                transitions += 1

        print(f"\nRegime transitions: {transitions}")
        print(f"Average regime duration: {len(regimes) / (transitions + 1):.1f} days")
