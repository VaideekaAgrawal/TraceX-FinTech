"""
Evidence Generator for TraceX — generates FIU-IND compliant STR evidence packs
as PDF and JSON, with graph images.
"""
import json
import io
from datetime import datetime
from typing import Dict, List, Any, Optional
from fpdf import FPDF
from utils.helpers import sanitize_text, format_inr
from utils.constants import SUSPICION_CATEGORIES


class EvidenceGenerator:
    """Generate FIU-IND compliant Suspicious Transaction Report evidence packs."""

    def generate_evidence_pack(self, case_id: str,
                                account_ids: List[str],
                                graph_engine,
                                risk_data: Dict,
                                pattern_results: Dict,
                                transactions_df,
                                accounts_df,
                                case_notes: str = "") -> Dict[str, Any]:
        """
        Generate a complete evidence pack.
        Returns dict with 'pdf_bytes', 'json_data', and 'summary'.
        """
        # Gather all data for the case
        case_data = self._assemble_case_data(
            case_id, account_ids, graph_engine, risk_data,
            pattern_results, transactions_df, accounts_df, case_notes,
        )

        pdf_bytes = self._generate_pdf(case_data)
        json_data = self._generate_json(case_data)

        return {
            "pdf_bytes": pdf_bytes,
            "json_data": json_data,
            "summary": case_data["summary"],
            "case_id": case_id,
        }

    def _assemble_case_data(self, case_id, account_ids, graph_engine,
                            risk_data, pattern_results, transactions_df,
                            accounts_df, case_notes) -> Dict:
        """Assemble all case data for report generation."""
        # Get transactions involving the accounts
        relevant_txns = transactions_df[
            (transactions_df["source_account"].isin(account_ids)) |
            (transactions_df["dest_account"].isin(account_ids))
        ].sort_values("timestamp")

        # Get account details
        account_details = []
        for acc_id in account_ids:
            acc_row = accounts_df[accounts_df["account_id"] == acc_id]
            if len(acc_row) > 0:
                account_details.append(acc_row.iloc[0].to_dict())

        # Determine suspicion categories
        categories = self._determine_categories(pattern_results, account_ids)

        total_amount = relevant_txns["amount"].sum()
        max_risk = max([risk_data.get(a, 0) for a in account_ids], default=0)

        summary = {
            "case_id": case_id,
            "generated_at": datetime.now().isoformat(),
            "accounts_investigated": len(account_ids),
            "total_transactions": len(relevant_txns),
            "total_amount_involved": round(total_amount, 2),
            "max_risk_score": round(max_risk, 2),
            "suspicion_categories": categories,
        }

        return {
            "case_id": case_id,
            "summary": summary,
            "account_ids": account_ids,
            "account_details": account_details,
            "transactions": relevant_txns.to_dict("records"),
            "risk_scores": {a: risk_data.get(a, 0) for a in account_ids},
            "pattern_results": pattern_results,
            "case_notes": case_notes,
            "categories": categories,
            "total_amount": total_amount,
        }

    def _generate_pdf(self, case_data: Dict) -> bytes:
        """Generate PDF evidence report in FIU-IND STR format."""
        pdf = FPDF()
        pdf.set_auto_page_break(auto=True, margin=15)
        pdf.add_page()

        # Header
        pdf.set_font("Helvetica", "B", 16)
        pdf.cell(0, 10, sanitize_text("SUSPICIOUS TRANSACTION REPORT (STR)"), new_x="LMARGIN", new_y="NEXT", align="C")
        pdf.set_font("Helvetica", "", 10)
        pdf.cell(0, 6, sanitize_text(f"Case ID: {case_data['case_id']}"), new_x="LMARGIN", new_y="NEXT", align="C")
        pdf.cell(0, 6, sanitize_text(f"Generated: {case_data['summary']['generated_at']}"), new_x="LMARGIN", new_y="NEXT", align="C")
        pdf.cell(0, 6, sanitize_text("CONFIDENTIAL - FOR LAW ENFORCEMENT USE ONLY"), new_x="LMARGIN", new_y="NEXT", align="C")
        pdf.ln(10)

        # Part A: Reporting Entity
        self._pdf_section(pdf, "PART A: REPORTING ENTITY INFORMATION")
        self._pdf_field(pdf, "Reporting Entity", "Public Sector Bank (Demo)")
        self._pdf_field(pdf, "Report Type", "Suspicious Transaction Report (STR)")
        self._pdf_field(pdf, "Filing Date", datetime.now().strftime("%Y-%m-%d"))
        pdf.ln(5)

        # Part B: Subject Information
        self._pdf_section(pdf, "PART B: SUBJECT (ACCOUNT HOLDER) INFORMATION")
        for acc in case_data.get("account_details", []):
            pdf.set_font("Helvetica", "B", 10)
            pdf.cell(0, 6, sanitize_text(f"Account: {acc.get('account_id', 'N/A')}"), new_x="LMARGIN", new_y="NEXT")
            pdf.set_font("Helvetica", "", 9)
            self._pdf_field(pdf, "  Account Type", str(acc.get("account_type", "N/A")))
            self._pdf_field(pdf, "  Branch City", str(acc.get("branch_city", "N/A")))
            self._pdf_field(pdf, "  Occupation", str(acc.get("occupation", "N/A")))
            self._pdf_field(pdf, "  Income Bracket", str(acc.get("income_bracket", "N/A")))
            self._pdf_field(pdf, "  Declared Annual Income",
                          sanitize_text(format_inr(acc.get("declared_annual_income", 0))))
            risk = case_data["risk_scores"].get(acc.get("account_id"), 0)
            self._pdf_field(pdf, "  Risk Score", f"{risk:.1f}/100")
            pdf.ln(3)
        pdf.ln(5)

        # Part C: Transaction Details
        self._pdf_section(pdf, "PART C: SUSPICIOUS TRANSACTION DETAILS")
        self._pdf_field(pdf, "Total Transactions Analyzed",
                        str(case_data["summary"]["total_transactions"]))
        self._pdf_field(pdf, "Total Amount Involved",
                        sanitize_text(format_inr(case_data["total_amount"])))
        pdf.ln(3)

        # Transaction table (top 20)
        txns = case_data.get("transactions", [])[:20]
        if txns:
            pdf.set_font("Helvetica", "B", 8)
            col_widths = [25, 25, 25, 20, 20, 20]
            headers = ["Date", "From", "To", "Amount", "Channel", "Type"]
            for w, h in zip(col_widths, headers):
                pdf.cell(w, 6, h, border=1)
            pdf.ln()

            pdf.set_font("Helvetica", "", 7)
            for txn in txns:
                ts = str(txn.get("timestamp", ""))[:10]
                src = str(txn.get("source_account", ""))[:10]
                dst = str(txn.get("dest_account", ""))[:10]
                amt = sanitize_text(format_inr(txn.get("amount", 0)))
                ch = str(txn.get("channel", ""))[:8]
                tt = str(txn.get("txn_type", ""))[:8]
                for w, val in zip(col_widths, [ts, src, dst, amt, ch, tt]):
                    pdf.cell(w, 5, val, border=1)
                pdf.ln()
        pdf.ln(5)

        # Part D: Suspicion Details
        self._pdf_section(pdf, "PART D: SUSPICION DETAILS")
        self._pdf_field(pdf, "Date of Detection", datetime.now().strftime("%Y-%m-%d"))
        self._pdf_field(pdf, "Categories of Suspicion",
                        ", ".join(case_data.get("categories", ["Other"])))
        pdf.ln(3)
        pdf.set_font("Helvetica", "B", 10)
        pdf.cell(0, 6, "Reason for Suspicion:", new_x="LMARGIN", new_y="NEXT")
        pdf.set_font("Helvetica", "", 9)
        if case_data.get("case_notes"):
            pdf.multi_cell(0, 5, sanitize_text(case_data["case_notes"]))
        else:
            pdf.multi_cell(0, 5, sanitize_text(
                "Automated detection by TraceX Fund Flow Intelligence System. "
                "Multiple suspicious indicators identified through graph analysis, "
                "ML anomaly detection, and pattern recognition."
            ))
        pdf.ln(5)

        # Pattern Summary
        self._pdf_section(pdf, "PATTERN ANALYSIS SUMMARY")
        patterns = case_data.get("pattern_results", {})
        for ptype, pdata in patterns.items():
            if pdata:
                pdf.set_font("Helvetica", "B", 9)
                pdf.cell(0, 6, sanitize_text(f"Pattern: {ptype.replace('_', ' ').title()}"), new_x="LMARGIN", new_y="NEXT")
                pdf.set_font("Helvetica", "", 8)
                if isinstance(pdata, list):
                    pdf.cell(0, 5, sanitize_text(f"  Instances detected: {len(pdata)}"), new_x="LMARGIN", new_y="NEXT")
                elif isinstance(pdata, dict):
                    for k, v in pdata.items():
                        if isinstance(v, list):
                            pdf.cell(0, 5, sanitize_text(f"  {k}: {len(v)} instances"), new_x="LMARGIN", new_y="NEXT")
        pdf.ln(5)

        # Footer
        pdf.set_font("Helvetica", "I", 8)
        pdf.cell(0, 6, sanitize_text(
            "This report is generated by TraceX and is intended for authorized personnel only."
        ), new_x="LMARGIN", new_y="NEXT")
        pdf.cell(0, 6, sanitize_text(
            "Tipping off the subject of this report is prohibited under PMLA 2002."
        ), new_x="LMARGIN", new_y="NEXT")

        return pdf.output()

    def _generate_json(self, case_data: Dict) -> str:
        """Generate JSON evidence for FINnet 2.0 submission."""
        # Convert timestamps to strings
        txns = []
        for txn in case_data.get("transactions", []):
            t = dict(txn)
            for k, v in t.items():
                if hasattr(v, "isoformat"):
                    t[k] = v.isoformat()
                elif isinstance(v, float) and (v != v):  # NaN check
                    t[k] = None
            txns.append(t)

        json_data = {
            "str_report": {
                "part_a_reporting_entity": {
                    "entity_type": "Public Sector Bank",
                    "report_type": "STR",
                    "filing_date": datetime.now().isoformat(),
                },
                "part_b_subjects": case_data.get("account_details", []),
                "part_c_transactions": {
                    "total_count": case_data["summary"]["total_transactions"],
                    "total_amount": case_data["total_amount"],
                    "transactions": txns[:100],  # Limit for JSON size
                },
                "part_d_suspicion": {
                    "detection_date": datetime.now().isoformat(),
                    "categories": case_data.get("categories", []),
                    "risk_scores": case_data.get("risk_scores", {}),
                    "case_notes": case_data.get("case_notes", ""),
                },
                "metadata": {
                    "case_id": case_data["case_id"],
                    "generated_by": "TraceX Fund Flow Intelligence",
                    "version": "1.0",
                },
            }
        }
        return json.dumps(json_data, indent=2, default=str)

    @staticmethod
    def _determine_categories(pattern_results: Dict, account_ids: List[str]) -> List[str]:
        """Map detected patterns to FIU-IND suspicion categories."""
        categories = set()

        if pattern_results.get("layering"):
            categories.add(SUSPICION_CATEGORIES[4])  # Layering
            categories.add(SUSPICION_CATEGORIES[6])  # Rapid movement

        if pattern_results.get("round_tripping"):
            categories.add(SUSPICION_CATEGORIES[7])  # Round-tripping

        structuring = pattern_results.get("structuring", {})
        if structuring.get("classic") or structuring.get("split"):
            categories.add(SUSPICION_CATEGORIES[3])  # Structuring

        if pattern_results.get("dormant_activation"):
            categories.add(SUSPICION_CATEGORIES[2])  # Inconsistent with profile

        if pattern_results.get("fan_in") or pattern_results.get("fan_out"):
            categories.add(SUSPICION_CATEGORIES[5])  # Shell companies / nominees

        if not categories:
            categories.add(SUSPICION_CATEGORIES[13])  # Other

        return list(categories)

    @staticmethod
    def _pdf_section(pdf: FPDF, title: str):
        pdf.set_font("Helvetica", "B", 12)
        pdf.set_fill_color(200, 220, 240)
        pdf.cell(0, 8, sanitize_text(title), new_x="LMARGIN", new_y="NEXT", fill=True)
        pdf.ln(3)

    @staticmethod
    def _pdf_field(pdf: FPDF, label: str, value: str):
        pdf.set_font("Helvetica", "B", 9)
        pdf.cell(60, 5, sanitize_text(label + ":"))
        pdf.set_font("Helvetica", "", 9)
        pdf.cell(0, 5, sanitize_text(value), new_x="LMARGIN", new_y="NEXT")
