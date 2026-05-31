# TraceX — AML Intelligence System (v3)

> Microservice-based AML detection engine with 5 independent fraud detectors, ensemble ML scoring, and regulatory evidence generation.

## Architecture

```
┌─────────────┐  ┌─────────────┐  ┌─────────────────┐  ┌──────────────────┐
│  Ingestion  │→│   Graph     │→│    Detection     │→│  Investigation   │
│   Service   │  │   Service   │  │     Service      │  │     Service      │
└─────────────┘  └─────────────┘  └─────────────────┘  └──────────────────┘
       ↕                ↕                  ↕                     ↕
╔═══════════════════════════════════════════════════════════════════════════╗
║                     Infrastructure Layer                                  ║
║   Event Bus (pub/sub)  │  Health Monitor (8 checkpoints)  │  Config      ║
╚═══════════════════════════════════════════════════════════════════════════╝
```

### Services
| Service | Purpose |
|---------|---------|
| **Ingestion** | Parses IBM AML, PaySim, generic CSV. Schema validation (CP-01). |
| **Graph** | NetworkX MultiDiGraph. Temporal BFS, cycle detection, random walk. |
| **Detection** | 5 detectors (Layering, Round-Trip, Structuring, Dormancy, Profile) + IF + XGBoost ensemble. |
| **Investigation** | Case lifecycle, alert triage, FIU-IND STR PDF generation (CP-08). |

### 5 Fraud Detectors
1. **Layering** — Multi-hop chains with amount decay
2. **Round-Trip** — Johnson's cycle detection, ≥85% amount return
3. **Structuring** — Below-threshold splitting (classic + daily aggregation)
4. **Dormancy** — Inactive accounts reactivated with burst activity
5. **Profile Mismatch** — Income, peer deviation, behavioural shift

### ML Pipeline
- **Isolation Forest** (unsupervised) — no labels needed
- **XGBoost** (supervised) — trained on REAL labels from IBM AML dataset (`is_laundering` column)
- **Ensemble** — ML 30% + Patterns 40% + Graph 30%

## Quick Start

```bash
# 1. Install dependencies
pip install -r requirements_v3.txt

# 2. Download IBM AML dataset
python scripts/download_data.py

# 3. Run Streamlit app
streamlit run app_v3.py

# OR run FastAPI server
uvicorn api.server_v3:app --reload --port 8000
```

## Dataset

**IBM Transactions for Anti Money Laundering** (Kaggle)
- 5M+ transactions, 5,100 labelled laundering cases
- 8 pattern types (fan-in, fan-out, cycle, scatter-gather, etc.)
- License: CDLA Sharing 1.0

## File Structure

```
fund-flow-tracker/
├── app_v3.py                    # Streamlit entry point
├── pages_v3/                    # Streamlit pages
├── api/server_v3.py             # FastAPI server
├── infrastructure/              # Event bus, config, health
├── services/
│   ├── common/                  # Models, constants
│   ├── ingestion/               # Data parsers
│   ├── graph/                   # Graph engine
│   ├── detection/               # 5 detectors + ensemble
│   └── investigation/           # Cases, alerts, evidence
├── scripts/download_data.py     # Dataset downloader
└── data/                        # Dataset files (gitignored)
```

## Health Checkpoints
| CP | Check |
|----|-------|
| CP-01 | Schema validation on ingest |
| CP-02 | Dead letter queue depth |
| CP-04 | Graph parity (nodes = accounts) |
| CP-05 | Confidence gate (ensemble threshold) |
| CP-08 | Evidence integrity (SHA-256 hash) |
