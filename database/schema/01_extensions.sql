-- Enable required PostgreSQL extensions
-- Run this first before any other schema files

-- TimescaleDB for time-series optimization
CREATE EXTENSION IF NOT EXISTS timescaledb;

-- Query performance tracking
CREATE EXTENSION IF NOT EXISTS pg_stat_statements;

-- Advanced GiST indexing (for time ranges)
CREATE EXTENSION IF NOT EXISTS btree_gist;

-- JSON schema validation (optional but useful)
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- Comments
COMMENT ON EXTENSION timescaledb IS 'Time-series database capabilities with automatic partitioning and compression';
COMMENT ON EXTENSION pg_stat_statements IS 'Track query execution statistics for performance monitoring';
COMMENT ON EXTENSION btree_gist IS 'Support for exclusion constraints and advanced time range indexing';
