"""Graph Explorer — interactive transaction flow visualization."""
import streamlit as st

st.set_page_config(page_title="Graph Explorer", page_icon="🔍", layout="wide")

system = st.session_state.get("system")
if not system:
    st.error("System not initialized. Go to the Home page first.")
    st.stop()

graph_svc = system["graph_service"]
detection_svc = system["detection_service"]
accounts_df = system["accounts_df"]
risk_scores = detection_svc.risk_scores
roles = detection_svc.roles

st.title("🔍 Graph Explorer")

# ── Controls ─────────────────────────────────────────────────────────────
col1, col2, col3 = st.columns(3)
with col1:
    view_mode = st.selectbox("View", ["Top Risk Subgraph", "Ego Network", "Fund Trail"])
with col2:
    max_nodes = st.slider("Max Nodes", 20, 200, 80)
with col3:
    account_list = sorted(accounts_df["account_id"].tolist())
    selected_account = st.selectbox("Select Account", account_list)

st.divider()

if view_mode == "Top Risk Subgraph":
    sub = graph_svc.get_renderable_subgraph(risk_scores, max_nodes)
elif view_mode == "Ego Network":
    radius = st.slider("Hop Radius", 1, 4, 2)
    sub = graph_svc.get_ego_subgraph(selected_account, radius)
else:
    trail_result = graph_svc.get_fund_trail(selected_account, "both", 5)
    sub = graph_svc.get_ego_subgraph(selected_account, 3)
    if "trails" in trail_result:
        st.info(f"Found {trail_result.get('trail_count', 0)} trails from {selected_account} "
                f"(component size: {trail_result.get('component_size', 0)})")
        if trail_result.get("warning"):
            st.warning(trail_result["warning"])

# ── Render graph ─────────────────────────────────────────────────────────
try:
    from pyvis.network import Network
    import streamlit.components.v1 as components
    import tempfile
    import os

    net = Network(height="600px", width="100%", directed=True,
                  bgcolor="#0e1117", font_color="white")
    net.set_options("""
    {
        "physics": {
            "forceAtlas2Based": {
                "gravitationalConstant": -50,
                "centralGravity": 0.01,
                "springLength": 200,
                "springConstant": 0.08
            },
            "maxVelocity": 50,
            "solver": "forceAtlas2Based",
            "timestep": 0.35,
            "stabilization": {"enabled": true, "iterations": 150}
        },
        "interaction": {"hover": true, "tooltipDelay": 100}
    }
    """)

    risk_colors = {"LOW": "#2ecc71", "MEDIUM": "#f39c12", "HIGH": "#e67e22", "CRITICAL": "#e74c3c"}
    role_shapes = {"SOURCE": "diamond", "MULE": "triangle", "SINK": "square", "NORMAL": "dot"}

    for n in sub.nodes():
        score = risk_scores.get(n, 0)
        level = "CRITICAL" if score >= 76 else "HIGH" if score >= 51 else "MEDIUM" if score >= 26 else "LOW"
        role = roles.get(n, {}).get("role", "NORMAL")
        color = risk_colors.get(level, "#888")
        size = max(10, min(50, score / 2))
        title = f"Account: {n}\nRisk: {level} ({score:.0f})\nRole: {role}"

        net.add_node(str(n), label=str(n)[:12], title=title,
                     color=color, size=size, shape=role_shapes.get(role, "dot"))

    for u, v, data in sub.edges(data=True):
        amt = data.get("amount", 0)
        ch = data.get("channel", "")
        width = max(1, min(8, amt / 500_000))
        net.add_edge(str(u), str(v), title=f"INR {amt:,.0f} via {ch}",
                     width=width, arrows="to")

    with tempfile.NamedTemporaryFile(delete=False, suffix=".html", mode="w") as f:
        net.save_graph(f.name)
        with open(f.name, "r") as hf:
            html = hf.read()
        os.unlink(f.name)
    components.html(html, height=620, scrolling=False)

except ImportError:
    st.warning("pyvis not installed. Showing graph stats instead.")
    stats = graph_svc.get_stats()
    st.json(stats)

# ── Graph stats ──────────────────────────────────────────────────────────
st.divider()
stats = graph_svc.get_stats()
c1, c2, c3, c4 = st.columns(4)
c1.metric("Nodes", f"{stats['num_nodes']:,}")
c2.metric("Edges", f"{stats['num_edges']:,}")
c3.metric("Components", f"{stats['num_components']:,}")
c4.metric("Density", f"{stats['density']:.4f}")

# ── Random walk ──────────────────────────────────────────────────────────
with st.expander("🎲 Random Walk — Find Related Accounts"):
    rw_account = st.selectbox("Start from", account_list, key="rw_account")
    if st.button("Run Random Walk"):
        probs = graph_svc.random_walk(rw_account)
        if probs:
            import pandas as pd
            rw_df = pd.DataFrame([
                {"Account": k, "Probability": f"{v:.4f}", "Risk": f"{risk_scores.get(k, 0):.0f}"}
                for k, v in list(probs.items())[:15]
            ])
            st.dataframe(rw_df, use_container_width=True)
        else:
            st.info("No connected accounts found.")
