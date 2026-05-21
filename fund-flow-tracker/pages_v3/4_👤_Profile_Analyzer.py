"""Profile Analyzer — income vs behaviour, peer comparison, behavioural shifts."""
import streamlit as st
import plotly.graph_objects as go
import plotly.express as px
import pandas as pd
import numpy as np

st.set_page_config(page_title="Profile Analyzer", page_icon="👤", layout="wide")

system = st.session_state.get("system")
if not system:
    st.error("System not initialized. Go to the Home page first.")
    st.stop()

detection_svc = system["detection_service"]
accounts_df = system["accounts_df"]
transactions_df = system["transactions_df"]
risk_scores = detection_svc.risk_scores
roles = detection_svc.roles

st.title("👤 Profile Analyzer")

# ── Account selector ─────────────────────────────────────────────────────
sorted_accounts = sorted(risk_scores.keys(), key=lambda x: risk_scores.get(x, 0), reverse=True)
selected = st.selectbox("Select Account (sorted by risk)", sorted_accounts[:200])

acc_row = accounts_df[accounts_df["account_id"] == selected]
if len(acc_row) == 0:
    st.error("Account not found.")
    st.stop()

info = acc_row.iloc[0]
role_info = roles.get(selected, {"role": "UNKNOWN", "confidence": 0})
score = risk_scores.get(selected, 0)

# ── Profile card ─────────────────────────────────────────────────────────
c1, c2, c3, c4 = st.columns(4)
c1.metric("Risk Score", f"{score:.0f}")
c2.metric("Role", role_info["role"])
c3.metric("Occupation", info.get("occupation", "N/A"))
c4.metric("Income Bracket", info.get("income_bracket", "N/A"))

c5, c6, c7, c8 = st.columns(4)
c5.metric("Account Type", info.get("account_type", "N/A"))
c6.metric("Branch City", info.get("branch_city", "N/A"))
c7.metric("Declared Income", f"₹{info.get('declared_annual_income', 0):,.0f}")
c8.metric("Role Confidence", f"{role_info.get('confidence', 0):.0%}")

st.divider()

# ── Transaction profile ─────────────────────────────────────────────────
acc_txns = transactions_df[
    (transactions_df["source_account"] == selected) |
    (transactions_df["dest_account"] == selected)
].copy()

if len(acc_txns) == 0:
    st.info("No transactions for this account.")
    st.stop()

outgoing = acc_txns[acc_txns["source_account"] == selected]
incoming = acc_txns[acc_txns["dest_account"] == selected]

c1, c2, c3, c4 = st.columns(4)
c1.metric("Total Transactions", len(acc_txns))
c2.metric("Outgoing", len(outgoing))
c3.metric("Incoming", len(incoming))
c4.metric("Net Flow", f"₹{incoming['amount'].sum() - outgoing['amount'].sum():,.0f}")

c5, c6, c7, c8 = st.columns(4)
c5.metric("Total Volume", f"₹{acc_txns['amount'].sum():,.0f}")
c6.metric("Avg Amount", f"₹{acc_txns['amount'].mean():,.0f}")
c7.metric("Max Amount", f"₹{acc_txns['amount'].max():,.0f}")
c8.metric("Counterparties", len(set(acc_txns["source_account"]) | set(acc_txns["dest_account"])) - 1)

# ── Income mismatch ─────────────────────────────────────────────────────
st.divider()
st.subheader("Income vs Transaction Volume")

declared_income = float(info.get("declared_annual_income", 0))
total_volume = float(acc_txns["amount"].sum())
ratio = total_volume / max(declared_income, 1)

fig = go.Figure()
fig.add_trace(go.Bar(x=["Declared Income"], y=[declared_income], name="Declared Income",
                     marker_color="#2ecc71"))
fig.add_trace(go.Bar(x=["Transaction Volume"], y=[total_volume], name="Transaction Volume",
                     marker_color="#e74c3c" if ratio > 10 else "#3498db"))
fig.update_layout(title=f"Income Ratio: {ratio:.1f}x" + (" ⚠️ SUSPICIOUS" if ratio > 10 else ""),
                  template="plotly_dark", height=350, barmode="group")
st.plotly_chart(fig, use_container_width=True)

if ratio > 10:
    st.warning(f"Transaction volume is **{ratio:.1f}×** declared annual income — "
               f"exceeds 10× threshold.")

# ── Transaction timeline ────────────────────────────────────────────────
st.divider()
st.subheader("Transaction Timeline")
acc_txns_sorted = acc_txns.sort_values("timestamp")
acc_txns_sorted["direction"] = acc_txns_sorted.apply(
    lambda r: "Outgoing" if r["source_account"] == selected else "Incoming", axis=1)

fig = px.scatter(acc_txns_sorted, x="timestamp", y="amount", color="direction",
                 hover_data=["source_account", "dest_account", "channel"],
                 color_discrete_map={"Incoming": "#2ecc71", "Outgoing": "#e74c3c"})
fig.update_layout(template="plotly_dark", height=400, title="Transaction Activity")
st.plotly_chart(fig, use_container_width=True)

# ── Behavioural shift ───────────────────────────────────────────────────
st.divider()
st.subheader("Behavioural Shift Analysis")

if "timestamp" in acc_txns.columns:
    daily = acc_txns.set_index("timestamp").resample("D")["amount"].sum().reset_index()
    daily.columns = ["date", "daily_volume"]

    if len(daily) > 7:
        daily["rolling_mean"] = daily["daily_volume"].rolling(7, min_periods=1).mean()
        daily["rolling_std"] = daily["daily_volume"].rolling(7, min_periods=1).std().fillna(0)
        daily["z_score"] = np.where(
            daily["rolling_std"] > 0,
            (daily["daily_volume"] - daily["rolling_mean"]) / daily["rolling_std"],
            0
        )

        fig = go.Figure()
        fig.add_trace(go.Scatter(x=daily["date"], y=daily["daily_volume"],
                                 mode="lines", name="Daily Volume", line=dict(color="#3498db")))
        fig.add_trace(go.Scatter(x=daily["date"], y=daily["rolling_mean"],
                                 mode="lines", name="7-day Mean", line=dict(color="#f39c12", dash="dash")))

        spikes = daily[daily["z_score"].abs() > 2]
        if len(spikes) > 0:
            fig.add_trace(go.Scatter(x=spikes["date"], y=spikes["daily_volume"],
                                     mode="markers", name="Spike (z>2)",
                                     marker=dict(color="#e74c3c", size=10, symbol="triangle-up")))

        fig.update_layout(template="plotly_dark", height=400,
                          title="Daily Volume with Behavioural Spikes")
        st.plotly_chart(fig, use_container_width=True)

        spike_count = len(spikes)
        if spike_count > 0:
            st.warning(f"**{spike_count}** behavioural spikes detected (z-score > 2)")
    else:
        st.info("Insufficient data for behavioural shift analysis (need > 7 days)")

# ── Channel distribution ────────────────────────────────────────────────
st.divider()
st.subheader("Channel Distribution")
if "channel" in acc_txns.columns:
    ch_counts = acc_txns["channel"].value_counts()
    fig = go.Figure(data=[go.Pie(labels=ch_counts.index, values=ch_counts.values,
                                 hole=0.4, textinfo="label+percent")])
    fig.update_layout(template="plotly_dark", height=350)
    st.plotly_chart(fig, use_container_width=True)

# ── Peer comparison ──────────────────────────────────────────────────────
st.divider()
st.subheader("Peer Comparison")
occupation = info.get("occupation", "")
peers = accounts_df[accounts_df["occupation"] == occupation] if occupation else pd.DataFrame()
if len(peers) > 1:
    peer_ids = set(peers["account_id"])
    peer_volumes = []
    for pid in peer_ids:
        vol = transactions_df[
            (transactions_df["source_account"] == pid) |
            (transactions_df["dest_account"] == pid)
        ]["amount"].sum()
        peer_volumes.append(vol)

    avg_peer = np.mean(peer_volumes) if peer_volumes else 0
    std_peer = np.std(peer_volumes) if peer_volumes else 1
    z = (total_volume - avg_peer) / max(std_peer, 1)

    st.markdown(f"**Peer group:** {occupation} ({len(peers)} accounts)")
    c1, c2, c3 = st.columns(3)
    c1.metric("This Account", f"₹{total_volume:,.0f}")
    c2.metric("Peer Average", f"₹{avg_peer:,.0f}")
    c3.metric("Z-Score", f"{z:.2f}", delta="Suspicious" if abs(z) > 2 else "Normal",
              delta_color="inverse" if abs(z) > 2 else "normal")
else:
    st.info("Not enough peers for comparison.")
