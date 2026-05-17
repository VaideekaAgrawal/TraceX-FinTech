# 🏦 TraceX — Fund Flow Intelligence System

> **"Every rupee leaves a trail. We make it visible."**

Graph-first, ML-second, law-enforcement-ready fund flow tracking for Anti-Money Laundering.

## Quick Start

```bash
cd fund-flow-tracker
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
streamlit run app.py
```

## Architecture

```
┌──────────────────────────────────────────────────────────────┐
│                     STREAMLIT UI (6 pages)                    │
│  Graph Explorer │ Anomaly Dashboard │ Pattern Detector        │
│  Profile Analyzer │ Channel Analytics │ FIU Evidence          │
├──────────────────────────────────────────────────────────────┤
│                     ANALYSIS ENGINE                           │
│  Graph Engine (NetworkX) │ ML (IsolationForest + XGBoost)     │
│  Pattern Detector (6 types) │ Risk Scorer │ Evidence Gen      │
├──────────────────────────────────────────────────────────────┤
│                     DATA LAYER                                │
│  IBM AML Dataset │ PaySim │ Custom CSV Upload │ Demo Data     │
└──────────────────────────────────────────────────────────────┘
```

## Features

- **Interactive Graph Explorer** — PyVis network with risk-colored nodes, role-shaped markers, fund trail tracing
- **30-Feature ML Pipeline** — Graph + behavioral + profile features fed to Isolation Forest + XGBoost
- **6 Pattern Detectors** — Layering, round-tripping, structuring, dormant activation, fan-in, fan-out
- **Fraud Confidence Meter** — Independent indicator counting (Weak/Moderate/Strong/Very Strong)
- **FIU-IND Evidence Packs** — One-click STR report generation (PDF + JSON)
- **Investigation Priority Queue** — P1-P4 ranking with composite risk scoring

## Data Sources

| Source | Description |
|--------|-------------|
| **Demo** | 200 accounts, 5000 transactions with 5 embedded fraud scenarios |
| **IBM AML** | Research-grade dataset with 8 labeled laundering patterns |
| **PaySim** | 6.3M mobile money transactions |
| **Upload CSV** | Auto-detect columns from any transaction CSV |

## Testing

```bash
python -m pytest tests/ -v
```

60 tests covering all core modules + full integration pipeline.
