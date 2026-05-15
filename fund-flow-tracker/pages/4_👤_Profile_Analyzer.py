"""
Page 4: Profile Analyzer — Profile-vs-behavior mismatch detection.
"""
import streamlit as st
import pandas as pd
from utils.helpers import format_inr
from utils.visualization import create_scatter_income_vs_volume

st.set_page_config(page_title="Profile Analyzer — TraceX", page_icon="👤", layout="wide")
st.title("👤 Profile Analyzer")

if "system" not in st.session_state:
    st.warning("Please load data from the main page first.")
    st.stop()

system = st.session_state["system"]
profile_analyzer = system["profile_analyzer"]

# --- Scatter Plot ---
st.subheader("Income vs Transaction Volume")
st.markdown("Accounts far above the diagonal line indicate profile-behavior mismatch.")

scatter_data = profile_analyzer.get_scatter_data()
fig = create_scatter_income_vs_volume(scatter_data)
st.plotly_chart(fig, use_container_width=True)

# --- Mismatches Table ---
st.divider()
st.subheader("🚨 Detected Mismatches")

mismatches = profile_analyzer.detect_all_mismatches()
if mismatches:
    col1, col2, col3 = st.columns(3)
    critical = sum(1 for m in mismatches if m["severity"] == "CRITICAL")
    high = sum(1 for m in mismatches if m["severity"] == "HIGH")
    medium = sum(1 for m in mismatches if m["severity"] == "MEDIUM")
    col1.metric("🔴 Critical", critical)
    col2.metric("🟠 High", high)
    col3.metric("🟡 Medium", medium)

    rows = []
    for m in mismatches:
        rows.append({
            "Account": m["account_id"],
            "Occupation": m["occupation"],
            "Income Bracket": m["income_bracket"],
            "Declared Income": format_inr(m["declared_income"]),
            "Actual Volume": format_inr(m["actual_volume"]),
            "Volume/Income Ratio": f"{m['volume_to_income_ratio']:.1f}x",
            "Severity": m["severity"],
        })
    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
else:
    st.info("No profile mismatches detected.")

# --- Individual Analysis ---
st.divider()
st.subheader("🔎 Individual Account Analysis")
account_list = sorted(system["accounts_df"]["account_id"].tolist())
selected = st.selectbox("Select Account", account_list)

if st.button("Analyze Profile"):
    result = profile_analyzer.compute_peer_group(selected)
    if "error" in result:
        st.warning(result["error"])
    else:
        col1, col2, col3, col4 = st.columns(4)
        col1.metric("Occupation", result["occupation"])
        col2.metric("Declared Income", format_inr(result["declared_income"]))
        col3.metric("Actual Volume", format_inr(result["actual_volume"]))
        col4.metric("Z-Score vs Peers", f"{result['z_score']:.2f}")

        st.markdown(f"**Peer Group:** {result['peer_count']} accounts with same "
                    f"occupation ({result['occupation']}) and income bracket ({result['income_bracket']})")
        st.markdown(f"**Peer Mean Volume:** {format_inr(result['peer_mean_volume'])}")
        st.markdown(f"**Peer Std Volume:** {format_inr(result['peer_std_volume'])}")

        if result["is_mismatch"]:
            st.error(f"⚠️ MISMATCH DETECTED — Severity: {result['mismatch_severity']}")
        else:
            st.success("✅ Account behavior is within normal range for peer group.")
