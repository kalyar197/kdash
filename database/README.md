# PostgreSQL/TimescaleDB Database

Complete database schema and ORM models for the BTC Trading Dashboard.

## Directory Structure

```
database/
├── schema/              # SQL schema files (execute in order)
│   ├── 01_extensions.sql
│   ├── 02_enums.sql
│   ├── 03_core_tables.sql
│   ├── 04_quality_tables.sql
│   ├── 05_analytics_tables.sql
│   ├── 06_timescaledb_config.sql
│   └── 07_triggers.sql
├── models/              # SQLAlchemy ORM models
│   ├── __init__.py
│   ├── base.py          # Database connection & session
│   ├── core.py          # Source, TimeseriesData, TimeIndex
│   ├── quality.py       # ValidationRule, Anomaly, AuditLog
│   └── analytics.py     # Lineage, Feature, Forecast, Backtest
└── migrations/          # Alembic migration scripts (to be created)
```

## Installation

### 1. Install PostgreSQL + TimescaleDB

**Windows:**
```bash
# Download PostgreSQL 15: https://www.postgresql.org/download/windows/
# Download TimescaleDB: https://docs.timescale.com/install/latest/windows/

# Or use Docker:
docker run -d --name timescaledb -p 5432:5432 \
  -e POSTGRES_PASSWORD=password \
  timescale/timescaledb:latest-pg15
```

**Linux/Mac:**
```bash
# Using Docker (recommended):
docker run -d --name timescaledb -p 5432:5432 \
  -e POSTGRES_PASSWORD=password \
  -v timescaledb_data:/var/lib/postgresql/data \
  timescale/timescaledb:latest-pg15
```

### 2. Create Database

```bash
# Connect to PostgreSQL
psql -U postgres -h localhost

# Create database
CREATE DATABASE btc_dashboard;

# Connect to new database
\c btc_dashboard
```

### 3. Run Schema Files

```bash
# Execute SQL files in order:
psql -U postgres -d btc_dashboard -f database/schema/01_extensions.sql
psql -U postgres -d btc_dashboard -f database/schema/02_enums.sql
psql -U postgres -d btc_dashboard -f database/schema/03_core_tables.sql
psql -U postgres -d btc_dashboard -f database/schema/04_quality_tables.sql
psql -U postgres -d btc_dashboard -f database/schema/05_analytics_tables.sql
psql -U postgres -d btc_dashboard -f database/schema/06_timescaledb_config.sql
psql -U postgres -d btc_dashboard -f database/schema/07_triggers.sql

# Or run all at once:
cat database/schema/*.sql | psql -U postgres -d btc_dashboard
```

### 4. Install Python Dependencies

```bash
pip install sqlalchemy psycopg2-binary alembic
```

### 5. Configure Connection

**Option 1: Environment Variable**
```bash
export DATABASE_URL="postgresql://postgres:password@localhost:5432/btc_dashboard"
```

**Option 2: Update config.py**
```python
# config.py
DATABASE_URL = "postgresql://postgres:password@localhost:5432/btc_dashboard"
```

### 6. Test Connection

```bash
python database/models/base.py
```

Expected output:
```
✓ Database connected: PostgreSQL 15.x
✓ TimescaleDB available: 2.x
```

## Usage

### Basic Query Examples

```python
from database.models import get_db, Source, TimeseriesData
from datetime import datetime, timedelta

# Get database session
db = next(get_db())

# Query all active sources
sources = db.query(Source).filter(Source.status == 'active').all()
for source in sources:
    print(f"{source.name}: {source.data_type}")

# Query timeseries data for last 30 days
thirty_days_ago = datetime.utcnow() - timedelta(days=30)
data = db.query(TimeseriesData).filter(
    TimeseriesData.source_id == 1,
    TimeseriesData.timestamp >= thirty_days_ago
).order_by(TimeseriesData.timestamp.desc()).all()

# Convert to JSON
json_data = [row.to_dict() for row in data]

# Close session
db.close()
```

### Bulk Insert with Upsert

```python
from database.models.base import bulk_upsert
from database.models import TimeseriesData

records = [
    {
        'source_id': 1,
        'timestamp': datetime(2024, 1, 1),
        'close': 42000.50,
        'value': None,
    },
    {
        'source_id': 1,
        'timestamp': datetime(2024, 1, 2),
        'close': 42500.75,
        'value': None,
    },
]

bulk_upsert(db, TimeseriesData, records, ['source_id', 'timestamp'])
```

### Query with Joins

```python
from sqlalchemy import desc

# Get latest data point for each source with source metadata
results = db.query(
    Source.name,
    Source.display_name,
    TimeseriesData.timestamp,
    TimeseriesData.value,
    TimeseriesData.quality_score
).join(
    TimeseriesData,
    Source.source_id == TimeseriesData.source_id
).order_by(
    Source.name,
    TimeseriesData.timestamp.desc()
).distinct(Source.name).all()

for name, display, timestamp, value, quality in results:
    print(f"{display}: {value} (quality: {quality}%)")
```

## Schema Overview

### Core Tables

| Table | Purpose | Key Columns |
|-------|---------|-------------|
| `sources` | Data plugin registry | source_id, name, data_type, status |
| `timeseries_data` | Unified time-series storage (hypertable) | source_id, timestamp, value/OHLCV |
| `time_index` | Common time grid for alignment | timestamp, date_only, is_trading_day |
| `market_calendar` | Market holidays/early closes | date, market, is_holiday |

### Quality Tables

| Table | Purpose |
|-------|---------|
| `validation_rules` | Extensible validation rules |
| `anomalies` | Automated outlier detection |
| `audit_log` | Immutable change history |
| `timeseries_archive` | Soft-deleted data recovery |

### Analytics Tables

| Table | Purpose |
|-------|---------|
| `lineage` | Data dependency tracking |
| `features` | Pre-computed ML features |
| `forecasts` | Model predictions & accuracy |
| `backtest_results` | Strategy performance |
| `ml_models` | Model registry |

## Key Features

### 1. TimescaleDB Hypertable

`timeseries_data` is automatically partitioned by month:

```sql
-- Check chunks
SELECT * FROM chunk_stats;

-- Manually compress chunk
SELECT compress_chunk('_timescaledb_internal._hyper_1_1_chunk');
```

### 2. Continuous Aggregates

Pre-computed views that auto-refresh:

```sql
-- Query daily OHLCV (fast)
SELECT * FROM daily_ohlcv WHERE source_id = 1 AND day > '2024-01-01';

-- Query hourly aggregates
SELECT * FROM hourly_values WHERE source_id = 2 AND hour > NOW() - INTERVAL '7 days';

-- Manually refresh all
SELECT refresh_all_aggregates();
```

### 3. Automatic Quality Scoring

Every insert triggers quality score calculation (0-100):
- Completeness: -30 points if required fields missing
- Timeliness: -20 points if data late
- Consistency: -25 points if >50% change from previous
- Validation: -10 points per rule violation

### 4. Anomaly Detection

Automatic z-score calculation on insert:
- |z| > 4: Flagged as anomaly
- |z| > 6: Flagged as black swan event
- Inserted into `anomalies` table for review

### 5. Audit Trail

All modifications logged to `audit_log`:
- Old value (JSON)
- New value (JSON)
- Changed fields (array)
- Who, when, why

## Performance Optimization

### Compression

```sql
-- View compression stats
SELECT * FROM chunk_compression_stats();

-- Expected: 6-10x storage reduction
```

### Indexes

All critical query patterns indexed:
- `(source_id, timestamp DESC)` for time-range queries
- `(quality_score)` for filtering low-quality data
- `(is_anomaly)` for anomaly analysis

### Query Performance Monitoring

```sql
-- Find slow queries
SELECT query, mean_exec_time, calls
FROM pg_stat_statements
WHERE mean_exec_time > 500
ORDER BY mean_exec_time DESC;
```

## Migration from JSON Files

See `scripts/migrate_json_to_postgres.py` (to be created).

Basic flow:
1. Register all sources in `sources` table
2. Load JSON files from `historical_data/`
3. Batch insert with upsert to `timeseries_data`
4. Refresh continuous aggregates
5. Compress old chunks

## Backup & Restore

```bash
# Backup
pg_dump -U postgres -d btc_dashboard -F c -f backup.dump

# Restore
pg_restore -U postgres -d btc_dashboard backup.dump

# Backup to S3 (automated)
# See Phase 8 implementation
```

## Next Steps

1. ✓ Schema created (Phases 1-2)
2. ✓ ORM models created (Phase 1.2)
3. ⏳ Alembic migrations setup (Phase 1.3)
4. ⏳ JSON → PostgreSQL migration script (Phase 5)
5. ⏳ Update Flask API routes (Phase 6)
6. ⏳ Add GraphQL layer (Phase 7)
7. ⏳ Setup monitoring (Phase 8)

## Troubleshooting

### Connection Refused
```bash
# Check if PostgreSQL running
pg_isready -h localhost -p 5432

# Check if TimescaleDB loaded
psql -d btc_dashboard -c "SELECT default_version FROM pg_available_extensions WHERE name = 'timescaledb';"
```

### Hypertable Conversion Failed
```sql
-- Check if data exists
SELECT COUNT(*) FROM timeseries_data;

-- If data exists, use migrate_data => TRUE
SELECT create_hypertable('timeseries_data', 'timestamp', migrate_data => TRUE);
```

### Trigger Not Firing
```sql
-- List all triggers
SELECT tgname, tgenabled FROM pg_trigger WHERE tgrelid = 'timeseries_data'::regclass;

-- Re-create trigger if needed
DROP TRIGGER IF EXISTS trg_calculate_quality_score ON timeseries_data;
CREATE TRIGGER trg_calculate_quality_score ...
```

## References

- [TimescaleDB Documentation](https://docs.timescale.com/)
- [SQLAlchemy ORM Tutorial](https://docs.sqlalchemy.org/en/14/orm/tutorial.html)
- [PostgreSQL Performance Tuning](https://wiki.postgresql.org/wiki/Performance_Optimization)
