"""
Page 2: Anomaly Dashboard — ML-flagged alerts, risk scores, investigation queue.
"""
import streamlit as st
import pandas as pd
from utils.helpers import get_risk_level, get_risk_color, format_inr
from utils.visualization import (
    create_risk_donut, create_feature_importance_chart,
    create_anomaly_histogram, create_alert_timeline,
)

st.set_page_config(page_title="Anomaly Dashboard — TraceX", page_icon="⚠️", layout="wide")
st.title("⚠️ Anomaly Dashboard")

if "system" not in st.session_state:
    st.warning("Please load data from the main page first.")
    st.stop()

system = st.session_state["system"]
risk_scores = system["risk_scores"]
anomaly_results = system["anomaly_results"]
fraud_results = system["fraud_results"]
roles = system["roles"]
features_df = system["features_df"]

# --- Top Metrics ---
total = len(risk_scores)
flagged = sum(1 for v in risk_scores.values() if v > 50)
critical = sum(1 for v in risk_scores.values() if v > 75)
medium = sum(1 for v in risk_scores.values() if 26 <= v <= 50)

col1, col2, col3, col4, col5 = st.columns(5)
col1.metric("Total Accounts", total)
col2.metric("🟢 Low Risk", total - flagged - medium)
col3.metric("🟡 Medium Risk", medium)
col4.metric("🟠 High Risk", flagged - critical)
col5.metric("🔴 Critical", critical)

st.divider()

# --- Charts Row ---
chart_col1, chart_col2 = st.columns(2)

with chart_col1:
    fig = create_risk_donut(risk_scores)
    st.plotly_chart(fig, use_container_width=True)

with chart_col2:
    fig = create_anomaly_histogram(anomaly_results)
    st.plotly_chart(fig, use_container_width=True)

# --- Feature Importance ---
importances = system["fraud_classifier"].get_feature_importance()
if importances:
    fig = create_feature_importance_chart(importances)
    st.plotly_chart(fig, use_container_width=True)

st.divider()

# --- Investigation Priority Queue ---
st.subheader("📋 Investigation Priority Queue")

risk_scorer = system["risk_scorer"]
all_patterns = system["all_patterns"]
pattern_flags = risk_scorer._build_pattern_flags(all_patterns)

queue_rows = []
for acc, score in sorted(risk_scores.items(), key=lambda x: x[1], reverse=True):
    if score < 25:
        continue

    # Compute confidence
    anomaly_row = anomaly_results[anomaly_results["account_id"] == acc]
    fraud_row = fraud_results[fraud_results["account_id"] == acc]

    ml_scores = {
        "anomaly_score": float(anomaly_row["anomaly_score"].values[0]) if len(anomaly_row) > 0 else 0,
        "fraud_prob": float(fraud_row["fraud_prob"].values[0]) if len(fraud_row) > 0 else 0,
    }

    acc_patterns = pattern_flags.get(acc, {})
    centrality = system["graph_engine"].compute_centrality()

    confidence_level, indicator_count, indicators = risk_scorer.compute_confidence(
        acc, acc_patterns, ml_scores,
        {"pagerank": centrality["pagerank"].get(acc, 0),
         "betweenness": centrality["betweenness"].get(acc, 0)},
    )

    # Amount involved
    txns = system["transactions_df"]
    acc_txns = txns[(txns["source_account"] == acc) | (txns["dest_account"] == acc)]
    amount = acc_txns["amount"].sum()

    priority = risk_scorer.compute_investigation_priority(
        score, confidence_level, amount, len(acc_patterns),
    )

    role = roles.get(acc, {}).get("role", "NORMAL")

    queue_rows.append({
        "Priority": priority,
        "Account": acc,
        "Risk Score": round(score, 1),
        "Risk Level": get_risk_level(score),
        "Confidence": confidence_level,
        "Indicators": indicator_count,
        "Role": role,
        "Patterns": ", ".join(acc_patterns.keys()) if acc_patterns else "None",
        "Amount Involved": format_inr(amount),
    })

if queue_rows:
    df = pd.DataFrame(queue_rows)
    # Color-code priority
    priority_order = {"P1": 0, "P2": 1, "P3": 2, "P4": 3}
    df["_sort"] = df["Priority"].map(priority_order)
    df = df.sort_values("_sort").drop(columns=["_sort"])
    st.dataframe(df, use_container_width=True, hide_index=True)
else:
    st.info("No flagged accounts found.")

st.divider()

# --- Speed Alerts ---
st.subheader("⚡ Transaction Speed Alerts")
speed_alerts = system["speed_alerts"]
if speed_alerts:
    for alert in speed_alerts[:10]:
        color = alert["color"]
        st.markdown(
            f"**{alert['label']}** — {alert['hops']} hops in "
            f"{alert['total_minutes']:.1f} min "
            f"({alert['avg_minutes_per_hop']:.1f} min/hop) | "
            f"Amount: {format_inr(alert['total_amount'])} | "
            f"Accounts: {', '.join(alert.get('accounts', [])[:5])}"
        )
else:
    st.info("No speed anomalies detected.")

st.divider()

# --- Alert Timeline ---
st.subheader("📅 Alert Timeline")
fig = create_alert_timeline(system["transactions_df"], risk_scores)
st.plotly_chart(fig, use_container_width=True)

# --- Account Detail Card ---
st.divider()
st.subheader("🔎 Account Detail Card")
account_list = sorted(risk_scores.keys())
selected = st.selectbox("Select Account", account_list)

if selected:
    risk = risk_scores.get(selected, 0)
    role_info = roles.get(selected, {})
    acc_info = system["accounts_df"][system["accounts_df"]["account_id"] == selected]

    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Risk Score", f"{risk:.1f}/100")
        st.markdown(f"**Level:** {get_risk_level(risk)}")
    with col2:
        st.metric("Role", role_info.get("role", "NORMAL"))
        st.markdown(f"**In-flow:** {format_inr(role_info.get('in_flow', 0))}")
        st.markdown(f"**Out-flow:** {format_inr(role_info.get('out_flow', 0))}")
    with col3:
        if len(acc_info) > 0:
            info = acc_info.iloc[0]
            st.markdown(f"**Type:** {info.get('account_type', 'N/A')}")
            st.markdown(f"**City:** {info.get('branch_city', 'N/A')}")
            st.markdown(f"**Occupation:** {info.get('occupation', 'N/A')}")
            st.markdown(f"**Income:** {format_inr(info.get('declared_annual_income', 0))}")

    # Feature values
    if selected in features_df.index:
        with st.expander("Feature Values"):
            feat_row = features_df.loc[selected]
            st.dataframe(feat_row.to_frame("Value"), use_container_width=True)
