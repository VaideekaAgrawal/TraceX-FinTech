# 🏦 TraceX — AML Intelligence System

> **"Every rupee leaves a trail. We make it visible."**

Graph-first, ML-second, law-enforcement-ready AML tracking for Anti-Money Laundering.

## Quick Start

```bash
cd fund-flow-tracker
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
streamlit run app.py
```

## Recent Changes (summary of uncommitted edits)

Date: 2026-05-31

- Branding and UI
	- Renamed product references from "Fund Flow" to "TraceX" and updated UI text to "AML Intelligence" across frontend and backend.
	- Updated frontend layout/title/subtitle and `Sidebar` to display TraceX branding.
	- Changed graph UI button from "Trace Fund Flow" to "Trace Flow".

- Ingestion & UX
	- Removed `is_laundering` from mock CSV; ingestion now defaults missing `is_laundering` to 0 and runs detection to label transactions.
	- Fixed ingest history flow: added a "Load & Analyze" action that now rebuilds the in-memory system from DB (no file path required).
	- Updated ingest page to auto-load history on mount and open analysis links in new tabs.

- Backend / API
	- Added a new endpoint: `POST /api/refresh` — rebuilds the graph and runs the full ML pipeline from existing DB data (useful for history "Load & Analyze").
	- Ensured `timestamp` strings read from SQLite are converted to datetimes before running detection.
	- Minor API and documentation string updates to reflect TraceX/AML naming.

- Detection / Services
	- Detection pipeline run on refresh; isolation forest + XGBoost pipelines executed and detection results created as alerts.
	- XGBoost correctly falls back to CPU when no GPU is available (warning logged).

- Files changed (uncommitted list)
	- Core: `core/*` (`__init__.py`, `evidence_generator.py`, `pattern_detector.py`, `role_classifier.py`)
	- API: `api/server_v3.py` (+ small edits in `api/server.py`)
	- Frontend: `frontend/src/app/ingest/page.tsx`, `frontend/src/app/graph/page.tsx`, `frontend/src/lib/api.ts`, `frontend/src/app/layout.tsx`, `frontend/src/components/Sidebar.tsx`, and related pages/components
	- Scripts & docs: `scripts/demo_run.sh`, `README_V3.md`, `CHANGELOGS.md`, `docs/ARCHITECTURE.md`

If you want a different summary format (short bullets per file, or full diff links), tell me which format and I'll update it.


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
