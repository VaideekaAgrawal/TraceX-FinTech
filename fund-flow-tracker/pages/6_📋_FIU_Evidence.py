"""
Page 6: FIU Evidence — One-click evidence pack generation (PDF + JSON).
"""
import streamlit as st
import pandas as pd
from datetime import datetime
from core.evidence_generator import EvidenceGenerator
from utils.helpers import format_inr, get_risk_level

st.set_page_config(page_title="FIU Evidence — TraceX", page_icon="📋", layout="wide")
st.title("📋 FIU Evidence Pack Generator")

if "system" not in st.session_state:
    st.warning("Please load data from the main page first.")
    st.stop()

system = st.session_state["system"]
risk_scores = system["risk_scores"]
accounts_df = system["accounts_df"]
transactions_df = system["transactions_df"]
all_patterns = system["all_patterns"]
graph_engine = system["graph_engine"]

# --- Case Management ---
if "cases" not in st.session_state:
    st.session_state["cases"] = {}

# --- Case Builder ---
st.subheader("📝 Build Evidence Case")

col1, col2 = st.columns(2)

with col1:
    # Sort accounts by risk
    sorted_accounts = sorted(risk_scores.items(), key=lambda x: x[1], reverse=True)
    account_options = [f"{a} (Risk: {s:.0f})" for a, s in sorted_accounts]
    selected_display = st.multiselect("Select Accounts to Investigate", account_options)
    selected_accounts = [s.split(" (")[0] for s in selected_display]

with col2:
    pattern_type = st.selectbox("Primary Pattern Type", [
        "Auto-detect", "Layering", "Round-tripping", "Structuring",
        "Dormant Activation", "Fan-In", "Fan-Out",
    ])

case_notes = st.text_area(
    "Case Notes",
    placeholder="Describe the suspicious activity and investigation context...",
    height=100,
)

# --- Generate ---
if st.button("📄 Generate Evidence Pack", type="primary", disabled=len(selected_accounts) == 0):
    case_id = f"CASE-{datetime.now().strftime('%Y%m%d-%H%M%S')}"

    # Build pattern results for selected accounts
    relevant_patterns = {}
    flagged_in_patterns = system["pattern_detector"].get_all_flagged_accounts(all_patterns)

    for ptype, pdata in all_patterns.items():
        if isinstance(pdata, list):
            relevant = []
            for item in pdata:
                item_accounts = set()
                for key in ["accounts", "cycle_nodes", "sources", "destinations"]:
                    if key in item:
                        item_accounts.update(item[key])
                for key in ["account_id", "sink_account", "source_account"]:
                    if key in item:
                        item_accounts.add(item[key])
                if item_accounts & set(selected_accounts):
                    relevant.append(item)
            if relevant:
                relevant_patterns[ptype] = relevant
        elif isinstance(pdata, dict):
            for sub_key, sub_list in pdata.items():
                relevant = []
                for item in sub_list:
                    acc = item.get("account_id", "")
                    if acc in selected_accounts:
                        relevant.append(item)
                if relevant:
                    relevant_patterns.setdefault(ptype, {})[sub_key] = relevant

    generator = EvidenceGenerator()
    try:
        pack = generator.generate_evidence_pack(
            case_id=case_id,
            account_ids=selected_accounts,
            graph_engine=graph_engine,
            risk_data=risk_scores,
            pattern_results=relevant_patterns,
            transactions_df=transactions_df,
            accounts_df=accounts_df,
            case_notes=case_notes,
        )

        # Store case
        st.session_state["cases"][case_id] = {
            "case_id": case_id,
            "accounts": selected_accounts,
            "status": "Open",
            "created": datetime.now().isoformat(),
            "summary": pack["summary"],
        }

        st.success(f"Evidence pack generated: {case_id}")

        # Preview and Download
        st.divider()
        tab1, tab2, tab3 = st.tabs(["📄 PDF Download", "📋 JSON Preview", "📊 Summary"])

        with tab1:
            st.download_button(
                label="⬇️ Download PDF Report",
                data=pack["pdf_bytes"],
                file_name=f"{case_id}_STR_Report.pdf",
                mime="application/pdf",
            )

        with tab2:
            st.json(pack["json_data"][:5000] if len(pack["json_data"]) > 5000
                    else pack["json_data"])
            st.download_button(
                label="⬇️ Download JSON",
                data=pack["json_data"],
                file_name=f"{case_id}_evidence.json",
                mime="application/json",
            )

        with tab3:
            summary = pack["summary"]
            col1, col2, col3 = st.columns(3)
            col1.metric("Accounts", summary["accounts_investigated"])
            col2.metric("Transactions", summary["total_transactions"])
            col3.metric("Amount", format_inr(summary["total_amount_involved"]))
            st.markdown(f"**Max Risk Score:** {summary['max_risk_score']:.1f}")
            st.markdown(f"**Suspicion Categories:** {', '.join(summary['suspicion_categories'])}")

    except Exception as e:
        st.error(f"Error generating evidence pack: {e}")

# --- Active Cases ---
st.divider()
st.subheader("📂 Active Cases")

if st.session_state.get("cases"):
    rows = []
    for cid, case in st.session_state["cases"].items():
        rows.append({
            "Case ID": cid,
            "Accounts": ", ".join(case["accounts"][:3]),
            "Status": case["status"],
            "Created": case["created"][:19],
        })
    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
else:
    st.info("No cases created yet. Select accounts above and generate an evidence pack.")
