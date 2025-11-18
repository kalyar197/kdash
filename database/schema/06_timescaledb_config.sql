-- TimescaleDB-Specific Configuration
-- Convert tables to hypertables, add compression, set up retention policies

-- IMPORTANT: Run this AFTER 03_core_tables.sql has created the timeseries_data table
-- IMPORTANT: Ensure no data exists in timeseries_data before converting to hypertable

-- ============================================================================
-- HYPERTABLE CONVERSION
-- ============================================================================

-- Convert timeseries_data to hypertable (automatic partitioning by time)
SELECT create_hypertable(
    'timeseries_data',
    'timestamp',
    chunk_time_interval => INTERVAL '1 month',
    if_not_exists => TRUE,
    migrate_data => TRUE  -- Set to FALSE if table has data (manual migration needed)
);

COMMENT ON TABLE timeseries_data IS 'TimescaleDB hypertable with automatic monthly partitioning';


-- ============================================================================
-- COMPRESSION POLICIES (DISABLED - overkill for our scale)
-- ============================================================================

-- COMPRESSION REMOVED PER USER REQUEST
-- Reason: Overkill for ~50K records, blocks schema changes, adds complexity
-- Can re-enable later if dataset grows to millions of records

-- Enable compression for old data (chunks > 7 days old)
-- ALTER TABLE timeseries_data SET (
--     timescaledb.compress,
--     timescaledb.compress_segmentby = 'source_id',  -- Segment by source for efficient queries
--     timescaledb.compress_orderby = 'timestamp DESC' -- Order within segments
-- );

-- Add compression policy: compress chunks older than 7 days
-- SELECT add_compression_policy(
--     'timeseries_data',
--     INTERVAL '7 days',
--     if_not_exists => TRUE
-- );

-- Manually compress existing chunks (one-time operation after migration)
-- SELECT compress_chunk(i) FROM show_chunks('timeseries_data') i;

-- COMMENT ON TABLE timeseries_data IS 'Compression enabled: 7 days+ old chunks compressed automatically';


-- ============================================================================
-- RETENTION POLICIES (Auto-delete old data)
-- ============================================================================

-- Keep raw 1-minute BTC data for 2 years (aggressive retention)
-- NOTE: Only add this after continuous aggregates are set up to preserve daily/hourly data
-- SELECT add_retention_policy(
--     'timeseries_data',
--     INTERVAL '2 years',
--     if_not_exists => TRUE
-- );

-- For now, comment out retention policy until aggregates are confirmed working


-- ============================================================================
-- CONTINUOUS AGGREGATES (Pre-computed Views)
-- ============================================================================

-- Daily OHLCV aggregate from potentially higher-frequency data
CREATE MATERIALIZED VIEW daily_ohlcv
WITH (timescaledb.continuous) AS
SELECT
    source_id,
    time_bucket('1 day', timestamp) AS day,
    FIRST(open, timestamp) AS open,
    MAX(high) AS high,
    MIN(low) AS low,
    LAST(close, timestamp) AS close,
    SUM(volume) AS volume,
    COUNT(*) AS data_points
FROM timeseries_data
WHERE open IS NOT NULL  -- Only OHLCV data
GROUP BY source_id, day
WITH NO DATA;  -- Build incrementally

-- Refresh policy: Update last 7 days every 10 minutes
SELECT add_continuous_aggregate_policy(
    'daily_ohlcv',
    start_offset => INTERVAL '7 days',
    end_offset => INTERVAL '1 hour',  -- Don't aggregate most recent hour (still being filled)
    schedule_interval => INTERVAL '10 minutes',
    if_not_exists => TRUE
);

COMMENT ON MATERIALIZED VIEW daily_ohlcv IS 'Daily OHLCV candles, auto-refreshed every 10 minutes';


-- Hourly simple value aggregate
CREATE MATERIALIZED VIEW hourly_values
WITH (timescaledb.continuous) AS
SELECT
    source_id,
    time_bucket('1 hour', timestamp) AS hour,
    AVG(value) AS avg_value,
    MIN(value) AS min_value,
    MAX(value) AS max_value,
    LAST(value, timestamp) AS last_value,
    COUNT(*) AS data_points,
    STDDEV(value) AS volatility
FROM timeseries_data
WHERE value IS NOT NULL  -- Only simple data
GROUP BY source_id, hour
WITH NO DATA;

SELECT add_continuous_aggregate_policy(
    'hourly_values',
    start_offset => INTERVAL '3 days',
    end_offset => INTERVAL '1 hour',
    schedule_interval => INTERVAL '1 hour',
    if_not_exists => TRUE
);

COMMENT ON MATERIALIZED VIEW hourly_values IS 'Hourly aggregates for simple value data (oscillators, metrics)';


-- Weekly statistics for dashboard overview
CREATE MATERIALIZED VIEW weekly_stats
WITH (timescaledb.continuous) AS
SELECT
    source_id,
    time_bucket('1 week', timestamp) AS week,

    -- OHLCV stats
    FIRST(open, timestamp) AS week_open,
    MAX(high) AS week_high,
    MIN(low) AS week_low,
    LAST(close, timestamp) AS week_close,
    SUM(volume) AS week_volume,

    -- Simple value stats
    AVG(value) AS avg_value,
    STDDEV(value) AS volatility,

    -- Data quality
    AVG(quality_score) AS avg_quality,
    COUNT(*) FILTER (WHERE is_anomaly = TRUE) AS anomaly_count,
    COUNT(*) AS total_records

FROM timeseries_data
GROUP BY source_id, week
WITH NO DATA;

SELECT add_continuous_aggregate_policy(
    'weekly_stats',
    start_offset => INTERVAL '4 weeks',
    end_offset => INTERVAL '1 day',
    schedule_interval => INTERVAL '1 day',
    if_not_exists => TRUE
);

COMMENT ON MATERIALIZED VIEW weekly_stats IS 'Weekly summary statistics for high-level dashboard views';


-- ============================================================================
-- OPTIMIZED INDEXES FOR HYPERTABLE
-- ============================================================================

-- Drop regular indexes (already created in 03_core_tables.sql)
-- They will be recreated automatically for each chunk by TimescaleDB

-- Add specialized indexes for compressed hypertables
CREATE INDEX IF NOT EXISTS idx_timeseries_source_quality
    ON timeseries_data (source_id, quality_score, timestamp DESC)
    WHERE quality_score < 80;

CREATE INDEX IF NOT EXISTS idx_timeseries_recent
    ON timeseries_data (timestamp DESC)
    WHERE timestamp > NOW() - INTERVAL '7 days';  -- Frequently accessed recent data


-- ============================================================================
-- HELPER VIEWS
-- ============================================================================

-- View for latest data point per source (fast dashboard refresh)
CREATE VIEW latest_values AS
SELECT DISTINCT ON (source_id)
    source_id,
    timestamp,
    COALESCE(close, value) AS latest_value,
    quality_score,
    NOW() - timestamp AS data_age
FROM timeseries_data
ORDER BY source_id, timestamp DESC;

COMMENT ON VIEW latest_values IS 'Most recent data point for each source (fast lookup)';


-- View for data quality overview
CREATE VIEW quality_overview AS
SELECT
    s.source_id,
    s.name,
    s.category,
    COUNT(*) AS total_records,
    COUNT(*) FILTER (WHERE td.is_anomaly = TRUE) AS anomaly_count,
    AVG(td.quality_score) AS avg_quality_score,
    MIN(td.quality_score) AS min_quality_score,
    MAX(td.timestamp) AS last_update,
    NOW() - MAX(td.timestamp) AS staleness
FROM sources s
LEFT JOIN timeseries_data td USING (source_id)
WHERE s.status = 'active'
GROUP BY s.source_id, s.name, s.category;

COMMENT ON VIEW quality_overview IS 'Real-time data quality metrics per active source';


-- ============================================================================
-- CHUNK MANAGEMENT FUNCTIONS
-- ============================================================================

-- Function to show chunk sizes (DISABLED - compression removed)
-- CREATE OR REPLACE FUNCTION chunk_compression_stats()
-- RETURNS TABLE (
--     chunk_name TEXT,
--     range_start TIMESTAMPTZ,
--     range_end TIMESTAMPTZ,
--     before_compression_bytes BIGINT,
--     after_compression_bytes BIGINT,
--     compression_ratio NUMERIC
-- ) AS $$
-- BEGIN
--     RETURN QUERY
--     SELECT
--         ch.chunk_name::TEXT,
--         ch.range_start,
--         ch.range_end,
--         ch.before_compression_total_bytes,
--         ch.after_compression_total_bytes,
--         ROUND(
--             ch.before_compression_total_bytes::NUMERIC /
--             NULLIF(ch.after_compression_total_bytes, 0),
--             2
--         ) AS compression_ratio
--     FROM timescaledb_information.chunks ch
--     WHERE ch.hypertable_name = 'timeseries_data'
--       AND ch.is_compressed = TRUE
--     ORDER BY ch.range_start DESC;
-- END;
-- $$ LANGUAGE plpgsql;

-- COMMENT ON FUNCTION chunk_compression_stats IS 'Monitor compression effectiveness across chunks';


-- Function to manually refresh all continuous aggregates
CREATE OR REPLACE FUNCTION refresh_all_aggregates()
RETURNS VOID AS $$
BEGIN
    CALL refresh_continuous_aggregate('daily_ohlcv', NULL, NULL);
    CALL refresh_continuous_aggregate('hourly_values', NULL, NULL);
    CALL refresh_continuous_aggregate('weekly_stats', NULL, NULL);

    -- Refresh materialized views
    REFRESH MATERIALIZED VIEW CONCURRENTLY data_freshness;

    RAISE NOTICE 'All continuous aggregates and materialized views refreshed';
END;
$$ LANGUAGE plpgsql;

COMMENT ON FUNCTION refresh_all_aggregates IS 'Manually refresh all continuous aggregates and materialized views';


-- ============================================================================
-- PERFORMANCE MONITORING
-- ============================================================================

-- View to monitor chunk statistics (DISABLED - compression removed)
-- CREATE VIEW chunk_stats AS
-- SELECT
--     hypertable_name,
--     chunk_name,
--     range_start,
--     range_end,
--     is_compressed,
--     CASE WHEN is_compressed THEN
--         pg_size_pretty(after_compression_total_bytes)
--     ELSE
--         pg_size_pretty(before_compression_total_bytes)
--     END AS chunk_size,
--     CASE WHEN is_compressed THEN
--         ROUND(before_compression_total_bytes::NUMERIC / NULLIF(after_compression_total_bytes, 0), 2)
--     END AS compression_ratio
-- FROM timescaledb_information.chunks
-- WHERE hypertable_name = 'timeseries_data'
-- ORDER BY range_start DESC;

-- COMMENT ON VIEW chunk_stats IS 'Monitor chunk sizes and compression ratios';


-- View for continuous aggregate refresh status
CREATE VIEW aggregate_refresh_status AS
SELECT
    view_name,
    completed_threshold,
    invalidation_threshold,
    NOW() - completed_threshold AS last_refresh_age,
    pg_size_pretty(total_bytes) AS view_size
FROM timescaledb_information.continuous_aggregates ca
JOIN timescaledb_information.hypertables h ON ca.materialization_hypertable_name = h.hypertable_name
ORDER BY view_name;

COMMENT ON VIEW aggregate_refresh_status IS 'Monitor continuous aggregate refresh status';


-- ============================================================================
-- INITIAL DATA LOAD (Run after migration)
-- ============================================================================

-- After migrating JSON data to timeseries_data, manually refresh aggregates:
-- SELECT refresh_all_aggregates();

-- Manually compress all existing chunks:
-- SELECT compress_chunk(i, if_not_compressed => TRUE)
-- FROM show_chunks('timeseries_data') i;

COMMENT ON SCHEMA public IS 'TimescaleDB hypertable configuration complete - ready for data migration';
