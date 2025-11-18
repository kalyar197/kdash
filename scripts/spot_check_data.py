"""
Spot-check data values to ensure no corruption occurred during migration attempts.
"""

import json

def check_file(filepath, data_type, validators):
    """Check a JSON file and validate its data."""
    print(f"\nChecking {filepath}...")
    try:
        with open(filepath, 'r') as f:
            data = json.load(f)

        if len(data) == 0:
            print(f"  WARNING: File is empty")
            return False

        # Check last record
        last_record = data[-1]

        if data_type == "ohlcv":
            ts, o, h, l, c, v = last_record
            print(f"  Last record: timestamp={ts}, close=${c:,.2f}")

            # Validate OHLCV relationships
            if not (h >= c and h >= o and h >= l):
                print(f"  ERROR: High ({h}) should be >= all other values")
                return False
            if not (l <= c and l <= o and l <= h):
                print(f"  ERROR: Low ({l}) should be <= all other values")
                return False
            if c <= 0:
                print(f"  ERROR: Close price ({c}) should be > 0")
                return False
            if v < 0:
                print(f"  ERROR: Volume ({v}) should be >= 0")
                return False

            # Custom validators
            for validator_name, validator_func in validators.items():
                if not validator_func(c):
                    print(f"  ERROR: {validator_name} failed for value {c}")
                    return False

            print(f"  [OK] OHLCV relationships valid, close price in expected range")
            return True

        elif data_type == "simple":
            ts, value = last_record
            print(f"  Last record: timestamp={ts}, value={value}")

            # Custom validators
            for validator_name, validator_func in validators.items():
                if not validator_func(value):
                    print(f"  ERROR: {validator_name} failed for value {value}")
                    return False

            print(f"  [OK] Value in expected range")
            return True

        else:
            print(f"  [OK] Unknown data type, skipping validation")
            return True

    except Exception as e:
        print(f"  ERROR: {e}")
        return False

def main():
    print("=" * 80)
    print("DATA VALUE SPOT CHECK")
    print("=" * 80)

    checks = [
        ("historical_data/btc_price.json", "ohlcv", {
            "BTC price $10k-$150k": lambda x: 10000 < x < 150000
        }),
        ("historical_data/rsi_btc.json", "simple", {
            "RSI 0-100": lambda x: 0 <= x <= 100
        }),
        ("historical_data/adx_btc.json", "simple", {
            "ADX 0-100": lambda x: 0 <= x <= 100
        }),
        ("historical_data/atr_btc.json", "simple", {
            "ATR > 0": lambda x: x > 0
        }),
        ("historical_data/funding_rate_btc.json", "simple", {
            "Funding rate -1% to +1%": lambda x: -0.01 < x < 0.01
        }),
        ("historical_data/gold_price.json", "ohlcv", {
            "Gold $1000-$5000": lambda x: 1000 < x < 5000
        }),
        ("historical_data/btc_dominance.json", "simple", {
            "BTC.D 30%-80%": lambda x: 30 < x < 80
        }),
        ("historical_data/dvol_btc.json", "simple", {
            "DVOL 20-200": lambda x: 20 < x < 200
        }),
    ]

    passed = 0
    failed = 0

    for filepath, data_type, validators in checks:
        if check_file(filepath, data_type, validators):
            passed += 1
        else:
            failed += 1

    print("\n" + "=" * 80)
    print("RESULTS")
    print("=" * 80)
    print(f"Passed: {passed}/{len(checks)}")
    print(f"Failed: {failed}/{len(checks)}")

    if failed == 0:
        print("\n[SUCCESS] All spot checks passed - no data corruption detected!")
        return True
    else:
        print(f"\n[FAILED] {failed} spot checks failed")
        return False

if __name__ == "__main__":
    success = main()
    exit(0 if success else 1)
