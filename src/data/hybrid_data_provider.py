"""
Hybrid Data Provider
Intelligently switches between PostgreSQL (fast) and JSON files (fallback)
Provides seamless integration without breaking existing routes
"""

from typing import Dict, Any, Optional
from data.postgres_data_provider import postgres_provider


class HybridDataProvider:
    """
    Hybrid data provider that:
    1. First tries PostgreSQL (fast, 200-300x faster than JSON)
    2. Falls back to original JSON-based plugin if not in PostgreSQL
    3. Caches results for 5 minutes
    """

    def __init__(self):
        # Dataset name mappings (route name → PostgreSQL name)
        self.dataset_name_map = {
            'btc': 'btc_price',  # /api/data?dataset=btc → btc_price in PostgreSQL
            'gold': 'gold_price',
            'spx': 'spx_price',
            'eth': 'eth_price_alpaca',
            'dxy': 'dxy_price'
        }

        # List of datasets confirmed to be in PostgreSQL (from migration)
        self.postgres_datasets = {
            # Price data (OHLCV)
            'btc_price', 'gold_price',

            # Oscillators (simple values)
            'rsi_btc', 'adx_btc', 'atr_btc', 'macd_histogram_btc', 'psar_btc',
            'sma_7_btc', 'sma_21_btc', 'sma_60_btc',

            # Derivatives
            'dvol_btc', 'basis_spread_btc', 'funding_rate_btc', 'funding_rate_daily_btc',

            # Macro
            'dxy_price', 'spx_price', 'eth_price_alpaca',
            'btc_dominance', 'usdt_dominance',

            # TradingView On-Chain
            'btc_sopr', 'btc_medianvolume', 'btc_meantxfees', 'btc_sendingaddresses',
            'btc_active1y', 'btc_receivingaddresses', 'btc_newaddresses',
            'btc_ser', 'btc_avgtx', 'btc_txcount', 'btc_splyadrbal1',
            'btc_addressessupply1in10k', 'btc_largetxcount', 'btc_activesupply1y',

            # TradingView Social
            'btc_postscreated', 'btc_contributorscreated', 'btc_socialdominance', 'btc_contributorsactive',

            # TradingView Market
            'total3', 'stable_c_d',

            # ETFs
            'ibit', 'gbtc',

            # Other
            'btcst_tvl', 'usdtusd_pm', 'usdt_tfsps', 'usdt_avgtx'
        }

        # Datasets NOT in PostgreSQL (kept in JSON)
        self.json_only_datasets = {
            'btc_price_1min_complete',  # 3M records - too large
            'rrpontsyd',                # Numeric overflow issue
            'eth_price'                 # Only 7 records (incomplete)
        }

    def get_data(self, dataset_name: str, days: str, json_plugin: Optional[Any] = None) -> Dict[str, Any]:
        """
        Fetch data - PostgreSQL first, JSON fallback

        Args:
            dataset_name: Name of dataset
            days: Number of days (or 'all')
            json_plugin: Original JSON-based plugin (for fallback)

        Returns:
            Dictionary with 'metadata' and 'data'
        """

        # Map dataset name to PostgreSQL name if needed
        postgres_name = self.dataset_name_map.get(dataset_name, dataset_name)

        # Strategy 1: PostgreSQL (if available)
        if postgres_name in self.postgres_datasets:
            try:
                print(f"[PostgreSQL] Fetching {dataset_name} (mapped to {postgres_name}) from database...")
                result = postgres_provider.get_data(postgres_name, days)

                # Check if data was actually found
                if result.get('data') or 'error' not in result.get('metadata', {}):
                    return result
                else:
                    print(f"[PostgreSQL] {dataset_name} not found in database, falling back to JSON...")

            except Exception as e:
                print(f"[PostgreSQL] Error fetching {dataset_name}: {e}, falling back to JSON...")

        # Strategy 2: JSON fallback (if plugin provided)
        if json_plugin:
            try:
                print(f"[JSON] Fetching {dataset_name} from JSON file...")

                # Check if it's a callable (lambda) or module with get_data method
                if callable(json_plugin) and not hasattr(json_plugin, 'get_data'):
                    # It's a lambda function
                    return json_plugin(days)
                else:
                    # It's a module
                    return json_plugin.get_data(days)

            except Exception as e:
                print(f"[JSON] Error fetching {dataset_name}: {e}")
                return {
                    'metadata': {'label': dataset_name, 'error': str(e)},
                    'data': []
                }

        # Strategy 3: No plugin, dataset not found
        return {
            'metadata': {'label': dataset_name, 'error': 'Dataset not found in PostgreSQL or JSON'},
            'data': []
        }

    def is_postgres_available(self, dataset_name: str) -> bool:
        """Check if dataset is available in PostgreSQL"""
        postgres_name = self.dataset_name_map.get(dataset_name, dataset_name)
        return postgres_name in self.postgres_datasets


# Global singleton instance
hybrid_provider = HybridDataProvider()
