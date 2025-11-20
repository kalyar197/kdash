"""
Verify oscillator pattern consistency by analyzing raw database values.
Checks if consistent patterns in certain oscillators come from pre-aggregated source data.
"""

import sys
import os
from datetime import datetime, timedelta
import pandas as pd
import numpy as np

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from database.models import SessionLocal, Source, TimeseriesData
from sqlalchemy import and_

def query_raw_data(dataset_name, days=100):
    """Query raw database values for a specific dataset."""
    print(f"\n{'='*80}")
    print(f"Querying {dataset_name} (last {days} days)")
    print(f"{'='*80}")

    # Create database session
    db = SessionLocal()

    try:
        # Get source
        source = db.query(Source).filter(Source.name == dataset_name).first()
        if not source:
            print(f"[ERROR] Source '{dataset_name}' not found in database")
            return None

        print(f"Source ID: {source.source_id}")
        print(f"Display Name: {source.display_name}")
        print(f"Category: {source.category}")

        # Calculate cutoff date
        cutoff = datetime.now() - timedelta(days=days)

        # Query data
        results = db.query(TimeseriesData).filter(
            and_(
                TimeseriesData.source_id == source.source_id,
                TimeseriesData.timestamp >= cutoff
            )
        ).order_by(TimeseriesData.timestamp.desc()).limit(days).all()

        if not results:
            print(f"[ERROR] No data found for {dataset_name}")
            return None

        # Convert to DataFrame
        data = pd.DataFrame([
            {
                'timestamp': r.timestamp,
                'value': float(r.value) if r.value else None
            }
            for r in results
        ])
        data = data.sort_values('timestamp').reset_index(drop=True)

        print(f"\n[OK] Retrieved {len(data)} data points")
        print(f"Date range: {data['timestamp'].min()} to {data['timestamp'].max()}")

        return data
    finally:
        db.close()

def analyze_patterns(data, dataset_name):
    """Analyze patterns in the raw data."""
    print(f"\nPattern Analysis for {dataset_name}")
    print(f"{'-'*80}")

    # Calculate day-to-day changes
    data['pct_change'] = data['value'].pct_change() * 100
    data['abs_change'] = data['value'].diff()

    # Check for consecutive identical values (stepwise pattern)
    data['same_as_prev'] = (data['value'].diff() == 0)
    consecutive_same = data['same_as_prev'].sum()

    # Statistics
    print(f"\nValue Statistics:")
    print(f"  Mean: {data['value'].mean():.2f}")
    print(f"  Std Dev: {data['value'].std():.2f}")
    print(f"  Min: {data['value'].min():.2f}")
    print(f"  Max: {data['value'].max():.2f}")
    print(f"  Coefficient of Variation: {(data['value'].std() / data['value'].mean() * 100):.2f}%")

    print(f"\nChange Statistics:")
    print(f"  Mean % Change: {data['pct_change'].mean():.4f}%")
    print(f"  Std Dev % Change: {data['pct_change'].std():.4f}%")
    print(f"  Days with ZERO change: {consecutive_same} / {len(data)} ({consecutive_same/len(data)*100:.1f}%)")

    # Find longest streak of identical values
    streaks = []
    current_streak = 1
    for i in range(1, len(data)):
        if data.iloc[i]['value'] == data.iloc[i-1]['value']:
            current_streak += 1
        else:
            if current_streak > 1:
                streaks.append(current_streak)
            current_streak = 1

    if streaks:
        print(f"\nIdentical Value Streaks:")
        print(f"  Longest streak: {max(streaks)} consecutive days")
        print(f"  Average streak length: {np.mean(streaks):.1f} days")
        print(f"  Number of streaks: {len(streaks)}")
    else:
        print(f"\nNo identical value streaks found (data changes daily)")

    # Pattern detection
    print(f"\nPattern Detection:")

    # Check for weekly patterns (7-day cycles)
    if consecutive_same / len(data) > 0.3:
        print(f"  [!] HIGH CONSISTENCY: {consecutive_same/len(data)*100:.1f}% days unchanged")
        print(f"      -> Likely pre-aggregated (weekly average) at source")
    elif consecutive_same / len(data) > 0.1:
        print(f"  [*] MODERATE CONSISTENCY: {consecutive_same/len(data)*100:.1f}% days unchanged")
        print(f"      -> Possibly slow-changing metric")
    else:
        print(f"  [OK] DAILY VARIANCE: Only {consecutive_same/len(data)*100:.1f}% days unchanged")
        print(f"       -> True daily data")

    # Variance analysis
    cv = (data['value'].std() / data['value'].mean() * 100)
    if cv < 5:
        print(f"  [LOW VARIANCE] CV = {cv:.2f}%")
        print(f"      -> Inherently stable metric")
    elif cv < 20:
        print(f"  [MODERATE VARIANCE] CV = {cv:.2f}%")
    else:
        print(f"  [HIGH VARIANCE] CV = {cv:.2f}%")
        print(f"      -> Volatile metric")

    # Show sample data
    print(f"\nSample Data (last 20 days):")
    sample = data[['timestamp', 'value', 'pct_change']].tail(20)
    for _, row in sample.iterrows():
        date_str = row['timestamp'].strftime('%Y-%m-%d')
        pct_str = f"{row['pct_change']:+.2f}%" if not pd.isna(row['pct_change']) else "N/A"
        print(f"  {date_str}: {row['value']:>15.2f}  ({pct_str})")

    return data

def compare_datasets(datasets_data):
    """Compare multiple datasets to find differences."""
    print(f"\n{'='*80}")
    print(f"COMPARATIVE ANALYSIS")
    print(f"{'='*80}\n")

    comparison = []
    for name, data in datasets_data.items():
        if data is not None and len(data) > 0:
            data['pct_change'] = data['value'].pct_change() * 100
            data['same_as_prev'] = (data['value'].diff() == 0)

            comparison.append({
                'Dataset': name,
                'Zero Change %': f"{data['same_as_prev'].sum() / len(data) * 100:.1f}%",
                'CV %': f"{(data['value'].std() / data['value'].mean() * 100):.2f}%",
                'Std Dev %Change': f"{data['pct_change'].std():.4f}%",
                'Pattern Type': 'Pre-aggregated' if data['same_as_prev'].sum() / len(data) > 0.3 else 'Daily'
            })

    df = pd.DataFrame(comparison)
    print(df.to_string(index=False))
    print()

def main():
    """Main analysis function."""
    print("\n" + "="*80)
    print("OSCILLATOR PATTERN CONSISTENCY ANALYSIS")
    print("="*80)
    print("\nAnalyzing raw database values to identify source of consistent patterns...")

    # Datasets to analyze
    problematic_datasets = [
        'btc_largetxcount',      # Large Tx Count
        'btc_avgtx',             # Average Tx Value
        'btc_receivingaddresses' # Receiving Addresses
    ]

    comparison_datasets = [
        'btc_txcount',           # Transaction Count (COINMETRICS - for comparison)
        'btc_sendingaddresses',  # Sending Addresses (GLASSNODE - for comparison)
        'btc_newaddresses'       # New Addresses (GLASSNODE - for comparison)
    ]

    all_datasets = problematic_datasets + comparison_datasets

    # Query and analyze each dataset
    datasets_data = {}
    for dataset in all_datasets:
        data = query_raw_data(dataset, days=100)
        if data is not None:
            analyze_patterns(data, dataset)
            datasets_data[dataset] = data

    # Compare all datasets
    compare_datasets(datasets_data)

    print("\n" + "="*80)
    print("[OK] Analysis Complete")
    print("="*80 + "\n")

if __name__ == '__main__':
    main()
