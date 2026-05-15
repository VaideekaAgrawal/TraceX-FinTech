"""
FastAPI backend for TraceX — Fund Flow Intelligence System.
Exposes the Python analytics pipeline as REST endpoints for the Next.js frontend.
"""

import os
import sys
import json
import base64
import traceback
from typing import Optional, List, Dict, Any

import pandas as pd
from fastapi import FastAPI, HTTPException, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel

# Ensure project root is on path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.data_loader import DataLoader, generate_demo_data
from core.graph_engine import TransactionGraph
from core.feature_extractor import FeatureExtractor
from core.ml_detector import AnomalyDetector, FraudClassifier
from core.pattern_detector import PatternDetector
from core.role_classifier import AccountRoleClassifier
from core.speed_analyzer import SpeedAnalyzer
from core.risk_scorer import RiskScorer
from core.profile_analyzer import ProfileAnalyzer
from core.evidence_generator import EvidenceGenerator
from utils.helpers import get_risk_level, get_risk_color, format_inr

app = FastAPI(title="TraceX API", version="2.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Global system state ──────────────────────────────────────────────────────
_system: Dict[str, Any] = {}


def _build_system(accounts_df: pd.DataFrame, transactions_df: pd.DataFrame) -> Dict[str, Any]:
    """Build the full analytics pipeline from raw DataFrames."""
    graph = TransactionGraph(accounts_df, transactions_df)
    features = FeatureExtractor(graph, accounts_df, transactions_df).extract_all()

    anomaly = AnomalyDetector(contamination=0.05).fit_predict(features)

    fraud_accs = set(transactions_df[transactions_df["is_laundering"] == 1]["source_account"].unique())
    labels = pd.Series(
        [1 if a in fraud_accs else 0 for a in features.index],
        index=features.index,
    )

    classifier = FraudClassifier()
    fraud_metrics = classifier.train(features, labels)
    fraud_results = classifier.predict(features)

    pattern_detector = PatternDetector(graph, transactions_df)
    all_patterns = pattern_detector.detect_all()

    roles = AccountRoleClassifier().classify_all(graph)
    speed_alerts = SpeedAnalyzer().get_speed_alerts(graph)

    scorer = RiskScorer()
    risk_scores = scorer.compute_all_scores(features, anomaly, fraud_results, all_patterns, graph)

    profile = ProfileAnalyzer(accounts_df, transactions_df)

    return {
        "accounts_df": accounts_df,
        "transactions_df": transactions_df,
        "graph_engine": graph,
        "features_df": features,
        "anomaly_results": anomaly,
        "fraud_classifier": classifier,
        "fraud_results": fraud_results,
        "fraud_metrics": fraud_metrics,
        "all_patterns": all_patterns,
        "pattern_detector": pattern_detector,
        "roles": roles,
        "speed_alerts": speed_alerts,
        "risk_scores": risk_scores,
        "risk_scorer": scorer,
        "profile_analyzer": profile,
    }


# ── Pydantic models ─────────────────────────────────────────────────────────
class InitRequest(BaseModel):
    source: str = "demo"
    n_accounts: int = 200
    n_transactions: int = 5000


class FundTrailRequest(BaseModel):
    account_id: str
    direction: str = "both"
    max_depth: int = 5


class EvidenceRequest(BaseModel):
    case_id: str
    account_ids: List[str]
    pattern_type: str = ""
    case_notes: str = ""


class RandomWalkRequest(BaseModel):
    start_node: str
    restart_prob: float = 0.15
    num_steps: int = 5000


# ── Startup: load demo by default ───────────────────────────────────────────
@app.on_event("startup")
async def startup():
    global _system
    accounts, txns = generate_demo_data(200, 5000, seed=42)
    _system = _build_system(accounts, txns)


def _get_system() -> Dict[str, Any]:
    if not _system:
        raise HTTPException(status_code=503, detail="System not initialized")
    return _system


# ── Utility serializers ──────────────────────────────────────────────────────
def _ts(val):
    """Safely convert a timestamp-like value to ISO string."""
    if pd.isna(val):
        return None
    if hasattr(val, "isoformat"):
        return val.isoformat()
    return str(val)


def _safe(obj):
    """Make an object JSON-safe."""
    if isinstance(obj, pd.Timestamp):
        return obj.isoformat()
    if isinstance(obj, pd.Timedelta):
        return obj.total_seconds()
    if hasattr(obj, "item"):
        return obj.item()
    return obj


# ═══════════════════════════════════════════════════════════════════════════
# ENDPOINTS
# ═══════════════════════════════════════════════════════════════════════════

# ── System ────────────────────────────────────────────────────────────────
@app.post("/api/init")
async def init_system(req: InitRequest):
    global _system
    if req.source == "demo":
        accounts, txns = generate_demo_data(req.n_accounts, req.n_transactions, seed=42)
    else:
        raise HTTPException(400, "Only 'demo' source supported via API. Upload CSV for custom data.")
    _system = _build_system(accounts, txns)
    return {"status": "ok", "accounts": len(accounts), "transactions": len(txns)}


@app.post("/api/upload")
async def upload_csv(file: UploadFile = File(...), source_type: str = Form("custom_csv")):
    global _system
    import io
    content = await file.read()
    df = pd.read_csv(io.BytesIO(content))
    loader = DataLoader()
    accounts, txns = loader.load(source=source_type, dataframe=df)
    _system = _build_system(accounts, txns)
    return {"status": "ok", "accounts": len(accounts), "transactions": len(txns)}


# ── Overview / Dashboard ─────────────────────────────────────────────────
@app.get("/api/overview")
async def get_overview():
    s = _get_system()
    risk = s["risk_scores"]
    stats = s["graph_engine"].get_stats()
    anomaly = s["anomaly_results"]
    patterns = s["all_patterns"]
    fraud_metrics = s["fraud_metrics"]
    roles = s["roles"]
    features = s["features_df"]
    accounts = s["accounts_df"]
    txns = s["transactions_df"]

    # Risk distribution
    risk_dist = {"LOW": 0, "MEDIUM": 0, "HIGH": 0, "CRITICAL": 0}
    for score in risk.values():
        risk_dist[get_risk_level(score)] += 1

    # Role distribution
    role_dist = {}
    for r in roles.values():
        role_dist[r["role"]] = role_dist.get(r["role"], 0) + 1

    # Top alerts
    sorted_risk = sorted(risk.items(), key=lambda x: x[1], reverse=True)[:20]
    top_alerts = []
    for acc_id, score in sorted_risk:
        role_info = roles.get(acc_id, {})
        acc_row = accounts[accounts["account_id"] == acc_id]
        top_alerts.append({
            "account_id": acc_id,
            "risk_score": round(score, 1),
            "risk_level": get_risk_level(score),
            "risk_color": get_risk_color(score),
            "role": role_info.get("role", "UNKNOWN"),
            "branch_city": acc_row["branch_city"].iloc[0] if len(acc_row) > 0 else "Unknown",
            "account_type": acc_row["account_type"].iloc[0] if len(acc_row) > 0 else "Unknown",
        })

    # Pattern counts
    pattern_counts = {}
    for k, v in patterns.items():
        if isinstance(v, list):
            pattern_counts[k] = len(v)
        elif isinstance(v, dict):
            pattern_counts[k] = sum(len(vv) for vv in v.values())

    # Total flagged
    flagged = sum(1 for s in risk.values() if s > 50)

    return {
        "stats": stats,
        "risk_distribution": risk_dist,
        "role_distribution": role_dist,
        "top_alerts": top_alerts,
        "pattern_counts": pattern_counts,
        "total_flagged": flagged,
        "total_anomalies": int((anomaly["is_anomaly"] == 1).sum()),
        "fraud_metrics": {k: (_safe(v) if not isinstance(v, list) else v) for k, v in fraud_metrics.items()},
        "total_amount": float(txns["amount"].sum()),
        "avg_risk": round(sum(risk.values()) / max(len(risk), 1), 1),
    }


# ── Accounts ──────────────────────────────────────────────────────────────
@app.get("/api/accounts")
async def get_accounts():
    s = _get_system()
    accounts = s["accounts_df"]
    risk = s["risk_scores"]
    roles = s["roles"]
    anomaly = s["anomaly_results"]

    results = []
    for _, row in accounts.iterrows():
        acc_id = row["account_id"]
        score = risk.get(acc_id, 0)
        role_info = roles.get(acc_id, {"role": "UNKNOWN", "confidence": 0})
        anom_row = anomaly[anomaly["account_id"] == acc_id]
        anomaly_score = float(anom_row["anomaly_score"].iloc[0]) if len(anom_row) > 0 else 0

        results.append({
            "account_id": acc_id,
            "account_type": row.get("account_type", ""),
            "branch_city": row.get("branch_city", ""),
            "occupation": row.get("occupation", ""),
            "income_bracket": row.get("income_bracket", ""),
            "declared_annual_income": float(row.get("declared_annual_income", 0)),
            "total_in_flow": float(row.get("total_in_flow", 0)),
            "total_out_flow": float(row.get("total_out_flow", 0)),
            "txn_count": int(row.get("txn_count", 0)),
            "risk_score": round(score, 1),
            "risk_level": get_risk_level(score),
            "risk_color": get_risk_color(score),
            "role": role_info["role"],
            "role_confidence": round(role_info.get("confidence", 0), 2),
            "anomaly_score": round(anomaly_score, 1),
        })

    return sorted(results, key=lambda x: x["risk_score"], reverse=True)


@app.get("/api/accounts/{account_id}")
async def get_account_detail(account_id: str):
    s = _get_system()
    accounts = s["accounts_df"]
    txns = s["transactions_df"]
    risk = s["risk_scores"]
    roles = s["roles"]
    features = s["features_df"]
    anomaly = s["anomaly_results"]
    fraud = s["fraud_results"]
    scorer = s["risk_scorer"]
    patterns = s["all_patterns"]
    graph = s["graph_engine"]

    acc_row = accounts[accounts["account_id"] == account_id]
    if len(acc_row) == 0:
        raise HTTPException(404, f"Account {account_id} not found")
    acc = acc_row.iloc[0].to_dict()
    for k, v in acc.items():
        acc[k] = _safe(v)

    score = risk.get(account_id, 0)
    role_info = roles.get(account_id, {"role": "UNKNOWN", "confidence": 0})

    # Features
    feat_dict = {}
    if account_id in features.index:
        feat_dict = {k: round(float(v), 4) for k, v in features.loc[account_id].items()}

    # Anomaly
    anom_row = anomaly[anomaly["account_id"] == account_id]
    anomaly_score = float(anom_row["anomaly_score"].iloc[0]) if len(anom_row) > 0 else 0

    # Fraud
    fraud_row = fraud[fraud["account_id"] == account_id]
    fraud_prob = float(fraud_row["fraud_prob"].iloc[0]) if len(fraud_row) > 0 else 0

    # Confidence & Priority
    centrality = graph.compute_centrality()
    graph_metrics = {
        "pagerank": centrality["pagerank"].get(account_id, 0),
        "betweenness": centrality["betweenness"].get(account_id, 0),
    }
    ml_scores = {"anomaly_score": anomaly_score, "fraud_prob": fraud_prob}
    conf_level, conf_count, indicators = scorer.compute_confidence(account_id, patterns, ml_scores, graph_metrics)

    acc_txns = txns[(txns["source_account"] == account_id) | (txns["dest_account"] == account_id)]
    total_amount = float(acc_txns["amount"].sum())
    n_counterparties = len(set(acc_txns["source_account"].unique()) | set(acc_txns["dest_account"].unique())) - 1
    priority = scorer.compute_investigation_priority(score, conf_level, total_amount, max(n_counterparties, 1))

    # Recent transactions
    recent_txns = acc_txns.sort_values("timestamp", ascending=False).head(20)
    txn_list = []
    for _, t in recent_txns.iterrows():
        txn_list.append({
            "txn_id": t["txn_id"],
            "timestamp": _ts(t["timestamp"]),
            "source_account": t["source_account"],
            "dest_account": t["dest_account"],
            "amount": float(t["amount"]),
            "channel": t.get("channel", ""),
            "is_laundering": int(t.get("is_laundering", 0)),
        })

    return {
        "account": acc,
        "risk_score": round(score, 1),
        "risk_level": get_risk_level(score),
        "risk_color": get_risk_color(score),
        "role": role_info["role"],
        "role_confidence": round(role_info.get("confidence", 0), 2),
        "anomaly_score": round(anomaly_score, 1),
        "fraud_probability": round(fraud_prob, 4),
        "features": feat_dict,
        "confidence": {"level": conf_level, "count": conf_count, "indicators": indicators},
        "priority": priority,
        "total_amount": total_amount,
        "counterparties": n_counterparties,
        "recent_transactions": txn_list,
    }


# ── Graph ─────────────────────────────────────────────────────────────────
@app.get("/api/graph")
async def get_graph(max_nodes: int = 100):
    s = _get_system()
    graph = s["graph_engine"]
    risk = s["risk_scores"]
    roles = s["roles"]

    sub = graph.get_renderable_subgraph(risk, max_nodes=max_nodes)

    nodes = []
    for n in sub.nodes():
        score = risk.get(n, 0)
        role_info = roles.get(n, {"role": "UNKNOWN"})
        nodes.append({
            "id": n,
            "risk_score": round(score, 1),
            "risk_level": get_risk_level(score),
            "risk_color": get_risk_color(score),
            "role": role_info["role"],
        })

    edges = []
    for u, v, key, data in sub.edges(keys=True, data=True):
        edges.append({
            "source": u,
            "target": v,
            "amount": float(data.get("amount", 0)),
            "channel": data.get("channel", ""),
            "timestamp": _ts(data.get("timestamp")),
        })

    return {"nodes": nodes, "edges": edges}


@app.get("/api/graph/ego/{account_id}")
async def get_ego_graph(account_id: str, radius: int = 2):
    s = _get_system()
    graph = s["graph_engine"]
    risk = s["risk_scores"]
    roles = s["roles"]

    sub = graph.get_ego_subgraph(account_id, radius=radius)
    nodes = []
    for n in sub.nodes():
        score = risk.get(n, 0)
        role_info = roles.get(n, {"role": "UNKNOWN"})
        nodes.append({
            "id": n,
            "risk_score": round(score, 1),
            "risk_level": get_risk_level(score),
            "risk_color": get_risk_color(score),
            "role": role_info["role"],
            "is_center": n == account_id,
        })

    edges = []
    for u, v, key, data in sub.edges(keys=True, data=True):
        edges.append({
            "source": u,
            "target": v,
            "amount": float(data.get("amount", 0)),
            "channel": data.get("channel", ""),
            "timestamp": _ts(data.get("timestamp")),
        })

    return {"nodes": nodes, "edges": edges, "center": account_id}


@app.post("/api/graph/fund-trail")
async def get_fund_trail(req: FundTrailRequest):
    s = _get_system()
    graph = s["graph_engine"]
    result = graph.get_fund_trail(req.account_id, direction=req.direction, max_depth=req.max_depth)

    # Serialize trails
    if "trails" in result:
        for trail in result["trails"]:
            for step in trail:
                step["timestamp"] = _ts(step.get("timestamp"))
                step["amount"] = float(step.get("amount", 0))

    return result


@app.post("/api/graph/random-walk")
async def random_walk(req: RandomWalkRequest):
    s = _get_system()
    graph = s["graph_engine"]
    risk = s["risk_scores"]
    roles = s["roles"]

    probs = graph.random_walk_with_restart(req.start_node, req.restart_prob, req.num_steps)
    top = list(probs.items())[:20]

    results = []
    for node, prob in top:
        if node == req.start_node:
            continue
        score = risk.get(node, 0)
        role_info = roles.get(node, {"role": "UNKNOWN"})
        results.append({
            "account_id": node,
            "visit_probability": round(prob, 6),
            "risk_score": round(score, 1),
            "risk_level": get_risk_level(score),
            "role": role_info["role"],
        })

    return {"start_node": req.start_node, "accomplices": results}


# ── Anomaly / Risk ────────────────────────────────────────────────────────
@app.get("/api/anomaly")
async def get_anomaly_data():
    s = _get_system()
    anomaly = s["anomaly_results"]
    risk = s["risk_scores"]
    roles = s["roles"]
    features = s["features_df"]
    classifier = s["fraud_classifier"]
    speed = s["speed_alerts"]
    scorer = s["risk_scorer"]
    patterns = s["all_patterns"]
    graph = s["graph_engine"]
    accounts = s["accounts_df"]

    # Anomaly scores for histogram
    scores_list = [{"account_id": row["account_id"], "anomaly_score": round(float(row["anomaly_score"]), 1)}
                   for _, row in anomaly.iterrows()]

    # Feature importance
    importance = classifier.get_feature_importance()

    # Investigation queue
    centrality = graph.compute_centrality()
    queue = []
    sorted_risk = sorted(risk.items(), key=lambda x: x[1], reverse=True)
    for acc_id, score in sorted_risk:
        if score < 30:
            continue
        graph_metrics = {
            "pagerank": centrality["pagerank"].get(acc_id, 0),
            "betweenness": centrality["betweenness"].get(acc_id, 0),
        }
        anom_row = anomaly[anomaly["account_id"] == acc_id]
        fraud_row = s["fraud_results"][s["fraud_results"]["account_id"] == acc_id]
        ml_scores = {
            "anomaly_score": float(anom_row["anomaly_score"].iloc[0]) if len(anom_row) > 0 else 0,
            "fraud_prob": float(fraud_row["fraud_prob"].iloc[0]) if len(fraud_row) > 0 else 0,
        }
        conf_level, conf_count, indicators = scorer.compute_confidence(acc_id, patterns, ml_scores, graph_metrics)
        txns = s["transactions_df"]
        acc_txns = txns[(txns["source_account"] == acc_id) | (txns["dest_account"] == acc_id)]
        total_amt = float(acc_txns["amount"].sum())
        n_cpty = len(set(acc_txns["source_account"].unique()) | set(acc_txns["dest_account"].unique())) - 1
        priority = scorer.compute_investigation_priority(score, conf_level, total_amt, max(n_cpty, 1))

        role_info = roles.get(acc_id, {"role": "UNKNOWN"})
        acc_row = accounts[accounts["account_id"] == acc_id]

        queue.append({
            "account_id": acc_id,
            "risk_score": round(score, 1),
            "risk_level": get_risk_level(score),
            "risk_color": get_risk_color(score),
            "role": role_info["role"],
            "priority": priority,
            "confidence_level": conf_level,
            "confidence_count": conf_count,
            "indicators": indicators,
            "anomaly_score": ml_scores["anomaly_score"],
            "fraud_probability": ml_scores["fraud_prob"],
            "total_amount": total_amt,
            "branch_city": acc_row["branch_city"].iloc[0] if len(acc_row) > 0 else "",
        })

    # Speed alerts
    speed_list = []
    for alert in speed[:20]:
        speed_list.append({
            "accounts": alert.get("accounts", []),
            "category": alert.get("category", ""),
            "label": alert.get("label", ""),
            "color": alert.get("color", ""),
            "avg_minutes_per_hop": round(alert.get("avg_minutes_per_hop", 0), 2),
            "total_minutes": round(alert.get("total_minutes", 0), 2),
            "hops": alert.get("hops", 0),
            "total_amount": float(alert.get("total_amount", 0)),
        })

    return {
        "anomaly_scores": scores_list,
        "feature_importance": {k: round(float(v), 4) for k, v in importance.items()} if importance else {},
        "investigation_queue": queue,
        "speed_alerts": speed_list,
    }


# ── Patterns ──────────────────────────────────────────────────────────────
@app.get("/api/patterns")
async def get_patterns():
    s = _get_system()
    patterns = s["all_patterns"]
    detector = s["pattern_detector"]

    # Convert all patterns to JSON-safe format
    result = {}
    for pattern_type, data in patterns.items():
        if isinstance(data, list):
            safe_list = []
            for item in data:
                safe_item = {}
                for k, v in item.items():
                    if isinstance(v, list):
                        safe_item[k] = [_safe(x) if not isinstance(x, dict) else {kk: _safe(vv) for kk, vv in x.items()} for x in v]
                    else:
                        safe_item[k] = _safe(v)
                safe_list.append(safe_item)
            result[pattern_type] = safe_list
        elif isinstance(data, dict):
            result[pattern_type] = {}
            for sub_key, sub_list in data.items():
                safe_list = []
                for item in sub_list:
                    safe_item = {k: _safe(v) for k, v in item.items()}
                    safe_list.append(safe_item)
                result[pattern_type][sub_key] = safe_list

    # Combined patterns
    combined = detector.detect_combined_patterns(patterns)
    result["combined"] = [
        {k: _safe(v) for k, v in item.items()}
        for item in combined
    ]

    # Flagged accounts
    flagged = list(detector.get_all_flagged_accounts(patterns))

    return {"patterns": result, "flagged_accounts": flagged}


@app.get("/api/patterns/first-suspicious/{account_id}")
async def get_first_suspicious(account_id: str):
    s = _get_system()
    detector = s["pattern_detector"]
    result = detector.detect_first_suspicious_point(account_id)
    if result is None:
        return {"found": False}
    safe = {k: _safe(v) for k, v in result.items()}
    safe["timestamp"] = _ts(result.get("timestamp"))
    return {"found": True, "data": safe}


# ── Profile ───────────────────────────────────────────────────────────────
@app.get("/api/profile")
async def get_profile_data():
    s = _get_system()
    profile = s["profile_analyzer"]

    scatter = profile.get_scatter_data()
    mismatches = profile.detect_all_mismatches()

    scatter_list = []
    for _, row in scatter.iterrows():
        scatter_list.append({
            "account_id": row["account_id"],
            "declared_income": float(row["declared_income"]),
            "actual_volume": float(row["actual_volume"]),
            "occupation": row.get("occupation", ""),
            "income_bracket": row.get("income_bracket", ""),
            "ratio": round(float(row.get("ratio", 0)), 2),
        })

    return {
        "scatter_data": scatter_list,
        "mismatches": [{k: _safe(v) for k, v in m.items()} for m in mismatches],
    }


@app.get("/api/profile/{account_id}")
async def get_peer_group(account_id: str):
    s = _get_system()
    profile = s["profile_analyzer"]
    result = profile.compute_peer_group(account_id)
    return {k: _safe(v) for k, v in result.items()}


# ── Channel Analytics ─────────────────────────────────────────────────────
@app.get("/api/channels")
async def get_channel_data():
    s = _get_system()
    txns = s["transactions_df"]
    accounts = s["accounts_df"]
    risk = s["risk_scores"]

    # Channel summary
    channel_summary = txns.groupby("channel").agg(
        count=("amount", "count"),
        total_amount=("amount", "sum"),
        avg_amount=("amount", "mean"),
        max_amount=("amount", "max"),
    ).reset_index()

    summary_list = []
    for _, row in channel_summary.iterrows():
        summary_list.append({
            "channel": row["channel"],
            "count": int(row["count"]),
            "total_amount": float(row["total_amount"]),
            "avg_amount": round(float(row["avg_amount"]), 2),
            "max_amount": float(row["max_amount"]),
        })

    # Sankey data (account_type -> channel -> account_type)
    merged = txns.merge(
        accounts[["account_id", "account_type"]],
        left_on="source_account",
        right_on="account_id",
        how="left",
    ).rename(columns={"account_type": "source_type"})
    merged = merged.merge(
        accounts[["account_id", "account_type"]],
        left_on="dest_account",
        right_on="account_id",
        how="left",
        suffixes=("", "_dest"),
    ).rename(columns={"account_type": "dest_type"})

    sankey_flows = merged.groupby(["source_type", "channel", "dest_type"]).agg(
        count=("amount", "count"),
        total=("amount", "sum"),
    ).reset_index().sort_values("total", ascending=False).head(50)

    sankey_list = []
    for _, row in sankey_flows.iterrows():
        sankey_list.append({
            "source_type": row["source_type"],
            "channel": row["channel"],
            "dest_type": row["dest_type"],
            "count": int(row["count"]),
            "total": float(row["total"]),
        })

    # Heatmap data (channel x hour)
    txns_copy = txns.copy()
    txns_copy["hour"] = pd.to_datetime(txns_copy["timestamp"]).dt.hour
    heatmap = txns_copy.groupby(["channel", "hour"]).size().reset_index(name="count")
    heatmap_list = [{"channel": r["channel"], "hour": int(r["hour"]), "count": int(r["count"])}
                    for _, r in heatmap.iterrows()]

    # Suspicious channel usage
    suspicious = []
    high_risk_accounts = {a for a, s in risk.items() if s > 60}
    if high_risk_accounts:
        sus_txns = txns[txns["source_account"].isin(high_risk_accounts)]
        if not sus_txns.empty:
            channel_risk = sus_txns.groupby("channel").agg(
                count=("amount", "count"),
                total=("amount", "sum"),
                unique_accounts=("source_account", "nunique"),
            ).reset_index().sort_values("total", ascending=False)
            for _, row in channel_risk.iterrows():
                suspicious.append({
                    "channel": row["channel"],
                    "count": int(row["count"]),
                    "total": float(row["total"]),
                    "unique_accounts": int(row["unique_accounts"]),
                })

    return {
        "summary": summary_list,
        "sankey": sankey_list,
        "heatmap": heatmap_list,
        "suspicious": suspicious,
    }


# ── Evidence ──────────────────────────────────────────────────────────────
@app.post("/api/evidence/generate")
async def generate_evidence(req: EvidenceRequest):
    s = _get_system()
    gen = EvidenceGenerator()
    risk_data = s["risk_scores"]

    try:
        pack = gen.generate_evidence_pack(
            case_id=req.case_id,
            account_ids=req.account_ids,
            graph_engine=s["graph_engine"],
            risk_data=risk_data,
            pattern_results=s["all_patterns"],
            transactions_df=s["transactions_df"],
            accounts_df=s["accounts_df"],
            case_notes=req.case_notes,
        )

        pdf_b64 = base64.b64encode(pack["pdf_bytes"]).decode("utf-8")

        return {
            "case_id": pack["case_id"],
            "summary": pack["summary"],
            "pdf_base64": pdf_b64,
            "json_data": pack["json_data"],
        }
    except Exception as e:
        raise HTTPException(500, f"Evidence generation failed: {str(e)}")


# ── Transactions ──────────────────────────────────────────────────────────
@app.get("/api/transactions")
async def get_transactions(limit: int = 100, offset: int = 0):
    s = _get_system()
    txns = s["transactions_df"]
    total = len(txns)
    page = txns.sort_values("timestamp", ascending=False).iloc[offset:offset + limit]

    rows = []
    for _, t in page.iterrows():
        rows.append({
            "txn_id": t["txn_id"],
            "timestamp": _ts(t["timestamp"]),
            "source_account": t["source_account"],
            "dest_account": t["dest_account"],
            "amount": float(t["amount"]),
            "channel": t.get("channel", ""),
            "txn_type": t.get("txn_type", ""),
            "is_laundering": int(t.get("is_laundering", 0)),
        })

    return {"total": total, "transactions": rows}


# ── Health ────────────────────────────────────────────────────────────────
@app.get("/api/health")
async def health():
    initialized = bool(_system)
    return {
        "status": "ok" if initialized else "uninitialized",
        "initialized": initialized,
        "accounts": len(_system["accounts_df"]) if initialized else 0,
        "transactions": len(_system["transactions_df"]) if initialized else 0,
    }
