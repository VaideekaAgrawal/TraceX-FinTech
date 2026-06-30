"""
TraceX REST API — FastAPI server backed by the microservice layer.

All business logic lives in services/. This layer only handles:
- HTTP routing and request/response serialisation
- CORS
- Health endpoints
"""

import base64
import logging
import os
import pathlib
import sys
import time
import traceback
import uuid
from typing import Any, Dict, List, Optional
from functools import lru_cache

import httpx
import pandas as pd
from cachetools import TTLCache
from fastapi import FastAPI, HTTPException, UploadFile, File, Form, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

# Configure logging FIRST so all service loggers output to console
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
    force=True,
)

# Project root on path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Load .env before any infrastructure imports so env vars are available to config.py
_env_path = os.path.join(os.path.dirname(__file__), '..', '.env')
if os.path.exists(_env_path):
    with open(_env_path) as _f:
        for _line in _f:
            _line = _line.strip()
            if _line and not _line.startswith('#') and '=' in _line:
                _k, _v = _line.split('=', 1)
                os.environ.setdefault(_k.strip(), _v.strip())

from infrastructure.config import OPENROUTER_API_KEY, OPENROUTER_MODEL
from infrastructure.event_bus import bus
from infrastructure.health import health
from services.ingestion import IngestionService
from services.graph import GraphService
from services.detection import DetectionService
from services.investigation import InvestigationService
from services.monitoring import monitor

logger = logging.getLogger(__name__)

app = FastAPI(title="TraceX API", version="3.0.0",
              description="TraceX AML Intelligence System — microservice API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Service instances ────────────────────────────────────────────────────
ingestion_svc = IngestionService()
graph_svc = GraphService()
detection_svc = DetectionService()
investigation_svc = InvestigationService()

# ── Response cache (TTL = 30s for expensive queries) ─────────────────────
_response_cache = TTLCache(maxsize=64, ttl=30)

# ── Shared state ─────────────────────────────────────────────────────────
_state: Dict[str, Any] = {}

# ── OpenRouter AI helper ──────────────────────────────────────────────────

_explain_cache: dict = {}


def _call_openrouter(prompt: str, max_tokens: int = 250) -> str:
    if not OPENROUTER_API_KEY:
        return "AI explanations not configured. Set OPENROUTER_API_KEY in .env"
    try:
        r = httpx.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {OPENROUTER_API_KEY}",
                "Content-Type": "application/json",
                "HTTP-Referer": "http://localhost:3000",
                "X-Title": "TraceX AML",
            },
            json={
                "model": OPENROUTER_MODEL,
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": max_tokens,
                "temperature": 0.3,
            },
            timeout=20.0,
        )
        r.raise_for_status()
        return r.json()["choices"][0]["message"]["content"].strip()
    except Exception as e:
        return f"Could not generate explanation: {str(e)}"


@app.on_event("startup")
async def _startup():
    """Ensure the database schema (including the cases table) is created on boot."""
    from infrastructure.database import get_database as _get_db
    _get_db()


def _require_ready():
    if not graph_svc.is_ready:
        raise HTTPException(503, "System not initialized. POST /api/init first.")


# ── Request models ───────────────────────────────────────────────────────

class InitRequest(BaseModel):
    source: str = "ibm_aml"
    filepath: Optional[str] = None
    max_rows: Optional[int] = None


class FundTrailRequest(BaseModel):
    account_id: str
    direction: str = "both"
    max_depth: int = 5


class EvidenceRequest(BaseModel):
    case_id: str
    account_ids: List[str]
    case_notes: str = ""


class CaseRequest(BaseModel):
    account_ids: List[str]
    typology: str
    priority: str = "P3"
    notes: str = ""


class CaseUpdateRequest(BaseModel):
    status: str
    notes: str = ""


class CaseResolveRequest(BaseModel):
    resolution: str
    is_true_positive: bool


class CaseCreate(BaseModel):
    case_id: str
    account_ids: List[str]
    risk_scores: Dict[str, float] = {}
    pattern_type: str = "manual"
    notes: str = ""
    investigator: str = "Unassigned"
    graph_snapshot: str = ""
    str_reference: str = ""


class CaseStatusUpdate(BaseModel):
    status: str  # open|in_progress|escalated|closed
    notes: str = ""


class RandomWalkRequest(BaseModel):
    start_node: str
    restart_prob: float = Field(default=0.15, ge=0.0, le=1.0)
    num_steps: int = Field(default=5000, ge=100, le=50000)


# ── Utility ──────────────────────────────────────────────────────────────

def _ts(val):
    if pd.isna(val):
        return None
    if hasattr(val, "isoformat"):
        return val.isoformat()
    return str(val)


def _safe(obj):
    if isinstance(obj, (pd.Timestamp, pd.Timedelta)):
        return obj.isoformat() if hasattr(obj, "isoformat") else str(obj)
    if hasattr(obj, "item"):
        return obj.item()
    return obj


def _risk_level(score: float) -> str:
    if score >= 76: return "CRITICAL"
    if score >= 51: return "HIGH"
    if score >= 26: return "MEDIUM"
    return "LOW"


def _risk_color(score: float) -> str:
    return {"LOW": "#2ecc71", "MEDIUM": "#f39c12", "HIGH": "#e67e22", "CRITICAL": "#e74c3c"}[_risk_level(score)]


# ═══════════════════════════════════════════════════════════════════════════
# ENDPOINTS
# ═══════════════════════════════════════════════════════════════════════════

# ── Health ────────────────────────────────────────────────────────────────

@app.get("/health")
async def health_check():
    return health.get_health()


@app.get("/health/live")
async def liveness():
    return {"status": "alive"}


@app.get("/health/ready")
async def readiness():
    return {"ready": graph_svc.is_ready}


# ── System init ──────────────────────────────────────────────────────────

@app.post("/api/init")
async def init_system(req: InitRequest):
    """Initialize the full pipeline from a data source."""
    global _state

    filepath = req.filepath
    if req.source == "ibm_aml" and not filepath:
        filepath = "data/HI-Small_Trans.csv"
    elif req.source == "paysim" and not filepath:
        filepath = "data/paysim.csv"

    accounts_df, txns_df = ingestion_svc.ingest(
        source=req.source, filepath=filepath, max_rows=req.max_rows,
    )

    graph_svc.build(accounts_df, txns_df)
    summary = detection_svc.run_full_pipeline(graph_svc, accounts_df, txns_df)
    investigation_svc.create_alerts_from_detections(detection_svc.detection_results)

    _state["accounts_df"] = accounts_df
    _state["transactions_df"] = txns_df
    _response_cache.clear()

    return {
        "status": "ok",
        "accounts": len(accounts_df),
        "transactions": len(txns_df),
        "pipeline_summary": summary,
    }


@app.post("/api/refresh")
async def refresh_from_db():
    """Rebuild the in-memory graph and run detection from existing DB data (no file needed)."""
    global _state
    from infrastructure.database import get_database
    import sqlite3

    db = get_database()

    # Load all accounts from DB
    with db._get_conn() as conn:
        acc_rows = conn.execute("SELECT * FROM accounts").fetchall()
        txn_rows = conn.execute("SELECT * FROM transactions LIMIT 200000").fetchall()

    if not acc_rows or not txn_rows:
        raise HTTPException(400, "No data in database. Upload a CSV first.")

    accounts_df = pd.DataFrame([dict(r) for r in acc_rows])
    txns_df = pd.DataFrame([dict(r) for r in txn_rows])

    # Convert timestamp strings to datetime (required by detection services)
    txns_df["timestamp"] = pd.to_datetime(txns_df["timestamp"], errors="coerce")

    # Ensure required column names match what the services expect
    col_map = {
        "account_id": "account_id",
        "account_type": "account_type",
        "branch_city": "branch_city",
        "occupation": "occupation",
        "income_bracket": "income_bracket",
        "declared_annual_income": "declared_annual_income",
        "risk_score": "risk_score",
        "risk_level": "risk_level",
        "role": "role",
    }
    for col in ["account_id", "account_type", "branch_city", "occupation",
                "income_bracket", "declared_annual_income", "risk_score", "risk_level", "role"]:
        if col not in accounts_df.columns:
            accounts_df[col] = "" if col not in ("risk_score", "declared_annual_income") else 0.0

    graph_svc.build(accounts_df, txns_df)
    summary = detection_svc.run_full_pipeline(graph_svc, accounts_df, txns_df)
    investigation_svc.create_alerts_from_detections(detection_svc.detection_results)

    _state["accounts_df"] = accounts_df
    _state["transactions_df"] = txns_df
    _response_cache.clear()

    return {
        "status": "ok",
        "accounts": len(accounts_df),
        "transactions": len(txns_df),
        "pipeline_summary": summary,
    }


@app.post("/api/upload")
async def upload_csv(file: UploadFile = File(...), max_rows: Optional[int] = None):
    """Upload a CSV and run the full pipeline."""
    global _state

    df = pd.read_csv(file.file)
    accounts_df, txns_df = ingestion_svc.ingest(
        source="csv", dataframe=df, max_rows=max_rows,
    )

    graph_svc.build(accounts_df, txns_df)
    summary = detection_svc.run_full_pipeline(graph_svc, accounts_df, txns_df)
    investigation_svc.create_alerts_from_detections(detection_svc.detection_results)

    _state["accounts_df"] = accounts_df
    _state["transactions_df"] = txns_df

    return {
        "status": "ok",
        "accounts": len(accounts_df),
        "transactions": len(txns_df),
        "pipeline_summary": summary,
    }


# ── Dashboard overview ───────────────────────────────────────────────────

@app.get("/api/overview")
async def get_overview():
    _require_ready()

    # Check cache first
    cache_key = "overview"
    if cache_key in _response_cache:
        return _response_cache[cache_key]

    graph_stats = graph_svc.get_stats()
    risk = detection_svc.risk_scores
    roles = detection_svc.roles
    accounts = _state.get("accounts_df")
    txns = _state.get("transactions_df")

    # Stats block matching frontend OverviewData.stats
    stats = {
        "num_nodes": graph_stats.get("num_nodes", 0),
        "num_edges": graph_stats.get("num_edges", 0),
        "num_components": graph_stats.get("num_components", 0),
        "density": graph_stats.get("density", 0),
        "avg_in_degree": graph_stats.get("avg_in_degree", 0),
        "avg_out_degree": graph_stats.get("avg_out_degree", 0),
    }

    # Risk distribution keyed as frontend expects (uppercase)
    risk_distribution = {
        "CRITICAL": sum(1 for s in risk.values() if s >= 76),
        "HIGH": sum(1 for s in risk.values() if 51 <= s < 76),
        "MEDIUM": sum(1 for s in risk.values() if 26 <= s < 51),
        "LOW": sum(1 for s in risk.values() if s < 26),
    }

    # Role distribution
    role_distribution = {}
    for r_info in roles.values():
        role = r_info.get("role", "UNKNOWN")
        role_distribution[role] = role_distribution.get(role, 0) + 1

    # Build detection types per account (for Patterns column in dashboard)
    det_types_by_account: dict = {}
    for det_type, dets in detection_svc.detection_results.items():
        for det in dets:
            for acc_id in det.account_ids:
                if acc_id not in det_types_by_account:
                    det_types_by_account[acc_id] = []
                if det_type not in det_types_by_account[acc_id]:
                    det_types_by_account[acc_id].append(det_type)

    # Top alerts — sorted by risk score desc
    top_alerts = []
    for acc_id, score in sorted(risk.items(), key=lambda x: x[1], reverse=True)[:50]:
        role_info = roles.get(acc_id, {"role": "UNKNOWN"})
        branch_city = ""
        acc_type = ""
        if accounts is not None:
            acc_row = accounts[accounts["account_id"] == acc_id]
            if len(acc_row) > 0:
                branch_city = str(acc_row.iloc[0].get("branch_city", "") or "")
                acc_type = str(acc_row.iloc[0].get("account_type", "") or "")
        top_alerts.append({
            "account_id": acc_id,
            "risk_score": round(score, 1),
            "risk_level": _risk_level(score),
            "risk_color": _risk_color(score),
            "role": role_info["role"],
            "branch_city": branch_city,
            "account_type": acc_type,
            "patterns": det_types_by_account.get(acc_id, []),
        })

    # Pattern counts
    det_summary = detection_svc.get_detection_summary()
    pattern_counts = {
        "layering": det_summary.get("layering", 0),
        "round_tripping": det_summary.get("round_trip", 0),
        "structuring": det_summary.get("structuring", 0),
        "dormant_activation": det_summary.get("dormancy", 0),
        "profile_mismatch": det_summary.get("profile_mismatch", 0),
    }

    # Total flagged (accounts with risk >= 51)
    total_flagged = risk_distribution["CRITICAL"] + risk_distribution["HIGH"]

    # Total amount
    total_amount = float(txns["amount"].sum()) if txns is not None and "amount" in txns.columns else 0

    result = {
        "stats": stats,
        "risk_distribution": risk_distribution,
        "role_distribution": role_distribution,
        "top_alerts": top_alerts,
        "pattern_counts": pattern_counts,
        "total_flagged": total_flagged,
        "total_anomalies": int(detection_svc.anomaly_results["is_anomaly"].sum()) if detection_svc.anomaly_results is not None else 0,
        "fraud_metrics": {k: _safe(v) for k, v in detection_svc.fraud_metrics.items()},
        "total_amount": total_amount,
        "avg_risk": round(sum(risk.values()) / max(len(risk), 1), 1),
    }
    _response_cache[cache_key] = result
    return result


# ── Accounts ─────────────────────────────────────────────────────────────

@app.get("/api/accounts")
async def list_accounts():
    _require_ready()
    accounts = _state["accounts_df"]
    txns = _state["transactions_df"]
    risk = detection_svc.risk_scores
    roles = detection_svc.roles
    anomaly = detection_svc.anomaly_results
    fraud = detection_svc.fraud_results

    # Pre-compute flows
    out_flow = txns.groupby("source_account")["amount"].sum()
    in_flow = txns.groupby("dest_account")["amount"].sum()
    txn_count_src = txns.groupby("source_account").size()
    txn_count_dst = txns.groupby("dest_account").size()

    # Pre-build O(1) lookup maps to avoid O(n²) DataFrame scans inside the loop
    anomaly_score_map = (
        anomaly.set_index("account_id")["anomaly_score"].to_dict()
        if anomaly is not None and not anomaly.empty else {}
    )

    results = []
    for _, row in accounts.iterrows():
        acc_id = row["account_id"]
        score = risk.get(acc_id, 0)
        role_info = roles.get(acc_id, {"role": "UNKNOWN", "confidence": 0})
        anom_score = anomaly_score_map.get(acc_id, 0)

        t_in = float(in_flow.get(acc_id, 0))
        t_out = float(out_flow.get(acc_id, 0))
        t_count = int(txn_count_src.get(acc_id, 0)) + int(txn_count_dst.get(acc_id, 0))

        results.append({
            "account_id": acc_id,
            "account_type": row.get("account_type", ""),
            "branch_city": row.get("branch_city", ""),
            "occupation": row.get("occupation", ""),
            "income_bracket": row.get("income_bracket", ""),
            "declared_annual_income": float(row.get("declared_annual_income", 0)),
            "total_in_flow": round(t_in, 2),
            "total_out_flow": round(t_out, 2),
            "txn_count": t_count,
            "risk_score": round(score, 1),
            "risk_level": _risk_level(score),
            "risk_color": _risk_color(score),
            "role": role_info["role"],
            "role_confidence": round(role_info.get("confidence", 0), 2),
            "anomaly_score": round(anom_score, 1),
            "is_new": bool(row.get("is_new", False)),
        })

    return sorted(results, key=lambda x: x["risk_score"], reverse=True)


@app.get("/api/accounts/{account_id}")
async def get_account(account_id: str):
    _require_ready()
    accounts = _state["accounts_df"]
    txns = _state["transactions_df"]
    risk = detection_svc.risk_scores
    roles = detection_svc.roles
    features = detection_svc.features_df
    anomaly = detection_svc.anomaly_results
    fraud = detection_svc.fraud_results

    row = accounts[accounts["account_id"] == account_id]
    if len(row) == 0:
        raise HTTPException(404, f"Account {account_id} not found")

    acc = {k: _safe(v) for k, v in row.iloc[0].to_dict().items()}
    score = risk.get(account_id, 0)
    role_info = roles.get(account_id, {"role": "UNKNOWN", "confidence": 0})

    feat = {}
    if features is not None and account_id in features.index:
        feat = {k: round(float(v), 4) for k, v in features.loc[account_id].items()}

    anom_score = 0
    if anomaly is not None:
        ar = anomaly[anomaly["account_id"] == account_id]
        anom_score = float(ar["anomaly_score"].iloc[0]) if len(ar) > 0 else 0

    fraud_prob = 0
    if fraud is not None:
        fr = fraud[fraud["account_id"] == account_id]
        fraud_prob = float(fr["fraud_prob"].iloc[0]) if len(fr) > 0 else 0

    # Confidence
    centrality = graph_svc.compute_centrality()
    det_flags = detection_svc.ensemble._build_flags(detection_svc.detection_results).get(account_id, {})
    conf_level, conf_count, indicators = detection_svc.ensemble.compute_confidence(
        account_id, det_flags, anom_score, fraud_prob,
        centrality["pagerank"].get(account_id, 0),
        centrality["betweenness"].get(account_id, 0),
    )

    acc_txns = txns[(txns["source_account"] == account_id) | (txns["dest_account"] == account_id)]
    total_amount = float(acc_txns["amount"].sum())
    n_cp = len(set(acc_txns["source_account"]) | set(acc_txns["dest_account"])) - 1
    priority = detection_svc.ensemble.compute_priority(score, conf_level, total_amount, max(n_cp, 1))

    recent = acc_txns.sort_values("timestamp", ascending=False).head(20)
    txn_list = [{
        "txn_id": t["txn_id"], "timestamp": _ts(t["timestamp"]),
        "source_account": t["source_account"], "dest_account": t["dest_account"],
        "amount": float(t["amount"]), "channel": t.get("channel", ""),
        "source_is_new": bool(t.get("source_is_new", False)),
        "dest_is_new": bool(t.get("dest_is_new", False)),
    } for _, t in recent.iterrows()]

    return {
        "account": acc,
        "risk_score": round(score, 1),
        "risk_level": _risk_level(score),
        "role": role_info["role"],
        "role_confidence": round(role_info.get("confidence", 0), 2),
        "anomaly_score": round(anom_score, 1),
        "fraud_probability": round(fraud_prob, 4),
        "features": feat,
        "confidence": {"level": conf_level, "count": conf_count, "indicators": indicators},
        "priority": priority,
        "total_amount": total_amount,
        "counterparties": n_cp,
        "recent_transactions": txn_list,
    }


@app.get("/api/explain/account/{account_id}")
def explain_account(account_id: str, force: bool = False):
    """Generate a human-readable AI explanation for why an account was flagged."""
    global _explain_cache

    if not force and account_id in _explain_cache:
        return {"account_id": account_id, "explanation": _explain_cache[account_id], "cached": True}

    # Gather all available data about this account
    acc_df = _state.get("accounts_df")
    txn_df = _state.get("transactions_df")

    if acc_df is None or txn_df is None:
        raise HTTPException(status_code=503, detail="System not initialized. POST /api/init first.")

    acc_row = acc_df[acc_df["account_id"] == account_id]
    if acc_row.empty:
        raise HTTPException(status_code=404, detail="Account not found")

    acc = acc_row.iloc[0]

    # Risk + ML scores
    risk_score = detection_svc.risk_scores.get(account_id, 0)
    risk_level = _risk_level(risk_score)

    # Anomaly score from DataFrame
    anomaly_score = 0
    if detection_svc.anomaly_results is not None:
        ar = detection_svc.anomaly_results[detection_svc.anomaly_results["account_id"] == account_id]
        anomaly_score = float(ar["anomaly_score"].iloc[0]) if len(ar) > 0 else 0

    # Fraud probability from DataFrame
    fraud_prob = 0
    if detection_svc.fraud_results is not None:
        fr = detection_svc.fraud_results[detection_svc.fraud_results["account_id"] == account_id]
        fraud_prob = float(fr["fraud_prob"].iloc[0]) if len(fr) > 0 else 0

    # Network role from detection_svc.roles
    role_info = detection_svc.roles.get(account_id, {})
    role = role_info.get("role", "UNKNOWN")
    role_conf = role_info.get("confidence", 0)

    # Detected patterns
    detected_patterns = []
    for det_type, dets in detection_svc.detection_results.items():
        for det in dets:
            if account_id in det.account_ids:
                detected_patterns.append(det_type)

    # Transaction stats
    acc_txns = txn_df[(txn_df["source_account"] == account_id) | (txn_df["dest_account"] == account_id)]
    txn_count = len(acc_txns)
    total_in = float(txn_df[txn_df["dest_account"] == account_id]["amount"].sum())
    total_out = float(txn_df[txn_df["source_account"] == account_id]["amount"].sum())

    declared_income = float(acc.get("declared_annual_income", 0) or 0)
    income_ratio = (total_in / declared_income) if declared_income > 0 else 0
    occupation = str(acc.get("occupation", "Unknown"))
    account_type = str(acc.get("account_type", "Unknown"))
    branch_city = str(acc.get("branch_city", "Unknown"))

    # Top features from ML (using features_df)
    features = {}
    if detection_svc.features_df is not None and account_id in detection_svc.features_df.index:
        features = {k: float(v) for k, v in detection_svc.features_df.loc[account_id].items()}
    top_features = sorted(features.items(), key=lambda x: abs(x[1]), reverse=True)[:5] if features else []

    # Unique counterparties
    counterparties = len(set(
        list(txn_df[txn_df["source_account"] == account_id]["dest_account"]) +
        list(txn_df[txn_df["dest_account"] == account_id]["source_account"])
    ))

    pattern_text = ", ".join(detected_patterns) if detected_patterns else "No specific pattern matched — ML model flagged anomalous behaviour"
    feature_text = "; ".join([f"{k.replace('_',' ')}: {v:.2f}" for k, v in top_features]) if top_features else "N/A"

    prompt = f"""You are a senior financial crime analyst writing investigation briefings for compliance officers at a bank. Write a clear, professional 3-4 sentence explanation of why account {account_id} has been flagged as suspicious by our AML system.

Account Profile:
- Account ID: {account_id}
- Account Type: {account_type}
- Branch: {branch_city}
- Occupation: {occupation}
- Declared Annual Income: ₹{declared_income:,.0f}
- Total Inflow: ₹{total_in:,.0f}
- Total Outflow: ₹{total_out:,.0f}
- Transaction Count: {txn_count}
- Unique Counterparties: {counterparties}
- Income-to-Volume Ratio: {income_ratio:.1f}x declared income
- Risk Score: {risk_score:.1f}/100 ({risk_level})
- Network Role: {role} (confidence: {role_conf:.0%})
- Anomaly Score: {anomaly_score:.1f}/100
- Fraud Probability: {fraud_prob:.1%}

AML Patterns Detected: {pattern_text}
Key Behavioural Indicators: {feature_text}

Instructions:
- Write as a compliance officer would for a Suspicious Activity Report
- Use specific numbers from the data above
- Explain what the patterns mean in plain English (e.g. "layering" = moving funds through multiple accounts to obscure origin)
- End with a concrete recommended investigative action
- Do NOT use bullet points or headers — write flowing prose only
- Do NOT mention model names like XGBoost or Isolation Forest
- Maximum 4 sentences"""

    explanation = _call_openrouter(prompt, max_tokens=300)
    _explain_cache[account_id] = explanation

    return {"account_id": account_id, "explanation": explanation, "cached": False}


# ── Graph ────────────────────────────────────────────────────────────────

@app.get("/api/graph")
async def get_graph(
    max_nodes: int = Query(default=40, ge=1, le=500),
    max_edges: int = Query(default=150, ge=1, le=2000),
):
    _require_ready()
    risk = detection_svc.risk_scores
    roles = detection_svc.roles

    # Select exactly max_nodes highest-risk accounts that exist in the graph.
    # This bypasses get_renderable_subgraph(), which internally caps its seed at
    # max_nodes // 2 and then slices an unordered set — causing the UI to show far
    # fewer nodes than requested even when max_nodes is set to a large value.
    G = graph_svc.graph.G
    sorted_accs = sorted(risk.items(), key=lambda x: x[1], reverse=True)
    selected = [acc for acc, _ in sorted_accs if acc in G][:max_nodes]
    sub = G.subgraph(selected)

    nodes = [{"id": n, "risk_score": round(risk.get(n, 0), 1),
              "risk_level": _risk_level(risk.get(n, 0)),
              "risk_color": _risk_color(risk.get(n, 0)),
              "role": roles.get(n, {}).get("role", "UNKNOWN")}
             for n in sub.nodes()]

    all_edges = [{"source": u, "target": v, "amount": float(d.get("amount", 0)),
              "channel": d.get("channel", ""), "timestamp": _ts(d.get("timestamp"))}
             for u, v, _, d in sub.edges(keys=True, data=True)]

    # Cap edges to prevent browser overload — keep highest-amount edges
    if len(all_edges) > max_edges:
        all_edges.sort(key=lambda e: e["amount"], reverse=True)
        all_edges = all_edges[:max_edges]

    return {"nodes": nodes, "edges": all_edges}


@app.get("/api/graph/ego/{account_id}")
async def get_ego(
    account_id: str,
    radius: int = Query(default=2, ge=1, le=5),
    max_edges: int = Query(default=100, ge=1, le=2000),
):
    _require_ready()
    risk = detection_svc.risk_scores
    roles = detection_svc.roles
    sub = graph_svc.get_ego_subgraph(account_id, radius)

    nodes = [{"id": n, "risk_score": round(risk.get(n, 0), 1),
              "risk_level": _risk_level(risk.get(n, 0)),
              "risk_color": _risk_color(risk.get(n, 0)),
              "role": roles.get(n, {}).get("role", "UNKNOWN"),
              "is_center": n == account_id}
             for n in sub.nodes()]

    all_edges = [{"source": u, "target": v, "amount": float(d.get("amount", 0)),
              "channel": d.get("channel", ""), "timestamp": _ts(d.get("timestamp"))}
             for u, v, _, d in sub.edges(keys=True, data=True)]

    # Cap edges to prevent browser overload
    if len(all_edges) > max_edges:
        all_edges.sort(key=lambda e: e["amount"], reverse=True)
        all_edges = all_edges[:max_edges]

    return {"nodes": nodes, "edges": all_edges, "center": account_id}


@app.post("/api/graph/fund-trail")
async def get_fund_trail(req: FundTrailRequest):
    _require_ready()
    result = graph_svc.get_fund_trail(req.account_id, req.direction, req.max_depth)
    if "trails" in result:
        for trail in result["trails"]:
            for hop in trail:
                hop["timestamp"] = _ts(hop.get("timestamp"))
    return result


@app.post("/api/graph/random-walk")
async def random_walk(req: RandomWalkRequest):
    _require_ready()
    probs = graph_svc.random_walk(req.start_node, req.restart_prob, req.num_steps)
    risk = detection_svc.risk_scores
    roles = detection_svc.roles
    accomplices = []
    for acc_id, prob in sorted(probs.items(), key=lambda x: x[1], reverse=True)[:20]:
        if acc_id == req.start_node:
            continue
        score = risk.get(acc_id, 0)
        role_info = roles.get(acc_id, {"role": "UNKNOWN"})
        accomplices.append({
            "account_id": acc_id,
            "visit_probability": round(prob, 6),
            "risk_score": round(score, 1),
            "risk_level": _risk_level(score),
            "role": role_info["role"],
        })
    return {"start_node": req.start_node, "accomplices": accomplices}


@app.get("/api/graph/pattern/{pattern_type}")
async def get_pattern_subgraph(pattern_type: str, max_nodes: int = 60, max_edges: int = 200):
    """
    Get the subgraph of accounts flagged for a specific pattern type.
    Returns nodes + edges suitable for Neo4j-style pattern visualization.
    Supported types: layering, round_trip, structuring, dormancy, profile_mismatch
    """
    _require_ready()
    risk = detection_svc.risk_scores
    roles = detection_svc.roles

    # Find accounts involved in this pattern
    dets = detection_svc.detection_results.get(pattern_type, [])
    if not dets:
        return {"nodes": [], "edges": [], "pattern_type": pattern_type, "count": 0}

    pattern_accounts = set()
    for d in dets:
        pattern_accounts.update(d.account_ids)

    # Limit to max_nodes
    sorted_accs = sorted(pattern_accounts, key=lambda a: risk.get(a, 0), reverse=True)
    selected = sorted_accs[:max_nodes]

    if not selected:
        return {"nodes": [], "edges": [], "pattern_type": pattern_type, "count": 0}

    # Build subgraph from those accounts
    G = graph_svc.graph.G
    valid_nodes = [n for n in selected if n in G]
    if not valid_nodes:
        return {"nodes": [], "edges": [], "pattern_type": pattern_type, "count": len(selected)}

    sub = G.subgraph(valid_nodes)

    nodes = [{
        "id": n,
        "risk_score": round(risk.get(n, 0), 1),
        "risk_level": _risk_level(risk.get(n, 0)),
        "risk_color": _risk_color(risk.get(n, 0)),
        "role": roles.get(n, {}).get("role", "UNKNOWN"),
        "flagged_pattern": pattern_type,
    } for n in sub.nodes()]

    all_edges = [{
        "source": u, "target": v,
        "amount": float(d.get("amount", 0)),
        "channel": d.get("channel", ""),
        "timestamp": _ts(d.get("timestamp")),
    } for u, v, _, d in sub.edges(keys=True, data=True)]

    # Cap edges
    if len(all_edges) > max_edges:
        all_edges.sort(key=lambda e: e["amount"], reverse=True)
        all_edges = all_edges[:max_edges]

    return {
        "nodes": nodes,
        "edges": all_edges,
        "pattern_type": pattern_type,
        "count": len(dets),
        "total_flagged_accounts": len(pattern_accounts),
    }


# ── Detection results ───────────────────────────────────────────────────

@app.get("/api/detections")
async def get_detections():
    _require_ready()
    return {
        det_type: [d.to_dict() for d in dets]
        for det_type, dets in detection_svc.detection_results.items()
    }


@app.get("/api/detections/{detection_type}")
async def get_detection_type(detection_type: str):
    _require_ready()
    dets = detection_svc.detection_results.get(detection_type, [])
    return [d.to_dict() for d in dets]


@app.get("/api/model-metrics")
async def get_model_metrics():
    _require_ready()
    return {
        "isolation_forest": {
            "method": "Unsupervised",
            "contamination": f"{detection_svc.anomaly_detector.model.contamination:.0%}",
            "accounts_flagged": int(detection_svc.anomaly_results["is_anomaly"].sum()) if detection_svc.anomaly_results is not None else 0,
        },
        "xgboost": {
            "method": "Supervised (trained on labelled data)",
            **detection_svc.fraud_metrics,
            "feature_importance": detection_svc.fraud_classifier.get_feature_importance(),
        },
    }


# ── Investigation ───────────────────────────────────────────────────────

@app.get("/api/alerts")
async def list_alerts(status: Optional[str] = None):
    return [a.to_dict() for a in investigation_svc.list_alerts(status)]


@app.post("/api/cases")
def create_case(body: CaseCreate):
    """Create a new investigation case (SQLite-persisted)."""
    db = get_database()
    return db.create_case(body.dict())


@app.get("/api/cases")
def list_cases():
    """List all cases, newest first (SQLite-persisted)."""
    db = get_database()
    return db.get_cases()


@app.get("/api/cases/{case_id}")
def get_case(case_id: str):
    """Retrieve a single case by ID."""
    db = get_database()
    case = db.get_case(case_id)
    if not case:
        raise HTTPException(404, f"Case {case_id} not found")
    return case


@app.put("/api/cases/{case_id}/status")
def update_case_status(case_id: str, body: CaseStatusUpdate):
    """Update case status and notes."""
    db = get_database()
    case = db.update_case_status(case_id, body.status, body.notes)
    if not case:
        raise HTTPException(404, f"Case {case_id} not found")
    return case


@app.post("/api/evidence")
async def generate_evidence(req: EvidenceRequest):
    _require_ready()
    pack = investigation_svc.generate_evidence(
        req.case_id, req.account_ids,
        graph_svc.graph, detection_svc.risk_scores,
        detection_svc.detection_results,
        _state["transactions_df"], _state["accounts_df"],
        req.case_notes,
    )
    return {
        "case_id": pack.case_id,
        "str_reference": pack.str_reference,
        "json_hash": pack.json_hash,
        "pdf_base64": base64.b64encode(pack.pdf_bytes).decode(),
        "generated_at": pack.generated_at,
    }


# ── Event bus stats ──────────────────────────────────────────────────────

@app.get("/api/bus/stats")
async def bus_stats():
    return bus.get_stats()


@app.get("/api/bus/dlq")
async def dlq_peek():
    items = bus.dlq.peek(20)
    return [{"event_id": i["event"]["event_id"], "error": i["error"],
             "consumer": i["consumer"], "failed_at": i["failed_at"]}
            for i in items if isinstance(i.get("event"), dict) or hasattr(i.get("event"), "event_id")]


# ═══════════════════════════════════════════════════════════════════════════
# FRONTEND-COMPATIBLE ENDPOINTS (Next.js dashboard)
# ═══════════════════════════════════════════════════════════════════════════


class EvidenceGenerateRequest(BaseModel):
    case_id: str
    account_ids: List[str]
    pattern_type: str = "Layering"
    case_notes: str = ""


@app.get("/api/health")
async def api_health():
    """Health endpoint expected by frontend."""
    return {
        "status": "ok",
        "initialized": graph_svc.is_ready,
        "accounts": len(_state.get("accounts_df", [])),
        "transactions": len(_state.get("transactions_df", [])),
    }


@app.get("/api/transactions")
async def get_transactions(limit: int = 100, offset: int = 0):
    """Paginated transaction list."""
    _require_ready()
    txns = _state["transactions_df"]
    total = len(txns)
    page = txns.iloc[offset:offset + limit]
    return {
        "total": total,
        "transactions": [{
            "txn_id": str(r.get("txn_id", "")),
            "timestamp": _ts(r.get("timestamp")),
            "source_account": r.get("source_account", ""),
            "dest_account": r.get("dest_account", ""),
            "amount": float(r.get("amount", 0)),
            "channel": r.get("channel", ""),
            "txn_type": r.get("txn_type", ""),
        } for _, r in page.iterrows()],
    }


@app.get("/api/anomaly")
async def get_anomaly():
    """Anomaly detection data for the frontend dashboard."""
    _require_ready()
    anomaly = detection_svc.anomaly_results
    features = detection_svc.features_df
    fraud = detection_svc.fraud_results
    risk = detection_svc.risk_scores
    roles = detection_svc.roles

    # Anomaly scores
    anomaly_scores = []
    if anomaly is not None:
        for _, row in anomaly.iterrows():
            anomaly_scores.append({
                "account_id": row["account_id"],
                "anomaly_score": round(float(row["anomaly_score"]), 2),
            })

    # Feature importance from XGBoost
    feature_importance = detection_svc.fraud_classifier.get_feature_importance()

    # Pre-build O(1) lookup maps — avoids O(n²) DataFrame scans inside the loop
    anom_score_map = (
        anomaly.set_index("account_id")["anomaly_score"].to_dict()
        if anomaly is not None and not anomaly.empty else {}
    )
    fraud_prob_map = (
        fraud.set_index("account_id")["fraud_prob"].to_dict()
        if fraud is not None and not fraud.empty else {}
    )

    # Compute centrality once for all accounts — not per-account
    centrality = graph_svc.compute_centrality()
    all_det_flags = detection_svc.ensemble._build_flags(detection_svc.detection_results)

    # Investigation queue — merge risk, anomaly, fraud, roles
    queue = []
    accounts_df = _state.get("accounts_df")
    txns_df = _state.get("transactions_df")
    branch_city_map = (
        dict(zip(accounts_df["account_id"], accounts_df.get("branch_city", "")))
        if accounts_df is not None else {}
    )
    for acc_id, score in sorted(risk.items(), key=lambda x: x[1], reverse=True)[:200]:
        role_info = roles.get(acc_id, {"role": "NORMAL", "confidence": 0})
        anom_score = anom_score_map.get(acc_id, 0.0)
        fraud_prob = fraud_prob_map.get(acc_id, 0.0)

        # Confidence
        det_flags = all_det_flags.get(acc_id, {})
        conf_level, conf_count, indicators = detection_svc.ensemble.compute_confidence(
            acc_id, det_flags, anom_score, fraud_prob,
            centrality["pagerank"].get(acc_id, 0),
            centrality["betweenness"].get(acc_id, 0),
        )
        # Total amount
        total_amount = 0.0
        if txns_df is not None:
            acc_txns = txns_df[(txns_df["source_account"] == acc_id) | (txns_df["dest_account"] == acc_id)]
            total_amount = float(acc_txns["amount"].sum())
        n_cp = 1
        priority = detection_svc.ensemble.compute_priority(score, conf_level, total_amount, n_cp)

        branch_city = branch_city_map.get(acc_id, "")

        queue.append({
            "account_id": acc_id,
            "risk_score": round(score, 1),
            "risk_level": _risk_level(score),
            "risk_color": _risk_color(score),
            "role": role_info["role"],
            "priority": priority,
            "confidence_level": conf_level,
            "confidence_count": conf_count,
            "indicators": indicators,
            "anomaly_score": round(anom_score, 1),
            "fraud_probability": round(fraud_prob, 4),
            "total_amount": round(total_amount, 2),
            "branch_city": branch_city,
        })

    # Speed alerts — derive from layering detections (rapid multi-hop chains)
    speed_alerts = []
    layering = detection_svc.detection_results.get("layering", [])
    for det in layering[:20]:
        d = det.details
        hops = d.get("hops", 0)
        time_span = d.get("time_span_minutes", 0)
        if hops > 0 and time_span > 0:
            avg_min_per_hop = time_span / hops
            category = "ABNORMAL" if avg_min_per_hop < 2 else "VERY_FAST" if avg_min_per_hop < 5 else "FAST"
            speed_alerts.append({
                "accounts": d.get("accounts", det.account_ids),
                "category": category,
                "label": f"{hops}-hop chain in {time_span:.0f} min",
                "color": "#ef4444" if category == "ABNORMAL" else "#f97316" if category == "VERY_FAST" else "#eab308",
                "avg_minutes_per_hop": round(avg_min_per_hop, 1),
                "total_minutes": round(time_span, 1),
                "hops": hops,
                "total_amount": float(d.get("total_amount", 0)),
            })

    return {
        "anomaly_scores": anomaly_scores,
        "feature_importance": feature_importance,
        "investigation_queue": queue,
        "speed_alerts": speed_alerts,
    }


@app.get("/api/patterns")
async def get_patterns():
    """All detected patterns for the Pattern Detector page."""
    _require_ready()
    patterns = detection_svc.get_all_patterns()

    # Ensure every pattern item has account_ids for the frontend
    # The profile_mismatch detector returns details without account references
    for det_type, detections in detection_svc.detection_results.items():
        key = det_type
        if key == "round_trip":
            key = "round_tripping"
        elif key == "dormancy":
            key = "dormant_activation"

        if key in patterns and isinstance(patterns[key], list):
            # Rebuild with account_ids injected
            enriched = []
            for det in detections:
                item = dict(det.details)
                item["account_ids"] = det.account_ids
                item["severity"] = det.severity
                item["score"] = det.score
                enriched.append(item)
            patterns[key] = enriched

    # Build flagged accounts list
    flagged = set()
    for dets in detection_svc.detection_results.values():
        for d in dets:
            flagged.update(d.account_ids)
    return {
        "patterns": patterns,
        "flagged_accounts": list(flagged),
    }


@app.get("/api/patterns/first-suspicious/{account_id}")
async def get_first_suspicious(account_id: str):
    """Find the first suspicious transaction for an account."""
    _require_ready()
    txns = _state["transactions_df"]
    acc_txns = txns[(txns["source_account"] == account_id) | (txns["dest_account"] == account_id)].copy()
    if len(acc_txns) == 0:
        return {"found": False}

    acc_txns["timestamp"] = pd.to_datetime(acc_txns["timestamp"], errors="coerce")
    acc_txns = acc_txns.sort_values("timestamp")

    # Find first suspicious via z-score on amounts
    amounts = acc_txns["amount"].values
    if len(amounts) < 3:
        return {"found": False}

    mean_amt = float(amounts.mean())
    std_amt = float(amounts.std())
    if std_amt == 0:
        return {"found": False}

    for _, row in acc_txns.iterrows():
        z = (float(row["amount"]) - mean_amt) / std_amt
        if abs(z) > 2.5:
            return {
                "found": True,
                "data": {
                    "txn_id": str(row.get("txn_id", "")),
                    "timestamp": _ts(row.get("timestamp")),
                    "amount": float(row["amount"]),
                    "z_score": round(z, 3),
                    "detection_method": "Z-score outlier (>2.5σ)",
                    "source_account": row.get("source_account", ""),
                    "dest_account": row.get("dest_account", ""),
                    "channel": row.get("channel", ""),
                },
            }

    # If no z-score outlier, check if account is flagged by detections
    flagged = set()
    for dets in detection_svc.detection_results.values():
        for d in dets:
            if account_id in d.account_ids:
                flagged.add(d.detection_type)

    if flagged:
        first_txn = acc_txns.iloc[0]
        return {
            "found": True,
            "data": {
                "txn_id": str(first_txn.get("txn_id", "")),
                "timestamp": _ts(first_txn.get("timestamp")),
                "amount": float(first_txn["amount"]),
                "z_score": 0.0,
                "detection_method": f"Pattern detection: {', '.join(flagged)}",
            },
        }

    return {"found": False}


@app.get("/api/profile")
async def get_profile():
    """Profile analysis — income vs volume scatter and mismatches."""
    _require_ready()
    accounts = _state["accounts_df"]
    txns = _state["transactions_df"]
    risk = detection_svc.risk_scores

    # Compute actual volume per account
    volume = txns.groupby("source_account")["amount"].sum()
    volume_in = txns.groupby("dest_account")["amount"].sum()
    total_volume = volume.add(volume_in, fill_value=0)

    scatter_data = []
    mismatches = []

    for _, row in accounts.iterrows():
        acc_id = row["account_id"]
        declared = float(row.get("declared_annual_income", 0))
        actual = float(total_volume.get(acc_id, 0))
        occupation = str(row.get("occupation", "Unknown"))
        income_bracket = str(row.get("income_bracket", "Unknown"))

        if declared <= 0:
            continue

        ratio = actual / declared if declared > 0 else 0
        scatter_data.append({
            "account_id": acc_id,
            "declared_income": declared,
            "actual_volume": round(actual, 2),
            "occupation": occupation,
            "income_bracket": income_bracket,
            "ratio": round(ratio, 2),
        })

        if ratio > 3.0:
            mismatches.append({
                "account_id": acc_id,
                "occupation": occupation,
                "income_bracket": income_bracket,
                "declared_income": declared,
                "actual_volume": round(actual, 2),
                "ratio": round(ratio, 2),
                "risk_score": round(risk.get(acc_id, 0), 1),
            })

    # Sort mismatches by ratio desc
    mismatches.sort(key=lambda x: x["ratio"], reverse=True)
    return {
        "scatter_data": scatter_data[:500],  # Limit for frontend performance
        "mismatches": mismatches[:100],
    }


@app.get("/api/profile/{account_id}")
async def get_profile_peer(account_id: str):
    """Peer group analysis for a specific account."""
    _require_ready()
    accounts = _state["accounts_df"]
    txns = _state["transactions_df"]

    acc_row = accounts[accounts["account_id"] == account_id]
    if len(acc_row) == 0:
        raise HTTPException(404, f"Account {account_id} not found")

    acc = acc_row.iloc[0]
    occupation = str(acc.get("occupation", "Unknown"))
    income_bracket = str(acc.get("income_bracket", "Unknown"))
    declared = float(acc.get("declared_annual_income", 0))

    # Compute volume
    volume = txns.groupby("source_account")["amount"].sum()
    volume_in = txns.groupby("dest_account")["amount"].sum()
    total_volume = volume.add(volume_in, fill_value=0)
    actual = float(total_volume.get(account_id, 0))

    # Find peers (same occupation + income bracket)
    peers = accounts[(accounts["occupation"] == occupation) & (accounts["income_bracket"] == income_bracket)]
    peer_volumes = [float(total_volume.get(pid, 0)) for pid in peers["account_id"] if pid != account_id]

    import statistics
    peer_mean = statistics.mean(peer_volumes) if peer_volumes else 0
    peer_std = statistics.stdev(peer_volumes) if len(peer_volumes) > 1 else 1
    z_score = (actual - peer_mean) / peer_std if peer_std > 0 else 0

    return {
        "account_id": account_id,
        "occupation": occupation,
        "income_bracket": income_bracket,
        "declared_income": declared,
        "actual_volume": round(actual, 2),
        "peer_mean": round(peer_mean, 2),
        "peer_std": round(peer_std, 2),
        "z_score": round(z_score, 2),
        "peer_count": len(peer_volumes),
    }


@app.get("/api/channels")
async def get_channels():
    """Channel analytics data."""
    _require_ready()
    txns = _state["transactions_df"]

    if "channel" not in txns.columns:
        return {"summary": [], "sankey": [], "heatmap": [], "suspicious": []}

    # Summary per channel
    ch_summary = txns.groupby("channel").agg(
        count=("amount", "count"),
        total_amount=("amount", "sum"),
        avg_amount=("amount", "mean"),
        max_amount=("amount", "max"),
    ).reset_index()
    summary = [{
        "channel": row["channel"],
        "count": int(row["count"]),
        "total_amount": round(float(row["total_amount"]), 2),
        "avg_amount": round(float(row["avg_amount"]), 2),
        "max_amount": round(float(row["max_amount"]), 2),
    } for _, row in ch_summary.iterrows()]

    # Sankey-style flows (source_type → channel → dest_type)
    accounts = _state["accounts_df"]
    type_map = dict(zip(accounts["account_id"], accounts.get("account_type", "Unknown")))
    txns_sample = txns.head(50000)  # limit for performance
    txns_sample = txns_sample.copy()
    txns_sample["source_type"] = txns_sample["source_account"].map(type_map).fillna("Unknown")
    txns_sample["dest_type"] = txns_sample["dest_account"].map(type_map).fillna("Unknown")
    sankey_raw = txns_sample.groupby(["source_type", "channel", "dest_type"]).agg(
        count=("amount", "count"), total=("amount", "sum")
    ).reset_index()
    sankey = [{
        "source_type": row["source_type"], "channel": row["channel"],
        "dest_type": row["dest_type"], "count": int(row["count"]),
        "total": round(float(row["total"]), 2),
    } for _, row in sankey_raw.head(50).iterrows()]

    # Heatmap (channel × hour)
    heatmap = []
    txns_ts = txns.copy()
    txns_ts["timestamp"] = pd.to_datetime(txns_ts["timestamp"], errors="coerce")
    txns_ts["hour"] = txns_ts["timestamp"].dt.hour
    hm_raw = txns_ts.groupby(["channel", "hour"]).size().reset_index(name="count")
    heatmap = [{"channel": row["channel"], "hour": int(row["hour"]), "count": int(row["count"])}
               for _, row in hm_raw.iterrows()]

    # Suspicious channel usage (channels used by flagged accounts)
    flagged_accs = set()
    for dets in detection_svc.detection_results.values():
        for d in dets:
            flagged_accs.update(d.account_ids)

    suspicious = []
    if flagged_accs:
        flagged_txns = txns[txns["source_account"].isin(flagged_accs)]
        if len(flagged_txns) > 0 and "channel" in flagged_txns.columns:
            sus_ch = flagged_txns.groupby("channel").agg(
                count=("amount", "count"),
                total=("amount", "sum"),
                unique_accounts=("source_account", "nunique"),
            ).reset_index()
            suspicious = [{
                "channel": row["channel"], "count": int(row["count"]),
                "total": round(float(row["total"]), 2),
                "unique_accounts": int(row["unique_accounts"]),
            } for _, row in sus_ch.iterrows()]

    return {"summary": summary, "sankey": sankey, "heatmap": heatmap, "suspicious": suspicious}


@app.post("/api/evidence/generate")
async def generate_evidence_v2(req: EvidenceGenerateRequest):
    """Generate evidence pack — frontend-compatible endpoint."""
    _require_ready()
    pack = investigation_svc.generate_evidence(
        req.case_id, req.account_ids,
        graph_svc.graph, detection_svc.risk_scores,
        detection_svc.detection_results,
        _state["transactions_df"], _state["accounts_df"],
        req.case_notes,
    )

    # Build summary for frontend
    txns = _state["transactions_df"]
    acc_txns = txns[txns["source_account"].isin(req.account_ids) | txns["dest_account"].isin(req.account_ids)]
    risk = detection_svc.risk_scores
    summary = {
        "total_transactions": int(len(acc_txns)),
        "total_amount": round(float(acc_txns["amount"].sum()), 2) if len(acc_txns) > 0 else 0,
        "max_risk_score": round(max((risk.get(a, 0) for a in req.account_ids), default=0), 1),
        "pattern_type": req.pattern_type,
        "accounts_investigated": len(req.account_ids),
    }

    return {
        "case_id": pack.case_id,
        "summary": summary,
        "pdf_base64": base64.b64encode(pack.pdf_bytes).decode(),
        "json_data": pack.json_payload if pack.json_payload else "{}",
    }


# ── Monitoring & Observability ───────────────────────────────────────────

@app.get("/api/metrics")
async def get_metrics():
    """Pipeline observability metrics and alerts."""
    return monitor.get_metrics()


@app.post("/api/metrics/acknowledge/{alert_index}")
async def acknowledge_alert(alert_index: int):
    """Acknowledge an alert."""
    success = monitor.acknowledge_alert(alert_index)
    if not success:
        raise HTTPException(404, "Alert not found")
    return {"acknowledged": True}


# ═══════════════════════════════════════════════════════════════════════════
# EOD INGESTION & DATABASE ENDPOINTS (Production-grade)
# ═══════════════════════════════════════════════════════════════════════════

from services.ingestion.eod_service import EODIngestionService
from infrastructure.database import get_database

eod_svc = EODIngestionService()


class IngestRequest(BaseModel):
    filepath: str
    date: Optional[str] = None
    source: str = "bank_system"
    max_rows: Optional[int] = None
    force: bool = False


_PROJECT_ROOT = pathlib.Path(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_ALLOWED_INGEST_DIRS = [
    _PROJECT_ROOT / "data",
    _PROJECT_ROOT / "data" / "uploads",
]


def _safe_ingest_path(filepath: str) -> pathlib.Path:
    """Validate that the requested filepath is within an allowed directory."""
    try:
        resolved = pathlib.Path(filepath).resolve()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid file path")
    allowed = any(
        str(resolved).startswith(str(d.resolve()))
        for d in _ALLOWED_INGEST_DIRS
    )
    if not allowed:
        raise HTTPException(status_code=400, detail="File path is outside allowed directories")
    if not resolved.exists():
        raise HTTPException(status_code=404, detail="File not found")
    return resolved


@app.post("/api/ingest")
async def ingest_eod(req: IngestRequest):
    """
    Ingest a daily EOD transaction CSV file (by path on server).

    Performs incremental analysis:
    - New accounts: detect patterns on today's data
    - Existing accounts: detect patterns on today + last 7 days
    """
    safe_path = _safe_ingest_path(req.filepath)
    try:
        result = eod_svc.ingest_daily_file(
            filepath=str(safe_path),
            date=req.date,
            max_rows=req.max_rows,
            force=req.force,
        )
        return result
    except FileNotFoundError as e:
        raise HTTPException(404, str(e))
    except ValueError as e:
        raise HTTPException(400, str(e))
    except Exception as e:
        logger.error("Ingestion failed: %s", e)
        raise HTTPException(500, f"Ingestion failed: {str(e)}")


@app.post("/api/ingest/upload")
async def ingest_upload(
    file: UploadFile = File(...),
    date: Optional[str] = Form(None),
    force: bool = Form(False),
):
    """
    Upload a CSV file for EOD ingestion via multipart form.
    The file is saved temporarily, processed, and results returned.
    After ingestion, the in-memory graph is refreshed with the new data.
    """
    import tempfile
    import shutil

    original_name = file.filename or "upload.csv"
    basename = os.path.basename(original_name)
    if not basename.lower().endswith(".csv"):
        raise HTTPException(400, "Only CSV files are accepted")

    # Use a UUID prefix to prevent path traversal and filename collisions
    safe_name = f"{uuid.uuid4().hex}_{basename}"

    # Save uploaded file to data/uploads/
    upload_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "uploads")
    os.makedirs(upload_dir, exist_ok=True)
    dest_path = os.path.join(upload_dir, safe_name)

    try:
        with open(dest_path, "wb") as f:
            shutil.copyfileobj(file.file, f)
    except Exception as e:
        raise HTTPException(500, f"Failed to save file: {str(e)}")
    finally:
        file.file.close()

    # Run ingestion
    try:
        result = eod_svc.ingest_daily_file(
            filepath=dest_path,
            date=date,
            force=force,
        )

        # After successful ingestion, always run the full pipeline to update in-memory state
        if result.get("status") in ("completed", "skipped"):
            try:
                # Re-ingest the uploaded file through the main ingestion service to get
                # properly typed DataFrames, then rebuild graph + run full detection.
                # Auto-detect format: try ibm_aml (our generated CSV format) first,
                # fall back to generic csv parser for custom uploads.
                try:
                    accounts_df, txns_df = ingestion_svc.ingest(
                        source="ibm_aml", filepath=dest_path
                    )
                    logger.info("Parsed upload as IBM-AML format")
                except Exception:
                    accounts_df, txns_df = ingestion_svc.ingest(
                        source="csv", filepath=dest_path
                    )
                    logger.info("Parsed upload as generic CSV format")
                graph_svc.build(accounts_df, txns_df)
                detection_svc.run_full_pipeline(graph_svc, accounts_df, txns_df)
                investigation_svc.create_alerts_from_detections(detection_svc.detection_results)
                # Store DataFrames in shared state so /api/overview etc. work immediately
                _state["accounts_df"] = accounts_df
                _state["transactions_df"] = txns_df
                # Clear response cache so next requests get fresh data
                _response_cache.clear()
                result["system_refreshed"] = True
                logger.info("System state refreshed after ingestion upload (%d accounts, %d txns)",
                            len(accounts_df), len(txns_df))
            except Exception as refresh_err:
                logger.warning("Could not refresh in-memory state: %s", refresh_err)
                result["system_refreshed"] = False
                result["refresh_warning"] = str(refresh_err)

        return result
    except FileNotFoundError as e:
        raise HTTPException(404, str(e))
    except ValueError as e:
        raise HTTPException(400, str(e))
    except Exception as e:
        logger.error("Upload ingestion failed: %s", e)
        raise HTTPException(500, f"Ingestion failed: {str(e)}")


@app.get("/api/ingest/status")
async def ingestion_status():
    """Get ingestion pipeline status and history."""
    return eod_svc.get_ingestion_status()


@app.get("/api/ingest/history")
async def ingestion_history():
    """Get recent ingestion history."""
    db = get_database()
    return db.get_ingestion_history(limit=50)


# ── Filtered Graph Endpoints ─────────────────────────────────────────────

@app.get("/api/graph/filtered")
async def get_graph_filtered(
    risk_min: float = Query(default=0, ge=0, le=100),
    risk_max: float = Query(default=100, ge=0, le=100),
    pattern: Optional[str] = None,
    since: Optional[str] = None,
    until: Optional[str] = None,
    max_nodes: int = Query(default=80, ge=1, le=500),
    role: Optional[str] = None,
):
    """
    Get filtered graph from the in-memory graph engine.
    Supports filtering by risk level, pattern type, time range, role.
    """
    _require_ready()
    risk = detection_svc.risk_scores
    roles = detection_svc.roles

    # Filter accounts by risk range
    filtered_accounts = [
        acc_id for acc_id, score in risk.items()
        if risk_min <= score <= risk_max
    ]

    # Filter by role if specified
    if role:
        filtered_accounts = [
            acc_id for acc_id in filtered_accounts
            if roles.get(acc_id, {}).get("role", "UNKNOWN") == role.upper()
        ]

    # Filter by pattern if specified
    if pattern:
        pattern_accounts = set()
        dets = detection_svc.detection_results.get(pattern, [])
        for d in dets:
            pattern_accounts.update(d.account_ids)
        filtered_accounts = [a for a in filtered_accounts if a in pattern_accounts]

    # Sort by risk score desc and limit
    filtered_accounts.sort(key=lambda a: risk.get(a, 0), reverse=True)
    filtered_accounts = filtered_accounts[:max_nodes]

    if not filtered_accounts:
        return {"nodes": [], "edges": [], "meta": {"total_matching": 0}}

    # Build subgraph from in-memory graph
    sub = graph_svc.graph.G.subgraph(filtered_accounts)

    nodes = [{
        "id": n,
        "risk_score": round(risk.get(n, 0), 1),
        "risk_level": _risk_level(risk.get(n, 0)),
        "risk_color": _risk_color(risk.get(n, 0)),
        "role": roles.get(n, {}).get("role", "UNKNOWN"),
    } for n in sub.nodes()]

    since_ts = pd.Timestamp(since) if since else None
    until_ts = pd.Timestamp(until) if until else None

    edges = []
    for u, v, _, d in sub.edges(keys=True, data=True):
        ts = d.get("timestamp")
        # Apply time filter if specified
        if since_ts or until_ts:
            try:
                ts_val = pd.Timestamp(ts) if ts is not None else None
            except Exception:
                ts_val = None
            if since_ts and (ts_val is None or ts_val < since_ts):
                continue
            if until_ts and (ts_val is None or ts_val > until_ts):
                continue
        edges.append({
            "source": u, "target": v,
            "amount": float(d.get("amount", 0)),
            "channel": d.get("channel", ""),
            "timestamp": _ts(ts),
        })

    # Cap edges to prevent browser overload
    if len(edges) > 300:
        edges.sort(key=lambda e: e["amount"], reverse=True)
        edges = edges[:300]

    return {
        "nodes": nodes,
        "edges": edges,
        "meta": {
            "total_matching": len(filtered_accounts),
            "nodes_returned": len(nodes),
            "edges_returned": len(edges),
        },
    }


# ── Paginated Transactions with Filters ──────────────────────────────────

@app.get("/api/transactions/filtered")
async def get_transactions_filtered(
    account_id: Optional[str] = None,
    channel: Optional[str] = None,
    min_amount: Optional[float] = None,
    max_amount: Optional[float] = None,
    since: Optional[str] = None,
    until: Optional[str] = None,
    is_laundering: Optional[int] = None,
    risk_level: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
    sort_by: str = "timestamp",
    sort_order: str = "desc",
):
    """
    Paginated transaction list with comprehensive filters.
    Supports filtering by account, channel, amount range, date range, and risk level.
    """
    _require_ready()
    txns = _state["transactions_df"].copy()

    # Apply filters
    if account_id:
        txns = txns[(txns["source_account"] == account_id) | (txns["dest_account"] == account_id)]
    if channel:
        txns = txns[txns["channel"] == channel]
    if min_amount is not None:
        txns = txns[txns["amount"] >= min_amount]
    if max_amount is not None:
        txns = txns[txns["amount"] <= max_amount]
    if since:
        txns["timestamp"] = pd.to_datetime(txns["timestamp"], errors="coerce")
        txns = txns[txns["timestamp"] >= pd.to_datetime(since)]
    if until:
        txns["timestamp"] = pd.to_datetime(txns["timestamp"], errors="coerce")
        txns = txns[txns["timestamp"] <= pd.to_datetime(until)]
    if is_laundering is not None and "is_laundering" in txns.columns:
        txns = txns[txns["is_laundering"] == is_laundering]

    # Filter by risk level of source account
    if risk_level:
        risk = detection_svc.risk_scores
        level_accounts = [
            acc_id for acc_id, score in risk.items()
            if _risk_level(score) == risk_level.upper()
        ]
        txns = txns[txns["source_account"].isin(level_accounts)]

    total = len(txns)

    # Sort
    if sort_by in txns.columns:
        ascending = sort_order.lower() != "desc"
        txns = txns.sort_values(sort_by, ascending=ascending)

    # Paginate
    page = txns.iloc[offset:offset + limit]

    transactions = [{
        "txn_id": str(r.get("txn_id", "")),
        "timestamp": _ts(r.get("timestamp")),
        "source_account": r.get("source_account", ""),
        "dest_account": r.get("dest_account", ""),
        "amount": float(r.get("amount", 0)),
        "channel": r.get("channel", ""),
        "txn_type": r.get("txn_type", ""),
    } for _, r in page.iterrows()]

    return {
        "total": total,
        "limit": limit,
        "offset": offset,
        "transactions": transactions,
    }


# ── DB Health ────────────────────────────────────────────────────────────

@app.get("/api/db/stats")
async def db_stats():
    """Database statistics."""
    try:
        db = get_database()
        return {
            "status": "connected",
            "accounts": db.get_account_count(),
            "transactions": db.get_transaction_count(),
        }
    except Exception as e:
        return {"status": "error", "error": str(e)}


# ── Metric Explanations ──────────────────────────────────────────────────

METRIC_EXPLANATIONS = {
    "risk_score": "Risk Score (0–100) combines outputs from three independent systems: an XGBoost machine learning classifier trained on transaction behaviour, an Isolation Forest anomaly detector, and graph centrality measures. A score above 80 indicates the account appears in the top tier of all three systems simultaneously.",
    "anomaly_score": "Anomaly Score measures how statistically unusual an account's behaviour is compared to all other accounts in the dataset. It is computed by an Isolation Forest model trained on 28 features including transaction velocity, amount variance, channel diversity, and time-of-day patterns. Scores above 70 indicate behaviour that falls outside normal ranges for the account's occupation and income bracket.",
    "fraud_probability": "Fraud Probability is the raw output probability from the XGBoost classifier (0–100%). It reflects the model's confidence that this account's transaction pattern resembles known money laundering cases in the training data. A probability above 50% does not mean confirmed fraud — it means the account warrants investigator review.",
    "role": "Network Role classifies the account's function in the transaction graph. MULE accounts primarily receive and forward funds. COLLECTOR accounts aggregate from many sources. SMURFER accounts make many small structured deposits. SOURCE accounts are primary fund originators. SINK accounts are final destinations. TRANSIENT accounts appear briefly and disappear.",
    "layering": "Layering is an AML typology where funds are moved through multiple intermediate accounts (typically 3 or more hops) in rapid succession to obscure the original source. Each transfer makes it harder to trace the money back to its origin. This account appears as an intermediate node in at least one such chain.",
    "round_trip": "Round-trip or circular flow is detected when funds sent by this account eventually return to it — directly or through intermediaries. This is a strong indicator of fictitious transactions designed to create an appearance of legitimate business activity.",
    "structuring": "Structuring (also called Smurfing) is the practice of breaking large amounts into smaller transactions — typically just below the ₹10 lakh CTR reporting threshold — to avoid regulatory detection. This account shows a statistical clustering of transaction amounts in the ₹9–9.9L range.",
    "fan_out": "Fan-Out pattern occurs when a single account distributes funds to an unusually large number of recipients in a short time window. This can indicate a money mule coordinator account that is distributing laundered funds across the network.",
    "fan_in": "Fan-In pattern occurs when a single account receives funds from an unusually large number of sources. Combined with rapid outflow, this indicates a collector account in a money laundering network.",
    "dormancy": "Dormant Account Activation flags accounts that had very low or zero activity for an extended period and then suddenly began high-volume transactions. This pattern is used by money launderers who acquire or reactivate old accounts to avoid triggering new-account monitoring rules.",
    "profile_mismatch": "Profile Mismatch is detected when an account's actual transaction volume significantly exceeds what would be expected given the account holder's declared occupation and income bracket. A daily wage earner transacting ₹50 lakh per month is an example of a profile mismatch.",
    "speed_alert": "Speed Alert flags transaction chains where funds moved between 3 or more accounts faster than normal banking settlement times. FAST = under 4 hours, VERY_FAST = under 1 hour, ABNORMAL = under 15 minutes. Rapid movement is a hallmark of automated layering.",
    "priority_p1": "P1 (Critical) accounts require action today. They have been flagged by multiple independent detection systems with high confidence, often showing 3+ AML typologies simultaneously. These cases represent the highest likelihood of active money laundering.",
    "priority_p2": "P2 (High Priority) accounts should be reviewed within 24 hours. They show strong signals from at least one major detection system and may have 1–2 AML typologies. These cases are likely to result in STR filing after investigation.",
    "priority_p3": "P3 (Medium) accounts should be reviewed within the week. They show moderate anomaly signals or a single AML typology with lower confidence. These may be false positives but warrant review.",
    "priority_p4": "P4 (Low) accounts are in the monitoring queue. They show mild statistical anomalies that do not yet meet the threshold for formal review. These accounts should be watched for escalating activity.",
    "str": "Suspicious Transaction Report (STR) is a mandatory filing with the Financial Intelligence Unit – India (FIU-IND) under the Prevention of Money Laundering Act (PMLA). Banks are required to file an STR within 7 days of detecting suspicious activity. The STR includes account details, transaction history, and the basis for suspicion.",
    "ego_graph": "The Ego Graph shows the direct neighbourhood of a selected account — all accounts it has transacted with (1st hop) and their connections (2nd hop). This helps investigators understand the account's immediate financial network and identify whether suspicious behaviour is isolated or part of a larger connected network.",
    "fund_trail": "Fund Trail traces the complete path of money from a source account through all intermediate transfers to its final destination. It helps investigators answer the question: where did this money come from, and where did it end up?",
    "accomplices": "Find Accomplices uses a random walk algorithm to identify accounts that are statistically likely to be connected to the selected account's suspicious activity, even if there is no direct transaction link. It surfaces hidden network relationships.",
    "total_flagged": "Total Flagged is the count of accounts that triggered at least one AML detection rule or received a risk score above the monitoring threshold. This does not mean all flagged accounts are committing fraud — it means each one requires investigator review to determine if a Suspicious Transaction Report should be filed.",
}


@app.get("/api/explain/metric/{metric_name}")
def explain_metric(metric_name: str):
    """Return a plain-English explanation of a dashboard metric or AML typology."""
    explanation = METRIC_EXPLANATIONS.get(metric_name)
    if not explanation:
        return {"metric": metric_name, "explanation": f"No explanation available for metric: {metric_name}"}
    return {"metric": metric_name, "explanation": explanation}


@app.get("/api/explain/metrics")
def explain_all_metrics():
    """Return all metric explanations as a single dictionary."""
    return METRIC_EXPLANATIONS
