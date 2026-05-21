"""
TraceX — Fund Flow Intelligence System
Streamlit application entry point (v3 — microservice architecture).
"""
import logging
import os
import sys

import pandas as pd
import streamlit as st

# Project root on path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(levelname)s: %(message)s")

from services.ingestion import IngestionService
from services.graph import GraphService
from services.detection import DetectionService
from services.investigation import InvestigationService
from infrastructure.health import health

st.set_page_config(
    page_title="TraceX — Fund Flow Intelligence",
    page_icon="🏦",
    layout="wide",
    initial_sidebar_state="expanded",
)


@st.cache_resource(show_spinner="Building TraceX analysis engine...")
def build_system(source: str, filepath: str = None, _uploaded_df=None, max_rows: int = None):
    """Build the entire pipeline through the service layer."""
    ingestion = IngestionService()
    graph = GraphService()
    detection = DetectionService()
    investigation = InvestigationService()

    accounts_df, txns_df = ingestion.ingest(
        source=source,
        filepath=filepath,
        dataframe=_uploaded_df,
        max_rows=max_rows,
    )

    graph.build(accounts_df, txns_df)
    pipeline_summary = detection.run_full_pipeline(graph, accounts_df, txns_df)
    investigation.create_alerts_from_detections(detection.detection_results)

    return {
        "accounts_df": accounts_df,
        "transactions_df": txns_df,
        "graph_service": graph,
        "detection_service": detection,
        "investigation_service": investigation,
        "pipeline_summary": pipeline_summary,
    }


# ── Sidebar ──────────────────────────────────────────────────────────────
st.sidebar.title("🏦 TraceX")
st.sidebar.markdown("**Fund Flow Intelligence System**")
st.sidebar.markdown("*Microservice Architecture v3*")
st.sidebar.divider()

data_source = st.sidebar.radio(
    "Data Source",
    ["📊 IBM AML Dataset", "💳 PaySim Dataset", "📤 Upload CSV"],
    index=0,
)

filepath = None
uploaded_df = None
source_key = "ibm_aml"
max_rows = st.sidebar.number_input("Max rows (0 = all)", min_value=0, value=50000, step=10000)
if max_rows == 0:
    max_rows = None

if data_source == "📊 IBM AML Dataset":
    filepath = st.sidebar.text_input("Path to IBM AML CSV", value="data/HI-Small_Trans.csv")
    source_key = "ibm_aml"
elif data_source == "💳 PaySim Dataset":
    filepath = st.sidebar.text_input("Path to PaySim CSV", value="data/paysim.csv")
    source_key = "paysim"
elif data_source == "📤 Upload CSV":
    uploaded_file = st.sidebar.file_uploader("Upload transaction CSV", type=["csv"])
    if uploaded_file:
        uploaded_df = pd.read_csv(uploaded_file)
        source_key = "csv"
    else:
        st.info("Upload a CSV to begin analysis.")
        st.stop()

# ── Build system ─────────────────────────────────────────────────────────
try:
    system = build_system(
        source=source_key,
        filepath=filepath,
        _uploaded_df=uploaded_df,
        max_rows=max_rows,
    )
except FileNotFoundError as e:
    st.error(f"**Data file not found:** {e}")
    st.markdown("""
    ### Setup Instructions

    1. **Download the IBM AML dataset** from Kaggle:
       ```
       python scripts/download_data.py
       ```
       Or manually download from: https://www.kaggle.com/datasets/ealtman2019/ibm-transactions-for-anti-money-laundering-aml

    2. Place `HI-Small_Trans.csv` in the `data/` directory.

    3. Restart the app.
    """)
    st.stop()
except Exception as e:
    st.error(f"**Error building system:** {e}")
    st.stop()

# ── Unpack ───────────────────────────────────────────────────────────────
accounts_df = system["accounts_df"]
transactions_df = system["transactions_df"]
graph_svc = system["graph_service"]
detection_svc = system["detection_service"]
investigation_svc = system["investigation_service"]
summary = system["pipeline_summary"]

# Store in session state for pages
st.session_state["system"] = system

# ── Sidebar metrics ──────────────────────────────────────────────────────
st.sidebar.divider()
st.sidebar.metric("Accounts", f"{len(accounts_df):,}")
st.sidebar.metric("Transactions", f"{len(transactions_df):,}")
st.sidebar.metric("Anomalies", f"{summary.get('anomalies_flagged', 0):,}")

risk_dist = summary.get("risk_distribution", {})
st.sidebar.markdown("**Risk Distribution**")
col1, col2 = st.sidebar.columns(2)
col1.metric("🔴 Critical", risk_dist.get("critical", 0))
col1.metric("🟠 High", risk_dist.get("high", 0))
col2.metric("🟡 Medium", risk_dist.get("medium", 0))
col2.metric("🟢 Low", risk_dist.get("low", 0))

# ── Case management sidebar ─────────────────────────────────────────────
st.sidebar.divider()
case_stats = investigation_svc.get_case_stats()
st.sidebar.markdown("**📋 Cases**")
st.sidebar.write(f"Open: {case_stats.get('open_cases', 0)} | "
                 f"Investigating: {case_stats.get('investigating', 0)} | "
                 f"Escalated: {case_stats.get('escalated', 0)}")

# ── Health ───────────────────────────────────────────────────────────────
st.sidebar.divider()
h = health.get_health()
status_emoji = "🟢" if h["status"] == "healthy" else "🟡"
st.sidebar.markdown(f"**System Health:** {status_emoji} {h['status']}")

# ═══════════════════════════════════════════════════════════════════════════
# HOME PAGE
# ═══════════════════════════════════════════════════════════════════════════

st.title("🏦 TraceX — Fund Flow Intelligence System")
st.markdown("**Microservice-based AML detection engine with 5 independent fraud detectors.**")

# ── Key metrics ──────────────────────────────────────────────────────────
m1, m2, m3, m4, m5 = st.columns(5)
m1.metric("Accounts", f"{len(accounts_df):,}")
m2.metric("Transactions", f"{len(transactions_df):,}")
m3.metric("Anomalies Flagged", f"{summary.get('anomalies_flagged', 0):,}")
m4.metric("Avg Risk", f"{sum(detection_svc.risk_scores.values()) / max(len(detection_svc.risk_scores), 1):.1f}")
m5.metric("Active Alerts", f"{case_stats.get('total_alerts', 0):,}")

st.divider()

# ── Detection summary ───────────────────────────────────────────────────
st.subheader("Detection Pipeline Results")
det_counts = summary.get("detection_counts", {})
cols = st.columns(5)
det_labels = {
    "layering": ("🔗 Layering", "Multi-hop chains with amount decay"),
    "round_trip": ("🔄 Round-Trip", "Circular fund flows"),
    "structuring": ("💰 Structuring", "Below-threshold splitting"),
    "dormancy": ("💤 Dormancy", "Inactive accounts reactivated"),
    "profile_mismatch": ("👤 Profile", "Behaviour vs declared profile"),
}
for col, (det_type, (label, desc)) in zip(cols, det_labels.items()):
    count = det_counts.get(det_type, 0)
    col.metric(label, count, help=desc)

# ── ML metrics ───────────────────────────────────────────────────────────
st.divider()
st.subheader("ML Model Performance")

if detection_svc.fraud_metrics:
    mc1, mc2, mc3, mc4 = st.columns(4)
    fm = detection_svc.fraud_metrics
    mc1.metric("Precision", f"{fm.get('precision', 0):.1%}")
    mc2.metric("Recall", f"{fm.get('recall', 0):.1%}")
    mc3.metric("F1 Score", f"{fm.get('f1', 0):.1%}")
    mc4.metric("AUC-ROC", f"{fm.get('auc_roc', 0):.3f}")

    # Feature importance
    importances = detection_svc.fraud_classifier.get_feature_importance()
    if importances:
        import plotly.graph_objects as go
        sorted_imp = sorted(importances.items(), key=lambda x: x[1], reverse=True)[:15]
        fig = go.Figure(go.Bar(
            x=[v for _, v in sorted_imp],
            y=[k for k, _ in sorted_imp],
            orientation="h",
            marker_color="#1f77b4",
        ))
        fig.update_layout(
            title="Top 15 Feature Importances (XGBoost)",
            template="plotly_dark", height=400,
            margin=dict(l=200, r=20, t=40, b=20),
            yaxis=dict(autorange="reversed"),
        )
        st.plotly_chart(fig, use_container_width=True)
else:
    st.info("No labelled data available — XGBoost metrics not computed. "
            "Use IBM AML dataset for supervised metrics.")

# ── Architecture overview ────────────────────────────────────────────────
st.divider()
st.subheader("System Architecture")
st.markdown("""
| Service | Responsibility | Status |
|---------|---------------|--------|
| **Ingestion** | Data loading, schema validation, format parsing | ✅ Active |
| **Graph Engine** | Transaction graph (NetworkX), temporal BFS, cycle detection | ✅ Active |
| **Detection Engine** | 5 fraud detectors + Isolation Forest + XGBoost ensemble | ✅ Active |
| **Investigation** | Case management, alert triage, evidence generation | ✅ Active |
| **Event Bus** | In-process pub/sub (production: swap for Kafka) | ✅ Active |
| **Health Monitor** | 8 checkpoint system, DLQ monitoring, service heartbeats | ✅ Active |

Navigate to the pages in the sidebar to explore:
- **Graph Explorer** — Interactive fund flow visualization
- **Anomaly Dashboard** — ML-detected anomalies
- **Pattern Detector** — 5 detection pattern results
- **Profile Analyzer** — Income vs behaviour mismatches
- **Channel Analytics** — Transaction channel heatmaps
- **FIU Evidence** — Generate STR evidence packs
""")

# ── Health details ───────────────────────────────────────────────────────
with st.expander("System Health & Checkpoints"):
    h = health.get_health()
    st.json(h)
