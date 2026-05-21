"""FIU Evidence — Generate STR evidence packs for regulatory submission."""
import base64
import streamlit as st
import pandas as pd

st.set_page_config(page_title="FIU Evidence", page_icon="📋", layout="wide")

system = st.session_state.get("system")
if not system:
    st.error("System not initialized. Go to the Home page first.")
    st.stop()

detection_svc = system["detection_service"]
investigation_svc = system["investigation_service"]
graph_svc = system["graph_service"]
accounts_df = system["accounts_df"]
transactions_df = system["transactions_df"]
risk_scores = detection_svc.risk_scores
detection_results = detection_svc.detection_results
roles = detection_svc.roles

st.title("📋 FIU Evidence — STR Generator")

tabs = st.tabs(["📄 Generate STR", "🔔 Alerts", "📁 Cases"])

# ═══════════════════════════════════════════════════════════════════════════
# TAB 1: Generate STR
# ═══════════════════════════════════════════════════════════════════════════
with tabs[0]:
    st.subheader("Generate Suspicious Transaction Report (STR)")

    sorted_accounts = sorted(risk_scores.keys(), key=lambda x: risk_scores.get(x, 0), reverse=True)
    selected_accounts = st.multiselect(
        "Select accounts for STR",
        sorted_accounts[:100],
        default=sorted_accounts[:3] if len(sorted_accounts) >= 3 else sorted_accounts,
        format_func=lambda x: f"{x} (Risk: {risk_scores.get(x, 0):.0f}, Role: {roles.get(x, {}).get('role', '?')})",
    )

    case_notes = st.text_area("Investigation Notes", placeholder="Describe the suspicious activity...")

    if selected_accounts and st.button("🔒 Generate Evidence Pack", type="primary"):
        with st.spinner("Generating STR evidence pack..."):
            case = investigation_svc.create_case(
                account_ids=selected_accounts,
                typology="Manual STR Generation",
                priority="P2",
                notes=case_notes,
            )

            pack = investigation_svc.generate_evidence(
                case_id=case.case_id,
                account_ids=selected_accounts,
                graph=graph_svc.graph,
                risk_scores=risk_scores,
                detection_results=detection_results,
                transactions_df=transactions_df,
                accounts_df=accounts_df,
                notes=case_notes,
            )

        st.success(f"Evidence pack generated — STR Reference: **{pack.str_reference}**")

        c1, c2, c3 = st.columns(3)
        c1.metric("Case ID", case.case_id)
        c2.metric("STR Reference", pack.str_reference)
        c3.metric("Integrity Hash", pack.json_hash[:16] + "...")

        # Download button
        pdf_b64 = base64.b64encode(pack.pdf_bytes).decode()
        st.download_button(
            label="📥 Download STR (PDF)",
            data=pack.pdf_bytes,
            file_name=f"STR_{pack.str_reference}.pdf",
            mime="application/pdf",
        )

        # Preview JSON evidence
        with st.expander("📄 JSON Evidence Summary"):
            st.json(pack.json_evidence)

# ═══════════════════════════════════════════════════════════════════════════
# TAB 2: Alerts
# ═══════════════════════════════════════════════════════════════════════════
with tabs[1]:
    st.subheader("🔔 Active Alerts")

    status_filter = st.selectbox("Filter by status",
                                 ["ALL", "OPEN", "ACKNOWLEDGED", "INVESTIGATING", "RESOLVED"])
    alerts = investigation_svc.list_alerts(
        None if status_filter == "ALL" else status_filter
    )

    if not alerts:
        st.info("No alerts found.")
    else:
        st.write(f"**{len(alerts)} alerts**")
        rows = []
        for a in alerts:
            rows.append({
                "Alert ID": a.alert_id,
                "Account": ", ".join(a.account_ids[:3]),
                "Type": a.alert_type,
                "Priority": a.priority,
                "Status": a.status,
                "Created": a.created_at[:19] if a.created_at else "",
            })
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

        # Alert detail
        selected_alert = st.selectbox(
            "Select alert for detail",
            [a.alert_id for a in alerts],
        )
        alert = next((a for a in alerts if a.alert_id == selected_alert), None)
        if alert:
            c1, c2 = st.columns(2)
            with c1:
                st.markdown(f"**Type:** {alert.alert_type}")
                st.markdown(f"**Priority:** {alert.priority}")
                st.markdown(f"**Status:** {alert.status}")
                st.markdown(f"**Accounts:** {', '.join(alert.account_ids)}")
            with c2:
                st.markdown(f"**Description:** {alert.description}")
                st.markdown(f"**Created:** {alert.created_at}")

            if st.button("Create Case from Alert"):
                case = investigation_svc.create_case(
                    alert.account_ids, alert.alert_type, alert.priority,
                )
                st.success(f"Case {case.case_id} created from alert.")
                st.rerun()

# ═══════════════════════════════════════════════════════════════════════════
# TAB 3: Cases
# ═══════════════════════════════════════════════════════════════════════════
with tabs[2]:
    st.subheader("📁 Case Management")

    case_status = st.selectbox("Filter cases",
                               ["ALL", "OPEN", "INVESTIGATING", "ESCALATED", "CLOSED_TP", "CLOSED_FP"],
                               key="case_filter")
    cases = investigation_svc.list_cases(
        None if case_status == "ALL" else case_status
    )

    if not cases:
        st.info("No cases found.")
    else:
        st.write(f"**{len(cases)} cases**")
        rows = []
        for c in cases:
            rows.append({
                "Case ID": c.case_id,
                "Accounts": ", ".join(c.account_ids[:3]),
                "Typology": c.typology,
                "Priority": c.priority,
                "Status": c.status,
                "Created": c.created_at[:19] if c.created_at else "",
            })
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

        # Case actions
        selected_case = st.selectbox("Select case", [c.case_id for c in cases])
        case = next((c for c in cases if c.case_id == selected_case), None)

        if case:
            st.markdown(f"### Case: {case.case_id}")
            c1, c2 = st.columns(2)
            with c1:
                st.markdown(f"**Typology:** {case.typology}")
                st.markdown(f"**Priority:** {case.priority}")
                st.markdown(f"**Status:** {case.status}")
                st.markdown(f"**Accounts:** {', '.join(case.account_ids)}")

            with c2:
                new_status = st.selectbox(
                    "Update status",
                    ["OPEN", "INVESTIGATING", "ESCALATED"],
                    index=["OPEN", "INVESTIGATING", "ESCALATED"].index(case.status) if case.status in ["OPEN", "INVESTIGATING", "ESCALATED"] else 0,
                )
                notes = st.text_input("Notes")
                if st.button("Update Case"):
                    updated = investigation_svc.update_case(case.case_id, new_status, notes)
                    if updated:
                        st.success(f"Case updated to {new_status}")
                        st.rerun()

            st.divider()
            col1, col2 = st.columns(2)
            with col1:
                if st.button("✅ Resolve as True Positive", type="primary"):
                    investigation_svc.resolve_case(case.case_id, "Confirmed suspicious activity", True)
                    st.success("Case resolved as TRUE POSITIVE")
                    st.rerun()
            with col2:
                if st.button("❌ Resolve as False Positive"):
                    investigation_svc.resolve_case(case.case_id, "False alarm", False)
                    st.success("Case resolved as FALSE POSITIVE")
                    st.rerun()

            # Generate evidence from case
            st.divider()
            if st.button("📋 Generate STR for this Case"):
                pack = investigation_svc.generate_evidence(
                    case.case_id, case.account_ids,
                    graph_svc.graph, risk_scores, detection_results,
                    transactions_df, accounts_df,
                )
                st.download_button(
                    "📥 Download STR (PDF)", pack.pdf_bytes,
                    f"STR_{pack.str_reference}.pdf", "application/pdf",
                )
