"""Anomaly Dashboard — ML detection results and risk scoring."""
import streamlit as st
import plotly.graph_objects as go
import plotly.express as px
import pandas as pd

st.set_page_config(page_title="Anomaly Dashboard", page_icon="⚠️", layout="wide")

system = st.session_state.get("system")
if not system:
    st.error("System not initialized. Go to the Home page first.")
    st.stop()

detection_svc = system["detection_service"]
accounts_df = system["accounts_df"]
transactions_df = system["transactions_df"]
risk_scores = detection_svc.risk_scores
anomaly_results = detection_svc.anomaly_results
fraud_results = detection_svc.fraud_results

st.title("⚠️ Anomaly Dashboard")

# ── Risk distribution ────────────────────────────────────────────────────
st.subheader("Risk Score Distribution")
c1, c2 = st.columns([2, 1])

with c1:
    risk_df = pd.DataFrame([
        {"account_id": k, "risk_score": v} for k, v in risk_scores.items()
    ])
    fig = px.histogram(risk_df, x="risk_score", nbins=30,
                       color_discrete_sequence=["#e74c3c"],
                       title="Risk Score Distribution")
    fig.update_layout(template="plotly_dark", height=350)
    st.plotly_chart(fig, use_container_width=True)

with c2:
    levels = {"LOW": 0, "MEDIUM": 0, "HIGH": 0, "CRITICAL": 0}
    for s in risk_scores.values():
        if s >= 76: levels["CRITICAL"] += 1
        elif s >= 51: levels["HIGH"] += 1
        elif s >= 26: levels["MEDIUM"] += 1
        else: levels["LOW"] += 1

    colors = {"LOW": "#2ecc71", "MEDIUM": "#f39c12", "HIGH": "#e67e22", "CRITICAL": "#e74c3c"}
    fig = go.Figure(data=[go.Pie(
        labels=list(levels.keys()), values=list(levels.values()),
        hole=0.5, marker_colors=[colors[k] for k in levels],
        textinfo="label+value",
    )])
    fig.update_layout(title="Risk Breakdown", template="plotly_dark", height=350)
    st.plotly_chart(fig, use_container_width=True)

st.divider()

# ── Top risk accounts ───────────────────────────────────────────────────
st.subheader("Top Risk Accounts")
top_n = st.slider("Show top N", 10, 50, 20)
sorted_risk = sorted(risk_scores.items(), key=lambda x: x[1], reverse=True)[:top_n]

rows = []
for acc_id, score in sorted_risk:
    role = detection_svc.roles.get(acc_id, {}).get("role", "UNKNOWN")
    anom = anomaly_results[anomaly_results["account_id"] == acc_id]
    anom_score = float(anom["anomaly_score"].iloc[0]) if len(anom) > 0 else 0
    fraud = fraud_results[fraud_results["account_id"] == acc_id] if fraud_results is not None else pd.DataFrame()
    fraud_prob = float(fraud["fraud_prob"].iloc[0]) if len(fraud) > 0 else 0

    acc_row = accounts_df[accounts_df["account_id"] == acc_id]
    occ = acc_row["occupation"].iloc[0] if len(acc_row) > 0 else ""
    city = acc_row["branch_city"].iloc[0] if len(acc_row) > 0 else ""

    rows.append({
        "Account": acc_id,
        "Risk": f"{score:.0f}",
        "Anomaly": f"{anom_score:.0f}",
        "Fraud Prob": f"{fraud_prob:.1%}",
        "Role": role,
        "Occupation": occ,
        "City": city,
    })

st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

# ── Anomaly scatter ──────────────────────────────────────────────────────
st.divider()
st.subheader("Anomaly Score vs Risk Score")
scatter_data = []
for acc_id, score in risk_scores.items():
    anom = anomaly_results[anomaly_results["account_id"] == acc_id]
    anom_s = float(anom["anomaly_score"].iloc[0]) if len(anom) > 0 else 0
    role = detection_svc.roles.get(acc_id, {}).get("role", "NORMAL")
    scatter_data.append({"Risk Score": score, "Anomaly Score": anom_s, "Role": role, "Account": acc_id})

scatter_df = pd.DataFrame(scatter_data)
fig = px.scatter(scatter_df, x="Anomaly Score", y="Risk Score", color="Role",
                 hover_data=["Account"],
                 color_discrete_map={"SOURCE": "#4444ff", "MULE": "#ffaa00",
                                     "SINK": "#ff4444", "NORMAL": "#888888"})
fig.update_layout(template="plotly_dark", height=500)
st.plotly_chart(fig, use_container_width=True)

# ── Transaction timeline ─────────────────────────────────────────────────
st.divider()
st.subheader("Transaction Timeline")
txn_df = transactions_df.copy()
txn_df["risk"] = txn_df["source_account"].map(risk_scores).fillna(0)
txn_df["level"] = txn_df["risk"].apply(lambda s: "CRITICAL" if s >= 76 else "HIGH" if s >= 51 else "MEDIUM" if s >= 26 else "LOW")

fig = px.scatter(txn_df.sample(min(5000, len(txn_df)), random_state=42),
                 x="timestamp", y="amount", color="level",
                 color_discrete_map=colors,
                 hover_data=["source_account", "dest_account", "channel"],
                 title="Transaction Timeline by Risk Level")
fig.update_layout(template="plotly_dark", height=400)
st.plotly_chart(fig, use_container_width=True)
