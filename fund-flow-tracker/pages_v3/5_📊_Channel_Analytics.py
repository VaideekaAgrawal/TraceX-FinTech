"""Channel Analytics — transaction channel heatmaps and patterns."""
import streamlit as st
import plotly.graph_objects as go
import plotly.express as px
import pandas as pd
import numpy as np

st.set_page_config(page_title="Channel Analytics", page_icon="📊", layout="wide")

system = st.session_state.get("system")
if not system:
    st.error("System not initialized. Go to the Home page first.")
    st.stop()

detection_svc = system["detection_service"]
transactions_df = system["transactions_df"]
risk_scores = detection_svc.risk_scores

st.title("📊 Channel Analytics")

# ── Overall channel distribution ─────────────────────────────────────────
st.subheader("Transaction Volume by Channel")

if "channel" not in transactions_df.columns:
    st.warning("No channel data available.")
    st.stop()

c1, c2 = st.columns([1, 1])

with c1:
    ch_volume = transactions_df.groupby("channel")["amount"].sum().sort_values(ascending=False)
    fig = go.Figure(data=[go.Pie(labels=ch_volume.index, values=ch_volume.values,
                                 hole=0.4, textinfo="label+percent")])
    fig.update_layout(title="Volume by Channel", template="plotly_dark", height=400)
    st.plotly_chart(fig, use_container_width=True)

with c2:
    ch_count = transactions_df["channel"].value_counts()
    fig = go.Figure(data=[go.Bar(x=ch_count.index, y=ch_count.values,
                                 marker_color="#3498db")])
    fig.update_layout(title="Count by Channel", template="plotly_dark", height=400)
    st.plotly_chart(fig, use_container_width=True)

# ── Channel metrics table ───────────────────────────────────────────────
st.divider()
st.subheader("Channel Metrics")
ch_stats = transactions_df.groupby("channel").agg(
    count=("amount", "count"),
    total_volume=("amount", "sum"),
    avg_amount=("amount", "mean"),
    max_amount=("amount", "max"),
    min_amount=("amount", "min"),
    std_amount=("amount", "std"),
).reset_index()

ch_stats["total_volume"] = ch_stats["total_volume"].apply(lambda x: f"₹{x:,.0f}")
ch_stats["avg_amount"] = ch_stats["avg_amount"].apply(lambda x: f"₹{x:,.0f}")
ch_stats["max_amount"] = ch_stats["max_amount"].apply(lambda x: f"₹{x:,.0f}")
ch_stats["min_amount"] = ch_stats["min_amount"].apply(lambda x: f"₹{x:,.0f}")
ch_stats["std_amount"] = ch_stats["std_amount"].apply(lambda x: f"₹{x:,.0f}")

st.dataframe(ch_stats, use_container_width=True, hide_index=True)

# ── Hourly heatmap ──────────────────────────────────────────────────────
st.divider()
st.subheader("Channel × Hour Heatmap")
txn = transactions_df.copy()
txn["hour"] = txn["timestamp"].dt.hour if hasattr(txn["timestamp"], "dt") else 0

heatmap = txn.groupby(["channel", "hour"])["amount"].sum().reset_index()
pivot = heatmap.pivot_table(index="channel", columns="hour", values="amount", fill_value=0)

fig = go.Figure(data=go.Heatmap(
    z=pivot.values,
    x=[f"{h:02d}:00" for h in pivot.columns],
    y=pivot.index,
    colorscale="YlOrRd",
    text=np.round(pivot.values / 1e6, 1),
    texttemplate="%{text}M",
))
fig.update_layout(title="Volume Heatmap (Channel × Hour)",
                  template="plotly_dark", height=400)
st.plotly_chart(fig, use_container_width=True)

# ── Day of week heatmap ─────────────────────────────────────────────────
st.divider()
st.subheader("Channel × Day of Week Heatmap")
txn["day_name"] = txn["timestamp"].dt.day_name() if hasattr(txn["timestamp"], "dt") else "Unknown"
day_order = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]

heatmap2 = txn.groupby(["channel", "day_name"])["amount"].sum().reset_index()
pivot2 = heatmap2.pivot_table(index="channel", columns="day_name", values="amount", fill_value=0)
pivot2 = pivot2.reindex(columns=[d for d in day_order if d in pivot2.columns])

fig = go.Figure(data=go.Heatmap(
    z=pivot2.values,
    x=pivot2.columns,
    y=pivot2.index,
    colorscale="Viridis",
    text=np.round(pivot2.values / 1e6, 1),
    texttemplate="%{text}M",
))
fig.update_layout(title="Volume Heatmap (Channel × Day)",
                  template="plotly_dark", height=400)
st.plotly_chart(fig, use_container_width=True)

# ── Risk by channel ─────────────────────────────────────────────────────
st.divider()
st.subheader("Risk Distribution by Channel")

txn["risk"] = txn["source_account"].map(risk_scores).fillna(0)
fig = px.box(txn, x="channel", y="risk", color="channel",
             title="Risk Score Distribution per Channel")
fig.update_layout(template="plotly_dark", height=400, showlegend=False)
st.plotly_chart(fig, use_container_width=True)

# ── High-risk channel combinations ──────────────────────────────────────
st.divider()
st.subheader("High-Risk Channel Patterns")

high_risk_txns = txn[txn["risk"] >= 51]
if len(high_risk_txns) > 0:
    ch_risk_counts = high_risk_txns["channel"].value_counts()
    ch_risk_pct = (ch_risk_counts / txn["channel"].value_counts()).fillna(0) * 100

    risk_ch_df = pd.DataFrame({
        "Channel": ch_risk_pct.index,
        "High Risk %": ch_risk_pct.values.round(1),
        "High Risk Count": ch_risk_counts.reindex(ch_risk_pct.index, fill_value=0).values,
    })
    risk_ch_df = risk_ch_df.sort_values("High Risk %", ascending=False)
    st.dataframe(risk_ch_df, use_container_width=True, hide_index=True)
else:
    st.info("No high-risk transactions detected.")
