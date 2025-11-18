"""
Data Quality ORM Models
ValidationRule, Anomaly, AuditLog, TimeseriesArchive
"""

from sqlalchemy import (
    Column, Integer, String, DateTime, Boolean, Text,
    Numeric, ForeignKey, Index, BigInteger, SmallInteger
)
from sqlalchemy.dialects.postgresql import JSONB, ENUM, TIMESTAMP, ARRAY, INET
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from .base import Base

# Import custom ENUM types
DataTypeEnum = ENUM(
    'ohlcv', 'simple', 'calculated', 'social', 'onchain',
    'macro', 'derivative', 'stablecoin', 'etf', 'defi',
    name='data_type_enum',
    create_type=False
)

AnomalyTypeEnum = ENUM(
    'outlier_4sigma', 'outlier_6sigma', 'missing_data',
    'late_data', 'corrupt_data', 'duplicate',
    name='anomaly_type_enum',
    create_type=False
)

AuditActionEnum = ENUM(
    'INSERT', 'UPDATE', 'DELETE', 'CORRECTION',
    name='audit_action_enum',
    create_type=False
)


# ============================================================================
# VALIDATION RULES TABLE
# ============================================================================

class ValidationRule(Base):
    """Extensible validation rules per data_type"""
    __tablename__ = 'validation_rules'

    rule_id = Column(Integer, primary_key=True, autoincrement=True)
    data_type = Column(DataTypeEnum, nullable=False, index=True)
    rule_name = Column(String(100), nullable=False)
    rule_sql = Column(Text, nullable=False)
    error_message = Column(Text, nullable=False)
    severity = Column(String(20), default='ERROR')  # ERROR, WARNING, INFO
    enabled = Column(Boolean, default=True, index=True)

    # Audit
    created_at = Column(TIMESTAMP, default=func.now())
    created_by = Column(String(100), default='system')

    __table_args__ = (
        Index('idx_validation_rules_enabled', 'data_type', postgresql_where=(enabled == True)),
    )

    def __repr__(self):
        return f"<ValidationRule(id={self.rule_id}, type={self.data_type}, rule='{self.rule_name}', enabled={self.enabled})>"

    def to_dict(self):
        return {
            'rule_id': self.rule_id,
            'data_type': self.data_type,
            'rule_name': self.rule_name,
            'rule_sql': self.rule_sql,
            'error_message': self.error_message,
            'severity': self.severity,
            'enabled': self.enabled,
        }


# ============================================================================
# ANOMALIES TABLE
# ============================================================================

class Anomaly(Base):
    """Automated detection of data quality issues"""
    __tablename__ = 'anomalies'

    anomaly_id = Column(BigInteger, primary_key=True, autoincrement=True)
    source_id = Column(Integer, ForeignKey('sources.source_id', ondelete='CASCADE'), nullable=False, index=True)
    timestamp = Column(TIMESTAMP, nullable=False, index=True)
    detected_at = Column(TIMESTAMP, default=func.now(), nullable=False, index=True)

    # Anomaly classification
    anomaly_type = Column(AnomalyTypeEnum, nullable=False, index=True)
    severity = Column(String(20), default='MEDIUM')  # LOW, MEDIUM, HIGH, CRITICAL

    # Statistical data
    value = Column(Numeric(20, 8))
    z_score = Column(Numeric(20, 8))
    expected_value = Column(Numeric(20, 8))
    deviation_pct = Column(Numeric(10, 4))

    # Flags
    is_blackswan = Column(Boolean, default=False, index=True)
    reviewed = Column(Boolean, default=False, index=True)
    is_false_positive = Column(Boolean, default=False)

    # Resolution
    resolved_at = Column(TIMESTAMP, nullable=True)
    resolved_by = Column(String(100), nullable=True)
    resolution_notes = Column(Text, nullable=True)

    # Context
    context = Column(JSONB, nullable=True)

    # Relationships
    source = relationship('Source', back_populates='anomalies')

    __table_args__ = (
        Index('idx_anomalies_source_time', 'source_id', 'timestamp'),
        Index('idx_anomalies_unreviewed', 'detected_at', postgresql_where=(reviewed == False)),
        Index('idx_anomalies_blackswan', 'detected_at', postgresql_where=(is_blackswan == True)),
    )

    def __repr__(self):
        return f"<Anomaly(id={self.anomaly_id}, source={self.source_id}, type={self.anomaly_type}, z={self.z_score}, blackswan={self.is_blackswan})>"

    def to_dict(self):
        return {
            'anomaly_id': self.anomaly_id,
            'source_id': self.source_id,
            'timestamp': self.timestamp.isoformat(),
            'detected_at': self.detected_at.isoformat(),
            'anomaly_type': self.anomaly_type,
            'severity': self.severity,
            'value': float(self.value) if self.value else None,
            'z_score': float(self.z_score) if self.z_score else None,
            'expected_value': float(self.expected_value) if self.expected_value else None,
            'deviation_pct': float(self.deviation_pct) if self.deviation_pct else None,
            'is_blackswan': self.is_blackswan,
            'reviewed': self.reviewed,
            'is_false_positive': self.is_false_positive,
            'resolved_at': self.resolved_at.isoformat() if self.resolved_at else None,
            'resolution_notes': self.resolution_notes,
        }


# ============================================================================
# AUDIT LOG TABLE
# ============================================================================

class AuditLog(Base):
    """Immutable log of all data modifications"""
    __tablename__ = 'audit_log'

    audit_id = Column(BigInteger, primary_key=True, autoincrement=True)
    source_id = Column(Integer, ForeignKey('sources.source_id', ondelete='SET NULL'), nullable=True, index=True)
    timestamp = Column(TIMESTAMP, nullable=True, index=True)

    # Action details
    action = Column(AuditActionEnum, nullable=False, index=True)
    table_name = Column(String(100), nullable=False)

    # Change tracking
    old_value = Column(JSONB, nullable=True)
    new_value = Column(JSONB, nullable=True)
    changed_fields = Column(ARRAY(Text), nullable=True)

    # Who and why
    changed_by = Column(String(100), nullable=False, default='system', index=True)
    changed_at = Column(TIMESTAMP, default=func.now(), nullable=False, index=True)
    reason = Column(Text, nullable=True)

    # Context
    ip_address = Column(INET, nullable=True)
    user_agent = Column(Text, nullable=True)

    __table_args__ = (
        Index('idx_audit_log_source', 'source_id', 'changed_at'),
        Index('idx_audit_log_timestamp', 'timestamp', 'changed_at'),
    )

    def __repr__(self):
        return f"<AuditLog(id={self.audit_id}, action={self.action}, table={self.table_name}, by={self.changed_by}, at={self.changed_at})>"

    def to_dict(self):
        return {
            'audit_id': self.audit_id,
            'source_id': self.source_id,
            'timestamp': self.timestamp.isoformat() if self.timestamp else None,
            'action': self.action,
            'table_name': self.table_name,
            'old_value': self.old_value,
            'new_value': self.new_value,
            'changed_fields': self.changed_fields,
            'changed_by': self.changed_by,
            'changed_at': self.changed_at.isoformat(),
            'reason': self.reason,
        }


# ============================================================================
# TIMESERIES ARCHIVE TABLE (Soft Delete)
# ============================================================================

class TimeseriesArchive(Base):
    """Immutable archive of deleted data"""
    __tablename__ = 'timeseries_archive'

    archive_id = Column(BigInteger, primary_key=True, autoincrement=True)

    # Original data (copy of timeseries_data row)
    source_id = Column(Integer, nullable=False, index=True)
    timestamp = Column(TIMESTAMP(3), nullable=False, index=True)
    date_only = Column(String, nullable=True)  # Store as string since it was generated

    # OHLCV
    open = Column(Numeric(20, 8))
    high = Column(Numeric(20, 8))
    low = Column(Numeric(20, 8))
    close = Column(Numeric(20, 8))
    volume = Column(Numeric(30, 8))

    # Simple value
    value = Column(Numeric(20, 8))

    # Quality metadata
    quality_score = Column(SmallInteger)
    is_anomaly = Column(Boolean)

    # Archive metadata
    deleted_at = Column(TIMESTAMP, default=func.now(), nullable=False, index=True)
    deleted_by = Column(String(100), nullable=False)
    deletion_reason = Column(Text, nullable=True)

    # Recovery support
    restored_at = Column(TIMESTAMP, nullable=True)
    restored_by = Column(String(100), nullable=True)

    __table_args__ = (
        Index('idx_archive_source_time', 'source_id', 'timestamp'),
        Index('idx_archive_restorable', 'source_id', 'timestamp', postgresql_where=(restored_at.is_(None))),
    )

    def __repr__(self):
        return f"<TimeseriesArchive(id={self.archive_id}, source={self.source_id}, time={self.timestamp}, deleted={self.deleted_at})>"

    def to_dict(self):
        return {
            'archive_id': self.archive_id,
            'source_id': self.source_id,
            'timestamp': self.timestamp.isoformat(),
            'value': float(self.value) if self.value else None,
            'close': float(self.close) if self.close else None,
            'deleted_at': self.deleted_at.isoformat(),
            'deleted_by': self.deleted_by,
            'deletion_reason': self.deletion_reason,
            'restored_at': self.restored_at.isoformat() if self.restored_at else None,
        }
