# app.py
"""
BTC Trading Dashboard - Flask Application
Production-ready web application for cryptocurrency market analysis
"""

# Standard library imports
import os
import time

# Third-party imports
import sentry_sdk
from flask import Flask, jsonify, request, send_from_directory
from flask_cors import CORS
from flask_apscheduler import APScheduler

# Application imports - Configuration
from config import CACHE_DURATION, RATE_LIMIT_DELAY

# Application imports - Data plugins
from src.data import (
    btc_price, rsi, macd_histogram, adx, atr, sma, parabolic_sar, funding_rate,
    eth_price_alpaca, spx_price_fmp, gold_price_oscillator,
    dxy_price_yfinance, btc_dominance_cmc, usdt_dominance_cmc,
    dvol_index_deribit, basis_spread_binance, markov_regime
)
from src.data.normalizers import zscore, pct_change_zscore
from src.data.postgres_provider import get_data as postgres_get_data, get_metadata as postgres_get_metadata

# Application imports - Management
from src.management.startup_check import check_and_update as startup_data_update

# Initialize Sentry SDK for error monitoring
SENTRY_DSN = os.getenv('SENTRY_DSN', 'https://51a1e702949ccbd441d980a082211e9f@o4510197158510592.ingest.us.sentry.io/4510197228044288')
sentry_sdk.init(
    dsn=SENTRY_DSN,
    send_default_pii=True,
)

app = Flask(__name__)
CORS(app)

# Initialize APScheduler for background tasks
scheduler = APScheduler()
scheduler.init_app(app)
scheduler.start()

# Auto-update data on startup (non-blocking)
startup_data_update()

# Cache configuration
cache = {}

# Rate limiting
last_api_call = {}

# A dictionary mapping dataset names to their data-fetching modules
# Note: OVERLAY_PLUGINS will be merged into this dictionary below
# Note: eth_price, gold_price, spx_price are kept as imports for future BTC oscillators
DATA_PLUGINS = {
    'btc': btc_price,
    'funding_rate_btc': lambda days: funding_rate.get_data(days, 'btc')
}

# Momentum Oscillator plugins (all require asset parameter)
OSCILLATOR_PLUGINS = {
    'rsi': rsi,
    'macd_histogram': macd_histogram,
    'adx': adx,
    'atr': atr,
    'dvol_index_deribit': dvol_index_deribit,
    'basis_spread_binance': basis_spread_binance
}

# Price Oscillator plugins (ETH, Gold, SPX prices normalized against BTC)
PRICE_OSCILLATOR_PLUGINS = {
    'eth_price_alpaca': eth_price_alpaca,
    'spx_price_fmp': spx_price_fmp,
    'gold_price_oscillator': gold_price_oscillator
}

# Macro Oscillator plugins (DXY, BTC.D, USDT.D - macroeconomic indicators)
MACRO_OSCILLATOR_PLUGINS = {
    'dxy_price_yfinance': dxy_price_yfinance,
    'btc_dominance_cmc': btc_dominance_cmc,
    'usdt_dominance_cmc': usdt_dominance_cmc
}

# Overlay plugins (Moving Averages & Parabolic SAR - callable via /api/data)
# These overlay on price charts rather than displaying in separate oscillator chart
# Only BTC overlays - ETH and Gold tabs removed
OVERLAY_PLUGINS = {
    'sma_7_btc': lambda days: sma.get_data(days, 'btc', 7),
    'sma_21_btc': lambda days: sma.get_data(days, 'btc', 21),
    'sma_60_btc': lambda days: sma.get_data(days, 'btc', 60),
    'psar_btc': lambda days: parabolic_sar.get_data(days, 'btc')
}

# Merge all plugin dictionaries into DATA_PLUGINS so they're accessible via /api/data
DATA_PLUGINS.update(OVERLAY_PLUGINS)
DATA_PLUGINS.update(PRICE_OSCILLATOR_PLUGINS)
DATA_PLUGINS.update(MACRO_OSCILLATOR_PLUGINS)
DATA_PLUGINS.update(OSCILLATOR_PLUGINS)

# Dataset name mapping: plugin name -> database source name
# This maps the names used in the frontend/API to actual PostgreSQL source names
DATASET_NAME_MAPPING = {
    # Price datasets
    'btc': 'btc_price',
    'eth': 'eth_price',
    'sol': 'sol_price',

    # Price oscillators
    'eth_price_alpaca': 'eth_price_alpaca',  # Already correct in DB
    'spx_price_fmp': 'spx_price_fmp',  # Already correct in DB
    'gold_price_oscillator': 'gold_price',  # DB uses gold_price, not gold_price_oscillator

    # Macro oscillators
    'dxy_price_yfinance': 'dxy_price',  # DB uses dxy_price, not dxy_price_yfinance
    'btc_dominance_cmc': 'btc_dominance',  # DB uses btc_dominance, not btc_dominance_cmc
    'usdt_dominance_cmc': 'usdt_dominance',  # DB uses usdt_dominance, not usdt_dominance_cmc

    # Derivatives oscillators
    'dvol_index_deribit': 'dvol_btc',  # DB uses dvol_btc, not dvol_index_deribit
    'basis_spread_binance': 'basis_spread_btc',  # DB uses basis_spread_btc, not basis_spread_binance

    # Momentum oscillators (require _btc suffix in DB)
    'rsi': 'rsi_btc',
    'adx': 'adx_btc',
    'atr': 'atr_btc',
    'macd_histogram': 'macd_histogram_btc',

    # Funding rate
    'funding_rate_btc': 'funding_rate_btc',  # Already correct
    'funding_rate_daily_btc': 'funding_rate_daily_btc',  # Already correct

    # Overlays
    'sma_7_btc': 'sma_7_btc',
    'sma_21_btc': 'sma_21_btc',
    'sma_60_btc': 'sma_60_btc',
    'psar_btc': 'psar_btc',

    # Other
    'stable_c_d': 'stable_c_d',

    # System 2: Velocity-Anchored Oscillators
    'volume_btc': 'volume_btc',
    'volume_eth': 'volume_eth',
    'btc_largetxcount': 'btc_largetxcount',
    'btc_avgtx': 'btc_avgtx',
    'btc_socialdominance': 'btc_socialdominance',
    'btc_postscreated': 'btc_postscreated',
    'btc_contributorsactive': 'btc_contributorsactive',
    'btc_contributorscreated': 'btc_contributorscreated',
    'btc_sendingaddresses': 'btc_sendingaddresses',
    'btc_receivingaddresses': 'btc_receivingaddresses',
    'btc_newaddresses': 'btc_newaddresses',
    'btc_txcount': 'btc_txcount',
    'usdt_tfsps': 'usdt_tfsps',
    'btc_meantxfees': 'btc_meantxfees',
    'btc_activesupply1y': 'btc_activesupply1y',
    'btc_active1y': 'btc_active1y',
    'btc_splyadrbal1': 'btc_splyadrbal1',
    'btc_addressessupply1in10k': 'btc_addressessupply1in10k',
    'btc_ser': 'btc_ser'
}

# Add PostgreSQL-only datasets (no JSON plugin, will be fetched via hybrid_provider)
POSTGRES_ONLY_DATASETS = {
    'funding_rate_daily_btc': None,  # Daily funding rate
    'stable_c_d': None,               # Stablecoin dominance
}
DATA_PLUGINS.update(POSTGRES_ONLY_DATASETS)

# Normalizer functions
NORMALIZERS = {
    'zscore': zscore,
    'pct_change_zscore': pct_change_zscore
}

# System 2: Velocity-Anchored Oscillators Configuration
# 19 datasets across 5 categories for momentum divergence detection
SYSTEM2_DATASETS = {
    # Derivatives (2)
    'funding': {'key': 'funding_rate_btc', 'label': 'Funding Rate', 'category': 'Derivatives'},
    'dvol': {'key': 'dvol_btc', 'label': 'DVOL Index', 'category': 'Derivatives'},

    # Whale Activity (2)
    'largetx': {'key': 'btc_largetxcount', 'label': 'Large Transaction Count', 'category': 'Whale'},
    'avgtx': {'key': 'btc_avgtx', 'label': 'Average Transaction Size', 'category': 'Whale'},

    # Social Velocity (4)
    'social_dominance': {'key': 'btc_socialdominance', 'label': 'Social Dominance', 'category': 'Social'},
    'posts': {'key': 'btc_postscreated', 'label': 'Posts Created', 'category': 'Social'},
    'contributors_active': {'key': 'btc_contributorsactive', 'label': 'Active Contributors', 'category': 'Social'},
    'contributors_new': {'key': 'btc_contributorscreated', 'label': 'New Contributors', 'category': 'Social'},

    # On-Chain Flow (6)
    'sending_addr': {'key': 'btc_sendingaddresses', 'label': 'Sending Addresses', 'category': 'On-Chain'},
    'receiving_addr': {'key': 'btc_receivingaddresses', 'label': 'Receiving Addresses', 'category': 'On-Chain'},
    'new_addr': {'key': 'btc_newaddresses', 'label': 'New Addresses', 'category': 'On-Chain'},
    'txcount': {'key': 'btc_txcount', 'label': 'Transaction Count', 'category': 'On-Chain'},
    'tether_flow': {'key': 'usdt_tfsps', 'label': 'USDT Tether Flow', 'category': 'On-Chain'},
    'mean_fees': {'key': 'btc_meantxfees', 'label': 'Mean Transaction Fees', 'category': 'On-Chain'},

    # Supply Dynamics (5)
    'active_supply_1y': {'key': 'btc_activesupply1y', 'label': 'Active Supply 1Y', 'category': 'Supply'},
    'active_1y': {'key': 'btc_active1y', 'label': 'Active 1Y', 'category': 'Supply'},
    'supply_addr_bal': {'key': 'btc_splyadrbal1', 'label': 'Supply Address Balance', 'category': 'Supply'},
    'addr_supply_10k': {'key': 'btc_addressessupply1in10k', 'label': 'Addresses Supply 1/10k', 'category': 'Supply'},
    'ser': {'key': 'btc_ser', 'label': 'Supply Equilibrium Ratio', 'category': 'Supply'}
}

def align_timestamps(normalized_oscillators):
    """
    Align multiple normalized oscillator datasets to common timestamps.

    Args:
        normalized_oscillators: Dict of {oscillator_name: [[timestamp, value], ...]}

    Returns:
        Tuple of (common_timestamps, aligned_values)
        where aligned_values is Dict of {oscillator_name: [values aligned to common timestamps]}
    """
    if not normalized_oscillators:
        return [], {}

    # Find common timestamps (intersection)
    timestamp_sets = [set(item[0] for item in data) for data in normalized_oscillators.values()]
    common_timestamps = sorted(set.intersection(*timestamp_sets))

    if not common_timestamps:
        print("[Composite] No common timestamps found across oscillators")
        return [], {}

    # Create lookup dictionaries for each oscillator
    aligned = {}
    for name, data in normalized_oscillators.items():
        lookup = {item[0]: item[1] for item in data}
        aligned[name] = [lookup[ts] for ts in common_timestamps]

    return common_timestamps, aligned

def calculate_composite_average(common_timestamps, aligned_values, weights=None):
    """
    Calculate equally-weighted (or custom-weighted) average of aligned oscillator values.

    Args:
        common_timestamps: List of timestamps
        aligned_values: Dict of {oscillator_name: [values]}
        weights: Dict of {oscillator_name: weight} or None for equal weights

    Returns:
        List of [timestamp, composite_value] pairs
    """
    if not common_timestamps or not aligned_values:
        return []

    # Determine weights
    oscillator_names = list(aligned_values.keys())
    if weights is None:
        # Equal weights for all oscillators (including RSI+ADX: 50/50)
        n = len(oscillator_names)
        weights = {name: 1.0 / n for name in oscillator_names}
        print(f"[Composite] Using equal weights: {weights}")
    else:
        # Normalize weights to sum to 1
        total = sum(weights.values())
        weights = {name: w / total for name, w in weights.items()}
        print(f"[Composite] Using custom weights: {weights}")

    # Calculate weighted average for each timestamp
    composite_data = []
    for i, timestamp in enumerate(common_timestamps):
        weighted_sum = 0.0
        for name, values in aligned_values.items():
            weight = weights.get(name, 0.0)
            value = values[i]
            weighted_sum += weight * value

        composite_data.append([timestamp, weighted_sum])

    print(f"[Composite] Generated {len(composite_data)} composite points")

    return composite_data

def get_cache_key(dataset_name, days):
    """Generate a cache key for the dataset and days combination"""
    return f"{dataset_name}_{days}"

def is_cache_valid(cache_key):
    """Check if cached data exists and is still valid"""
    if cache_key not in cache:
        return False
    
    cached_time = cache[cache_key]['timestamp']
    return (time.time() - cached_time) < CACHE_DURATION

def rate_limit_check(dataset_name):
    """Check if we can make an API call for this dataset"""
    current_time = time.time()
    if dataset_name in last_api_call:
        time_since_last = current_time - last_api_call[dataset_name]
        if time_since_last < RATE_LIMIT_DELAY:
            time.sleep(RATE_LIMIT_DELAY - time_since_last)
    
    last_api_call[dataset_name] = time.time()

@app.route('/api/datasets')
def get_datasets_metadata():
    """
    Returns metadata for all available datasets
    """
    metadata = {}
    for name, module in DATA_PLUGINS.items():
        if hasattr(module, 'get_metadata'):
            metadata[name] = module.get_metadata()
        else:
            # Fallback for modules without metadata
            metadata[name] = {'label': name.upper(), 'color': '#888888'}
    return jsonify(metadata)

@app.route('/api/data')
def get_data():
    """
    A single, flexible endpoint to fetch data for any dataset.
    Query parameters:
    - dataset: The name of the dataset to fetch (e.g., 'eth_btc', 'btc', 'gold', 'rsi', 'vwap', 'adx')
    - days: The number of days of data to retrieve (e.g., '365', 'max')
    """
    dataset_name = request.args.get('dataset')
    days = request.args.get('days', '365')

    if not dataset_name or dataset_name not in DATA_PLUGINS:
        return jsonify({'error': 'Invalid or missing dataset parameter'}), 400

    # Check cache first
    cache_key = get_cache_key(dataset_name, days)

    if is_cache_valid(cache_key):
        print(f"Serving {dataset_name} from cache")
        return jsonify(cache[cache_key]['data'])

    try:
        # Apply rate limiting before making API call
        rate_limit_check(dataset_name)

        # Convert days parameter to integer
        if days == 'max':
            days_int = 3650  # ~10 years
        else:
            days_int = int(days)

        # Map dataset name to database source name using the mapping dictionary
        source_name = DATASET_NAME_MAPPING.get(dataset_name, dataset_name)

        # Fetch data from PostgreSQL (no JSON fallback)
        data = postgres_get_data(source_name, days_int)

        # Fetch metadata
        metadata = postgres_get_metadata(source_name)
        if not metadata:
            # Fallback metadata if not found in database
            metadata = {'label': dataset_name.upper()}

        # Build response with data and metadata
        result = {
            'data': data,
            'metadata': metadata
        }

        # Store in cache
        cache[cache_key] = {
            'data': result,
            'timestamp': time.time()
        }

        # Log data source (PostgreSQL-only now)
        print(f"Fetched {dataset_name} from PostgreSQL ({len(data)} records)")

        return jsonify(result)
        
    except Exception as e:
        # If we have cached data (even if expired), return it on error
        if cache_key in cache:
            print(f"Error fetching {dataset_name}, returning stale cache: {str(e)}")
            return jsonify(cache[cache_key]['data'])
        
        return jsonify({'error': f'Server error processing {dataset_name}: {str(e)}'}), 500

@app.route('/api/oscillator-data')
def get_oscillator_data():
    """
    Fetch oscillator data with optional composite mode and regime detection.

    Query parameters:
    - asset: 'btc' | 'eth' | 'gold'
    - datasets: comma-separated list (e.g., 'rsi,macd,volume,dxy')
    - days: '7' | '30' | '180' | '1095'
    - normalizer: 'zscore' (Regression Divergence - only normalizer available)
    - mode: 'individual' | 'composite' (default: 'individual')
    - noise_level: 14 | 30 | 50 | 100 | 200 (window size for composite Z-score, default: 50)

    When mode='composite':
    - Returns composite Z-score oscillator (weighted avg of all specified oscillators)
    - Returns Markov regime data for background shading
    - noise_level controls oscillator sensitivity
    """
    asset = request.args.get('asset')
    datasets_param = request.args.get('datasets', '')
    days = request.args.get('days', '30')
    normalizer_name = request.args.get('normalizer', 'zscore')
    mode = request.args.get('mode', 'individual')
    noise_level = int(request.args.get('noise_level', '50'))

    if not asset or asset not in DATA_PLUGINS:
        return jsonify({'error': 'Invalid or missing asset parameter'}), 400

    if not datasets_param:
        return jsonify({'error': 'Missing datasets parameter'}), 400

    # Parse dataset names
    dataset_names = [d.strip() for d in datasets_param.split(',') if d.strip()]

    if not dataset_names:
        return jsonify({'error': 'No valid datasets specified'}), 400

    # Validate normalizer (only used in individual mode)
    if mode == 'individual' and normalizer_name not in NORMALIZERS:
        return jsonify({'error': f'Invalid normalizer: {normalizer_name}'}), 400

    # Validate noise level
    valid_noise_levels = [14, 30, 50, 100, 200]
    if noise_level not in valid_noise_levels:
        return jsonify({'error': f'Invalid noise_level. Must be one of: {valid_noise_levels}'}), 400

    # Generate cache key (include mode and noise_level)
    cache_key = f"oscillator_{mode}_{asset}_{datasets_param}_{days}_{normalizer_name}_{noise_level}"

    # Check cache
    if is_cache_valid(cache_key):
        print(f"Serving oscillator data from cache: {cache_key}")
        return jsonify(cache[cache_key]['data'])

    try:
        # Handle composite mode
        if mode == 'composite':
            print(f"[Composite Mode] Generating composite oscillator for {asset} with window={noise_level}")
            print(f"[Composite Mode] Oscillators: {dataset_names}")

            # Apply rate limiting
            rate_limit_check(f"composite_{asset}")

            # Step 1: Fetch asset price data (OHLCV) for normalization
            # Request extra days to ensure enough history for rolling window
            if days == 'max':
                price_days = 3650  # ~10 years of data for 'max'
            else:
                price_days = int(days) + noise_level + 10

            # Fetch asset price data (use hybrid provider)
            asset_plugin = DATA_PLUGINS.get(asset)
            # Map asset name to database source name (e.g., 'btc' -> 'btc_price')
            asset_dataset_name = asset  # e.g., 'btc', 'eth'
            source_name = DATASET_NAME_MAPPING.get(asset_dataset_name, f"{asset}_price")
            asset_ohlcv_data = postgres_get_data(source_name, price_days)

            if not asset_ohlcv_data:
                raise ValueError(f"No {asset.upper()} price data available")

            print(f"[Composite Mode] Fetched {len(asset_ohlcv_data)} price points for {asset.upper()}")

            # Step 2: Normalize each oscillator using regression-based normalizer
            normalized_oscillators = {}
            oscillator_metadata = {}  # Store metadata for breakdown chart

            for oscillator_name in dataset_names:
                # Check oscillator plugins (momentum, price, and macro oscillators)
                if oscillator_name in OSCILLATOR_PLUGINS:
                    oscillator_module = OSCILLATOR_PLUGINS[oscillator_name]
                elif oscillator_name in PRICE_OSCILLATOR_PLUGINS:
                    oscillator_module = PRICE_OSCILLATOR_PLUGINS[oscillator_name]
                elif oscillator_name in MACRO_OSCILLATOR_PLUGINS:
                    oscillator_module = MACRO_OSCILLATOR_PLUGINS[oscillator_name]
                else:
                    print(f"[Composite Mode] Warning: Unknown oscillator '{oscillator_name}', skipping...")
                    continue

                try:
                    # Apply rate limiting
                    rate_limit_check(f"{oscillator_name}_{asset}")

                    # Request extra days to ensure enough history for rolling window
                    # Add noise_level + 10 extra days as buffer
                    if days == 'max':
                        extra_days = 3650  # ~10 years of data
                    else:
                        # For stock market data (weekdays only), request ~1.5x more calendar days
                        # to ensure we have enough weekday data points after accounting for weekends
                        stock_market_oscillators = ['spx_price_fmp', 'gold_price_oscillator']
                        if oscillator_name in stock_market_oscillators:
                            # Need ~1.5x calendar days to get enough weekday data
                            extra_days = int((int(days) + noise_level + 10) * 1.5)
                        else:
                            extra_days = int(days) + noise_level + 10

                    # All momentum oscillators require asset parameter
                    # Use hybrid provider with oscillator module as fallback
                    oscillator_dataset_name = f"{oscillator_name}_{asset}" if oscillator_name in ['rsi', 'adx', 'atr', 'macd_histogram'] else oscillator_name

                    # Map to database source name using centralized mapping
                    source_name = DATASET_NAME_MAPPING.get(oscillator_dataset_name, oscillator_dataset_name)

                    # Create wrapper lambda that calls oscillator with asset parameter
                    oscillator_wrapper = lambda days: oscillator_module.get_data(days, asset)

                    # Ensure extra_days is always an integer
                    extra_days_int = int(extra_days)
                    raw_oscillator_data = postgres_get_data(source_name, extra_days_int)

                    if not raw_oscillator_data:
                        print(f"[Composite Mode] Warning: No data for {oscillator_name}, skipping...")
                        continue

                    print(f"[Composite Mode] Fetched {len(raw_oscillator_data)} points for {oscillator_name}")

                    # Normalize using Rolling OLS Regression Divergence
                    normalized_data = zscore.normalize(
                        dataset_data=raw_oscillator_data,
                        asset_price_data=asset_ohlcv_data,
                        window=noise_level
                    )

                    if not normalized_data:
                        print(f"[Composite Mode] Warning: Normalization failed for {oscillator_name}, skipping...")
                        continue

                    # Store original normalized data for breakdown (before any inversion)
                    # This ensures breakdown charts show intuitive values
                    normalized_oscillators[oscillator_name] = normalized_data

                    # INVERT ATR for composite calculation only
                    # Rationale: High ATR = high volatility/risk = bearish contribution
                    # Note: Inversion happens later when aligning values for composite
                    if oscillator_name in ['atr']:
                        print(f"[Composite Mode] Will invert {oscillator_name} for composite (high = bearish)")

                    # Capture metadata for breakdown chart
                    metadata = postgres_get_metadata(source_name)
                    if metadata:
                        metadata['normalizer'] = 'Rolling OLS Regression Divergence'
                        metadata['window'] = noise_level
                    else:
                        # Fallback metadata if not found in database
                        metadata = {
                            'label': oscillator_name.upper(),
                            'normalizer': 'Rolling OLS Regression Divergence',
                            'window': noise_level
                        }
                    oscillator_metadata[oscillator_name] = metadata

                    print(f"[Composite Mode] Normalized {oscillator_name}: {len(normalized_data)} points")

                except Exception as e:
                    print(f"[Composite Mode] Error processing {oscillator_name}: {e}")
                    import traceback
                    traceback.print_exc()
                    # Continue with other oscillators

            if not normalized_oscillators:
                raise ValueError("No oscillators could be normalized successfully")

            # Step 3: Align all normalized oscillators to common timestamps
            common_timestamps, aligned_values = align_timestamps(normalized_oscillators)

            if not common_timestamps:
                raise ValueError("No common timestamps found across normalized oscillators")

            # Step 3.5: Invert ATR for composite calculation only
            # (Breakdown will use original non-inverted values from normalized_oscillators)
            aligned_values_for_composite = aligned_values.copy()
            if 'atr' in aligned_values_for_composite:
                aligned_values_for_composite['atr'] = [-v for v in aligned_values_for_composite['atr']]
                print(f"[Composite Mode] Inverted ATR values for composite (high ATR = bearish)")

            # Step 4: Calculate equally-weighted composite average
            composite_data = calculate_composite_average(
                common_timestamps=common_timestamps,
                aligned_values=aligned_values_for_composite,
                weights=None  # Equal weights
            )

            # Step 4.5: Trim composite data to requested number of days
            if composite_data and days != 'max':
                cutoff_timestamp = composite_data[-1][0] - (int(days) * 24 * 60 * 60 * 1000)
                composite_data = [d for d in composite_data if d[0] >= cutoff_timestamp]
                print(f"[Composite Mode] Trimmed to {len(composite_data)} points for {days} days")

            # Step 5: Get Markov regime data aligned to composite timestamps
            # Filter OHLCV data to match common timestamps for perfect alignment
            common_timestamps_set = set(common_timestamps)
            aligned_ohlcv_data = [candle for candle in asset_ohlcv_data if candle[0] in common_timestamps_set]

            print(f"[Composite Mode] Aligned OHLCV data: {len(aligned_ohlcv_data)} points (from {len(asset_ohlcv_data)} total)")

            # Calculate volatility from aligned OHLCV data
            from src.data import volatility
            aligned_volatility_data = volatility.calculate_gk_volatility(aligned_ohlcv_data)

            # Fit Markov model to aligned volatility
            fitted_model = markov_regime.fit_markov_model(aligned_volatility_data)

            # Classify regimes
            if fitted_model is not None:
                aligned_regime_data = markov_regime.classify_regimes(fitted_model, aligned_volatility_data)
                print(f"[Composite Mode] Markov model fitted successfully: {len(aligned_regime_data)} regime points")
            else:
                # Fallback to simple threshold
                print("[Composite Mode] Markov model fitting failed, using threshold-based classification")
                aligned_regime_data = markov_regime.simple_threshold_regimes(aligned_volatility_data)

            # Trim regime data to requested number of days (same as composite)
            if aligned_regime_data and days != 'max':
                cutoff_timestamp = aligned_regime_data[-1][0] - (int(days) * 24 * 60 * 60 * 1000)
                aligned_regime_data = [d for d in aligned_regime_data if d[0] >= cutoff_timestamp]

            regime_result = {
                'data': aligned_regime_data,
                'metadata': markov_regime.get_metadata(),
                'structure': 'simple'
            }

            # Step 5.5: Build breakdown data (individual normalized oscillators)
            # Use aligned common timestamps to ensure all oscillators have same time range
            breakdown_data = {}

            for oscillator_name in aligned_values.keys():
                # Reconstruct aligned data using common timestamps
                aligned_data = [[common_timestamps[i], aligned_values[oscillator_name][i]]
                               for i in range(len(common_timestamps))]

                # Trim to requested number of days
                trimmed_data = aligned_data
                if aligned_data and days != 'max':
                    cutoff_timestamp = aligned_data[-1][0] - (int(days) * 24 * 60 * 60 * 1000)
                    trimmed_data = [d for d in aligned_data if d[0] >= cutoff_timestamp]

                breakdown_data[oscillator_name] = {
                    'data': trimmed_data,
                    'metadata': oscillator_metadata[oscillator_name]
                }

            # Step 6: Build result
            result = {
                'mode': 'composite',
                'asset': asset,
                'noise_level': noise_level,
                'composite': {
                    'data': composite_data,
                    'metadata': {
                        'label': 'Composite Regression Divergence',
                        'yAxisId': 'zscore',
                        'yAxisLabel': 'Standard Deviations',
                        'unit': 'σ',
                        'color': '#00D9FF',
                        'chartType': 'line',
                        'window': noise_level,
                        'components': list(normalized_oscillators.keys()),
                        'weights': {name: 1.0/len(normalized_oscillators) for name in normalized_oscillators.keys()},
                        'normalizer': 'Rolling OLS Regression Divergence'
                    }
                },
                'regime': {
                    'data': regime_result['data'],
                    'metadata': regime_result['metadata']
                },
                'breakdown': breakdown_data
            }

            print(f"[Composite Mode] Generated {len(composite_data)} composite points")
            print(f"[Composite Mode] Generated {len(regime_result['data'])} regime points")

            # Store in cache
            cache[cache_key] = {
                'data': result,
                'timestamp': time.time()
            }

            return jsonify(result)

        # Handle individual mode (existing logic)
        else:
            # Fetch asset price data (needed for normalization) - use hybrid provider
            asset_plugin = DATA_PLUGINS.get(asset)
            # Map asset name to database source name (e.g., 'btc' -> 'btc_price')
            asset_dataset_name = asset  # e.g., 'btc', 'eth'
            source_name = DATASET_NAME_MAPPING.get(asset_dataset_name, f"{asset}_price")
            days_int = int(days) if days != 'max' else 3650
            asset_ohlcv_data = postgres_get_data(source_name, days_int)

            if not asset_ohlcv_data:
                raise ValueError(f"No {asset.upper()} price data available")

            # Fetch oscillator datasets
            result = {
                'mode': 'individual',
                'asset': asset,
                'normalizer': normalizer_name,
                'datasets': {}
            }

            normalizer_module = NORMALIZERS[normalizer_name]

            for dataset_name in dataset_names:
                # Check both momentum and price oscillator plugins
                if dataset_name in OSCILLATOR_PLUGINS:
                    oscillator_module = OSCILLATOR_PLUGINS[dataset_name]
                elif dataset_name in PRICE_OSCILLATOR_PLUGINS:
                    oscillator_module = PRICE_OSCILLATOR_PLUGINS[dataset_name]
                else:
                    print(f"Warning: Unknown oscillator dataset '{dataset_name}', skipping...")
                    continue

                try:
                    # Apply rate limiting
                    rate_limit_check(f"{dataset_name}_{asset}")

                    # All momentum oscillators require asset parameter
                    # Use hybrid provider with oscillator module as fallback
                    oscillator_dataset_name = f"{dataset_name}_{asset}" if dataset_name in ['rsi', 'adx', 'atr', 'macd_histogram'] else dataset_name

                    # Map to database source name using centralized mapping
                    source_name = DATASET_NAME_MAPPING.get(oscillator_dataset_name, oscillator_dataset_name)

                    # Create wrapper lambda that calls oscillator with asset parameter
                    oscillator_wrapper = lambda days: oscillator_module.get_data(days, asset)
                    raw_data = postgres_get_data(source_name, days_int)

                    if not raw_data:
                        print(f"Warning: No data for {dataset_name}, skipping...")
                        continue

                    # Apply normalization
                    normalized_data = normalizer_module.normalize(raw_data, asset_ohlcv_data)

                    # Get metadata
                    metadata = postgres_get_metadata(source_name)
                    if not metadata:
                        # Fallback metadata if not found in database
                        metadata = {'label': dataset_name.upper()}

                    result['datasets'][dataset_name] = {
                        'data': normalized_data,
                        'metadata': metadata
                    }

                    print(f"Fetched and normalized {dataset_name} for {asset}: {len(normalized_data)} points")

                except Exception as e:
                    print(f"Error fetching oscillator {dataset_name}: {e}")
                    # Continue with other datasets

            # Store in cache
            cache[cache_key] = {
                'data': result,
                'timestamp': time.time()
            }

            return jsonify(result)

    except Exception as e:
        print(f"Error processing oscillator data: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': f'Server error processing oscillator data: {str(e)}'}), 500


@app.route('/api/system2-data')
def get_system2_data():
    """
    Fetch all 22 System 2 velocity-anchored oscillators.

    System 2 detects when indicator momentum diverges from BTC momentum using
    percentage change regression (log returns).

    Query parameters:
    - asset: 'btc' (default, only BTC supported for System 2)
    - days: Number of days to fetch (default: 365)
    - noise_level: Rolling window size for regression (default: 30)

    Returns:
        JSON with structure matching /api/oscillator-data format:
        {
            'data': [
                {
                    'name': 'funding',
                    'label': 'Funding Rate',
                    'category': 'Derivatives',
                    'values': [[timestamp, z_score], ...],
                    'metadata': {...}
                },
                ... (22 total datasets)
            ],
            'errors': [
                {'dataset': 'btc_ser', 'error': 'Source not found'}
            ],
            'common_timestamps': [ts1, ts2, ...],
            'regime_data': [[ts, regime_value], ...],
            'metadata': {
                'asset': 'btc',
                'days': 365,
                'noise_level': 30,
                'normalizer': 'pct_change_zscore',
                'total_datasets': 22,
                'successful': 21,
                'failed': 1
            }
        }
    """
    # Parse query parameters
    asset = request.args.get('asset', 'btc')
    days_param = request.args.get('days', '365')
    noise_level = int(request.args.get('noise_level', '30'))

    # Validate parameters
    if asset != 'btc':
        return jsonify({'error': 'System 2 only supports asset=btc'}), 400

    try:
        days = int(days_param)
    except ValueError:
        return jsonify({'error': 'days parameter must be an integer'}), 400

    # Validate noise level
    valid_noise_levels = [14, 30, 50, 100, 200]
    if noise_level not in valid_noise_levels:
        return jsonify({'error': f'Invalid noise_level. Must be one of: {valid_noise_levels}'}), 400

    # Generate cache key
    cache_key = f"system2_{asset}_{days}_{noise_level}"

    # Check cache
    if is_cache_valid(cache_key):
        print(f"Serving System 2 data from cache: {cache_key}")
        return jsonify(cache[cache_key]['data'])

    try:
        print(f"[System 2] Generating velocity-anchored oscillators for {asset} with window={noise_level}, days={days}")

        # Apply rate limiting
        rate_limit_check(f"system2_{asset}")

        # Step 1: Fetch BTC price data (OHLCV) for normalization
        # Request extra days to ensure enough history for rolling window
        price_days = days + noise_level + 10
        source_name = DATASET_NAME_MAPPING.get('btc', 'btc_price')
        btc_ohlcv_data = postgres_get_data(source_name, price_days)

        if not btc_ohlcv_data:
            return jsonify({'error': 'No BTC price data available'}), 500

        print(f"[System 2] Fetched {len(btc_ohlcv_data)} BTC price points")

        # Step 2: Process each System 2 dataset
        successful_oscillators = []
        failed_datasets = []
        normalized_data_dict = {}  # For finding common timestamps

        for short_name, config in SYSTEM2_DATASETS.items():
            dataset_key = config['key']
            dataset_label = config['label']
            dataset_category = config['category']

            try:
                # Apply rate limiting
                rate_limit_check(f"system2_{dataset_key}")

                # Map to database source name
                source_name = DATASET_NAME_MAPPING.get(dataset_key, dataset_key)

                # Fetch raw dataset
                raw_data = postgres_get_data(source_name, price_days)

                if not raw_data:
                    error_msg = f"No data found in database for source: {source_name}"
                    print(f"[System 2] {error_msg}")
                    failed_datasets.append({
                        'dataset': short_name,
                        'label': dataset_label,
                        'error': error_msg
                    })
                    continue

                print(f"[System 2] Fetched {len(raw_data)} points for {dataset_label}")

                # Normalize using percentage change z-score
                normalized_data = pct_change_zscore.normalize(
                    dataset_data=raw_data,
                    asset_price_data=btc_ohlcv_data,
                    window=noise_level
                )

                if not normalized_data:
                    error_msg = "Normalization returned no data (insufficient history or variance)"
                    print(f"[System 2] {error_msg} for {dataset_label}")
                    failed_datasets.append({
                        'dataset': short_name,
                        'label': dataset_label,
                        'error': error_msg
                    })
                    continue

                # Trim to requested number of days
                if normalized_data and days:
                    cutoff_timestamp = normalized_data[-1][0] - (days * 24 * 60 * 60 * 1000)
                    normalized_data = [d for d in normalized_data if d[0] >= cutoff_timestamp]

                # Get metadata
                metadata = postgres_get_metadata(source_name)
                if not metadata:
                    metadata = {
                        'label': dataset_label,
                        'category': dataset_category,
                        'source': source_name
                    }

                # Add normalization metadata
                metadata['normalizer'] = 'Velocity-Anchored Regression Divergence'
                metadata['window'] = noise_level
                metadata['data_points'] = len(normalized_data)

                # Store successful oscillator
                successful_oscillators.append({
                    'name': short_name,
                    'label': dataset_label,
                    'category': dataset_category,
                    'values': normalized_data,
                    'metadata': metadata
                })

                # Store for timestamp alignment
                normalized_data_dict[short_name] = normalized_data

                print(f"[System 2] Normalized {dataset_label}: {len(normalized_data)} points")

            except Exception as e:
                error_msg = str(e)
                print(f"[System 2] Error processing {dataset_label}: {error_msg}")
                import traceback
                traceback.print_exc()
                failed_datasets.append({
                    'dataset': short_name,
                    'label': dataset_label,
                    'error': error_msg
                })

        # Step 3: Find common timestamps across all successful oscillators
        common_timestamps = []
        if normalized_data_dict:
            timestamp_sets = [set(item[0] for item in data) for data in normalized_data_dict.values()]
            common_timestamps = sorted(set.intersection(*timestamp_sets))
            print(f"[System 2] Found {len(common_timestamps)} common timestamps")

        # Step 4: Get Markov regime data
        regime_data = []
        try:
            # Get regime data aligned to BTC price
            common_timestamps_set = set(common_timestamps) if common_timestamps else set()
            if common_timestamps_set:
                aligned_ohlcv_data = [candle for candle in btc_ohlcv_data if candle[0] in common_timestamps_set]
            else:
                aligned_ohlcv_data = btc_ohlcv_data

            # Calculate volatility
            from src.data import volatility
            aligned_volatility_data = volatility.calculate_gk_volatility(aligned_ohlcv_data)

            # Fit Markov model
            fitted_model = markov_regime.fit_markov_model(aligned_volatility_data)

            if fitted_model is not None:
                regime_data = markov_regime.classify_regimes(fitted_model, aligned_volatility_data)
                print(f"[System 2] Generated {len(regime_data)} regime points")
            else:
                # Fallback to simple threshold
                print("[System 2] Markov model fitting failed, using threshold-based classification")
                regime_data = markov_regime.simple_threshold_regimes(aligned_volatility_data)

            # Trim regime data to requested number of days
            if regime_data and days:
                cutoff_timestamp = regime_data[-1][0] - (days * 24 * 60 * 60 * 1000)
                regime_data = [d for d in regime_data if d[0] >= cutoff_timestamp]

        except Exception as e:
            print(f"[System 2] Error generating regime data: {e}")
            import traceback
            traceback.print_exc()
            # Continue without regime data

        # Step 5: Transform to breakdown format (matching /api/oscillator-data structure)
        breakdown = {}
        for oscillator in successful_oscillators:
            breakdown[oscillator['name']] = {
                'data': oscillator['values'],  # Rename 'values' to 'data'
                'metadata': {
                    'label': oscillator['label'],
                    'category': oscillator['category'],
                    'color': '#00D9FF',  # Cyan for velocity-anchored oscillators
                    **oscillator['metadata']  # Include all original metadata
                }
            }

        # Step 6: Build response
        result = {
            'mode': 'system2',
            'asset': asset,
            'noise_level': noise_level,
            'breakdown': breakdown,  # Changed from 'data' array to 'breakdown' object
            'regime_data': regime_data,
            'common_timestamps': common_timestamps,
            'errors': failed_datasets,
            'metadata': {
                'system': 'System 2: Velocity-Anchored Oscillators',
                'normalizer': 'pct_change_zscore',
                'total_datasets': len(SYSTEM2_DATASETS),
                'successful': len(breakdown),
                'failed': len(failed_datasets),
                'days': days,
                'noise_level': noise_level
            }
        }

        print(f"[System 2] Successfully processed {len(successful_oscillators)}/{len(SYSTEM2_DATASETS)} datasets")

        # Store in cache
        cache[cache_key] = {
            'data': result,
            'timestamp': time.time()
        }

        return jsonify(result)

    except Exception as e:
        print(f"Error processing System 2 data: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': f'Server error processing System 2 data: {str(e)}'}), 500


@app.route('/api/clear-cache')
def clear_cache():
    """Clear the cache manually if needed"""
    global cache
    cache = {}
    return jsonify({'message': 'Cache cleared successfully'})

@app.route('/api/config')
def get_config():
    """Show current configuration (without revealing API keys)"""
    from config import API_PROVIDER, DEFAULT_DAYS, RSI_PERIOD, FMP_API_KEY, COINAPI_KEY

    return jsonify({
        'api_provider': API_PROVIDER,
        'cache_duration': f'{CACHE_DURATION} seconds',
        'rate_limit_delay': f'{RATE_LIMIT_DELAY} seconds',
        'default_days': DEFAULT_DAYS,
        'rsi_period': RSI_PERIOD,
        'api_keys_configured': {
            'fmp': bool(FMP_API_KEY and FMP_API_KEY != 'YOUR_FMP_API_KEY'),
            'coinapi': bool(COINAPI_KEY and COINAPI_KEY != 'YOUR_COINAPI_KEY_HERE')
        }
    })

@app.route('/')
def home():
    """
    Serve the main HTML page
    """
    return send_from_directory('.', 'index.html')

@app.route('/js/<path:filename>')
def serve_js(filename):
    """
    Serve JavaScript files from the static/js directory
    """
    return send_from_directory('src/static/js', filename)

@app.route('/favicon.ico')
def favicon():
    """Return a simple 204 No Content response for favicon requests"""
    return '', 204

@app.route('/api/status')
def api_status():
    """
    API status endpoint to verify server is running
    """
    from config import FMP_API_KEY, COINAPI_KEY

    # Check API key status
    api_status = {
        'FMP': "[OK]" if (FMP_API_KEY and FMP_API_KEY != 'YOUR_FMP_API_KEY') else "[NOT CONFIGURED]",
        'CoinAPI': "[OK]" if (COINAPI_KEY and COINAPI_KEY != 'YOUR_COINAPI_KEY_HERE') else "[NOT CONFIGURED]"
    }

    return jsonify({
        'status': 'running',
        'message': 'BTC Trading System - Core Infrastructure (Rebuild Mode)',
        'endpoint': '/api/data?dataset=<name>&days=<number>',
        'available_datasets': list(DATA_PLUGINS.keys()),
        'cache_duration': f'{CACHE_DURATION} seconds',
        'cached_items': len(cache),
        'api_key_status': api_status,
        'config_endpoint': '/api/config',
        'clear_cache_endpoint': '/api/clear-cache',
        'rebuild_status': 'Core infrastructure only - plugins will be added incrementally'
    })

@scheduler.task('interval', id='update_dominance_data', minutes=15, misfire_grace_time=900)
def update_dominance_data():
    """
    Scheduled task to update BTC.D and USDT.D data every 15 minutes.
    This ensures dominance data stays current without requiring page loads.
    """
    try:
        print("[Scheduler] Updating dominance data...")

        # Fetch and update BTC dominance
        btc_dom_result = btc_dominance_cmc.get_data('1', 'btc')
        if btc_dom_result and btc_dom_result.get('data'):
            print(f"[Scheduler] BTC.D updated: {len(btc_dom_result['data'])} records")

        # Fetch and update USDT dominance
        usdt_dom_result = usdt_dominance_cmc.get_data('1', 'btc')
        if usdt_dom_result and usdt_dom_result.get('data'):
            print(f"[Scheduler] USDT.D updated: {len(usdt_dom_result['data'])} records")

        print("[Scheduler] Dominance data update complete")

    except Exception as e:
        print(f"[Scheduler] Error updating dominance data: {e}")
        import traceback
        traceback.print_exc()

if __name__ == '__main__':
    from config import FMP_API_KEY, COINAPI_KEY

    print("="*60)
    print("BTC Trading System - Core Infrastructure")
    print("="*60)
    print(f"Server URL: http://127.0.0.1:5000")
    print(f"Status: REBUILD MODE - Core infrastructure only")
    print(f"Available datasets: {list(DATA_PLUGINS.keys()) if DATA_PLUGINS else 'None (rebuild in progress)'}")
    print(f"Cache duration: {CACHE_DURATION} seconds")
    print(f"Rate limit: {RATE_LIMIT_DELAY} seconds between API calls")

    print("\nAPI Key Status:")
    if FMP_API_KEY and FMP_API_KEY != 'YOUR_FMP_API_KEY':
        print(f"  FMP: [OK] Configured")
    else:
        print(f"  FMP: [X] Not configured")

    if COINAPI_KEY and COINAPI_KEY != 'YOUR_COINAPI_KEY_HERE':
        print(f"  CoinAPI: [OK] Configured")
    else:
        print(f"  CoinAPI: [X] Not configured")

    print("\n[REBUILD] Trading System Features:")
    print("  - Core infrastructure preserved")
    print("  - Frontend design and styling intact")
    print("  - Data plugins will be added one-by-one")
    print("  - Chart system ready for 12+ normalized indicators")

    print("\n[SCHEDULER] Background Tasks:")
    print("  - BTC.D & USDT.D auto-update: Every 15 minutes")
    print("  - Keeps dominance data current without page refreshes")

    print("="*60)
    print("Dependencies: pip install Flask requests Flask-Cors numpy")
    print("="*60)

    app.run(debug=True, port=5000)