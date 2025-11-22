#!/usr/bin/env python3
"""
Generate complete inventory of all plottable datasets in the system.
Scans historical_data/*.json files and reports data point counts.
"""

import json
import os
from pathlib import Path

def get_json_files():
    """Get all JSON files from historical_data directory."""
    data_dir = Path(__file__).parent.parent / 'historical_data'
    return sorted(data_dir.glob('*.json'))

def analyze_file(filepath):
    """Analyze a JSON file and return metadata."""
    try:
        with open(filepath, 'r') as f:
            data = json.load(f)

        # Skip non-data files
        filename = filepath.stem
        if filename in ['backfill_progress', 'backfill_results', 'validation_report', 'tradingview_update_log']:
            return None

        # Determine data format
        if isinstance(data, list) and len(data) > 0:
            sample = data[0]
            if isinstance(sample, list):
                if len(sample) == 2:
                    format_type = "simple"  # [timestamp, value]
                elif len(sample) == 6:
                    format_type = "ohlcv"  # [timestamp, open, high, low, close, volume]
                else:
                    format_type = f"array_{len(sample)}"
            else:
                format_type = "unknown"

            return {
                "filename": filename,
                "path": str(filepath),
                "data_points": len(data),
                "format": format_type,
                "sample": data[0] if len(data) > 0 else None,
                "date_range": {
                    "start": data[0][0] if len(data) > 0 and isinstance(data[0], list) else None,
                    "end": data[-1][0] if len(data) > 0 and isinstance(data[0], list) else None
                }
            }
        elif isinstance(data, dict):
            return {
                "filename": filename,
                "path": str(filepath),
                "data_points": "dict",
                "format": "object",
                "keys": list(data.keys())[:5]
            }
        else:
            return None

    except Exception as e:
        return {
            "filename": filepath.stem,
            "path": str(filepath),
            "error": str(e)
        }

def categorize_datasets():
    """Categorize all datasets by type."""
    categories = {
        "price_ohlcv": [],
        "oscillators": [],
        "derivatives": [],
        "on_chain": [],
        "social": [],
        "market": [],
        "etf": [],
        "macro": [],
        "stablecoin": [],
        "other": []
    }

    json_files = get_json_files()

    for filepath in json_files:
        info = analyze_file(filepath)
        if not info:
            continue

        filename = info['filename']

        # Categorize based on filename patterns
        if 'price' in filename and info.get('format') == 'ohlcv':
            categories['price_ohlcv'].append(info)
        elif any(x in filename for x in ['rsi', 'adx', 'atr', 'macd', 'sma', 'psar']):
            categories['oscillators'].append(info)
        elif any(x in filename for x in ['dvol', 'basis', 'funding']):
            categories['derivatives'].append(info)
        elif any(x in filename for x in ['sopr', 'addresses', 'txcount', 'supply', 'txfees', 'volume', 'ser', 'avgtx', 'largetxcount']):
            categories['on_chain'].append(info)
        elif any(x in filename for x in ['posts', 'contributors', 'socialdominance']):
            categories['social'].append(info)
        elif any(x in filename for x in ['total3', 'stable', 'dominance']):
            categories['market'].append(info)
        elif any(x in filename for x in ['ibit', 'gbtc']):
            categories['etf'].append(info)
        elif any(x in filename for x in ['usdt', 'usdtusd']):
            categories['stablecoin'].append(info)
        else:
            categories['other'].append(info)

    return categories

def main():
    categories = categorize_datasets()

    inventory = {
        "metadata": {
            "generated": "2025-11-14",
            "total_files": sum(len(items) for items in categories.values()),
            "total_categories": len([cat for cat, items in categories.items() if len(items) > 0])
        },
        "categories": {}
    }

    # Build inventory with stats
    for category, items in categories.items():
        if len(items) == 0:
            continue

        inventory['categories'][category] = {
            "count": len(items),
            "datasets": []
        }

        for item in items:
            dataset_info = {
                "name": item['filename'],
                "data_points": item['data_points'],
                "format": item['format']
            }

            # Add date range for time series data
            if 'date_range' in item and item['date_range']['start']:
                from datetime import datetime
                start_ts = item['date_range']['start']
                end_ts = item['date_range']['end']
                dataset_info['date_range'] = {
                    "start": datetime.fromtimestamp(start_ts / 1000).strftime('%Y-%m-%d'),
                    "end": datetime.fromtimestamp(end_ts / 1000).strftime('%Y-%m-%d')
                }

            inventory['categories'][category]['datasets'].append(dataset_info)

    # Output as formatted JSON
    print(json.dumps(inventory, indent=2))

    # Also save to file
    output_path = Path(__file__).parent.parent / 'DATASET_INVENTORY.json'
    with open(output_path, 'w') as f:
        json.dump(inventory, f, indent=2)

    print(f"\n✅ Inventory saved to: {output_path}", flush=True)

if __name__ == '__main__':
    main()
