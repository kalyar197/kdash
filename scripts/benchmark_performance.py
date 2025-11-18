"""
Performance Benchmark: PostgreSQL vs JSON File Loading
Compares query times for common dashboard operations.
"""

import sys
import os
import json
import time
from datetime import datetime, timedelta
from pathlib import Path
from statistics import mean, median, stdev

# Add parent directory to path for imports
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from database.models import SessionLocal, Source, TimeseriesData
from sqlalchemy import func


def benchmark_decorator(func):
    """Decorator to time function execution."""
    def wrapper(*args, **kwargs):
        start = time.time()
        result = func(*args, **kwargs)
        elapsed = time.time() - start
        return result, elapsed
    return wrapper


@benchmark_decorator
def json_load_all_data(source_name):
    """Benchmark: Load all data from JSON file."""
    json_file = f"historical_data/{source_name}.json"
    if not Path(json_file).exists():
        json_file = f"data_cache/{source_name}_cache.json"

    with open(json_file, 'r') as f:
        data = json.load(f)

    return len(data)


@benchmark_decorator
def pg_load_all_data(db, source_id):
    """Benchmark: Load all data from PostgreSQL."""
    records = db.query(
        TimeseriesData.timestamp,
        TimeseriesData.open,
        TimeseriesData.high,
        TimeseriesData.low,
        TimeseriesData.close,
        TimeseriesData.volume,
        TimeseriesData.value
    ).filter(
        TimeseriesData.source_id == source_id
    ).order_by(
        TimeseriesData.timestamp
    ).all()

    return len(records)


@benchmark_decorator
def json_load_date_range(source_name, days=90):
    """Benchmark: Load last N days from JSON file."""
    json_file = f"historical_data/{source_name}.json"
    if not Path(json_file).exists():
        json_file = f"data_cache/{source_name}_cache.json"

    with open(json_file, 'r') as f:
        data = json.load(f)

    # Filter by date (assumes timestamps in milliseconds)
    cutoff = int((datetime.now() - timedelta(days=days)).timestamp() * 1000)
    filtered = [row for row in data if row[0] >= cutoff]

    return len(filtered)


@benchmark_decorator
def pg_load_date_range(db, source_id, days=90):
    """Benchmark: Load last N days from PostgreSQL."""
    cutoff = datetime.now() - timedelta(days=days)

    records = db.query(
        TimeseriesData.timestamp,
        TimeseriesData.open,
        TimeseriesData.high,
        TimeseriesData.low,
        TimeseriesData.close,
        TimeseriesData.volume,
        TimeseriesData.value
    ).filter(
        TimeseriesData.source_id == source_id,
        TimeseriesData.timestamp >= cutoff
    ).order_by(
        TimeseriesData.timestamp
    ).all()

    return len(records)


@benchmark_decorator
def json_aggregation(source_name):
    """Benchmark: Calculate aggregations from JSON (min, max, avg)."""
    json_file = f"historical_data/{source_name}.json"
    if not Path(json_file).exists():
        json_file = f"data_cache/{source_name}_cache.json"

    with open(json_file, 'r') as f:
        data = json.load(f)

    # For simple data (2 columns), aggregate value
    # For OHLCV (6 columns), aggregate close price
    if len(data[0]) == 2:
        values = [row[1] for row in data]
    else:
        values = [row[4] for row in data]  # close price

    return {
        'min': min(values),
        'max': max(values),
        'avg': mean(values),
        'count': len(values)
    }


@benchmark_decorator
def pg_aggregation(db, source_id, data_type):
    """Benchmark: Calculate aggregations from PostgreSQL."""
    if data_type == 'ohlcv':
        result = db.query(
            func.min(TimeseriesData.close).label('min'),
            func.max(TimeseriesData.close).label('max'),
            func.avg(TimeseriesData.close).label('avg'),
            func.count(TimeseriesData.id).label('count')
        ).filter(
            TimeseriesData.source_id == source_id
        ).first()
    else:
        result = db.query(
            func.min(TimeseriesData.value).label('min'),
            func.max(TimeseriesData.value).label('max'),
            func.avg(TimeseriesData.value).label('avg'),
            func.count(TimeseriesData.id).label('count')
        ).filter(
            TimeseriesData.source_id == source_id
        ).first()

    return {
        'min': float(result.min),
        'max': float(result.max),
        'avg': float(result.avg),
        'count': result.count
    }


@benchmark_decorator
def json_multi_source_join(source_names):
    """Benchmark: Load multiple sources and find common timestamps (JSON)."""
    all_data = {}

    for source_name in source_names:
        json_file = f"historical_data/{source_name}.json"
        if not Path(json_file).exists():
            json_file = f"data_cache/{source_name}_cache.json"

        with open(json_file, 'r') as f:
            data = json.load(f)
            all_data[source_name] = {row[0]: row for row in data}

    # Find common timestamps
    common_timestamps = set(all_data[source_names[0]].keys())
    for source_name in source_names[1:]:
        common_timestamps &= set(all_data[source_name].keys())

    return len(common_timestamps)


@benchmark_decorator
def pg_multi_source_join(db, source_ids):
    """Benchmark: Load multiple sources and find common timestamps (PostgreSQL)."""
    # This would use a JOIN in real implementation
    # For benchmark, we'll do it similar to JSON approach

    all_data = {}
    for source_id in source_ids:
        records = db.query(
            TimeseriesData.timestamp,
            TimeseriesData.value,
            TimeseriesData.close
        ).filter(
            TimeseriesData.source_id == source_id
        ).all()
        all_data[source_id] = {r.timestamp: r for r in records}

    # Find common timestamps
    common_timestamps = set(all_data[source_ids[0]].keys())
    for source_id in source_ids[1:]:
        common_timestamps &= set(all_data[source_id].keys())

    return len(common_timestamps)


def run_benchmarks():
    """Run all benchmarks and display results."""
    print("="*80)
    print("PERFORMANCE BENCHMARK: PostgreSQL vs JSON")
    print("="*80)
    print(f"Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")

    db = SessionLocal()

    try:
        # Get some test sources
        sources = db.query(Source).limit(5).all()

        if not sources:
            print("[ERROR] No sources found in database")
            return

        print(f"Testing with {len(sources)} sources\n")

        results = []

        # Test 1: Load all data
        print("="*80)
        print("TEST 1: Load All Historical Data")
        print("="*80)

        for source in sources[:3]:  # Test with first 3 sources
            print(f"\nSource: {source.name}")

            # JSON benchmark
            try:
                json_count, json_time = json_load_all_data(source.name)
                print(f"  JSON:       {json_count:>8,} records in {json_time:>8.3f}s")
            except Exception as e:
                print(f"  JSON:       [ERROR] {e}")
                json_time = None

            # PostgreSQL benchmark
            pg_count, pg_time = pg_load_all_data(db, source.id)
            print(f"  PostgreSQL: {pg_count:>8,} records in {pg_time:>8.3f}s")

            if json_time:
                speedup = json_time / pg_time
                print(f"  Speedup: {speedup:.1f}x faster")
                results.append(('load_all', source.name, json_time, pg_time, speedup))

        # Test 2: Load date range (90 days)
        print("\n" + "="*80)
        print("TEST 2: Load Last 90 Days")
        print("="*80)

        for source in sources[:3]:
            print(f"\nSource: {source.name}")

            # JSON benchmark
            try:
                json_count, json_time = json_load_date_range(source.name, days=90)
                print(f"  JSON:       {json_count:>8,} records in {json_time:>8.3f}s")
            except Exception as e:
                print(f"  JSON:       [ERROR] {e}")
                json_time = None

            # PostgreSQL benchmark
            pg_count, pg_time = pg_load_date_range(db, source.id, days=90)
            print(f"  PostgreSQL: {pg_count:>8,} records in {pg_time:>8.3f}s")

            if json_time:
                speedup = json_time / pg_time
                print(f"  Speedup: {speedup:.1f}x faster")
                results.append(('load_90d', source.name, json_time, pg_time, speedup))

        # Test 3: Aggregations
        print("\n" + "="*80)
        print("TEST 3: Calculate Aggregations (min, max, avg)")
        print("="*80)

        for source in sources[:3]:
            print(f"\nSource: {source.name}")

            # JSON benchmark
            try:
                json_agg, json_time = json_aggregation(source.name)
                print(f"  JSON:       min={json_agg['min']:.2f}, max={json_agg['max']:.2f}, avg={json_agg['avg']:.2f} in {json_time:.3f}s")
            except Exception as e:
                print(f"  JSON:       [ERROR] {e}")
                json_time = None

            # PostgreSQL benchmark
            pg_agg, pg_time = pg_aggregation(db, source.id, source.data_type)
            print(f"  PostgreSQL: min={pg_agg['min']:.2f}, max={pg_agg['max']:.2f}, avg={pg_agg['avg']:.2f} in {pg_time:.3f}s")

            if json_time:
                speedup = json_time / pg_time
                print(f"  Speedup: {speedup:.1f}x faster")
                results.append(('aggregate', source.name, json_time, pg_time, speedup))

        # Test 4: Multi-source join (correlation queries)
        print("\n" + "="*80)
        print("TEST 4: Multi-Source Join (Find Common Timestamps)")
        print("="*80)

        if len(sources) >= 3:
            test_sources = sources[:3]
            source_names = [s.name for s in test_sources]
            source_ids = [s.id for s in test_sources]

            print(f"\nJoining: {', '.join(source_names)}")

            # JSON benchmark
            try:
                json_count, json_time = json_multi_source_join(source_names)
                print(f"  JSON:       {json_count:>8,} common timestamps in {json_time:>8.3f}s")
            except Exception as e:
                print(f"  JSON:       [ERROR] {e}")
                json_time = None

            # PostgreSQL benchmark
            pg_count, pg_time = pg_multi_source_join(db, source_ids)
            print(f"  PostgreSQL: {pg_count:>8,} common timestamps in {pg_time:>8.3f}s")

            if json_time:
                speedup = json_time / pg_time
                print(f"  Speedup: {speedup:.1f}x faster")
                results.append(('multi_join', 'multiple', json_time, pg_time, speedup))

        # Summary
        print("\n" + "="*80)
        print("BENCHMARK SUMMARY")
        print("="*80)

        if results:
            speedups = [r[4] for r in results]

            print(f"\nTotal tests run: {len(results)}")
            print(f"Average speedup: {mean(speedups):.1f}x")
            print(f"Median speedup:  {median(speedups):.1f}x")
            print(f"Min speedup:     {min(speedups):.1f}x")
            print(f"Max speedup:     {max(speedups):.1f}x")

            if len(speedups) > 1:
                print(f"Std deviation:   {stdev(speedups):.1f}x")

            print("\n" + "="*80)
            print("DETAILED RESULTS")
            print("="*80)
            print(f"{'Test':<15} {'Source':<30} {'JSON (s)':<10} {'PG (s)':<10} {'Speedup':<10}")
            print("-"*80)

            for test, source, json_t, pg_t, speedup in results:
                print(f"{test:<15} {source:<30} {json_t:>9.3f} {pg_t:>9.3f} {speedup:>9.1f}x")

        print("\n" + "="*80)
        print("[SUCCESS] Benchmark complete")
        print("="*80)

    finally:
        db.close()


if __name__ == '__main__':
    run_benchmarks()
