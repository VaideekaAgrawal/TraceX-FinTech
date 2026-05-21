"""Pattern Detector — 5 independent fraud detection algorithms."""
import streamlit as st
import plotly.graph_objects as go
import plotly.express as px
import pandas as pd

st.set_page_config(page_title="Pattern Detector", page_icon="🔄", layout="wide")

system = st.session_state.get("system")
if not system:
    st.error("System not initialized. Go to the Home page first.")
    st.stop()

detection_svc = system["detection_service"]
graph_svc = system["graph_service"]
risk_scores = detection_svc.risk_scores
detection_results = detection_svc.detection_results

st.title("🔄 Pattern Detector — 5 Fraud Detectors")

# ── Overview ─────────────────────────────────────────────────────────────
det_meta = {
    "layering": {"icon": "🔗", "name": "Layering", "color": "#e74c3c",
                 "desc": "Multi-hop transaction chains with amount decay, designed to obscure the source of funds."},
    "round_trip": {"icon": "🔄", "name": "Round-Trip", "color": "#9b59b6",
                   "desc": "Circular fund flows where money returns to origin through intermediaries."},
    "structuring": {"icon": "💰", "name": "Structuring", "color": "#e67e22",
                    "desc": "Splitting transactions to stay below reporting thresholds (CTR)."},
    "dormancy": {"icon": "💤", "name": "Dormancy Activation", "color": "#3498db",
                 "desc": "Inactive accounts suddenly reactivated with high-volume transactions."},
    "profile_mismatch": {"icon": "👤", "name": "Profile Mismatch", "color": "#1abc9c",
                         "desc": "Transaction patterns inconsistent with declared income or peer behaviour."},
}

cols = st.columns(5)
for col, (det_type, meta) in zip(cols, det_meta.items()):
    count = len(detection_results.get(det_type, []))
    col.metric(f"{meta['icon']} {meta['name']}", count)

# ── Pattern selector ─────────────────────────────────────────────────────
st.divider()
selected = st.selectbox(
    "Select detection type to explore",
    list(det_meta.keys()),
    format_func=lambda x: f"{det_meta[x]['icon']} {det_meta[x]['name']}",
)

meta = det_meta[selected]
dets = detection_results.get(selected, [])

st.subheader(f"{meta['icon']} {meta['name']} Detections ({len(dets)})")
st.caption(meta["desc"])

if not dets:
    st.info(f"No {meta['name']} patterns detected.")
    st.stop()

# ── Results table ────────────────────────────────────────────────────────
rows = []
for d in dets:
    rows.append({
        "Account": d.account_id,
        "Confidence": f"{d.confidence:.0%}",
        "Severity": d.severity,
        "Description": d.description,
        "Risk Score": f"{risk_scores.get(d.account_id, 0):.0f}",
    })

st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

# ── Severity distribution ───────────────────────────────────────────────
st.divider()
sev_counts = {}
for d in dets:
    sev_counts[d.severity] = sev_counts.get(d.severity, 0) + 1

c1, c2 = st.columns([1, 2])
with c1:
    st.markdown("**Severity Breakdown**")
    for sev in ["CRITICAL", "HIGH", "MEDIUM", "LOW"]:
        if sev in sev_counts:
            st.write(f"• **{sev}**: {sev_counts[sev]}")

with c2:
    conf_values = [d.confidence for d in dets]
    fig = go.Figure(go.Histogram(x=conf_values, nbinsx=20, marker_color=meta["color"]))
    fig.update_layout(title="Confidence Score Distribution",
                      xaxis_title="Confidence", yaxis_title="Count",
                      template="plotly_dark", height=300)
    st.plotly_chart(fig, use_container_width=True)

# ── Detail view ──────────────────────────────────────────────────────────
st.divider()
st.subheader("Detection Detail")
det_account = st.selectbox(
    "Select detection",
    range(len(dets)),
    format_func=lambda i: f"{dets[i].account_id} — {dets[i].severity} ({dets[i].confidence:.0%})",
)

d = dets[det_account]
c1, c2 = st.columns(2)
with c1:
    st.markdown(f"**Account:** `{d.account_id}`")
    st.markdown(f"**Detection Type:** {d.detection_type}")
    st.markdown(f"**Severity:** {d.severity}")
    st.markdown(f"**Confidence:** {d.confidence:.0%}")
    st.markdown(f"**Risk Score:** {risk_scores.get(d.account_id, 0):.0f}")

with c2:
    st.markdown(f"**Description:** {d.description}")
    if d.evidence:
        st.markdown("**Evidence:**")
        for k, v in d.evidence.items():
            st.write(f"• {k}: {v}")
    if d.related_accounts:
        st.markdown(f"**Related Accounts:** {', '.join(d.related_accounts[:10])}")

# ── Ego graph of detected account ────────────────────────────────────────
with st.expander(f"🔍 Network around {d.account_id}"):
    try:
        from pyvis.network import Network
        import streamlit.components.v1 as components
        import tempfile
        import os

        sub = graph_svc.get_ego_subgraph(d.account_id, 2)
        net = Network(height="400px", width="100%", directed=True,
                      bgcolor="#0e1117", font_color="white")

        risk_colors = {"LOW": "#2ecc71", "MEDIUM": "#f39c12", "HIGH": "#e67e22", "CRITICAL": "#e74c3c"}

        for n in sub.nodes():
            score = risk_scores.get(n, 0)
            level = "CRITICAL" if score >= 76 else "HIGH" if score >= 51 else "MEDIUM" if score >= 26 else "LOW"
            color = meta["color"] if n == d.account_id else risk_colors.get(level, "#888")
            size = 30 if n == d.account_id else max(10, score / 3)
            net.add_node(str(n), label=str(n)[:12], color=color, size=size,
                         title=f"{n}\nRisk: {score:.0f}")

        for u, v, data in sub.edges(data=True):
            net.add_edge(str(u), str(v), title=f"INR {data.get('amount', 0):,.0f}",
                         arrows="to", width=2)

        with tempfile.NamedTemporaryFile(delete=False, suffix=".html", mode="w") as f:
            net.save_graph(f.name)
            with open(f.name, "r") as hf:
                html = hf.read()
            os.unlink(f.name)
        components.html(html, height=420)
    except ImportError:
        st.info("pyvis not installed — network visualization unavailable.")

# ── Cross-detection analysis ─────────────────────────────────────────────
st.divider()
st.subheader("Multi-Pattern Detection Overlap")
all_det_accounts = {}
for det_type, dets_list in detection_results.items():
    for det in dets_list:
        all_det_accounts.setdefault(det.account_id, set()).add(det_type)

multi = {k: v for k, v in all_det_accounts.items() if len(v) > 1}
if multi:
    st.markdown(f"**{len(multi)} accounts** flagged by multiple detectors:")
    multi_rows = []
    for acc, patterns in sorted(multi.items(), key=lambda x: len(x[1]), reverse=True)[:20]:
        multi_rows.append({
            "Account": acc,
            "Patterns": ", ".join(sorted(patterns)),
            "Count": len(patterns),
            "Risk": f"{risk_scores.get(acc, 0):.0f}",
        })
    st.dataframe(pd.DataFrame(multi_rows), use_container_width=True, hide_index=True)
else:
    st.info("No accounts flagged by multiple detectors.")
