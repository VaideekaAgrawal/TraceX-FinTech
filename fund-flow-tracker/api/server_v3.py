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
import sys
import traceback
from typing import Any, Dict, List, Optional

import pandas as pd
from fastapi import FastAPI, HTTPException, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel

# Configure logging FIRST so all service loggers output to console
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
    force=True,
)

# Project root on path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from infrastructure.event_bus import bus
from infrastructure.health import health
from services.ingestion import IngestionService
from services.graph import GraphService
from services.detection import DetectionService
from services.investigation import InvestigationService

logger = logging.getLogger(__name__)

app = FastAPI(title="TraceX API", version="3.0.0",
              description="Fund Flow Intelligence System — microservice API")

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

# ── Shared state ─────────────────────────────────────────────────────────
_state: Dict[str, Any] = {}


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


class RandomWalkRequest(BaseModel):
    start_node: str
    restart_prob: float = 0.15
    num_steps: int = 5000


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
    stats = graph_svc.get_stats()
    risk = detection_svc.risk_scores
    return {
        "graph": stats,
        "total_accounts": stats["num_nodes"],
        "total_transactions": stats["num_edges"],
        "total_anomalies": int(detection_svc.anomaly_results["is_anomaly"].sum()) if detection_svc.anomaly_results is not None else 0,
        "fraud_metrics": {k: _safe(v) for k, v in detection_svc.fraud_metrics.items()},
        "detection_summary": detection_svc.get_detection_summary(),
        "risk_distribution": {
            "critical": sum(1 for s in risk.values() if s >= 76),
            "high": sum(1 for s in risk.values() if 51 <= s < 76),
            "medium": sum(1 for s in risk.values() if 26 <= s < 51),
            "low": sum(1 for s in risk.values() if s < 26),
        },
        "case_stats": investigation_svc.get_case_stats(),
        "avg_risk": round(sum(risk.values()) / max(len(risk), 1), 1),
    }


# ── Accounts ─────────────────────────────────────────────────────────────

@app.get("/api/accounts")
async def list_accounts():
    _require_ready()
    accounts = _state["accounts_df"]
    risk = detection_svc.risk_scores
    roles = detection_svc.roles
    anomaly = detection_svc.anomaly_results

    results = []
    for _, row in accounts.iterrows():
        acc_id = row["account_id"]
        score = risk.get(acc_id, 0)
        role_info = roles.get(acc_id, {"role": "UNKNOWN", "confidence": 0})
        anom_row = anomaly[anomaly["account_id"] == acc_id] if anomaly is not None else pd.DataFrame()
        anom_score = float(anom_row["anomaly_score"].iloc[0]) if len(anom_row) > 0 else 0

        results.append({
            "account_id": acc_id,
            "account_type": row.get("account_type", ""),
            "branch_city": row.get("branch_city", ""),
            "occupation": row.get("occupation", ""),
            "income_bracket": row.get("income_bracket", ""),
            "declared_annual_income": float(row.get("declared_annual_income", 0)),
            "risk_score": round(score, 1),
            "risk_level": _risk_level(score),
            "risk_color": _risk_color(score),
            "role": role_info["role"],
            "anomaly_score": round(anom_score, 1),
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
        "is_laundering": int(t.get("is_laundering", 0)),
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


# ── Graph ────────────────────────────────────────────────────────────────

@app.get("/api/graph")
async def get_graph(max_nodes: int = 100):
    _require_ready()
    risk = detection_svc.risk_scores
    roles = detection_svc.roles
    sub = graph_svc.get_renderable_subgraph(risk, max_nodes)

    nodes = [{"id": n, "risk_score": round(risk.get(n, 0), 1),
              "risk_level": _risk_level(risk.get(n, 0)),
              "risk_color": _risk_color(risk.get(n, 0)),
              "role": roles.get(n, {}).get("role", "UNKNOWN")}
             for n in sub.nodes()]

    edges = [{"source": u, "target": v, "amount": float(d.get("amount", 0)),
              "channel": d.get("channel", ""), "timestamp": _ts(d.get("timestamp"))}
             for u, v, _, d in sub.edges(keys=True, data=True)]

    return {"nodes": nodes, "edges": edges}


@app.get("/api/graph/ego/{account_id}")
async def get_ego(account_id: str, radius: int = 2):
    _require_ready()
    risk = detection_svc.risk_scores
    roles = detection_svc.roles
    sub = graph_svc.get_ego_subgraph(account_id, radius)

    nodes = [{"id": n, "risk_score": round(risk.get(n, 0), 1),
              "risk_level": _risk_level(risk.get(n, 0)),
              "role": roles.get(n, {}).get("role", "UNKNOWN"),
              "is_center": n == account_id}
             for n in sub.nodes()]

    edges = [{"source": u, "target": v, "amount": float(d.get("amount", 0)),
              "channel": d.get("channel", ""), "timestamp": _ts(d.get("timestamp"))}
             for u, v, _, d in sub.edges(keys=True, data=True)]

    return {"nodes": nodes, "edges": edges, "center": account_id}


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
    return {"start": req.start_node, "related_accounts": [
        {"account_id": k, "probability": round(v, 6)} for k, v in list(probs.items())[:20]
    ]}


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
async def create_case(req: CaseRequest):
    case = investigation_svc.create_case(
        req.account_ids, req.typology, req.priority, notes=req.notes,
    )
    return case.to_dict()


@app.get("/api/cases")
async def list_cases(status: Optional[str] = None):
    return [c.to_dict() for c in investigation_svc.list_cases(status)]


@app.get("/api/cases/{case_id}")
async def get_case(case_id: str):
    case = investigation_svc.get_case(case_id)
    if not case:
        raise HTTPException(404, f"Case {case_id} not found")
    return case.to_dict()


@app.put("/api/cases/{case_id}")
async def update_case(case_id: str, req: CaseUpdateRequest):
    case = investigation_svc.update_case(case_id, req.status, req.notes)
    if not case:
        raise HTTPException(404, f"Case {case_id} not found")
    return case.to_dict()


@app.post("/api/cases/{case_id}/resolve")
async def resolve_case(case_id: str, req: CaseResolveRequest):
    case = investigation_svc.resolve_case(case_id, req.resolution, req.is_true_positive)
    if not case:
        raise HTTPException(404, f"Case {case_id} not found")
    return case.to_dict()


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
