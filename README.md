# 🏦 TraceX — Fund Flow Tracking & AML Intelligence System

> **"Every rupee leaves a trail. We make it visible."**

**Problem Statement:** PS3 — Tracking of Funds within Bank for Fraud Detection  
**Hackathon:** Union Bank of India × iDEA 2.0

TraceX is a graph-first, ML-powered Anti-Money Laundering detection system that ingests bank transaction data, builds a directed multigraph of account relationships, applies 5 custom fraud pattern detectors + ensemble ML (Isolation Forest + XGBoost), and enables investigators to trace fund flows and generate FIU-IND evidence packages.

---

## 🚀 Quick Start — Clone & Run in 5 Minutes

### Prerequisites

| Tool | Version | Check |
|------|---------|-------|
| Python | 3.10+ | `python --version` |
| Node.js | 18+ | `node --version` |
| npm | 9+ | `npm --version` |
| Git | Any | `git --version` |

### Step 1: Clone the Repository

```bash
git clone https://github.com/your-team/TraceX-FinTech.git
cd TraceX-FinTech
```

### Step 2: Setup Python Backend

```bash
cd fund-flow-tracker

# Create virtual environment
python -m venv venv

# Activate it
# Windows (CMD):
venv\Scripts\activate
# Windows (PowerShell):
.\venv\Scripts\Activate.ps1
# Linux/Mac:
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

### Step 3: Generate Test Data

```bash
python scripts/generate_test_pair.py
```

This creates 3 test CSVs in the `data/` folder:
- `tracex_test_day1.csv` — 8,000 transactions, 312 accounts
- `tracex_test_day2_incremental.csv` — 5,000 transactions (incremental)
- `tracex_test_day3_demo.csv` — 6,000 transactions (demo-optimized, all patterns guaranteed)

### Step 4: Start the Backend Server

```bash
uvicorn api.server:app --host 0.0.0.0 --port 8000
```

You should see:
```
INFO:     Uvicorn running on http://0.0.0.0:8000
```

Verify: Open http://localhost:8000/health in your browser.

### Step 5: Start the Frontend (New Terminal)

```bash
cd fund-flow-tracker/frontend
npm install
npm run dev
```

You should see:
```
▲ Next.js 16.x
- Local: http://localhost:3000
✓ Ready
```

### Step 6: Use the Application

1. Open **http://localhost:3000** in your browser
2. Go to the **Ingest** page (`/ingest`)
3. Upload `data/tracex_test_day3_demo.csv` (recommended for demo)
4. Wait ~10 seconds for the full pipeline to run
5. Explore all pages: Dashboard, Graph Explorer, Anomaly, Patterns, Profile, Evidence

---

## 📊 What Happens When You Upload Data

```
CSV Upload → Parse & Validate → Build Graph (NetworkX MultiDiGraph)
     → Extract 29 Features/Account → Train ML Models (IF + XGBoost)
     → Run 5 Pattern Detectors → Compute Ensemble Risk Scores
     → Classify Roles (SOURCE/MULE/SINK) → Generate Alerts
```

**Pipeline time:** ~8-10 seconds for 6,000 transactions on standard hardware.

---

## 🔍 Features

### 5 Fraud Pattern Detectors

| Detector | What It Finds | Algorithm |
|----------|--------------|-----------|
| **Layering** | Multi-hop chains (A→B→C→D) with amount decay | Temporal chain extraction |
| **Round-Trip** | Circular flows (A→B→A) with ≥85% return | Johnson's cycle detection |
| **Structuring** | Amounts just below ₹10L CTR threshold | Rule + statistical hybrid |
| **Dormancy** | Inactive 180+ days, sudden burst | Gap analysis + burst detection |
| **Profile Mismatch** | Volume vs. declared income anomalies | Z-score + peer comparison |

### ML Pipeline
- **Isolation Forest** — unsupervised anomaly detection (no labels needed)
- **XGBoost** — supervised classifier (GPU/CUDA accelerated, F1=0.683, AUC-ROC=0.933)
- **Ensemble Scoring** — ML 30% + Pattern flags 40% + Graph centrality 30%

### Graph Intelligence
- Role Classification (SOURCE / MULE / SINK / NORMAL)
- Fund Trail Tracing (temporal BFS — money only flows forward in time)
- Accomplice Discovery (Random Walk with Restart)
- Neo4j-style interactive visualization (Cytoscape.js)

### Regulatory
- FIU-IND Suspicious Transaction Report generation (PDF + JSON)
- SHA-256 integrity hash for tamper detection
- Investigation priority queue (P1–P4)

---

## 🏗️ Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│  FRONTEND — Next.js 16 + React 19 + Cytoscape.js (port 3000)   │
│  Dashboard │ Graph │ Anomaly │ Patterns │ Profile │ Evidence    │
├─────────────────────────────────────────────────────────────────┤
│  BACKEND — FastAPI + Uvicorn (port 8000)                        │
│  25+ REST endpoints │ Event Bus │ Health Monitor                │
├─────────────────────────────────────────────────────────────────┤
│  DETECTION — 5 Detectors + Isolation Forest + XGBoost           │
│  29 features/account │ Ensemble scoring │ Role classification   │
├─────────────────────────────────────────────────────────────────┤
│  GRAPH — NetworkX Directed MultiGraph                           │
│  Cycle detection │ PageRank │ BFS │ Random Walk │ Centrality    │
├─────────────────────────────────────────────────────────────────┤
│  INFRASTRUCTURE — SQLite │ Event Bus │ Config │ Health          │
└─────────────────────────────────────────────────────────────────┘
```

---

## 📁 Project Structure

```
TraceX-FinTech/
├── README.md                          ← You are here
└── fund-flow-tracker/
    ├── api/server.py                  # FastAPI server (25+ endpoints)
    ├── services/
    │   ├── detection/                 # 5 detectors + ML ensemble
    │   ├── graph/                     # NetworkX graph engine
    │   ├── ingestion/                 # CSV/IBM AML parser
    │   ├── investigation/             # Case management + evidence
    │   ├── monitoring/                # System metrics
    │   └── validation/                # Data contracts
    ├── infrastructure/                # Config, DB, Event Bus, Health
    ├── frontend/                      # Next.js dashboard (8 pages)
    ├── scripts/
    │   ├── generate_test_pair.py      # Generate test CSVs
    │   ├── download_data.py           # Download IBM AML dataset
    │   └── init_system.py             # CLI initialization
    ├── tests/                         # Pytest test suite
    ├── data/                          # Datasets (gitignored)
    ├── docs/                          # Architecture + submission docs
    ├── Dockerfile                     # Container deployment
    └── requirements.txt               # Python dependencies
```

---

## 🧪 Testing

```bash
cd fund-flow-tracker
python -m pytest tests/ -v
```

### Demo Test Accounts (Day 3 CSV)

| Account | Pattern | What to Look For |
|---------|---------|-----------------|
| `D3_LAY_A1` → `D3_LAY_F1` | Layering | 6-hop chain, 3-8 min/hop, 13% decay |
| `D3_RT_A1` / `D3_RT_B1` | Round-Trip | Bilateral flows, 90-97% return |
| `D3_RT_A3→B3→C3→A3` | 3-Node Cycle | Triangle round-trip |
| `D3_STR01` – `D3_STR04` | Structuring | ₹9.5L–₹9.99L (below ₹10L threshold) |
| `D3_DORM01` – `D3_DORM03` | Dormancy | 200-day gap, then 20+ txns burst |
| `D3_FAN01` – `D3_FAN02` | Fan-Out | SOURCE role, 20-30 recipients |

---

## 🐳 Docker Deployment

```bash
cd fund-flow-tracker
docker build -t tracex .
docker run -p 8000:8000 tracex
```

---

## ⚠️ Known Limitations

- Trained on synthetic + IBM AML public dataset (no real bank data)
- Batch processing (not real-time streaming)
- No authentication on dashboard (acceptable for POC)
- Evidence PDF follows FIU-IND structure but is not legally certified

---

## 👥 Team

| Name | Role |
|------|------|
| [Name 1] | ML Pipeline & Ensemble |
| [Name 2] | Graph Engine & Backend |
| [Name 3] | Frontend & Visualization |
| [Name 4] | Data Engineering & Research |

---

## 📎 Links

- 🎥 **Demo Video:** [YouTube — Unlisted]
- 🎥 **Pitch Video:** [YouTube — Unlisted]
- 📧 **Contact:** [Team Email]

---

*PS3: Tracking of Funds within Bank for Fraud Detection — Union Bank × iDEA 2.0 Phase 2*
