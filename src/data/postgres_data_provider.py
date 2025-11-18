"""
PostgreSQL Data Provider
Fetches timeseries data from PostgreSQL instead of JSON files
Provides same interface as JSON-based data plugins for drop-in replacement
"""

from datetime import datetime, timedelta, timezone
from typing import List, Tuple, Optional, Dict, Any
from sqlalchemy import text
from database.models import get_db


class PostgresDataProvider:
    """
    Unified data provider that queries PostgreSQL
    Replaces individual JSON-based data plugins
    """

    def __init__(self):
        self._cache = {}
        self._cache_ttl = 300  # 5 minutes
        self._cache_timestamps = {}

    def _get_cache_key(self, dataset_name: str, days: str) -> str:
        """Generate cache key"""
        return f"{dataset_name}:{days}"

    def _is_cache_valid(self, cache_key: str) -> bool:
        """Check if cached data is still valid"""
        if cache_key not in self._cache:
            return False

        timestamp = self._cache_timestamps.get(cache_key, 0)
        age = datetime.now(timezone.utc).timestamp() - timestamp
        return age < self._cache_ttl

    def _set_cache(self, cache_key: str, data: Any):
        """Store data in cache with timestamp"""
        self._cache[cache_key] = data
        self._cache_timestamps[cache_key] = datetime.now(timezone.utc).timestamp()

    def get_data(self, dataset_name: str, days: str = '365') -> Dict[str, Any]:
        """
        Fetch timeseries data from PostgreSQL

        Args:
            dataset_name: Name of the dataset (e.g., 'btc_price', 'rsi_btc')
            days: Number of days to fetch ('all' for all data)

        Returns:
            Dictionary with 'metadata' and 'data' keys
        """
        cache_key = self._get_cache_key(dataset_name, days)

        # Check cache first
        if self._is_cache_valid(cache_key):
            return self._cache[cache_key]

        try:
            db = next(get_db())

            # Get source metadata (query only columns that exist)
            source_query = text("""
                SELECT
                    source_id,
                    display_name,
                    category,
                    data_type,
                    source_metadata
                FROM sources
                WHERE name = :name
                LIMIT 1
            """)

            source = db.execute(source_query, {"name": dataset_name}).fetchone()

            if not source:
                return {
                    'metadata': {'label': dataset_name, 'error': 'Dataset not found'},
                    'data': []
                }

            source_id, display_name, category, data_type, source_metadata = source

            # Extract metadata from JSONB (with defaults)
            meta = source_metadata or {}

            # Build metadata with defaults for missing fields
            metadata = {
                'label': display_name or dataset_name,
                'yAxisId': meta.get('y_axis_id', 'default'),  # Default axis
                'color': meta.get('color', '#3B82F6'),  # Default blue
                'category': category,
                'data_type': data_type,
                'unit': meta.get('unit', ''),
                'chart_type': meta.get('chart_type', 'line')
            }

            # Optional metadata fields
            if meta.get('line_style'):
                metadata['lineStyle'] = meta['line_style']
            if meta.get('line_width'):
                metadata['lineWidth'] = meta['line_width']

            # Build time filter
            time_filter = ""
            params = {"source_id": source_id}

            if days != 'all':
                try:
                    days_int = int(days)
                    cutoff_date = datetime.now(timezone.utc) - timedelta(days=days_int)
                    time_filter = "AND timestamp >= :cutoff_date"
                    params['cutoff_date'] = cutoff_date
                except ValueError:
                    pass  # Invalid days format, fetch all

            # Fetch data based on type
            if data_type == 'ohlcv':
                # OHLCV data (6 components)
                data_query = text(f"""
                    SELECT
                        EXTRACT(EPOCH FROM timestamp) * 1000 AS ts_ms,
                        open,
                        high,
                        low,
                        close,
                        volume
                    FROM timeseries_data
                    WHERE source_id = :source_id
                      {time_filter}
                    ORDER BY timestamp ASC
                """)

                rows = db.execute(data_query, params).fetchall()
                data = [[int(row[0]), float(row[1]) if row[1] is not None else None,
                        float(row[2]) if row[2] is not None else None,
                        float(row[3]) if row[3] is not None else None,
                        float(row[4]) if row[4] is not None else None,
                        float(row[5]) if row[5] is not None else None] for row in rows]

            else:
                # Simple value data (2 components: timestamp, value)
                data_query = text(f"""
                    SELECT
                        EXTRACT(EPOCH FROM timestamp) * 1000 AS ts_ms,
                        value
                    FROM timeseries_data
                    WHERE source_id = :source_id
                      {time_filter}
                    ORDER BY timestamp ASC
                """)

                rows = db.execute(data_query, params).fetchall()
                data = [[int(row[0]), float(row[1]) if row[1] is not None else None] for row in rows]

            result = {
                'metadata': metadata,
                'data': data
            }

            # Cache the result
            self._set_cache(cache_key, result)

            return result

        except Exception as e:
            print(f"[ERROR] PostgresDataProvider.get_data({dataset_name}, {days}): {e}")
            return {
                'metadata': {'label': dataset_name, 'error': str(e)},
                'data': []
            }

    def get_metadata(self, dataset_name: str) -> Dict[str, Any]:
        """
        Get just the metadata for a dataset

        Args:
            dataset_name: Name of the dataset

        Returns:
            Metadata dictionary
        """
        try:
            db = next(get_db())

            source_query = text("""
                SELECT
                    display_name,
                    category,
                    data_type,
                    source_metadata
                FROM sources
                WHERE name = :name
                LIMIT 1
            """)

            source = db.execute(source_query, {"name": dataset_name}).fetchone()

            if not source:
                return {'label': dataset_name, 'error': 'Dataset not found'}

            display_name, category, data_type, source_metadata = source

            # Extract metadata from JSONB (with defaults)
            meta = source_metadata or {}

            metadata = {
                'label': display_name or dataset_name,
                'yAxisId': meta.get('y_axis_id', 'default'),
                'color': meta.get('color', '#3B82F6'),
                'category': category,
                'data_type': data_type,
                'unit': meta.get('unit', ''),
                'chart_type': meta.get('chart_type', 'line')
            }

            # Optional metadata fields
            if meta.get('line_style'):
                metadata['lineStyle'] = meta['line_style']
            if meta.get('line_width'):
                metadata['lineWidth'] = meta['line_width']

            return metadata

        except Exception as e:
            print(f"[ERROR] PostgresDataProvider.get_metadata({dataset_name}): {e}")
            return {'label': dataset_name, 'error': str(e)}


# Global singleton instance
postgres_provider = PostgresDataProvider()
