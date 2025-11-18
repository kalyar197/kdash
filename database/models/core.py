"""
Core ORM Models
Sources, TimeseriesData, TimeIndex, MarketCalendar
"""

from sqlalchemy import (
    Column, Integer, String, DateTime, Boolean, Interval,
    Date, Time, Text, Numeric, ForeignKey, Index,
    CheckConstraint, UniqueConstraint, SmallInteger
)
from sqlalchemy.dialects.postgresql import JSONB, ENUM, TIMESTAMP
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from datetime import datetime

from .base import Base

# Import custom ENUM types (must match 02_enums.sql)
DataTypeEnum = ENUM(
    'ohlcv', 'simple', 'calculated', 'social', 'onchain',
    'macro', 'derivative', 'stablecoin', 'etf', 'defi',
    name='data_type_enum',
    create_type=False  # Type already exists in database
)

PluginStatusEnum = ENUM(
    'active', 'inactive', 'deprecated', 'testing',
    name='plugin_status_enum',
    create_type=False
)

MarketEnum = ENUM(
    'US', 'CRYPTO', 'FOREX', 'COMMODITIES',
    name='market_enum',
    create_type=False
)


# ============================================================================
# SOURCES TABLE (Data Plugin Registry)
# ============================================================================

class Source(Base):
    """
    Data source plugin registry
    Maps to sources table in database
    """
    __tablename__ = 'sources'

    source_id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(100), unique=True, nullable=False, index=True)
    display_name = Column(String(200), nullable=False)
    category = Column(String(50), nullable=False, index=True)
    data_type = Column(DataTypeEnum, nullable=False, index=True)

    # API Configuration
    api_endpoint = Column(Text, nullable=True)
    api_provider = Column(String(50), nullable=True)
    requires_auth = Column(Boolean, default=False)

    # Update Configuration
    update_frequency = Column(Interval, nullable=False, default='1 day')
    last_successful_update = Column(TIMESTAMP, nullable=True)
    next_scheduled_update = Column(TIMESTAMP, nullable=True)

    # Plugin Status
    status = Column(PluginStatusEnum, default='active', index=True)
    market_type = Column(MarketEnum, default='CRYPTO')

    # Metadata (flexible JSONB) - renamed from 'metadata' to avoid SQLAlchemy reserved name
    source_metadata = Column(JSONB, default={})

    # Audit fields
    created_at = Column(TIMESTAMP, default=func.now(), nullable=False)
    updated_at = Column(TIMESTAMP, default=func.now(), onupdate=func.now(), nullable=False)
    created_by = Column(String(100), default='system')

    # Relationships
    timeseries_data = relationship('TimeseriesData', back_populates='source', cascade='all, delete-orphan')
    anomalies = relationship('Anomaly', back_populates='source', cascade='all, delete-orphan')

    # Constraints
    __table_args__ = (
        CheckConstraint("name ~ '^[a-z0-9_]+$'", name='chk_name_format'),
        Index('idx_sources_next_update', 'next_scheduled_update', postgresql_where=(status == 'active')),
    )

    def __repr__(self):
        return f"<Source(id={self.source_id}, name='{self.name}', type={self.data_type}, status={self.status})>"

    def to_dict(self):
        """Convert to dictionary for JSON serialization"""
        return {
            'source_id': self.source_id,
            'name': self.name,
            'display_name': self.display_name,
            'category': self.category,
            'data_type': self.data_type,
            'status': self.status,
            'market_type': self.market_type,
            'last_update': self.last_successful_update.isoformat() if self.last_successful_update else None,
            'next_update': self.next_scheduled_update.isoformat() if self.next_scheduled_update else None,
        }


# ============================================================================
# TIME INDEX TABLE (Common Time Grid)
# ============================================================================

class TimeIndex(Base):
    """Pre-generated time grid for timestamp alignment"""
    __tablename__ = 'time_index'

    timestamp = Column(TIMESTAMP, primary_key=True)
    date_only = Column(Date, nullable=False, index=True)
    day_of_week = Column(Integer, nullable=False)  # 0=Monday, 6=Sunday
    is_weekend = Column(Boolean)  # Generated column in DB
    is_trading_day_us = Column(Boolean, default=True)
    is_trading_day_crypto = Column(Boolean, default=True)
    market = Column(String(20), default='US')
    notes = Column(Text, nullable=True)

    __table_args__ = (
        Index('idx_time_index_trading_us', 'timestamp', postgresql_where=(is_trading_day_us == True)),
        Index('idx_time_index_weekend', 'timestamp', postgresql_where=(is_weekend == True)),
    )

    def __repr__(self):
        return f"<TimeIndex(timestamp={self.timestamp}, date={self.date_only}, trading_us={self.is_trading_day_us})>"


# ============================================================================
# MARKET CALENDAR TABLE
# ============================================================================

class MarketCalendar(Base):
    """Market-specific trading schedule"""
    __tablename__ = 'market_calendar'

    calendar_id = Column(Integer, primary_key=True, autoincrement=True)
    date = Column(Date, nullable=False, index=True)
    market = Column(MarketEnum, nullable=False)
    is_holiday = Column(Boolean, default=False)
    holiday_name = Column(String(100), nullable=True)
    open_time = Column(Time(timezone=True), nullable=True)
    close_time = Column(Time(timezone=True), nullable=True)
    is_early_close = Column(Boolean, default=False)

    __table_args__ = (
        UniqueConstraint('date', 'market', name='uq_calendar_date_market'),
        Index('idx_market_calendar_holidays', 'date', postgresql_where=(is_holiday == True)),
    )

    def __repr__(self):
        return f"<MarketCalendar(date={self.date}, market={self.market}, holiday={self.is_holiday})>"


# ============================================================================
# TIMESERIES DATA TABLE (Unified Storage - Hypertable)
# ============================================================================

class TimeseriesData(Base):
    """
    Unified time-series storage for all datasets
    This is a TimescaleDB hypertable (automatic partitioning by time)
    """
    __tablename__ = 'timeseries_data'

    source_id = Column(Integer, ForeignKey('sources.source_id', ondelete='CASCADE'), primary_key=True)
    timestamp = Column(TIMESTAMP(3), primary_key=True)  # Millisecond precision
    date_only = Column(Date)  # Generated column in DB

    # OHLCV columns (NULL for simple data)
    # NUMERIC(24, 8) supports values up to $1 quadrillion (needed for macro data like Fed RRP)
    open = Column(Numeric(24, 8), nullable=True)
    high = Column(Numeric(24, 8), nullable=True)
    low = Column(Numeric(24, 8), nullable=True)
    close = Column(Numeric(24, 8), nullable=True)
    volume = Column(Numeric(24, 8), nullable=True)

    # Simple value column (NULL for OHLCV)
    value = Column(Numeric(24, 8), nullable=True)

    # Data quality metadata
    quality_score = Column(SmallInteger, default=100)
    is_anomaly = Column(Boolean, default=False, index=True)
    is_validated = Column(Boolean, default=True)

    # Audit fields
    created_at = Column(TIMESTAMP, default=func.now(), nullable=False)
    updated_at = Column(TIMESTAMP, default=func.now(), onupdate=func.now(), nullable=False)
    ingestion_timestamp = Column(TIMESTAMP, default=func.now(), nullable=False)

    # Relationships
    source = relationship('Source', back_populates='timeseries_data')

    # Constraints (enforced in database via triggers and CHECK constraints)
    __table_args__ = (
        CheckConstraint('quality_score BETWEEN 0 AND 100', name='chk_quality_score'),
        CheckConstraint('high >= low', name='chk_high_low'),
        Index('idx_timeseries_source_time', 'source_id', 'timestamp', postgresql_using='btree'),
        Index('idx_timeseries_date', 'date_only'),
        Index('idx_timeseries_quality', 'quality_score', postgresql_where=(quality_score < 80)),
        Index('idx_timeseries_anomalies', 'source_id', 'timestamp', postgresql_where=(is_anomaly == True)),
    )

    def __repr__(self):
        val = self.close if self.close is not None else self.value
        return f"<TimeseriesData(source={self.source_id}, time={self.timestamp}, value={val}, quality={self.quality_score})>"

    def to_dict(self):
        """Convert to dictionary for JSON serialization"""
        return {
            'source_id': self.source_id,
            'timestamp': int(self.timestamp.timestamp() * 1000),  # Milliseconds
            'date': self.date_only.isoformat() if self.date_only else None,
            # OHLCV fields
            'open': float(self.open) if self.open else None,
            'high': float(self.high) if self.high else None,
            'low': float(self.low) if self.low else None,
            'close': float(self.close) if self.close else None,
            'volume': float(self.volume) if self.volume else None,
            # Simple value
            'value': float(self.value) if self.value else None,
            # Quality
            'quality_score': self.quality_score,
            'is_anomaly': self.is_anomaly,
        }

    def to_simple_format(self):
        """Convert to [timestamp_ms, value] format for frontend"""
        timestamp_ms = int(self.timestamp.timestamp() * 1000)
        val = float(self.close if self.close is not None else self.value)
        return [timestamp_ms, val]

    def to_ohlcv_format(self):
        """Convert to [timestamp_ms, open, high, low, close, volume] format"""
        timestamp_ms = int(self.timestamp.timestamp() * 1000)
        return [
            timestamp_ms,
            float(self.open) if self.open else None,
            float(self.high) if self.high else None,
            float(self.low) if self.low else None,
            float(self.close) if self.close else None,
            float(self.volume) if self.volume else None,
        ]

    @classmethod
    def from_simple(cls, source_id: int, timestamp: datetime, value: float, **kwargs):
        """Create TimeseriesData from simple [timestamp, value] format"""
        return cls(
            source_id=source_id,
            timestamp=timestamp,
            value=value,
            **kwargs
        )

    @classmethod
    def from_ohlcv(cls, source_id: int, timestamp: datetime,
                   open: float, high: float, low: float, close: float, volume: float,
                   **kwargs):
        """Create TimeseriesData from OHLCV format"""
        return cls(
            source_id=source_id,
            timestamp=timestamp,
            open=open,
            high=high,
            low=low,
            close=close,
            volume=volume,
            **kwargs
        )
