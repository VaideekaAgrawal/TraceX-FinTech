"""
Transaction Speed Analyzer for TraceX — measures fund movement velocity
and flags abnormally fast chains.
"""
import pandas as pd
import numpy as np
from typing import Dict, List, Optional


class SpeedAnalyzer:
    """Analyze transaction chain velocity to detect rapid fund movement."""

    SPEED_CATEGORIES = {
        "NORMAL": {"max_minutes_per_hop": 60, "label": "Normal", "color": "#2ecc71"},
        "FAST": {"max_minutes_per_hop": 15, "label": "Fast", "color": "#f39c12"},
        "VERY_FAST": {"max_minutes_per_hop": 5, "label": "Very Fast", "color": "#e67e22"},
        "ABNORMAL": {"max_minutes_per_hop": 1, "label": "Abnormal", "color": "#e74c3c"},
    }

    def analyze_chain_speed(self, chain: List[Dict]) -> Dict:
        """Analyze the speed of a transaction chain."""
        if len(chain) < 2:
            return {"category": "NORMAL", "avg_minutes_per_hop": 0, "hops": len(chain)}

        timestamps = []
        for step in chain:
            ts = step.get("timestamp")
            if ts is not None:
                timestamps.append(pd.Timestamp(ts))

        if len(timestamps) < 2:
            return {"category": "NORMAL", "avg_minutes_per_hop": 0, "hops": len(chain)}

        total_seconds = (max(timestamps) - min(timestamps)).total_seconds()
        hops = len(chain)
        avg_seconds_per_hop = total_seconds / hops

        avg_minutes = avg_seconds_per_hop / 60

        if avg_minutes <= 1:
            category = "ABNORMAL"
        elif avg_minutes <= 5:
            category = "VERY_FAST"
        elif avg_minutes <= 15:
            category = "FAST"
        else:
            category = "NORMAL"

        return {
            "category": category,
            "avg_minutes_per_hop": round(avg_minutes, 2),
            "total_minutes": round(total_seconds / 60, 2),
            "hops": hops,
            "total_amount": sum(s.get("amount", 0) for s in chain),
            "label": self.SPEED_CATEGORIES[category]["label"],
            "color": self.SPEED_CATEGORIES[category]["color"],
        }

    def analyze_all_chains(self, chains: List[List[Dict]]) -> List[Dict]:
        """Analyze speed of all transaction chains."""
        results = []
        for chain in chains:
            speed_info = self.analyze_chain_speed(chain)
            if speed_info["category"] != "NORMAL":
                accounts = set()
                for step in chain:
                    accounts.add(step.get("from", ""))
                    accounts.add(step.get("to", ""))
                accounts.discard("")

                speed_info["accounts"] = list(accounts)
                speed_info["chain"] = chain
                results.append(speed_info)

        return sorted(results, key=lambda x: x["avg_minutes_per_hop"])

    def get_speed_alerts(self, graph_engine) -> List[Dict]:
        """Get all speed alerts from the graph's transaction chains."""
        chains = graph_engine.get_transaction_chains(min_hops=2, time_window_minutes=60)
        return self.analyze_all_chains(chains)
