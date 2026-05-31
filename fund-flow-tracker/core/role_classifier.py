"""
Account Role Classifier for TraceX — classifies accounts as Source, Mule, Sink, or Normal
using statistical thresholds based on the graph structure.
"""
import numpy as np
import pandas as pd
from typing import Dict
from utils.helpers import safe_ratio


class AccountRoleClassifier:
    """Classify accounts by their role in transaction flow using percentile-based thresholds."""

    ROLES = {
        "SOURCE": "🔵 Source — Primarily sends funds",
        "MULE": "🟡 Mule — Pass-through intermediary",
        "SINK": "🔴 Sink — Primarily receives funds",
        "NORMAL": "⚪ Normal — Balanced transaction profile",
    }

    def classify_all(self, graph_engine) -> Dict[str, Dict]:
        """Classify all accounts using statistical thresholds."""
        G = graph_engine.G
        roles = {}

        # Compute ratios for all accounts
        ratios = {}
        for node in G.nodes():
            in_flow = sum(d.get("amount", 0) for _, _, d in G.in_edges(node, data=True))
            out_flow = sum(d.get("amount", 0) for _, _, d in G.out_edges(node, data=True))
            total = in_flow + out_flow
            in_degree = G.in_degree(node)
            out_degree = G.out_degree(node)

            ratios[node] = {
                "in_ratio": safe_ratio(in_flow, total),
                "out_ratio": safe_ratio(out_flow, total),
                "in_degree": in_degree,
                "out_degree": out_degree,
                "total_flow": total,
                "in_flow": in_flow,
                "out_flow": out_flow,
                "degree_ratio": safe_ratio(out_degree, max(in_degree + out_degree, 1)),
            }

        if not ratios:
            return {}

        # Compute percentile-based thresholds
        out_ratios = [r["out_ratio"] for r in ratios.values()]
        in_ratios = [r["in_ratio"] for r in ratios.values()]

        p75_out = np.percentile(out_ratios, 75) if out_ratios else 0.7
        p75_in = np.percentile(in_ratios, 75) if in_ratios else 0.7

        for node, r in ratios.items():
            if r["total_flow"] == 0:
                role = "NORMAL"
                confidence = 0.5
            elif r["out_ratio"] > p75_out and r["in_ratio"] < 0.3:
                role = "SOURCE"
                confidence = min(r["out_ratio"] * 1.2, 1.0)
            elif r["in_ratio"] > p75_in and r["out_ratio"] < 0.3:
                role = "SINK"
                confidence = min(r["in_ratio"] * 1.2, 1.0)
            elif 0.3 <= r["in_ratio"] <= 0.7 and 0.3 <= r["out_ratio"] <= 0.7:
                # Pass-through: receives AND sends roughly equal amounts
                if r["in_degree"] >= 2 and r["out_degree"] >= 2:
                    role = "MULE"
                    confidence = 1.0 - abs(r["in_ratio"] - 0.5)
                else:
                    role = "NORMAL"
                    confidence = 0.6
            else:
                role = "NORMAL"
                confidence = 0.5

            roles[node] = {
                "role": role,
                "confidence": round(confidence, 3),
                "in_flow": round(r["in_flow"], 2),
                "out_flow": round(r["out_flow"], 2),
                "in_degree": r["in_degree"],
                "out_degree": r["out_degree"],
            }

        return roles
