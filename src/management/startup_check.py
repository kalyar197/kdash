#!/usr/bin/env python3
"""
Startup Data Updater: Auto-update data when Flask app starts
Runs in background thread to avoid blocking server startup
"""

import json
import threading
import subprocess
from datetime import datetime, timezone, timedelta
from pathlib import Path

# Data files to check (relative to project root)
PROJECT_ROOT = Path(__file__).parent.parent.parent  # Go up from src/management/ to root
TAKER_DATA_FILE = PROJECT_ROOT / 'storage' / 'data' / 'options_pcr_cvd' / 'taker_ratio_3m.json'

# Update scripts
TAKER_UPDATE_SCRIPT = PROJECT_ROOT / 'scripts' / 'binance_taker_ratio_update.py'

# Update threshold: only update if data is older than this
UPDATE_THRESHOLD_HOURS = 6


def get_last_update_time(file_path):
    """Get timestamp of last record in data file."""
    try:
        if not file_path.exists():
            return None

        with open(file_path, 'r') as f:
            data = json.load(f)

        if not data:
            return None

        last_ts = data[-1][0]
        return datetime.fromtimestamp(last_ts / 1000, tz=timezone.utc)

    except Exception as e:
        print(f"[Startup Update] Warning: Could not read {file_path.name}: {e}")
        return None


def needs_update(file_path, threshold_hours=UPDATE_THRESHOLD_HOURS):
    """Check if data needs updating based on age."""
    last_update = get_last_update_time(file_path)

    if last_update is None:
        return True

    now = datetime.now(tz=timezone.utc)
    age = now - last_update

    return age > timedelta(hours=threshold_hours)


def run_updater(script_path, name):
    """Run updater script."""
    try:
        print(f"[Startup Update] Running {name}...")

        result = subprocess.run(
            ['python', str(script_path)],
            capture_output=True,
            text=True,
            timeout=120
        )

        if result.returncode == 0:
            print(f"[Startup Update] ✓ {name} completed")
        else:
            print(f"[Startup Update] ✗ {name} failed: {result.stderr[:200]}")

    except subprocess.TimeoutExpired:
        print(f"[Startup Update] ✗ {name} timed out (>2 min)")
    except Exception as e:
        print(f"[Startup Update] ✗ {name} error: {e}")


def update_data_background():
    """Background thread: check and update data if needed."""
    print("="*60)
    print("STARTUP DATA UPDATE CHECK")
    print("="*60)

    # Check Taker Ratio data
    if TAKER_DATA_FILE.exists():
        last_update = get_last_update_time(TAKER_DATA_FILE)
        if last_update:
            age_hours = (datetime.now(tz=timezone.utc) - last_update).total_seconds() / 3600
            print(f"[Taker Ratio] Last update: {last_update.strftime('%Y-%m-%d %H:%M')} UTC ({age_hours:.1f}h ago)")
        else:
            print(f"[Taker Ratio] Could not read last update")
    else:
        print(f"[Taker Ratio] File not found")

    # Run updates if needed
    updates_needed = []

    if needs_update(TAKER_DATA_FILE):
        updates_needed.append(('Taker Ratio', TAKER_UPDATE_SCRIPT))

    if updates_needed:
        print(f"\n[Action] {len(updates_needed)} dataset(s) need updating...")
        for name, script in updates_needed:
            run_updater(script, name)
        print(f"\n{'='*60}")
        print("STARTUP UPDATES COMPLETE")
        print(f"{'='*60}\n")
    else:
        print(f"\n[Action] All data is fresh (< {UPDATE_THRESHOLD_HOURS}h old)")
        print(f"{'='*60}\n")


def check_and_update():
    """
    Public function: Check and update data on startup (non-blocking).
    Call this from app.py on startup.
    """
    thread = threading.Thread(target=update_data_background, daemon=True)
    thread.start()
    print("[Startup Update] Background update check started (non-blocking)")
