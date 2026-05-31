# 🏦 TraceX — AML Intelligence System

> **"Every rupee leaves a trail. We make it visible."**

Graph-first, ML-second, law-enforcement-ready AML tracking for Anti-Money Laundering.

## Quick Start

### Next.js Frontend + FastAPI Backend (recommended)
```bash
cd fund-flow-tracker

# Backend
python -m venv venv && source venv/bin/activate
pip install -r requirements_v3.txt
uvicorn api.server_v3:app --reload --port 8000

# Frontend (separate terminal)
cd frontend
npm install
npm run dev          # http://localhost:3000
```

### Streamlit (legacy)
```bash
pip install -r requirements.txt
streamlit run app.py
```

## What's New (v2 → v3)

### Branding
- Renamed from **Fund Flow Tracker** → **TraceX — AML Intelligence** across all frontend, backend, core, and docs.

### Ingestion & Detection
- **Auto-labelling**: `is_laundering` column is no longer required in uploaded CSVs. If absent, it is defaulted to `0` and the ML pipeline assigns fraud labels automatically.
- **EOD Ingestion Service** (`services/ingestion/eod_service.py`): batch end-of-day ingestion with dedup, schema normalization, and DB persistence.
- **CSV parser** auto-detects schema and maps common column aliases.

### Database Layer
- New **SQLite adapter** (`infrastructure/database.py`) persists accounts, transactions, ingestion history, and alerts.
- Supports `get_ingestion_history`, `insert_transactions`, `account_exists`, and full alert CRUD.

### API Endpoints (FastAPI)
| Endpoint | Method | Description |
|---|---|---|
| `/api/health` | GET | System health and initialization state |
| `/api/init` | POST | Load dataset and build graph + run detection |
| `/api/refresh` | POST | Rebuild graph & re-run ML pipeline from existing DB data (no re-upload needed) |
| `/api/graph` | GET | Full graph data (nodes + edges) |
| `/api/graph/trail/{account}` | GET | Fund-flow trail for an account |
| `/api/anomalies` | GET | All detected anomalies |
| `/api/patterns` | GET | Detected laundering patterns |
| `/api/profile/{account}` | GET | Account risk profile |
| `/api/channels` | GET | Channel analytics |
| `/api/evidence/{account}` | GET | FIU evidence pack |
| `/api/ingest` | POST | Upload and ingest a CSV file |
| `/api/ingest/history` | GET | List all past ingestion sessions |

### Frontend (Next.js / TypeScript)
- **Ingest page** (`/ingest`): drag-and-drop CSV upload, auto-loads history on mount, **"Load & Analyze"** button re-runs full detection from DB without re-uploading the file.
- **Cytoscape graph** (`CytoscapeGraph.tsx`): interactive force-directed graph with risk-colored nodes and fund-trail highlighting.
- Updated **Graph, Patterns, Profile, Channels** pages with improved layout and live API data.
- `api.ts` client with `initSystem()` and `refreshSystem()` helpers.

### Infrastructure & DevOps
- **Dockerfile** — containerised backend, ready for cloud deploy.
- **GitHub Actions CI** (`.github/workflows/ci.yml`) — runs tests on every push.
- **`.gitignore`** — excludes large data files, SQLite DB, and upload artifacts.

### Scripts
| Script | Purpose |
|---|---|
| `scripts/demo_run.sh` | One-shot demo: ingest → detect → print summary |
| `scripts/fetch_datasets.py` | Download IBM AML / PaySim datasets |
| `scripts/generate_test_eod.py` | Generate synthetic EOD test CSVs |
| `scripts/ingest_eod.py` | Ingest an EOD CSV via the API |

### Docs & Tests
- `docs/ARCHITECTURE.md` — full system architecture diagram and component guide.
- `tests/test_ingestion.py` — 240-line integration test suite for ingestion service.

---


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
