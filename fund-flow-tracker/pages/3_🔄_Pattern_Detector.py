"""
Page 3: Pattern Detector — Layering, Round-tripping, Structuring, Dormant, Fan-in/out.
"""
import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from utils.helpers import format_inr
from utils.visualization import create_amount_timeline

st.set_page_config(page_title="Pattern Detector — TraceX", page_icon="🔄", layout="wide")
st.title("🔄 Pattern Detector")

if "system" not in st.session_state:
    st.warning("Please load data from the main page first.")
    st.stop()

system = st.session_state["system"]
all_patterns = system["all_patterns"]
pattern_detector = system["pattern_detector"]

# --- Summary Metrics ---
layering_count = len(all_patterns.get("layering", []))
cycle_count = len(all_patterns.get("round_tripping", []))
struct_classic = len(all_patterns.get("structuring", {}).get("classic", []))
struct_split = len(all_patterns.get("structuring", {}).get("split", []))
dormant_count = len(all_patterns.get("dormant_activation", []))
fan_in_count = len(all_patterns.get("fan_in", []))
fan_out_count = len(all_patterns.get("fan_out", []))

col1, col2, col3, col4, col5, col6 = st.columns(6)
col1.metric("Layering", layering_count)
col2.metric("Round-Trip", cycle_count)
col3.metric("Structuring", struct_classic + struct_split)
col4.metric("Dormant", dormant_count)
col5.metric("Fan-In", fan_in_count)
col6.metric("Fan-Out", fan_out_count)

st.divider()

# --- Tabs ---
tab1, tab2, tab3, tab4, tab5, tab6, tab7 = st.tabs([
    "🔗 Layering", "🔄 Round-Tripping", "📊 Structuring",
    "💤 Dormant Activation", "📥 Fan-In", "📤 Fan-Out", "⚠️ Combined",
])

# --- Tab 1: Layering ---
with tab1:
    st.subheader("Layering Detection")
    st.markdown("Rapid chain transfers with decreasing amounts through multiple accounts.")

    if all_patterns.get("layering"):
        for i, chain_result in enumerate(all_patterns["layering"]):
            with st.expander(
                f"Chain {i + 1}: {chain_result['hops']} hops | "
                f"{format_inr(chain_result['total_amount'])} | "
                f"{chain_result['severity']}",
                expanded=i == 0,
            ):
                st.markdown(f"**Accounts:** {' → '.join(chain_result['accounts'])}")
                st.markdown(f"**Time Span:** {chain_result['time_span_minutes']:.1f} minutes")
                st.markdown(f"**Amount Decay:** {chain_result['amount_decay']:.1%}")

                # Amount degradation chart
                fig = create_amount_timeline(chain_result["chain"])
                st.plotly_chart(fig, use_container_width=True)

                # Transaction details
                rows = []
                for step in chain_result["chain"]:
                    rows.append({
                        "From": step["from"],
                        "To": step["to"],
                        "Amount": format_inr(step["amount"]),
                        "Time": str(step["timestamp"])[:19],
                        "Channel": step["channel"],
                    })
                st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
    else:
        st.info("No layering patterns detected.")

# --- Tab 2: Round-Tripping ---
with tab2:
    st.subheader("Round-Tripping / Cycle Detection")
    st.markdown("Circular transaction flows where money returns to origin.")

    if all_patterns.get("round_tripping"):
        for i, cycle in enumerate(all_patterns["round_tripping"]):
            with st.expander(
                f"Cycle {i + 1}: {cycle['cycle_length']} nodes | "
                f"{format_inr(cycle['total_amount'])} | "
                f"{cycle['severity']}",
                expanded=i == 0,
            ):
                st.markdown(f"**Cycle:** {' → '.join(cycle['cycle_nodes'])} → {cycle['cycle_nodes'][0]}")
                st.markdown(f"**Time Span:** {cycle['time_span_hours']:.1f} hours")
                st.markdown(f"**Iterations:** {cycle['iteration_count']}")

                # Circular visualization
                import plotly.express as px
                nodes = cycle["cycle_nodes"]
                n = len(nodes)
                import math
                angles = [2 * math.pi * i / n for i in range(n)]
                x = [math.cos(a) for a in angles]
                y = [math.sin(a) for a in angles]

                fig = go.Figure()
                # Edges
                for j in range(n):
                    fig.add_trace(go.Scatter(
                        x=[x[j], x[(j + 1) % n]], y=[y[j], y[(j + 1) % n]],
                        mode="lines", line=dict(color="#e74c3c", width=2),
                        showlegend=False,
                    ))
                # Nodes
                fig.add_trace(go.Scatter(
                    x=x, y=y, mode="markers+text",
                    marker=dict(size=20, color="#e74c3c"),
                    text=nodes, textposition="top center",
                    showlegend=False,
                ))
                fig.update_layout(template="plotly_dark", height=300,
                                  xaxis=dict(visible=False), yaxis=dict(visible=False))
                st.plotly_chart(fig, use_container_width=True)

                # Transaction table
                if cycle.get("transactions"):
                    rows = [{"From": t["from"], "To": t["to"],
                             "Amount": format_inr(t["amount"]),
                             "Time": str(t["timestamp"])[:19]}
                            for t in cycle["transactions"]]
                    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
    else:
        st.info("No round-tripping cycles detected.")

# --- Tab 3: Structuring ---
with tab3:
    st.subheader("Structuring Detection")
    st.markdown("Transactions designed to avoid ₹10 lakh CTR reporting threshold.")

    structuring = all_patterns.get("structuring", {})

    # Classic structuring
    st.markdown("### Classic Structuring")
    classic = structuring.get("classic", [])
    if classic:
        for item in classic:
            with st.expander(f"{item['account_id']} — {item['near_threshold_count']} transactions | {item['severity']}"):
                st.markdown(f"**Total Amount:** {format_inr(item['total_amount'])}")

                # Histogram of amounts
                fig = go.Figure(go.Histogram(
                    x=item["amounts"],
                    nbinsx=20,
                    marker_color="#e74c3c",
                ))
                fig.add_vline(x=1_000_000, line_dash="dash", line_color="white",
                              annotation_text="₹10L Threshold")
                fig.update_layout(title="Transaction Amounts", template="plotly_dark",
                                  xaxis_title="Amount (₹)", yaxis_title="Count", height=300)
                st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("No classic structuring detected.")

    # Split structuring
    st.markdown("### Split Structuring")
    split = structuring.get("split", [])
    if split:
        df = pd.DataFrame(split)
        st.dataframe(df, use_container_width=True, hide_index=True)
    else:
        st.info("No split structuring detected.")

# --- Tab 4: Dormant Activation ---
with tab4:
    st.subheader("Dormant Account Activation")
    st.markdown("Accounts inactive for 6+ months that suddenly became active.")

    dormant = all_patterns.get("dormant_activation", [])
    if dormant:
        for item in dormant:
            with st.expander(f"{item['account_id']} — {item['dormancy_days']:.0f} days dormant | {item['severity']}"):
                col1, col2, col3 = st.columns(3)
                col1.metric("Dormancy Period", f"{item['dormancy_days']:.0f} days")
                col2.metric("Burst Transactions", item['burst_txn_count'])
                col3.metric("Burst Amount", format_inr(item['burst_total_amount']))
                st.markdown(f"**Dormant from:** {item['dormancy_start'][:10]} to {item['dormancy_end'][:10]}")
    else:
        st.info("No dormant account activations detected.")

# --- Tab 5: Fan-In ---
with tab5:
    st.subheader("Fan-In Detection")
    st.markdown("Multiple sources funneling into a single account.")

    fan_in = all_patterns.get("fan_in", [])
    if fan_in:
        for item in fan_in:
            with st.expander(f"{item['sink_account']} — {item['unique_sources']} sources | {item['severity']}"):
                st.metric("Total Received", format_inr(item['total_amount']))
                st.markdown(f"**Sources:** {', '.join(item['sources'][:10])}")
    else:
        st.info("No fan-in patterns detected.")

# --- Tab 6: Fan-Out ---
with tab6:
    st.subheader("Fan-Out Detection")
    st.markdown("Single account dispersing to many destinations.")

    fan_out = all_patterns.get("fan_out", [])
    if fan_out:
        for item in fan_out:
            with st.expander(f"{item['source_account']} — {item['unique_destinations']} destinations | {item['severity']}"):
                st.metric("Total Sent", format_inr(item['total_amount']))
                st.markdown(f"**Destinations:** {', '.join(item['destinations'][:10])}")
    else:
        st.info("No fan-out patterns detected.")

# --- Tab 7: Combined Patterns ---
with tab7:
    st.subheader("Combined Pattern Analysis")
    st.markdown("Accounts flagged by multiple independent pattern types — highest risk.")

    combined = pattern_detector.detect_combined_patterns(all_patterns)
    if combined:
        rows = []
        for item in combined:
            rows.append({
                "Account": item["account_id"],
                "Patterns": ", ".join(item["patterns"]),
                "Pattern Count": item["pattern_count"],
                "Combo Score": item["combo_score"],
                "Severity": item["severity"],
            })
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
    else:
        st.info("No accounts flagged by multiple patterns.")

# --- First Suspicious Point ---
st.divider()
st.subheader("⚡ First Suspicious Point")
account_list = sorted(system["graph_engine"].G.nodes())
fsp_account = st.selectbox("Select Account", account_list, key="fsp")

if st.button("Detect First Suspicious Point"):
    result = pattern_detector.detect_first_suspicious_point(fsp_account)
    if result:
        st.success(f"First suspicious transaction detected!")
        col1, col2, col3 = st.columns(3)
        col1.metric("Transaction", result["txn_id"])
        col2.metric("Amount", format_inr(result["amount"]))
        col3.metric("Z-Score", f"{result['z_score']:.2f}")
        st.markdown(f"**Time:** {result['timestamp']} | **Method:** {result['detection_method']}")
    else:
        st.info("No suspicious point detected (insufficient transaction history).")
