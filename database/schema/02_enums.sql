-- Custom ENUM types for type safety

-- Data type classification
CREATE TYPE data_type_enum AS ENUM (
    'ohlcv',        -- Open, High, Low, Close, Volume
    'simple',       -- Single value time series
    'calculated',   -- Derived from other datasets (RSI, MACD, etc.)
    'social',       -- Social metrics (posts, contributors)
    'onchain',      -- Blockchain metrics (addresses, tx count)
    'macro',        -- Macro economic (DXY, gold, SPX)
    'derivative',   -- Derivatives data (funding rate, basis)
    'stablecoin',   -- Stablecoin metrics
    'etf',          -- ETF data
    'defi'          -- DeFi metrics (TVL, etc.)
);

-- Plugin status
CREATE TYPE plugin_status_enum AS ENUM (
    'active',       -- Currently updating
    'inactive',     -- Temporarily disabled
    'deprecated',   -- No longer maintained
    'testing'       -- In development/testing
);

-- Market type for trading schedules
CREATE TYPE market_enum AS ENUM (
    'US',           -- US stock market hours (9:30 AM - 4:00 PM ET)
    'CRYPTO',       -- 24/7 cryptocurrency markets
    'FOREX',        -- Forex market hours
    'COMMODITIES'   -- Commodities market hours
);

-- Anomaly types
CREATE TYPE anomaly_type_enum AS ENUM (
    'outlier_4sigma',  -- 4 standard deviations from mean
    'outlier_6sigma',  -- 6 standard deviations (black swan)
    'missing_data',    -- Expected data not received
    'late_data',       -- Data received past expected time
    'corrupt_data',    -- Data failed validation
    'duplicate'        -- Duplicate timestamp detected
);

-- Audit action types
CREATE TYPE audit_action_enum AS ENUM (
    'INSERT',
    'UPDATE',
    'DELETE',
    'CORRECTION'    -- Manual data correction
);

COMMENT ON TYPE data_type_enum IS 'Classification of dataset structure and source type';
COMMENT ON TYPE plugin_status_enum IS 'Operational status of data source plugins';
COMMENT ON TYPE market_enum IS 'Trading schedule type for timestamp alignment';
COMMENT ON TYPE anomaly_type_enum IS 'Categories of data quality issues';
COMMENT ON TYPE audit_action_enum IS 'Types of modifications tracked in audit log';
