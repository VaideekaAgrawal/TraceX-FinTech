# CHANGELOGS.md — TraceX Fund Flow Intelligence System

## v1.0.0 — Initial Release (2026-05-14)

### Core Modules
- **Data Loader** (`core/data_loader.py`): Unified loader supporting IBM AML, PaySim, custom CSV upload, and demo data generation with 5 embedded fraud scenarios (layering, round-tripping, structuring, dormant activation, fan-in).
- **Graph Engine** (`core/graph_engine.py`): NetworkX MultiDiGraph with temporal BFS, bounded cycle detection (length_bound=5), PageRank, betweenness centrality, ego subgraph, fund trail tracer, transaction chain extraction, suspicious path ranking, and random walk with restart.
- **Feature Extractor** (`core/feature_extractor.py`): 30-feature pipeline covering graph features (8), transaction behavioral features (9), account profile features (4), and additional features (9) including reciprocity ratio, geographic dispersion, temporal regularity, and Gini concentration.
- **ML Detector** (`core/ml_detector.py`): Dual-model approach — Isolation Forest (unsupervised, contamination=0.05) + XGBoost classifier (supervised, class-imbalance handled via scale_pos_weight). Returns anomaly scores (0-100), fraud probabilities, and feature importance.
- **Pattern Detector** (`core/pattern_detector.py`): 6 pattern types — layering (chain + amount decay), round-tripping (bounded cycles), structuring (classic + split), dormant activation, fan-in, fan-out. Plus combined pattern analysis, first suspicious point detection (z-score method), and repeat behavior detection.
- **Role Classifier** (`core/role_classifier.py`): Percentile-based classification of accounts as SOURCE, MULE, SINK, or NORMAL based on in/out flow ratios and degree distribution.
- **Speed Analyzer** (`core/speed_analyzer.py`): Transaction chain velocity analysis with categories: Normal, Fast, Very Fast, Abnormal. Flags rapid fund movement chains.
- **Risk Scorer** (`core/risk_scorer.py`): Composite risk scoring (ML 30% + Patterns 40% + Graph 30%), fraud confidence meter (Weak/Moderate/Strong/Very Strong based on independent indicator count), investigation priority (P1-P4).
- **Profile Analyzer** (`core/profile_analyzer.py`): Peer-group comparison, income-vs-volume mismatch detection, scatter plot data generation.
- **Evidence Generator** (`core/evidence_generator.py`): FIU-IND compliant STR report generation — PDF (Parts A-D) and JSON (FINnet 2.0 format). Handles Unicode sanitization.

### Streamlit UI (6 pages)
- **Home** (`app.py`): Overview metrics, risk donut chart, alert timeline, top alerts table, model metrics display. Data source selector (Demo/IBM AML/PaySim/Upload CSV).
- **Graph Explorer** (`pages/1_🔍_Graph_Explorer.py`): PyVis interactive graph with risk-colored nodes, role-shaped nodes, channel-colored edges. Account search, hop depth slider, filter panel, fund trail tracer, random walk accomplice detection.
- **Anomaly Dashboard** (`pages/2_⚠️_Anomaly_Dashboard.py`): Risk donut, anomaly histogram, feature importance chart, investigation priority queue (P1-P4), speed alerts, account detail card with features.
- **Pattern Detector** (`pages/3_🔄_Pattern_Detector.py`): 7 tabs (Layering, Round-Tripping, Structuring, Dormant, Fan-In, Fan-Out, Combined). Amount degradation charts, circular cycle visualization, structuring histograms. First suspicious point detector.
- **Profile Analyzer** (`pages/4_👤_Profile_Analyzer.py`): Income vs volume scatter plot, mismatch table, individual peer-group analysis.
- **Channel Analytics** (`pages/5_📊_Channel_Analytics.py`): Sankey diagram (Account Type → Channel → Account Type), channel×hour heatmap, suspicious channel usage.
- **FIU Evidence** (`pages/6_📋_FIU_Evidence.py`): Case builder with multi-select accounts, pattern type, case notes. PDF/JSON download. Case management tracker.

### Utilities
- **Constants** (`utils/constants.py`): All PMLA/RBI thresholds, FIU-IND suspicion categories, risk levels, Indian bank context data.
- **Helpers** (`utils/helpers.py`): Safe division, channel entropy, risk level mapping, INR formatting, text sanitization, Gini coefficient.
- **Visualization** (`utils/visualization.py`): Reusable Plotly components — risk donut, feature importance bar, anomaly histogram, alert timeline scatter, Sankey, heatmap, amount degradation, income-vs-volume scatter.

### Testing
- **60 tests** covering all modules: helpers, data loader, graph engine, feature extraction, anomaly detection, fraud classification, pattern detection, role classification, speed analysis, risk scoring, profile analysis, evidence generation, and full integration pipeline.
- All tests pass (0 failures, 0 warnings).

### Bug Fixes Applied (from V2 Plan)
1. Fixed circular ML training — supports real labeled data (IBM AML) for supervised training
2. Bounded cycle detection — `length_bound=5` prevents crash on dense graphs
3. Structuring threshold consistency — single source of truth in constants.py with both classic and split detection
4. Role classifier uses percentile-based thresholds instead of magic numbers
5. Speed analyzer connected to graph engine via `get_transaction_chains()`
6. Disconnected components handled — fund trail reports component size and warnings
7. PageRank works via collapsed weighted DiGraph (no MultiDiGraph issues)
8. Division-by-zero guarded via `safe_ratio()` and `channel_entropy()` helpers
9. Temporal BFS implemented — money only flows forward in time
10. PDF Unicode handled via `sanitize_text()` for ₹ and special characters
11. Fixed fpdf2 `ln=True` deprecation warnings — using `new_x`/`new_y` parameters
12. Removed XGBoost `use_label_encoder` deprecation warning
