-- Core tables for the BTC Trading Dashboard
-- These form the foundation of the data architecture

-- ============================================================================
-- SOURCES TABLE (Data Plugin Registry)
-- ============================================================================
CREATE TABLE sources (
    source_id SERIAL PRIMARY KEY,
    name VARCHAR(100) UNIQUE NOT NULL,
    display_name VARCHAR(200) NOT NULL,
    category VARCHAR(50) NOT NULL,
    data_type data_type_enum NOT NULL,

    -- API Configuration
    api_endpoint TEXT,
    api_provider VARCHAR(50), -- 'coinapi', 'yahoo', 'tradingview', etc.
    requires_auth BOOLEAN DEFAULT FALSE,

    -- Update Configuration
    update_frequency INTERVAL NOT NULL DEFAULT INTERVAL '1 day',
    last_successful_update TIMESTAMPTZ,
    next_scheduled_update TIMESTAMPTZ,

    -- Plugin Status
    status plugin_status_enum DEFAULT 'active',
    market_type market_enum DEFAULT 'CRYPTO',

    -- Metadata (flexible JSONB for plugin-specific config)
    metadata JSONB DEFAULT '{}',

    -- Audit fields
    created_at TIMESTAMPTZ DEFAULT NOW() NOT NULL,
    updated_at TIMESTAMPTZ DEFAULT NOW() NOT NULL,
    created_by VARCHAR(100) DEFAULT 'system',

    -- Constraints
    CONSTRAINT chk_update_frequency CHECK (update_frequency > INTERVAL '0'),
    CONSTRAINT chk_name_format CHECK (name ~ '^[a-z0-9_]+$') -- Lowercase, numbers, underscores only
);

CREATE INDEX idx_sources_status ON sources(status) WHERE status = 'active';
CREATE INDEX idx_sources_category ON sources(category);
CREATE INDEX idx_sources_data_type ON sources(data_type);
CREATE INDEX idx_sources_next_update ON sources(next_scheduled_update) WHERE status = 'active';

COMMENT ON TABLE sources IS 'Registry of all data source plugins (analogous to data/*.py modules)';
COMMENT ON COLUMN sources.metadata IS 'Plugin-specific configuration stored as JSON (API keys, parameters, etc.)';
COMMENT ON COLUMN sources.market_type IS 'Determines trading schedule for timestamp alignment';


-- ============================================================================
-- TIME INDEX TABLE (Common Time Grid)
-- ============================================================================
CREATE TABLE time_index (
    timestamp TIMESTAMPTZ PRIMARY KEY,
    date_only DATE NOT NULL,
    day_of_week INT NOT NULL, -- 0 = Monday, 6 = Sunday
    is_weekend BOOLEAN GENERATED ALWAYS AS (day_of_week IN (5, 6)) STORED,
    is_trading_day_us BOOLEAN DEFAULT TRUE,
    is_trading_day_crypto BOOLEAN DEFAULT TRUE, -- Always true (24/7)
    market VARCHAR(20) DEFAULT 'US',

    -- For future expansion (holidays, early closes)
    notes TEXT
);

CREATE INDEX idx_time_index_date ON time_index(date_only);
CREATE INDEX idx_time_index_trading_us ON time_index(timestamp) WHERE is_trading_day_us = TRUE;
CREATE INDEX idx_time_index_weekend ON time_index(timestamp) WHERE is_weekend = TRUE;

COMMENT ON TABLE time_index IS 'Pre-generated time grid for timestamp alignment across all datasets';
COMMENT ON COLUMN time_index.is_trading_day_us IS 'FALSE on US market holidays (NYSE/NASDAQ calendar)';


-- ============================================================================
-- MARKET CALENDAR TABLE (Holidays, Early Closes)
-- ============================================================================
CREATE TABLE market_calendar (
    calendar_id SERIAL PRIMARY KEY,
    date DATE NOT NULL,
    market market_enum NOT NULL,
    is_holiday BOOLEAN DEFAULT FALSE,
    holiday_name VARCHAR(100),
    open_time TIMETZ, -- NULL if closed
    close_time TIMETZ,
    is_early_close BOOLEAN DEFAULT FALSE,

    UNIQUE(date, market)
);

CREATE INDEX idx_market_calendar_date ON market_calendar(date);
CREATE INDEX idx_market_calendar_holidays ON market_calendar(date) WHERE is_holiday = TRUE;

COMMENT ON TABLE market_calendar IS 'Market-specific trading schedule (holidays, early closes)';
COMMENT ON COLUMN market_calendar.open_time IS 'Market opening time with timezone (e.g., 09:30:00-05 for US Eastern)';


-- ============================================================================
-- TIMESERIES DATA TABLE (Unified Storage - Will become Hypertable)
-- ============================================================================
CREATE TABLE timeseries_data (
    source_id INT NOT NULL REFERENCES sources(source_id) ON DELETE CASCADE,
    timestamp TIMESTAMPTZ(3) NOT NULL, -- Millisecond precision
    date_only DATE GENERATED ALWAYS AS (timestamp::DATE) STORED,

    -- OHLCV columns (NULL for simple/calculated data)
    open NUMERIC(20,8),
    high NUMERIC(20,8),
    low NUMERIC(20,8),
    close NUMERIC(20,8),
    volume NUMERIC(30,8),

    -- Simple value column (NULL for OHLCV data)
    value NUMERIC(20,8),

    -- Data quality metadata
    quality_score SMALLINT DEFAULT 100,
    is_anomaly BOOLEAN DEFAULT FALSE,
    is_validated BOOLEAN DEFAULT TRUE,

    -- Audit fields
    created_at TIMESTAMPTZ DEFAULT NOW() NOT NULL,
    updated_at TIMESTAMPTZ DEFAULT NOW() NOT NULL,
    ingestion_timestamp TIMESTAMPTZ DEFAULT NOW() NOT NULL,

    PRIMARY KEY (source_id, timestamp),

    -- Data integrity constraints
    CONSTRAINT chk_quality_score CHECK (quality_score BETWEEN 0 AND 100),
    CONSTRAINT chk_ohlcv_consistency CHECK (
        (open IS NULL AND high IS NULL AND low IS NULL AND close IS NULL AND volume IS NULL) OR
        (open IS NOT NULL AND high IS NOT NULL AND low IS NOT NULL AND close IS NOT NULL)
    ),
    CONSTRAINT chk_high_low CHECK (high >= low),
    CONSTRAINT chk_prices_positive CHECK (
        (open IS NULL OR open > 0) AND
        (high IS NULL OR high > 0) AND
        (low IS NULL OR low > 0) AND
        (close IS NULL OR close > 0)
    ),
    CONSTRAINT chk_volume_non_negative CHECK (volume IS NULL OR volume >= 0),
    CONSTRAINT chk_one_value_type CHECK (
        (value IS NOT NULL AND close IS NULL) OR
        (value IS NULL AND close IS NOT NULL) OR
        (value IS NULL AND close IS NULL)
    )
);

-- Indexes (before hypertable conversion)
CREATE INDEX idx_timeseries_source_time ON timeseries_data (source_id, timestamp DESC);
CREATE INDEX idx_timeseries_date ON timeseries_data (date_only);
CREATE INDEX idx_timeseries_quality ON timeseries_data (quality_score) WHERE quality_score < 80;
CREATE INDEX idx_timeseries_anomalies ON timeseries_data (source_id, timestamp) WHERE is_anomaly = TRUE;

COMMENT ON TABLE timeseries_data IS 'Unified time-series storage for all datasets (OHLCV and simple formats)';
COMMENT ON COLUMN timeseries_data.timestamp IS 'Unix timestamp in milliseconds, normalized to UTC';
COMMENT ON COLUMN timeseries_data.value IS 'For simple [timestamp, value] format (oscillators, dominance, etc.)';
COMMENT ON COLUMN timeseries_data.quality_score IS '0-100 score based on completeness, timeliness, consistency';
COMMENT ON COLUMN timeseries_data.ingestion_timestamp IS 'When data was inserted into database (for lag tracking)';


-- ============================================================================
-- HELPER FUNCTIONS
-- ============================================================================

-- Function to standardize timestamp to daily UTC boundary (00:00:00)
CREATE OR REPLACE FUNCTION normalize_to_daily_utc(ts TIMESTAMPTZ)
RETURNS TIMESTAMPTZ AS $$
BEGIN
    RETURN DATE_TRUNC('day', ts AT TIME ZONE 'UTC') AT TIME ZONE 'UTC';
END;
$$ LANGUAGE plpgsql IMMUTABLE;

COMMENT ON FUNCTION normalize_to_daily_utc IS 'Normalize any timestamp to midnight UTC (00:00:00)';


-- Function to detect data type from source_id
CREATE OR REPLACE FUNCTION get_data_type(p_source_id INT)
RETURNS data_type_enum AS $$
DECLARE
    v_data_type data_type_enum;
BEGIN
    SELECT data_type INTO v_data_type
    FROM sources
    WHERE source_id = p_source_id;

    RETURN v_data_type;
END;
$$ LANGUAGE plpgsql STABLE;

COMMENT ON FUNCTION get_data_type IS 'Retrieve data_type for a given source_id';


-- ============================================================================
-- SAMPLE DATA FOR TESTING
-- ============================================================================

-- Insert common time index entries (2020-2026, daily)
INSERT INTO time_index (timestamp, date_only, day_of_week, market)
SELECT
    ts,
    ts::DATE,
    EXTRACT(DOW FROM ts)::INT,
    'US'
FROM generate_series(
    '2020-01-01 00:00:00+00'::TIMESTAMPTZ,
    '2026-12-31 00:00:00+00'::TIMESTAMPTZ,
    INTERVAL '1 day'
) AS ts
ON CONFLICT (timestamp) DO NOTHING;

COMMENT ON TABLE time_index IS 'Pre-populated with daily timestamps 2020-2026 for consistent alignment';
