# SESSIONLOGS.md — TraceX Development Session Log

## Session 1 — Full System Build (2026-05-14)

### Timeline

| Time | Task | Status |
|------|------|--------|
| Start | Project scaffolding: directory structure, venv, requirements.txt, .streamlit/config.toml | ✅ Done |
| +5min | Installed all dependencies (streamlit, pandas, numpy, networkx, scikit-learn, xgboost, plotly, fpdf2, pyvis, etc.) | ✅ Done |
| +10min | Created `utils/constants.py` — all domain constants (PMLA thresholds, FIU-IND categories, Indian bank context) | ✅ Done |
| +12min | Created `utils/helpers.py` — safe_ratio, channel_entropy, risk level mapping, INR formatting, Gini coefficient | ✅ Done |
| +20min | Created `core/data_loader.py` — DataLoader class (IBM AML, PaySim, custom CSV) + demo data generator with 5 fraud scenarios | ✅ Done |
| +30min | Created `core/graph_engine.py` — TransactionGraph with temporal BFS, cycle detection, centrality, fund trails, RWR | ✅ Done |
| +40min | Created `core/feature_extractor.py` — 30-feature extraction pipeline | ✅ Done |
| +48min | Created `core/ml_detector.py` — AnomalyDetector (Isolation Forest) + FraudClassifier (XGBoost) | ✅ Done |
| +58min | Created `core/pattern_detector.py` — 6 pattern types + combined + first suspicious point + repeat behavior | ✅ Done |
| +65min | Created `core/role_classifier.py` — AccountRoleClassifier (percentile-based) | ✅ Done |
| +68min | Created `core/speed_analyzer.py` — SpeedAnalyzer with 4 speed categories | ✅ Done |
| +75min | Created `core/risk_scorer.py` — Composite scoring + confidence meter + investigation priority | ✅ Done |
| +82min | Created `core/profile_analyzer.py` — Peer group comparison + mismatch detection | ✅ Done |
| +92min | Created `core/evidence_generator.py` — FIU-IND STR format PDF + JSON generator | ✅ Done |
| +98min | Created `utils/visualization.py` — 9 reusable Plotly chart components | ✅ Done |
| +108min | Created `app.py` — Main Streamlit app with data source selector and build_system pipeline | ✅ Done |
| +115min | Created `pages/1_🔍_Graph_Explorer.py` — PyVis graph, fund trail tracer, accomplice detection | ✅ Done |
| +122min | Created `pages/2_⚠️_Anomaly_Dashboard.py` — Priority queue, speed alerts, account detail cards | ✅ Done |
| +132min | Created `pages/3_🔄_Pattern_Detector.py` — 7 tabs for all pattern types + first suspicious point | ✅ Done |
| +138min | Created `pages/4_👤_Profile_Analyzer.py` — Scatter plot + mismatch table + peer analysis | ✅ Done |
| +142min | Created `pages/5_📊_Channel_Analytics.py` — Sankey + heatmap + suspicious channels | ✅ Done |
| +148min | Created `pages/6_📋_FIU_Evidence.py` — Case builder + PDF/JSON download + case management | ✅ Done |
| +160min | Wrote comprehensive test suite: 60 tests covering all modules + integration | ✅ Done |
| +162min | Ran tests — all 60 passed, identified deprecation warnings | ✅ Done |
| +168min | Fixed fpdf2 `ln=True` deprecation, XGBoost `use_label_encoder` warning | ✅ Done |
| +170min | Re-ran tests — all 60 passed, 0 warnings | ✅ Done |
| +175min | Created CHANGELOGS.md and SESSIONLOGS.md | ✅ Done |

### Decisions Made
1. **Demo data as default**: System starts with synthetic Indian bank data (200 accounts, 5000 transactions) with 5 embedded fraud scenarios. Real data (IBM AML, PaySim) loaded when files are available.
2. **Dual ML approach**: Isolation Forest for unsupervised anomaly detection (catches unknown patterns), XGBoost for supervised classification (when labels available).
3. **Temporal BFS**: Graph traversal respects time ordering — money can only flow forward in time. Critical for realistic fund tracing.
4. **Bounded cycle detection**: `length_bound=5` parameter prevents exponential blowup on dense graphs.
5. **Composite risk scoring**: ML (30%) + Patterns (40%) + Graph centrality (30%) gives balanced risk assessment.
6. **Percentile-based role classification**: Avoids magic number thresholds that break across datasets.
7. **PyVis for graph rendering**: Rich physics simulation, interactive, works in Streamlit iframe.

### Files Created (27 total)
```
fund-flow-tracker/
├── app.py
├── requirements.txt
├── CHANGELOGS.md
├── SESSIONLOGS.md
├── .streamlit/config.toml
├── core/
│   ├── __init__.py
│   ├── data_loader.py
│   ├── graph_engine.py
│   ├── feature_extractor.py
│   ├── ml_detector.py
│   ├── pattern_detector.py
│   ├── role_classifier.py
│   ├── speed_analyzer.py
│   ├── risk_scorer.py
│   ├── profile_analyzer.py
│   └── evidence_generator.py
├── utils/
│   ├── __init__.py
│   ├── constants.py
│   ├── helpers.py
│   └── visualization.py
├── pages/
│   ├── 1_🔍_Graph_Explorer.py
│   ├── 2_⚠️_Anomaly_Dashboard.py
│   ├── 3_🔄_Pattern_Detector.py
│   ├── 4_👤_Profile_Analyzer.py
│   ├── 5_📊_Channel_Analytics.py
│   └── 6_📋_FIU_Evidence.py
├── tests/
│   ├── __init__.py
│   └── test_core.py
├── data/
└── exports/
```

### Test Results
```
60 passed in 16.20s
0 failed
0 warnings
```

### Known Limitations
- Large IBM AML datasets (>1GB) require pre-download — not bundled with repo
- PyVis graph rendering may be slow with >300 nodes in browser
- No persistent database — all in-memory (by design for hackathon)
- Case management uses session_state — cases lost on app restart
