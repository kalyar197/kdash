# Three-System Oscillator Dashboard - Implementation Plan

**Status**: APPROVED - Ready for next session implementation
**Priority**: NEW PHASE 1 (Top Priority)
**Date Created**: 2025-11-16

---

## Overview

Implement three complementary oscillator visualization systems to replace weighted aggregation with granular, transparent analysis.

**User Philosophy**:
- No aggregation, no weights - show every metric separately
- Research mindset, not black-box trading
- Understand components before acting
- "Build 21 Ferrari engines and show each RPM gauge, don't mash into one average score"

---

## System Specifications

### System 1: Price-Anchored Oscillators (11 datasets)

**Purpose**: Identify equilibrium relationships and correlation breakdowns

**Method**: Regress indicators against BTC price level
**Formula**: `indicator ~ α*BTC_price + β` → z-score of residuals

**Datasets**:
1. DXY (inverse correlation)
2. Gold (positive correlation)
3. SPX (risk-on proxy)
4. ETH (beta to BTC)
5. BTC.D (dominance)
6. USDT.D (fear gauge)
7. TOTAL3 (altcoin cap)
8. STABLE.C.D (stablecoin dominance)
9. IBIT (ETF flow)
10. GBTC (ETF flow)
11. USDTUSD_PM (Tether premium stress)

**Visualization**: One oscillator chart per dataset, vertically stacked, synchronized zoom

---

### System 2: Velocity-Anchored Oscillators (22 datasets)

**Purpose**: Capture momentum/velocity shifts and acceleration patterns

**Method**: Regress indicators against BTC % change (velocity)
**Formula**: `indicator_change ~ α*BTC_pct_change + β` → z-score of residuals

**Datasets**:

**Derivatives (3)**:
- Funding Rate, Basis Spread, DVOL Index

**Volume & Participation (2)**:
- volume_btc, volume_eth

**Whale Activity (2)**:
- btc_largetxcount, btc_avgtx

**Social Velocity (4)**:
- btc_socialdominance, btc_postscreated, btc_contributorsactive, btc_contributorscreated

**On-Chain Flow Velocity (6)**:
- btc_sendingaddresses, btc_receivingaddresses, btc_newaddresses
- btc_txcount, usdt_tfsps, btc_meantxfees

**Supply Dynamics (5)**:
- btc_activesupply1y, btc_active1y, btc_splyadrbal1
- btc_addressessupply1in10k, btc_ser

**Visualization**: One oscillator chart per dataset, grouped by category, vertically stacked

---

### System 3: Tension² Pairs (21 pairs, 6 categories)

**Purpose**: Contrarian opportunity detection via information asymmetry

**Method**: Two-level divergence analysis
- **Tension₁**: `Sentiment_z - Mechanics_z` (raw divergence)
- **Tension₂**: `z-score(Tension₁)` (abnormality score)

**Academic Basis**: Kyle's Lambda, VPIN, Error Correction Models, Market Microstructure Theory

**Categories & Pairs**:

**Category A: Volatility (3 pairs)**
1. DVOL vs ATR
2. Basis Spread vs ATR
3. Funding Rate vs ATR

**Category B: Sentiment vs Participation (4 pairs)**
4. Funding Rate vs volume_btc
5. Basis Spread vs volume_btc
6. btc_socialdominance vs volume_btc
7. btc_postscreated vs btc_txcount

**Category C: Whale vs Retail (5 pairs)**
8. Basis Spread vs btc_largetxcount
9. Funding Rate vs btc_largetxcount
10. btc_socialdominance vs btc_largetxcount
11. btc_newaddresses vs btc_addressessupply1in10k
12. volume_btc vs btc_largetxcount

**Category D: Supply Dynamics (3 pairs)**
13. btc_newaddresses vs btc_activesupply1y
14. btc_sendingaddresses vs btc_receivingaddresses
15. btc_active1y vs btc_splyadrbal1

**Category E: Macro vs Crypto (4 pairs)**
16. SPX momentum vs BTC momentum
17. DXY momentum vs BTC.D
18. Gold momentum vs BTC momentum
19. RRPONTSYD vs volume_btc

**Category F: DeFi vs CeFi (2 pairs)**
20. BTCST_TVL vs Basis Spread
21. btc_txcount vs volume_btc

**Visualization**: Each pair = 1 oscillator chart with 2 lines (Tension₁ blue, Tension₂ red)
- Red overlay when Tension₂ > +2σ & Tension₁ > 0 (SELL signal)
- Green overlay when Tension₂ > +2σ & Tension₁ < 0 (BUY signal)
- 6 category sub-tabs

---

## Technical Implementation

### Backend Tasks

**1. Create New Normalizers**

File: `data/normalizers/pct_change_zscore.py`
- Regress indicators against BTC % change
- Formula: `indicator_change ~ α*btc_pct_change + β`
- Return z-scores of residuals
- Data source: PostgreSQL via `hybrid_data_provider`

File: `data/normalizers/tension_analyzer.py`
- Calculate Tension₁: `Sentiment_z - Mechanics_z`
- Calculate Tension₂: `z-score(Tension₁)` with rolling window
- Return both tension timeseries
- Data source: PostgreSQL via `hybrid_data_provider`

**2. PostgreSQL Data Integration**

Update `hybrid_data_provider.py`:
- Already has all 47 datasets in `postgres_datasets` set
- No changes needed, already supports System 1 & 2 datasets
- System 3 pairs use existing dataset queries

**3. Add API Routes (app.py)**

Route: `/api/system1-data?asset=<asset>&days=<days>`
- Fetch 11 datasets from PostgreSQL via `hybrid_provider.get_data()`
- Normalize using `zscore.normalize(dataset, btc_price)`
- Return array of oscillator data

Route: `/api/system2-data?asset=<asset>&days=<days>`
- Fetch 22 datasets from PostgreSQL via `hybrid_provider.get_data()`
- Normalize using `pct_change_zscore.normalize(dataset, btc_price)`
- Return array of oscillator data

Route: `/api/system3-data?category=<A-F>&asset=<asset>&days=<days>`
- Fetch paired datasets from PostgreSQL
- Calculate tensions using `tension_analyzer.calculate_tensions()`
- Return array: `[{pair_name, tension1_data, tension2_data, sentiment_name, mechanics_name}, ...]`

**4. Dataset Mapping (app.py)**

Add configuration dicts:
```python
SYSTEM1_DATASETS = {
    'dxy': 'dxy_price',
    'gold': 'gold_price',
    'spx': 'spx_price',
    'eth': 'eth_price_alpaca',
    'btc_d': 'btc_dominance',
    'usdt_d': 'usdt_dominance',
    'total3': 'total3',
    'stable_d': 'stable_c_d',
    'ibit': 'ibit',
    'gbtc': 'gbtc',
    'usdtusd': 'usdtusd_pm'
}

SYSTEM2_DATASETS = {
    # Derivatives
    'funding': 'funding_rate_btc',
    'basis': 'basis_spread_btc',
    'dvol': 'dvol_btc',
    # Volume
    'volume_btc': 'volume_btc',
    'volume_eth': 'volume_eth',
    # Whale
    'largetx': 'btc_largetxcount',
    'avgtx': 'btc_avgtx',
    # Social
    'social_dom': 'btc_socialdominance',
    'posts': 'btc_postscreated',
    'contrib_active': 'btc_contributorsactive',
    'contrib_created': 'btc_contributorscreated',
    # On-Chain Flow
    'sending': 'btc_sendingaddresses',
    'receiving': 'btc_receivingaddresses',
    'new_addr': 'btc_newaddresses',
    'txcount': 'btc_txcount',
    'usdt_tfsps': 'usdt_tfsps',
    'mean_fees': 'btc_meantxfees',
    # Supply
    'active_supply': 'btc_activesupply1y',
    'active1y': 'btc_active1y',
    'supply_bal': 'btc_splyadrbal1',
    'addr_supply': 'btc_addressessupply1in10k',
    'ser': 'btc_ser'
}

SYSTEM3_PAIRS = {
    'A': [
        ('dvol_btc', 'atr_btc'),
        ('basis_spread_btc', 'atr_btc'),
        ('funding_rate_btc', 'atr_btc')
    ],
    'B': [
        ('funding_rate_btc', 'volume_btc'),
        ('basis_spread_btc', 'volume_btc'),
        ('btc_socialdominance', 'volume_btc'),
        ('btc_postscreated', 'btc_txcount')
    ],
    'C': [
        ('basis_spread_btc', 'btc_largetxcount'),
        ('funding_rate_btc', 'btc_largetxcount'),
        ('btc_socialdominance', 'btc_largetxcount'),
        ('btc_newaddresses', 'btc_addressessupply1in10k'),
        ('volume_btc', 'btc_largetxcount')
    ],
    'D': [
        ('btc_newaddresses', 'btc_activesupply1y'),
        ('btc_sendingaddresses', 'btc_receivingaddresses'),
        ('btc_active1y', 'btc_splyadrbal1')
    ],
    'E': [
        ('spx_price', 'btc_price'),  # Both as momentum
        ('dxy_price', 'btc_dominance'),
        ('gold_price', 'btc_price'),
        ('rrpontsyd', 'volume_btc')  # JSON-only dataset
    ],
    'F': [
        ('btcst_tvl', 'basis_spread_btc'),
        ('btc_txcount', 'volume_btc')
    ]
}
```

---

### Frontend Tasks

**5. HTML Structure (index.html)**

Add tab buttons:
```html
<button class="tab-btn" data-tab="system1">System 1</button>
<button class="tab-btn" data-tab="system2">System 2</button>
<button class="tab-btn" data-tab="system3">System 3</button>
```

Add tab content containers:
```html
<div id="system1-tab" class="tab-content">
  <div id="system1-dxy-chart"></div>
  <div id="system1-gold-chart"></div>
  <!-- 9 more chart divs -->
</div>

<div id="system2-tab" class="tab-content">
  <div id="system2-funding-chart"></div>
  <div id="system2-basis-chart"></div>
  <!-- 20 more chart divs -->
</div>

<div id="system3-tab" class="tab-content">
  <div class="category-tabs">
    <button data-category="A">Volatility</button>
    <button data-category="B">Sentiment</button>
    <!-- 4 more category tabs -->
  </div>
  <div id="system3-category-A">
    <div id="system3-pair-1-chart"></div>
    <div id="system3-pair-2-chart"></div>
    <div id="system3-pair-3-chart"></div>
  </div>
  <!-- 5 more category containers -->
</div>
```

**6. Tab Management (main.js)**

Add state variables:
```javascript
appState.system1Initialized = false;
appState.system2Initialized = false;
appState.system3Initialized = false;
appState.system3ActiveCategory = 'A';
```

Add load functions:
```javascript
async function loadSystem1Tab() { /* ... */ }
async function loadSystem2Tab() { /* ... */ }
async function loadSystem3Tab() { /* ... */ }
```

**7. Chart Rendering (oscillator.js)**

For System 3, modify to support 2 lines per chart:
- Line 1 (Tension₁): Blue solid line
- Line 2 (Tension₂): Red solid line
- Add visual zones (red/green overlays) based on thresholds

**8. API Integration (api.js)**

Add fetch functions:
```javascript
export async function getSystem1Data(asset, days) { /* ... */ }
export async function getSystem2Data(asset, days) { /* ... */ }
export async function getSystem3Data(category, asset, days) { /* ... */ }
```

**9. CSS Styling**

Add styles for new tabs, ensure vertical stacking, synchronized zoom

---

### Integration Tasks

**10. Testing Checklist**

- [ ] PostgreSQL connection active
- [ ] System 1 loads 11 datasets correctly
- [ ] System 2 loads 22 datasets correctly
- [ ] System 3 loads 21 pairs across 6 categories
- [ ] All charts synchronized (zoom, regime backgrounds)
- [ ] Reference lines (0, ±2σ, ±3σ) render correctly
- [ ] Visual zones (red/green) appear for System 3
- [ ] Main tab remains unchanged

---

## Minimal Implementation (No Overkill)

**Skip for now** (add later):
- Advanced error handling
- Loading spinners
- Data validation beyond null checks
- Performance optimization
- Historical win rate backtesting
- Caching layer (PostgreSQL is fast)

**Focus**: Get charts rendering with correct PostgreSQL data

---

## Task Execution Order

1. PostgreSQL data integration check (verify hybrid_provider ready)
2. Create `pct_change_zscore.py` normalizer
3. Create `tension_analyzer.py` normalizer
4. Add dataset mappings to `app.py`
5. Add `/api/system1-data` route
6. Add `/api/system2-data` route
7. Add `/api/system3-data` route
8. Add HTML tab structure
9. Update `main.js` tab management
10. Update `oscillator.js` for tension rendering
11. Add API functions to `api.js`
12. Add CSS styling
13. Test each system individually
14. Test synchronization across systems

---

## Success Criteria

✅ System 1 tab loads 11 price-anchored oscillators from PostgreSQL
✅ System 2 tab loads 22 velocity-anchored oscillators from PostgreSQL
✅ System 3 tab loads 6 categories with tension pairs from PostgreSQL (21 total)
✅ All charts synchronized (zoom, regime backgrounds, reference lines)
✅ Current "Main" tab remains unchanged
✅ Hybrid fallback to JSON works if PostgreSQL unavailable

---

## Phase Reorganization

**OLD Phase 1** (Mathematical Validation):
- Z-score validation
- RSI/ADX/ATR verification
- MACD validation
- Floating point precision
- Timestamp alignment

**NOW → Phase 2+** (Audits after implementation)

**NEW Phase 1** (This Implementation):
- Three-system oscillator dashboard
- PostgreSQL integration
- Granular visualization (no aggregation)

---

## References

See `OSCILLATOR_VISUALIZATION_RESEARCH.md` for:
- Academic foundations
- Mathematical formulas
- Dataset categorization
- Visualization mockups
- Risk assessment

---

**END OF IMPLEMENTATION PLAN**
