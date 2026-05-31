"""
Page 1: Interactive Graph Explorer — the star of the demo.
"""
import streamlit as st
import pandas as pd
import networkx as nx
from pyvis.network import Network
import streamlit.components.v1 as components
from utils.helpers import get_risk_color, get_risk_level, format_inr

st.set_page_config(page_title="Graph Explorer — TraceX", page_icon="🔍", layout="wide")
st.title("🔍 Graph Explorer")

if "system" not in st.session_state:
    st.warning("Please load data from the main page first.")
    st.stop()

system = st.session_state["system"]
graph_engine = system["graph_engine"]
risk_scores = system["risk_scores"]
roles = system["roles"]

# --- Controls ---
col1, col2, col3, col4 = st.columns(4)

with col1:
    account_list = sorted(graph_engine.G.nodes())
    selected_account = st.selectbox("Center on Account", ["(Full Graph)"] + account_list)

with col2:
    depth = st.slider("Hop Depth", 1, 5, 2)

with col3:
    max_nodes = st.slider("Max Nodes", 20, 300, 80)

with col4:
    view_mode = st.radio("View Mode", ["All", "Suspicious Only"], horizontal=True)

# --- Filter Panel ---
with st.expander("🔧 Filters"):
    fcol1, fcol2, fcol3 = st.columns(3)
    with fcol1:
        min_risk = st.slider("Min Risk Score", 0, 100, 0)
    with fcol2:
        channel_filter = st.multiselect(
            "Channel Filter",
            system["transactions_df"]["channel"].unique().tolist(),
            default=[],
        )
    with fcol3:
        min_amount = st.number_input("Min Amount (₹)", value=0, step=100000)

# --- Build subgraph ---
if selected_account != "(Full Graph)" and selected_account in graph_engine.G:
    subgraph = graph_engine.get_ego_subgraph(selected_account, radius=depth)
else:
    subgraph = graph_engine.get_renderable_subgraph(risk_scores, max_nodes=max_nodes)

# Apply filters
if view_mode == "Suspicious Only":
    suspicious_nodes = [n for n in subgraph.nodes() if risk_scores.get(n, 0) > 50]
    if suspicious_nodes:
        all_nodes = set(suspicious_nodes)
        for n in suspicious_nodes:
            all_nodes.update(list(subgraph.successors(n))[:3])
            all_nodes.update(list(subgraph.predecessors(n))[:3])
        subgraph = subgraph.subgraph(list(all_nodes)[:max_nodes]).copy()

if min_risk > 0:
    nodes = [n for n in subgraph.nodes() if risk_scores.get(n, 0) >= min_risk]
    if nodes:
        subgraph = subgraph.subgraph(nodes).copy()

# --- Render with PyVis ---
net = Network(height="600px", width="100%", bgcolor="#0e1117", font_color="white",
              directed=True, notebook=False)
net.barnes_hut(gravity=-5000, central_gravity=0.3, spring_length=100)

role_shapes = {"SOURCE": "diamond", "MULE": "triangle", "SINK": "square", "NORMAL": "dot"}

for node in subgraph.nodes():
    risk = risk_scores.get(node, 0)
    color = get_risk_color(risk)
    role = roles.get(node, {}).get("role", "NORMAL")
    shape = role_shapes.get(role, "dot")
    size = 10 + risk * 0.3

    label = f"{node}\n{get_risk_level(risk)}: {risk:.0f}"
    title = (f"<b>{node}</b><br>"
             f"Risk: {risk:.1f}/100 ({get_risk_level(risk)})<br>"
             f"Role: {role}<br>"
             f"In-flow: {format_inr(roles.get(node, {}).get('in_flow', 0))}<br>"
             f"Out-flow: {format_inr(roles.get(node, {}).get('out_flow', 0))}")

    net.add_node(node, label=node, title=title, color=color, size=size, shape=shape)

for u, v, data in subgraph.edges(data=True):
    amount = data.get("amount", 0)
    channel = data.get("channel", "")
    ts = str(data.get("timestamp", ""))[:16]

    channel_colors = {
        "UPI": "#9b59b6", "NEFT": "#3498db", "RTGS": "#2980b9",
        "IMPS": "#1abc9c", "branch_cash": "#27ae60", "ATM": "#f39c12",
        "cheque": "#e67e22", "net_banking": "#95a5a6", "mobile_app": "#e74c3c",
    }
    edge_color = channel_colors.get(channel, "#7f8c8d")
    is_laundering = data.get("is_laundering", 0)
    if is_laundering:
        edge_color = "#ff0000"

    title = f"{format_inr(amount)} via {channel}<br>{ts}"
    width = max(1, min(amount / 200000, 5))

    net.add_edge(u, v, title=title, color=edge_color, width=width,
                 arrows="to", smooth={"type": "curvedCW", "roundness": 0.2})

# Save and render
html = net.generate_html()
components.html(html, height=620, scrolling=False)

# --- Legend ---
st.markdown("---")
lcol1, lcol2 = st.columns(2)
with lcol1:
    st.markdown("**Node Colors (Risk Level)**")
    st.markdown("🟢 LOW (0-25) | 🟡 MEDIUM (26-50) | 🟠 HIGH (51-75) | 🔴 CRITICAL (76-100)")
with lcol2:
    st.markdown("**Node Shapes (Role)**")
    st.markdown("◆ SOURCE | △ MULE | ■ SINK | ● NORMAL")

# --- Path Tracer ---
st.divider()
st.subheader("🛤️ Fund Trail Tracer")
pcol1, pcol2, pcol3 = st.columns(3)

with pcol1:
    trace_account = st.selectbox("Trace Account", account_list, key="trace_acc")
with pcol2:
    trace_direction = st.selectbox("Direction", ["forward", "backward", "both"])
with pcol3:
    trace_depth = st.slider("Max Depth", 1, 8, 3, key="trace_depth")

if st.button("🔍 Trace Flow"):
    trail_result = graph_engine.get_fund_trail(trace_account, trace_direction, trace_depth)

    if trail_result.get("error"):
        st.error(trail_result["error"])
    elif trail_result.get("warning"):
        st.warning(trail_result["warning"])
    else:
        st.success(f"Found {trail_result['trail_count']} trails "
                   f"(component size: {trail_result['component_size']})")

        for i, trail in enumerate(trail_result["trails"][:5]):
            with st.expander(f"Trail {i + 1} ({len(trail)} hops)"):
                rows = []
                for step in trail:
                    rows.append({
                        "From": step["from"],
                        "To": step["to"],
                        "Amount": format_inr(step["amount"]),
                        "Time": str(step["timestamp"])[:19],
                        "Channel": step["channel"],
                    })
                st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

# --- Random Walk Accomplice Detection ---
st.divider()
st.subheader("🎯 Accomplice Detection (Random Walk)")
rw_account = st.selectbox("Suspicious Account", account_list, key="rw_acc")

if st.button("🔎 Find Likely Accomplices"):
    probs = graph_engine.random_walk_with_restart(rw_account)
    if probs:
        top_10 = list(probs.items())[:10]
        rows = []
        for acc, prob in top_10:
            rows.append({
                "Account": acc,
                "Association Probability": f"{prob:.4f}",
                "Risk Score": round(risk_scores.get(acc, 0), 1),
                "Role": roles.get(acc, {}).get("role", "NORMAL"),
            })
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
    else:
        st.info("No connections found for this account.")
