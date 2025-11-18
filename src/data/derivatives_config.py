"""
Configuration constants for derivatives oscillators (DVOL, Basis Spread, Taker Ratio, OI).

This module centralizes all configuration for Binance Futures and Deribit API integrations.
"""

# API Base URLs
BINANCE_FUTURES_BASE = "https://fapi.binance.com"
DERIBIT_BASE = "https://www.deribit.com/api/v2"

# Rate Limiting
REQUEST_DELAY = 0.5  # seconds between requests
MAX_RETRIES = 3  # maximum retry attempts
RETRY_BACKOFF_BASE = 1.0  # exponential backoff base (seconds)

# Historical Data Configuration
DEFAULT_DAYS_BACK = 1095  # 36 months
CACHE_DIR = "historical_data"

# Data Limits (from testing - see scripts/test_*_historical_depth.py)
BINANCE_BASIS_LIMIT = 500  # 16.6 months per request
BINANCE_OI_LIMIT = 31  # 1 month per request
BINANCE_TAKER_LIMIT = 31  # 1 month per request
DERIBIT_DVOL_LIMIT = 1000  # 33.3 months per request

# Binance Futures Endpoints
BINANCE_ENDPOINTS = {
    'basis': '/futures/data/basis',
    'oi_history': '/futures/data/openInterestHist',
    'taker_ratio': '/futures/data/takerlongshortRatio',
}

# Deribit Endpoints
DERIBIT_ENDPOINTS = {
    'dvol_history': '/public/get_volatility_index_data',
    'ticker': '/public/ticker',
}

# Default Symbols
DEFAULT_SYMBOL = 'BTCUSDT'  # Binance
DEFAULT_CURRENCY = 'BTC'  # Deribit

# Data Validation Ranges (for sanity checks)
DVOL_VALID_RANGE = (10, 300)  # DVOL typically 20-200
BASIS_VALID_RANGE = (-10000, 10000)  # Basis in USD
TAKER_RATIO_VALID_RANGE = (0.5, 2.0)  # Ratio typically 0.8-1.2
OI_VALID_RANGE = (0, 1e12)  # OI in base currency
