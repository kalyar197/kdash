"""
Analytics and ML ORM Models
Lineage, Feature, Forecast, BacktestResult, BacktestTrade, MLModel
"""

from sqlalchemy import (
    Column, Integer, String, DateTime, Boolean, Text,
    Numeric, ForeignKey, Index, BigInteger, Interval, Date,
    CheckConstraint, UniqueConstraint
)
from sqlalchemy.dialects.postgresql import JSONB, TIMESTAMP, ARRAY
from sqlalchemy.orm import relationship, column_property
from sqlalchemy.sql import func, select
from sqlalchemy.ext.hybrid import hybrid_property

from .base import Base


# ============================================================================
# LINEAGE TABLE (Dependency Tracking)
# ============================================================================

class Lineage(Base):
    """Track data lineage and dependencies"""
    __tablename__ = 'lineage'

    lineage_id = Column(Integer, primary_key=True, autoincrement=True)
    derived_source_id = Column(Integer, ForeignKey('sources.source_id', ondelete='CASCADE'), nullable=False, index=True)
    parent_source_id = Column(Integer, ForeignKey('sources.source_id', ondelete='CASCADE'), nullable=False, index=True)

    # Calculation specification
    calculation_type = Column(String(50), nullable=False)  # 'indicator', 'zscore', 'aggregate', 'composite'
    calculation_sql = Column(Text, nullable=True)
    calculation_function = Column(Text, nullable=True)

    # Dependency metadata
    dependency_level = Column(Integer, nullable=False, default=1)
    refresh_required = Column(Boolean, default=True, index=True)

    # Performance tracking
    last_calculation_time = Column(Interval, nullable=True)
    avg_calculation_time = Column(Interval, nullable=True)

    created_at = Column(TIMESTAMP, default=func.now())

    # Relationships
    derived_source = relationship('Source', foreign_keys=[derived_source_id])
    parent_source = relationship('Source', foreign_keys=[parent_source_id])

    __table_args__ = (
        UniqueConstraint('derived_source_id', 'parent_source_id', name='uq_lineage_derived_parent'),
        CheckConstraint('derived_source_id != parent_source_id', name='chk_no_self_reference'),
        Index('idx_lineage_refresh_needed', 'refresh_required', postgresql_where=(refresh_required == True)),
    )

    def __repr__(self):
        return f"<Lineage(derived={self.derived_source_id}, parent={self.parent_source_id}, level={self.dependency_level})>"


# ============================================================================
# FEATURES TABLE (Pre-computed ML Features)
# ============================================================================

class Feature(Base):
    """Pre-computed ML features for fast model training"""
    __tablename__ = 'features'

    feature_id = Column(BigInteger, primary_key=True, autoincrement=True)
    source_id = Column(Integer, ForeignKey('sources.source_id', ondelete='CASCADE'), nullable=False, index=True)
    timestamp = Column(TIMESTAMP, nullable=False, index=True)

    # Common financial features
    volatility_7d = Column(Numeric(20, 8))
    volatility_30d = Column(Numeric(20, 8))
    volatility_90d = Column(Numeric(20, 8))

    # Momentum features
    rsi_value = Column(Numeric(10, 4))
    rsi_momentum = Column(Numeric(10, 4))
    macd_value = Column(Numeric(20, 8))
    macd_signal = Column(Numeric(20, 8))

    # Volume features
    volume_sma_20 = Column(Numeric(30, 8))
    volume_ratio = Column(Numeric(10, 4))

    # Derivatives features
    funding_rate = Column(Numeric(10, 8))
    funding_delta = Column(Numeric(10, 8))
    basis_spread = Column(Numeric(10, 4))

    # Social/sentiment features
    social_volume = Column(Numeric(20, 2))
    social_sentiment = Column(Numeric(5, 4))

    # Regime features
    regime = Column(String(20))
    regime_probability = Column(Numeric(5, 4))

    # Extensible custom features
    custom_features = Column(JSONB, default={})

    # Metadata
    feature_set_version = Column(String(20), default='1.0')
    computed_at = Column(TIMESTAMP, default=func.now())

    # Relationship
    source = relationship('Source')

    __table_args__ = (
        UniqueConstraint('source_id', 'timestamp', name='uq_features_source_timestamp'),
        Index('idx_features_source_time', 'source_id', 'timestamp'),
        Index('idx_features_regime', 'regime', postgresql_where=(regime.isnot(None))),
    )

    def __repr__(self):
        return f"<Feature(source={self.source_id}, time={self.timestamp}, volatility_30d={self.volatility_30d})>"

    def to_dict(self):
        return {
            'feature_id': self.feature_id,
            'source_id': self.source_id,
            'timestamp': self.timestamp.isoformat(),
            'volatility_7d': float(self.volatility_7d) if self.volatility_7d else None,
            'volatility_30d': float(self.volatility_30d) if self.volatility_30d else None,
            'volatility_90d': float(self.volatility_90d) if self.volatility_90d else None,
            'rsi_value': float(self.rsi_value) if self.rsi_value else None,
            'funding_rate': float(self.funding_rate) if self.funding_rate else None,
            'regime': self.regime,
            'custom_features': self.custom_features,
        }


# ============================================================================
# FORECASTS TABLE (Model Predictions)
# ============================================================================

class Forecast(Base):
    """Store model predictions and track accuracy"""
    __tablename__ = 'forecasts'

    forecast_id = Column(BigInteger, primary_key=True, autoincrement=True)
    source_id = Column(Integer, ForeignKey('sources.source_id', ondelete='CASCADE'), nullable=False, index=True)

    # Forecast metadata
    forecast_timestamp = Column(TIMESTAMP, nullable=False)  # When prediction made
    target_timestamp = Column(TIMESTAMP, nullable=False, index=True)  # What is predicted

    # Prediction
    predicted_value = Column(Numeric(20, 8), nullable=False)
    confidence_lower = Column(Numeric(20, 8))
    confidence_upper = Column(Numeric(20, 8))
    confidence_level = Column(Numeric(5, 4), default=0.95)

    # Model information
    model_name = Column(String(100), nullable=False, index=True)
    model_version = Column(String(50))
    model_parameters = Column(JSONB)

    # Validation (populated after target_timestamp)
    actual_value = Column(Numeric(20, 8))
    prediction_error = Column(Numeric(20, 8))  # actual - predicted
    absolute_error = Column(Numeric(20, 8))
    percentage_error = Column(Numeric(10, 4))

    created_at = Column(TIMESTAMP, default=func.now())

    # Relationship
    source = relationship('Source')

    __table_args__ = (
        CheckConstraint('target_timestamp > forecast_timestamp', name='chk_target_future'),
        Index('idx_forecasts_source_target', 'source_id', 'target_timestamp'),
        Index('idx_forecasts_model', 'model_name', 'created_at'),
        Index('idx_forecasts_pending', 'target_timestamp', postgresql_where=(actual_value.is_(None))),
    )

    @hybrid_property
    def is_accurate(self):
        """Check if prediction is within 5% of actual"""
        if self.actual_value and self.percentage_error:
            return abs(self.percentage_error) < 5.0
        return None

    def __repr__(self):
        return f"<Forecast(id={self.forecast_id}, model={self.model_name}, target={self.target_timestamp}, predicted={self.predicted_value})>"

    def to_dict(self):
        return {
            'forecast_id': self.forecast_id,
            'source_id': self.source_id,
            'forecast_timestamp': self.forecast_timestamp.isoformat(),
            'target_timestamp': self.target_timestamp.isoformat(),
            'predicted_value': float(self.predicted_value),
            'confidence_lower': float(self.confidence_lower) if self.confidence_lower else None,
            'confidence_upper': float(self.confidence_upper) if self.confidence_upper else None,
            'model_name': self.model_name,
            'model_version': self.model_version,
            'actual_value': float(self.actual_value) if self.actual_value else None,
            'prediction_error': float(self.prediction_error) if self.prediction_error else None,
            'percentage_error': float(self.percentage_error) if self.percentage_error else None,
        }


# ============================================================================
# BACKTEST RESULTS TABLE
# ============================================================================

class BacktestResult(Base):
    """Store strategy backtest performance"""
    __tablename__ = 'backtest_results'

    backtest_id = Column(Integer, primary_key=True, autoincrement=True)
    strategy_name = Column(String(100), nullable=False, index=True)
    strategy_version = Column(String(50), nullable=False)
    strategy_description = Column(Text)

    # Time range
    start_date = Column(Date, nullable=False)
    end_date = Column(Date, nullable=False)
    total_days = Column(Integer)  # Generated in database

    # Performance metrics
    total_return = Column(Numeric(10, 4), nullable=False)
    annualized_return = Column(Numeric(10, 4))
    sharpe_ratio = Column(Numeric(10, 4), index=True)
    sortino_ratio = Column(Numeric(10, 4))
    max_drawdown = Column(Numeric(10, 4))
    max_drawdown_duration = Column(Integer)

    # Trade statistics
    total_trades = Column(Integer, default=0)
    winning_trades = Column(Integer, default=0)
    losing_trades = Column(Integer, default=0)
    win_rate = Column(Numeric(5, 2))  # Generated in database

    # Risk metrics
    value_at_risk_95 = Column(Numeric(20, 8))
    conditional_var_95 = Column(Numeric(20, 8))
    beta = Column(Numeric(10, 4))
    alpha = Column(Numeric(10, 4))

    # Configuration
    initial_capital = Column(Numeric(20, 2), default=100000)
    position_size = Column(Numeric(5, 4))
    config = Column(JSONB, default={})

    # Execution metadata
    executed_at = Column(TIMESTAMP, default=func.now(), nullable=False, index=True)
    executed_by = Column(String(100), default='system')
    execution_time = Column(Interval)

    # Environment
    data_source = Column(String(100))
    fees_included = Column(Boolean, default=True)
    slippage_included = Column(Boolean, default=True)

    # Relationship to trades
    trades = relationship('BacktestTrade', back_populates='backtest', cascade='all, delete-orphan')

    __table_args__ = (
        CheckConstraint('end_date > start_date', name='chk_date_order'),
        CheckConstraint('total_trades >= 0 AND winning_trades >= 0 AND losing_trades >= 0', name='chk_trade_counts'),
        Index('idx_backtest_strategy', 'strategy_name', 'strategy_version', 'executed_at'),
    )

    def __repr__(self):
        return f"<BacktestResult(id={self.backtest_id}, strategy={self.strategy_name}, sharpe={self.sharpe_ratio}, return={self.total_return}%)>"

    def to_dict(self):
        return {
            'backtest_id': self.backtest_id,
            'strategy_name': self.strategy_name,
            'strategy_version': self.strategy_version,
            'start_date': self.start_date.isoformat(),
            'end_date': self.end_date.isoformat(),
            'total_return': float(self.total_return),
            'sharpe_ratio': float(self.sharpe_ratio) if self.sharpe_ratio else None,
            'max_drawdown': float(self.max_drawdown) if self.max_drawdown else None,
            'total_trades': self.total_trades,
            'win_rate': float(self.win_rate) if self.win_rate else None,
            'executed_at': self.executed_at.isoformat(),
        }


# ============================================================================
# BACKTEST TRADES TABLE
# ============================================================================

class BacktestTrade(Base):
    """Individual trade records within backtests"""
    __tablename__ = 'backtest_trades'

    trade_id = Column(BigInteger, primary_key=True, autoincrement=True)
    backtest_id = Column(Integer, ForeignKey('backtest_results.backtest_id', ondelete='CASCADE'), nullable=False, index=True)

    # Trade execution
    entry_timestamp = Column(TIMESTAMP, nullable=False, index=True)
    exit_timestamp = Column(TIMESTAMP, nullable=False)
    direction = Column(String(10), nullable=False)  # LONG, SHORT

    # Prices
    entry_price = Column(Numeric(20, 8), nullable=False)
    exit_price = Column(Numeric(20, 8), nullable=False)
    stop_loss = Column(Numeric(20, 8))
    take_profit = Column(Numeric(20, 8))

    # Position sizing
    quantity = Column(Numeric(30, 8), nullable=False)
    position_value = Column(Numeric(30, 2), nullable=False)

    # P&L
    gross_pnl = Column(Numeric(30, 2), nullable=False)
    fees = Column(Numeric(30, 2), default=0)
    net_pnl = Column(Numeric(30, 2), nullable=False)
    return_pct = Column(Numeric(10, 4), nullable=False, index=True)

    # Trade metadata
    entry_signal = Column(Text)
    exit_reason = Column(String(50))  # TAKE_PROFIT, STOP_LOSS, SIGNAL, END_OF_TEST
    duration = Column(Interval)  # Generated in database

    # Relationship
    backtest = relationship('BacktestResult', back_populates='trades')

    __table_args__ = (
        CheckConstraint("direction IN ('LONG', 'SHORT')", name='chk_direction'),
        CheckConstraint('exit_timestamp > entry_timestamp', name='chk_exit_after_entry'),
        CheckConstraint('quantity > 0', name='chk_quantity_positive'),
        Index('idx_backtest_trades_backtest', 'backtest_id', 'entry_timestamp'),
        Index('idx_backtest_trades_duration', 'duration'),
    )

    def __repr__(self):
        return f"<BacktestTrade(id={self.trade_id}, direction={self.direction}, pnl={self.net_pnl}, return={self.return_pct}%)>"


# ============================================================================
# ML MODELS TABLE
# ============================================================================

class MLModel(Base):
    """Registry of all ML models with metadata"""
    __tablename__ = 'ml_models'

    model_id = Column(Integer, primary_key=True, autoincrement=True)
    model_name = Column(String(100), nullable=False)
    model_version = Column(String(50), nullable=False)
    model_type = Column(String(50), nullable=False)  # regression, classification, timeseries

    # Model artifacts
    model_path = Column(Text)
    model_hash = Column(String(64))  # SHA256

    # Training metadata
    training_start_date = Column(Date)
    training_end_date = Column(Date)
    validation_start_date = Column(Date)
    validation_end_date = Column(Date)
    features_used = Column(ARRAY(Text))

    # Performance metrics
    train_score = Column(Numeric(10, 6))
    validation_score = Column(Numeric(10, 6))
    test_score = Column(Numeric(10, 6))
    rmse = Column(Numeric(20, 8))
    mae = Column(Numeric(20, 8))
    r2_score = Column(Numeric(10, 6))

    # Hyperparameters
    hyperparameters = Column(JSONB)

    # Status
    status = Column(String(20), default='training', index=True)  # training, validated, deployed, retired
    deployed_at = Column(TIMESTAMP)
    retired_at = Column(TIMESTAMP)

    # Audit
    created_at = Column(TIMESTAMP, default=func.now())
    created_by = Column(String(100))
    notes = Column(Text)

    __table_args__ = (
        UniqueConstraint('model_name', 'model_version', name='uq_model_name_version'),
        Index('idx_ml_models_deployed', 'deployed_at', postgresql_where=(status == 'deployed')),
    )

    def __repr__(self):
        return f"<MLModel(name={self.model_name}, version={self.model_version}, status={self.status}, test_score={self.test_score})>"

    def to_dict(self):
        return {
            'model_id': self.model_id,
            'model_name': self.model_name,
            'model_version': self.model_version,
            'model_type': self.model_type,
            'status': self.status,
            'train_score': float(self.train_score) if self.train_score else None,
            'validation_score': float(self.validation_score) if self.validation_score else None,
            'test_score': float(self.test_score) if self.test_score else None,
            'deployed_at': self.deployed_at.isoformat() if self.deployed_at else None,
        }
