# config.py
"""
Centralized configuration file for all API keys and settings
"""
import os

# Load environment variables from .env file
# IMPORTANT: You must install python-dotenv first: pip install python-dotenv
try:
    from dotenv import load_dotenv
    load_dotenv()  # This loads variables from .env file into os.environ
    print("[OK] Environment variables loaded from .env file")
except ImportError:
    print("[WARNING] python-dotenv not installed. Run: pip install python-dotenv")
    print("[WARNING] Falling back to system environment variables only")

# API Keys (loaded from .env file or system environment)
COINAPI_KEY = os.environ.get('COINAPI_KEY')  # For crypto data (BTC, ETH, dominance)
FMP_API_KEY = os.environ.get('FMP_API_KEY')  # Financial Modeling Prep for Gold/SPX
FRED_API_KEY = os.environ.get('FRED_API_KEY')  # NOT USED - DXY uses Yahoo Finance (free, no key required)
ALPACA_API_KEY = os.environ.get('ALPACA_API_KEY')  # Alpaca Markets API key
ALPACA_SECRET_KEY = os.environ.get('ALPACA_SECRET_KEY')  # Alpaca Markets secret key
COINMARKETCAP_API_KEY = os.environ.get('COINMARKETCAP_API_KEY')  # CoinMarketCap for market dominance data

# Legacy/Deprecated API Keys (kept for reference only)
COINSTATS_API_KEY = 'hn8xFxvTblGTj6wEq35nxyijBlQNyBrdJUWqPIeHZCU='  # DEPRECATED
ALPHA_VANTAGE_API_KEY = '5EK27ZM3JQC594PO'  # Legacy - not used
CRYPTOCOMPARE_API_KEY = ''  # Optional - not used
COINGECKO_API_KEY = ''  # Optional - not used

# CoinAPI Settings (Startup Tier: $79/month)
COINAPI_BASE_URL = 'https://rest.coinapi.io/v1'
COINAPI_RATE_LIMIT = 1000  # Requests per day
COINAPI_CACHE_TTL = 3600 * 12  # 12 hours (aggressive caching to conserve API calls)

# Cache Settings
CACHE_DURATION = 300  # 5 minutes in seconds
RATE_LIMIT_DELAY = 2  # Seconds between API calls

# Data Settings
DEFAULT_DAYS = '365'
RSI_PERIOD = 14  # Period for RSI calculation

# API Provider Selection
API_PROVIDER = 'mixed'  # Using multiple providers: CoinAPI for crypto, FMP for gold/SPX, Yahoo Finance for DXY (free)