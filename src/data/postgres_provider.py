"""PostgreSQL Data Provider - No JSON fallback"""
from datetime import datetime, timedelta
from database.models import get_db, Source, TimeseriesData
from sqlalchemy import and_

def get_data(dataset_name, days=365):
    """
    Fetch data from PostgreSQL for specified dataset and time range.

    Args:
        dataset_name: Name of the dataset (source name)
        days: Number of days to fetch (default: 365)

    Returns:
        List of [timestamp_ms, value/ohlcv...] arrays
    """
    db = next(get_db())
    try:
        source = db.query(Source).filter(Source.name == dataset_name).first()
        if not source:
            return []

        cutoff = datetime.now() - timedelta(days=days)
        results = db.query(TimeseriesData).filter(
            and_(TimeseriesData.source_id == source.source_id, TimeseriesData.timestamp >= cutoff)
        ).order_by(TimeseriesData.timestamp).all()

        data = []
        for row in results:
            ts_ms = int(row.timestamp.timestamp() * 1000)
            if row.open is not None:
                data.append([ts_ms, float(row.open), float(row.high), float(row.low), float(row.close), float(row.volume) if row.volume else 0.0])
            elif row.value is not None:
                data.append([ts_ms, float(row.value)])
        return data
    finally:
        db.close()


def get_metadata(dataset_name):
    """
    Get metadata for a dataset from PostgreSQL.

    Args:
        dataset_name: Name of the dataset

    Returns:
        Dict with metadata fields
    """
    db = next(get_db())
    try:
        source = db.query(Source).filter(Source.name == dataset_name).first()
        if not source:
            return {}

        return {
            'label': source.display_name,
            'category': source.category,
            'data_type': source.data_type,
            'update_frequency': str(source.update_frequency) if source.update_frequency else None,
            'status': source.status
        }
    finally:
        db.close()
