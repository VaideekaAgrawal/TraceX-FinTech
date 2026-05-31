# 🏦 TraceX — AML Intelligence System

> **"Every rupee leaves a trail. We make it visible."**

Graph-first, ML-powered, law-enforcement-ready Anti-Money Laundering detection system.

---

## Quick Start

### Prerequisites
- Python 3.10+
- Node.js 18+
- npm

### Backend (FastAPI)
```bash
cd fund-flow-tracker
python -m venv venv
# Windows:
venv\Scripts\activate
# Linux/Mac:
source venv/bin/activate

pip install -r requirements.txt
uvicorn api.server:app --host 0.0.0.0 --port 8000
```

### Frontend (Next.js)
```bash
cd fund-flow-tracker/frontend
npm install
npm run dev          # http://localhost:3000
```

### Generate Test Data
```bash
cd fund-flow-tracker
python scripts/generate_test_pair.py
```
This creates two CSVs in `data/`:
- `tracex_test_day1.csv` — 8000 transactions, 312 accounts (initial load)
- `tracex_test_day2_incremental.csv` — 5000 transactions (incremental with behavioral shifts)

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                    Next.js Frontend (port 3000)                       │
│  Dashboard │ Graph Explorer │ Anomaly │ Patterns │ Profile │ Ingest  │
├─────────────────────────────────────────────────────────────────────┤
│                    FastAPI Backend (port 8000)                        │
│  /api/init │ /api/graph │ /api/anomaly │ /api/patterns │ /api/ingest │
├─────────────────────────────────────────────────────────────────────┤
│                    Microservice Layer                                 │
│  Ingestion │ Graph (NetworkX) │ Detection (5 detectors + ML) │ Inv.  │
├─────────────────────────────────────────────────────────────────────┤
│                    Infrastructure                                     │
│  Event Bus │ Health Monitor │ Config │ SQLite DB                      │
└─────────────────────────────────────────────────────────────────────┘
```

---

## Features

### 5 Fraud Detectors
| Detector | What It Finds |
|----------|--------------|
| **Layering** | Multi-hop chains (A→B→C→D) with amount decay |
| **Round-Trip** | Circular flows (A→B→A) with ≥85% amount return |
| **Structuring** | Amounts just below ₹10L CTR threshold |
| **Dormancy** | Accounts inactive 6+ months, suddenly active |
| **Profile Mismatch** | Income vs. actual volume anomalies |

### ML Pipeline
- **Isolation Forest** — unsupervised anomaly detection (no labels needed)
- **XGBoost** — supervised classification (trains on `is_laundering` labels, GPU/CUDA supported)
- **Ensemble Scoring** — ML 30% + Pattern flags 40% + Graph centrality 30%

### Graph Intelligence
- **Role Classification** — SOURCE / MULE / SINK / NORMAL
- **Fund Trail Tracing** — Follow money through the network
- **Random Walk** — Find accomplices via PageRank
- **Pattern Subgraphs** — Neo4j-style visualization of flagged networks

### Regulatory
- **FIU-IND Evidence Packs** — one-click STR report (PDF + JSON)
- **Investigation Priority Queue** — P1-P4 ranking

---

## API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/health` | GET | System health |
| `/api/init` | POST | Initialize from dataset (ibm_aml, paysim, csv) |
| `/api/refresh` | POST | Rebuild from DB data |
| `/api/ingest/upload` | POST | Upload CSV (multipart form) |
| `/api/ingest/history` | GET | Ingestion history |
| `/api/overview` | GET | Dashboard summary |
| `/api/graph` | GET | Network graph (nodes + edges) |
| `/api/graph/ego/{id}` | GET | Ego-network for account |
| `/api/graph/pattern/{type}` | GET | Pattern-specific subgraph |
| `/api/graph/fund-trail` | POST | Fund flow trail |
| `/api/graph/random-walk` | POST | Find accomplices |
| `/api/anomaly` | GET | Anomaly scores + investigation queue |
| `/api/patterns` | GET | Detected fraud patterns |
| `/api/profile` | GET | Income/volume mismatch data |
| `/api/channels` | GET | Channel analytics |
| `/api/accounts` | GET | All accounts with risk scores |
| `/api/accounts/{id}` | GET | Account detail + features |
| `/api/evidence/generate` | POST | Generate FIU STR report |

---

## Project Structure

```
fund-flow-tracker/
├── api/
│   └── server.py             # FastAPI server (all endpoints)
├── services/
│   ├── ingestion/             # Data parsing (IBM AML, CSV, EOD)
│   ├── graph/                 # NetworkX graph engine
│   ├── detection/             # 5 detectors + ensemble ML
│   ├── investigation/         # Cases, alerts, evidence
│   ├── monitoring/            # System metrics
│   ├── validation/            # Data contracts
│   └── common/                # Shared models & constants
├── infrastructure/
│   ├── config.py              # System configuration
│   ├── database.py            # SQLite adapter
│   ├── event_bus.py           # Pub/sub event bus
│   └── health.py              # Health checkpoints
├── frontend/
│   └── src/
│       ├── app/               # Next.js pages (dashboard, graph, etc.)
│       ├── components/        # UI components (CytoscapeGraph, etc.)
│       └── lib/               # API client, utilities
├── scripts/
│   ├── generate_test_pair.py  # Generate Day1 + Day2 test CSVs
│   ├── download_data.py       # Download IBM AML dataset
│   ├── ingest_eod.py          # CLI ingestion tool
│   └── init_system.py         # Initialize system from CLI
├── data/                      # Datasets and test CSVs
├── tests/                     # Pytest test suite
├── utils/                     # Domain constants
├── docs/                      # Architecture docs
├── Dockerfile                 # Container deployment
└── requirements.txt           # Python dependencies
```

---

## Testing

### Run Test Suite
```bash
python -m pytest tests/ -v
```

### Manual Testing Flow
1. Start backend + frontend (see Quick Start)
2. Generate test data: `python scripts/generate_test_pair.py`
3. Open http://localhost:3000/ingest
4. Upload `data/tracex_test_day1.csv` → explore all pages
5. Upload `data/tracex_test_day2_incremental.csv` (check "Force re-process") → watch risk scores change

### Key Test Accounts
| Account | Pattern | Expected |
|---------|---------|----------|
| `STR001AA01` | Structuring | HIGH risk, amounts near ₹10L |
| `RT_SRC_001` | Round-tripping | Circular flows with `RT_DST_001` |
| `LAY_A01→LAY_E01` | Layering | 5-hop chain with amount decay |
| `FANOUT_01` | Fan-out | SOURCE role, many recipients |
| `DORM_001` | Dormancy | Quiet Day1, burst Day2 |
| `SHIFT_001` | Behavioral shift | Clean Day1 → Dirty Day2 |
| `VELO_001` | Velocity spike | 20+ transactions in 30 minutes |

---

## Graph Legend

| Symbol | Meaning |
|--------|---------|
| 🔴 Red node | CRITICAL risk (76-100) |
| 🟠 Orange node | HIGH risk (51-75) |
| 🟡 Yellow node | MEDIUM risk (26-50) |
| 🟢 Green node | LOW risk (0-25) |
| △ Triangle | SOURCE (sends money out) |
| ◇ Diamond | MULE (passes money through) |
| ▽ Inverted triangle | SINK (receives money) |
| ○ Circle | NORMAL account |
| Node size | Proportional to risk score |
| Edge thickness | Proportional to transaction amount |

---

## Data Sources

| Source | Description |
|--------|-------------|
| **IBM AML** | 5M+ transactions, 5,100 labelled laundering cases |
| **Custom CSV** | Upload any CSV with timestamp, source, dest, amount |
| **Generated** | Synthetic test data with embedded patterns |

---

## Deployment

```bash
# Docker
docker build -t tracex .
docker run -p 8000:8000 tracex
```

---

## License

Research & educational use. IBM AML dataset: CDLA Sharing 1.0.
