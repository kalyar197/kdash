"""
SQLAlchemy Base Configuration
Database connection, session management, and base model class
"""

import os
from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.pool import NullPool
from typing import Generator

# ============================================================================
# DATABASE CONFIGURATION
# ============================================================================

# Load from environment variables (or config.py)
DATABASE_URL = os.getenv(
    'DATABASE_URL',
    'postgresql://postgres:password@localhost:5432/btc_dashboard'
)

# Create engine
# For TimescaleDB, we use standard PostgreSQL driver
engine = create_engine(
    DATABASE_URL,
    echo=False,  # Set to True for SQL query logging
    pool_size=10,  # Connection pool size
    max_overflow=20,  # Max overflow connections
    pool_pre_ping=True,  # Verify connections before using
    pool_recycle=3600,  # Recycle connections after 1 hour
    # Use NullPool for background tasks to avoid connection leaks
    # poolclass=NullPool,  # Uncomment for serverless/background jobs
)

# Session factory
SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine
)

# Base class for all models
Base = declarative_base()

# ============================================================================
# DATABASE SESSION HELPERS
# ============================================================================

def get_db() -> Generator[Session, None, None]:
    """
    Dependency injection for Flask/FastAPI routes

    Usage in Flask:
        @app.route('/api/data')
        def get_data():
            db = next(get_db())
            try:
                results = db.query(TimeseriesData).all()
                return jsonify(results)
            finally:
                db.close()

    Usage in FastAPI:
        @app.get('/api/data')
        def get_data(db: Session = Depends(get_db)):
            results = db.query(TimeseriesData).all()
            return results
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    """
    Initialize database tables
    WARNING: Only use in development. Use Alembic migrations in production.
    """
    Base.metadata.create_all(bind=engine)
    print("✓ Database tables created successfully")


def drop_all():
    """
    Drop all tables
    WARNING: Destructive operation. Only use in development/testing.
    """
    confirm = input("Are you sure you want to drop all tables? (yes/no): ")
    if confirm.lower() == 'yes':
        Base.metadata.drop_all(bind=engine)
        print("✓ All tables dropped")
    else:
        print("✗ Operation cancelled")


# ============================================================================
# CUSTOM TYPES FOR SQLALCHEMY
# ============================================================================

from sqlalchemy.types import TypeDecorator, String
from decimal import Decimal
import json

class PrecisionNumeric(TypeDecorator):
    """
    Custom type for high-precision numeric values
    Stores as NUMERIC(20,8) to avoid float precision issues
    """
    impl = String
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is not None:
            return str(value)
        return value

    def process_result_value(self, value, dialect):
        if value is not None:
            return Decimal(value)
        return value


# ============================================================================
# QUERY HELPERS
# ============================================================================

def bulk_upsert(session: Session, model_class, records: list, conflict_columns: list):
    """
    Perform bulk upsert (INSERT ... ON CONFLICT DO UPDATE)

    Args:
        session: SQLAlchemy session
        model_class: Model class (e.g., TimeseriesData)
        records: List of dicts with data
        conflict_columns: Columns to check for conflicts (e.g., ['source_id', 'timestamp'])

    Example:
        records = [
            {'source_id': 1, 'timestamp': datetime(2024,1,1), 'value': 100},
            {'source_id': 1, 'timestamp': datetime(2024,1,2), 'value': 105},
        ]
        bulk_upsert(db, TimeseriesData, records, ['source_id', 'timestamp'])
    """
    from sqlalchemy.dialects.postgresql import insert

    stmt = insert(model_class.__table__).values(records)

    # Build update dict (all columns except conflict columns)
    update_dict = {
        c.name: c
        for c in stmt.excluded
        if c.name not in conflict_columns
    }

    stmt = stmt.on_conflict_do_update(
        index_elements=conflict_columns,
        set_=update_dict
    )

    session.execute(stmt)
    session.commit()


# ============================================================================
# CONNECTION TESTING
# ============================================================================

def test_connection():
    """Test database connection"""
    try:
        with engine.connect() as conn:
            result = conn.execute("SELECT version();")
            version = result.fetchone()[0]
            print(f"✓ Database connected: {version}")

            # Check for TimescaleDB
            result = conn.execute("SELECT default_version FROM pg_available_extensions WHERE name = 'timescaledb';")
            timescale_version = result.fetchone()
            if timescale_version:
                print(f"✓ TimescaleDB available: {timescale_version[0]}")
            else:
                print("⚠ TimescaleDB extension not found")

            return True
    except Exception as e:
        print(f"✗ Database connection failed: {e}")
        return False


if __name__ == '__main__':
    # Test connection when run directly
    test_connection()
