"""
Page 5: Channel Analytics — Sankey diagram + Channel heatmap.
"""
import streamlit as st
import pandas as pd
from utils.visualization import create_sankey_diagram, create_channel_heatmap
from utils.helpers import format_inr

st.set_page_config(page_title="Channel Analytics — TraceX", page_icon="📊", layout="wide")
st.title("📊 Channel Analytics")

if "system" not in st.session_state:
    st.warning("Please load data from the main page first.")
    st.stop()

system = st.session_state["system"]
txns = system["transactions_df"]
accounts = system["accounts_df"]

# --- Channel summary ---
st.subheader("Channel Summary")
channel_stats = txns.groupby("channel").agg(
    count=("amount", "size"),
    total=("amount", "sum"),
    avg=("amount", "mean"),
    max_amt=("amount", "max"),
).reset_index()
channel_stats["total_formatted"] = channel_stats["total"].apply(format_inr)
channel_stats["avg_formatted"] = channel_stats["avg"].apply(format_inr)
channel_stats = channel_stats.sort_values("total", ascending=False)

st.dataframe(
    channel_stats[["channel", "count", "total_formatted", "avg_formatted", "max_amt"]].rename(
        columns={"channel": "Channel", "count": "Transactions",
                 "total_formatted": "Total Volume", "avg_formatted": "Avg Amount",
                 "max_amt": "Max Amount"}
    ),
    use_container_width=True, hide_index=True,
)

st.divider()

# --- Sankey Diagram ---
st.subheader("Transaction Flow: Account Type → Channel → Account Type")
fig = create_sankey_diagram(txns, accounts)
st.plotly_chart(fig, use_container_width=True)

st.divider()

# --- Channel Heatmap ---
st.subheader("Transaction Volume: Channel × Hour of Day")
fig = create_channel_heatmap(txns)
st.plotly_chart(fig, use_container_width=True)

st.divider()

# --- Suspicious channel usage ---
st.subheader("🔍 Suspicious Channel Patterns")
risk_scores = system["risk_scores"]
high_risk_accs = [a for a, s in risk_scores.items() if s > 50]
if high_risk_accs:
    suspicious_txns = txns[
        (txns["source_account"].isin(high_risk_accs)) |
        (txns["dest_account"].isin(high_risk_accs))
    ]
    sus_channels = suspicious_txns.groupby("channel").agg(
        count=("amount", "size"),
        total=("amount", "sum"),
    ).reset_index().sort_values("total", ascending=False)

    sus_channels["total_formatted"] = sus_channels["total"].apply(format_inr)
    st.dataframe(
        sus_channels.rename(columns={"channel": "Channel", "count": "Suspicious Txns",
                                      "total_formatted": "Total Volume"}),
        use_container_width=True, hide_index=True,
    )
else:
    st.info("No high-risk accounts to analyze.")
