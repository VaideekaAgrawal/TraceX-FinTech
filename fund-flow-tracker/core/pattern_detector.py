"""
Pattern Detection for TraceX — Layering, Round-tripping, Structuring,
Dormant Activation, Fan-in/Fan-out, Combined Patterns, First Suspicious Point.
"""
import numpy as np
import pandas as pd
from typing import Dict, List, Any, Optional
from collections import defaultdict
from utils.constants import (
    CTR_THRESHOLD, STRUCTURING_LOWER, STRUCTURING_UPPER,
    MAX_DORMANT_DAYS, SUSPICIOUS_VELOCITY,
)


class PatternDetector:
    """Rule-based + graph-based pattern detection."""

    def __init__(self, graph_engine, transactions_df: pd.DataFrame):
        self.graph = graph_engine
        self.txns = transactions_df.copy()
        self.txns["timestamp"] = pd.to_datetime(self.txns["timestamp"])

    def detect_all(self) -> Dict[str, Any]:
        """Run all pattern detectors and return results."""
        return {
            "layering": self.detect_layering(),
            "round_tripping": self.detect_round_tripping(),
            "structuring": self.detect_structuring(),
            "dormant_activation": self.detect_dormant_activation(),
            "fan_in": self.detect_fan_in(),
            "fan_out": self.detect_fan_out(),
        }

    # ------------------------------------------------------------------
    # Layering Detection
    # ------------------------------------------------------------------
    def detect_layering(self, min_chain_length: int = 3,
                        time_window_minutes: int = 30,
                        amount_decay_threshold: float = 0.15) -> List[Dict]:
        """
        Detect layering: rapid chain transfers with decreasing amounts.
        A→B→C→D within short time, amounts decreasing at each hop.
        """
        chains = self.graph.get_transaction_chains(
            min_hops=min_chain_length,
            time_window_minutes=time_window_minutes,
        )
        layering_results = []

        for chain in chains:
            amounts = [step["amount"] for step in chain]
            if len(amounts) < 2:
                continue

            # Check for consistently decreasing amounts
            decreasing_count = sum(
                1 for i in range(1, len(amounts)) if amounts[i] < amounts[i - 1]
            )
            decay_ratio = decreasing_count / (len(amounts) - 1)

            # Calculate total time span
            timestamps = [step["timestamp"] for step in chain if step["timestamp"] is not None]
            if len(timestamps) >= 2:
                time_span = (max(timestamps) - min(timestamps)).total_seconds() / 60
            else:
                time_span = 0

            # Calculate amount decay
            total_decay = (amounts[0] - amounts[-1]) / amounts[0] if amounts[0] > 0 else 0

            if decay_ratio >= 0.5 and time_span <= time_window_minutes:
                accounts = []
                for step in chain:
                    accounts.append(step["from"])
                accounts.append(chain[-1]["to"])

                layering_results.append({
                    "chain": chain,
                    "accounts": list(dict.fromkeys(accounts)),
                    "hops": len(chain),
                    "time_span_minutes": round(time_span, 2),
                    "total_amount": sum(amounts),
                    "amount_decay": round(total_decay, 4),
                    "start_amount": amounts[0],
                    "end_amount": amounts[-1],
                    "severity": "HIGH" if len(chain) >= 5 else "MEDIUM",
                })

        return sorted(layering_results, key=lambda x: x["hops"], reverse=True)

    # ------------------------------------------------------------------
    # Round-tripping / Cycle Detection
    # ------------------------------------------------------------------
    def detect_round_tripping(self, max_cycle_length: int = 5) -> List[Dict]:
        """Detect circular fund flows (A→B→C→A)."""
        cycles = self.graph.detect_cycles(max_length=max_cycle_length, max_cycles=100)
        results = []

        for cycle_nodes in cycles:
            cycle_txns = []
            total_amount = 0
            for i in range(len(cycle_nodes)):
                src = cycle_nodes[i]
                dst = cycle_nodes[(i + 1) % len(cycle_nodes)]
                # Find transactions between consecutive cycle nodes
                edge_txns = self.txns[
                    (self.txns["source_account"] == src) &
                    (self.txns["dest_account"] == dst)
                ]
                if len(edge_txns) > 0:
                    for _, txn in edge_txns.iterrows():
                        cycle_txns.append({
                            "from": src, "to": dst,
                            "amount": txn["amount"],
                            "timestamp": txn["timestamp"],
                        })
                        total_amount += txn["amount"]

            if cycle_txns:
                timestamps = [t["timestamp"] for t in cycle_txns]
                time_span = (max(timestamps) - min(timestamps)).total_seconds() / 3600

                # Calculate net delta (how much leaked out of the cycle)
                amounts_in = defaultdict(float)
                amounts_out = defaultdict(float)
                for t in cycle_txns:
                    amounts_out[t["from"]] += t["amount"]
                    amounts_in[t["to"]] += t["amount"]

                results.append({
                    "cycle_nodes": cycle_nodes,
                    "cycle_length": len(cycle_nodes),
                    "transactions": cycle_txns,
                    "total_amount": round(total_amount, 2),
                    "time_span_hours": round(time_span, 2),
                    "iteration_count": len(cycle_txns) // max(len(cycle_nodes), 1),
                    "severity": "CRITICAL" if len(cycle_nodes) >= 3 else "MEDIUM",
                })

        return results

    # ------------------------------------------------------------------
    # Structuring Detection
    # ------------------------------------------------------------------
    def detect_structuring(self, min_count: int = 3) -> Dict[str, List[Dict]]:
        """
        Detect structuring: transactions just below ₹10L CTR threshold.
        Two types:
          1. Classic: individual transactions in ₹9L-₹10L range
          2. Split: multiple smaller amounts summing to near-threshold
        """
        results = {"classic": [], "split": []}

        # Type 1: Classic structuring
        near_threshold = self.txns[
            (self.txns["amount"] >= STRUCTURING_LOWER) &
            (self.txns["amount"] < CTR_THRESHOLD)
        ]
        if len(near_threshold) > 0:
            account_counts = near_threshold.groupby("source_account").agg(
                count=("amount", "size"),
                total=("amount", "sum"),
                amounts=("amount", list),
            ).reset_index()

            for _, row in account_counts.iterrows():
                if row["count"] >= min_count:
                    results["classic"].append({
                        "account_id": row["source_account"],
                        "near_threshold_count": int(row["count"]),
                        "total_amount": round(row["total"], 2),
                        "amounts": [round(a, 2) for a in row["amounts"]],
                        "severity": "CRITICAL" if row["count"] >= 5 else "HIGH",
                    })

        # Type 2: Split structuring (daily totals near threshold)
        if len(self.txns) > 0:
            daily_totals = self.txns.groupby(
                [self.txns["source_account"], self.txns["timestamp"].dt.date]
            )["amount"].agg(["sum", "count"]).reset_index()
            daily_totals.columns = ["source_account", "date", "daily_total", "txn_count"]

            split_candidates = daily_totals[
                (daily_totals["daily_total"] >= STRUCTURING_LOWER) &
                (daily_totals["daily_total"] < CTR_THRESHOLD) &
                (daily_totals["txn_count"] >= 2)
            ]
            for _, row in split_candidates.iterrows():
                results["split"].append({
                    "account_id": row["source_account"],
                    "date": str(row["date"]),
                    "daily_total": round(row["daily_total"], 2),
                    "transaction_count": int(row["txn_count"]),
                    "severity": "HIGH",
                })

        return results

    # ------------------------------------------------------------------
    # Dormant Account Activation
    # ------------------------------------------------------------------
    def detect_dormant_activation(self, dormancy_threshold_days: int = MAX_DORMANT_DAYS,
                                   burst_min_txns: int = 5) -> List[Dict]:
        """Detect accounts that were dormant then suddenly became active."""
        results = []
        all_accounts = set(self.txns["source_account"].unique()) | set(self.txns["dest_account"].unique())

        for account_id in all_accounts:
            acc_txns = self.txns[
                (self.txns["source_account"] == account_id) |
                (self.txns["dest_account"] == account_id)
            ].sort_values("timestamp")

            if len(acc_txns) < burst_min_txns + 1:
                continue

            timestamps = acc_txns["timestamp"].values
            gaps = np.diff(timestamps).astype("timedelta64[D]").astype(float)

            if len(gaps) == 0:
                continue

            max_gap_idx = np.argmax(gaps)
            max_gap_days = gaps[max_gap_idx]

            if max_gap_days >= dormancy_threshold_days:
                # Check burst after dormancy
                post_dormancy = acc_txns.iloc[max_gap_idx + 1:]
                if len(post_dormancy) >= burst_min_txns:
                    burst_span = (post_dormancy["timestamp"].max() - post_dormancy["timestamp"].min())
                    burst_days = burst_span.total_seconds() / 86400

                    results.append({
                        "account_id": account_id,
                        "dormancy_days": round(max_gap_days, 1),
                        "dormancy_start": str(acc_txns.iloc[max_gap_idx]["timestamp"]),
                        "dormancy_end": str(acc_txns.iloc[max_gap_idx + 1]["timestamp"]),
                        "burst_txn_count": len(post_dormancy),
                        "burst_total_amount": round(post_dormancy["amount"].sum(), 2),
                        "burst_span_days": round(burst_days, 1),
                        "severity": "CRITICAL" if max_gap_days > 365 else "HIGH",
                    })

        return sorted(results, key=lambda x: x["dormancy_days"], reverse=True)

    # ------------------------------------------------------------------
    # Fan-in Detection (multiple sources → one sink)
    # ------------------------------------------------------------------
    def detect_fan_in(self, min_sources: int = 5,
                      time_window_hours: int = 24) -> List[Dict]:
        """Detect accounts receiving from many sources in a short period."""
        results = []
        G = self.graph.G

        for node in G.nodes():
            in_edges = list(G.in_edges(node, data=True))
            if len(in_edges) < min_sources:
                continue

            # Group by time window
            edge_data = [(data.get("timestamp"), data.get("amount", 0),
                          src) for src, _, data in in_edges if data.get("timestamp")]
            if not edge_data:
                continue

            edge_df = pd.DataFrame(edge_data, columns=["timestamp", "amount", "source"])
            edge_df["timestamp"] = pd.to_datetime(edge_df["timestamp"])
            edge_df = edge_df.sort_values("timestamp")

            # Sliding window analysis
            for i, row in edge_df.iterrows():
                window_end = row["timestamp"] + pd.Timedelta(hours=time_window_hours)
                window = edge_df[
                    (edge_df["timestamp"] >= row["timestamp"]) &
                    (edge_df["timestamp"] <= window_end)
                ]
                unique_sources = window["source"].nunique()
                if unique_sources >= min_sources:
                    results.append({
                        "sink_account": node,
                        "unique_sources": unique_sources,
                        "total_amount": round(window["amount"].sum(), 2),
                        "time_window_hours": time_window_hours,
                        "sources": window["source"].unique().tolist(),
                        "severity": "HIGH" if unique_sources >= 8 else "MEDIUM",
                    })
                    break  # One result per account

        return results

    # ------------------------------------------------------------------
    # Fan-out Detection (one source → many destinations)
    # ------------------------------------------------------------------
    def detect_fan_out(self, min_destinations: int = 5,
                       time_window_hours: int = 24) -> List[Dict]:
        """Detect accounts sending to many destinations in a short period."""
        results = []
        G = self.graph.G

        for node in G.nodes():
            out_edges = list(G.out_edges(node, data=True))
            if len(out_edges) < min_destinations:
                continue

            edge_data = [(data.get("timestamp"), data.get("amount", 0),
                          dst) for _, dst, data in out_edges if data.get("timestamp")]
            if not edge_data:
                continue

            edge_df = pd.DataFrame(edge_data, columns=["timestamp", "amount", "dest"])
            edge_df["timestamp"] = pd.to_datetime(edge_df["timestamp"])
            edge_df = edge_df.sort_values("timestamp")

            for i, row in edge_df.iterrows():
                window_end = row["timestamp"] + pd.Timedelta(hours=time_window_hours)
                window = edge_df[
                    (edge_df["timestamp"] >= row["timestamp"]) &
                    (edge_df["timestamp"] <= window_end)
                ]
                unique_dests = window["dest"].nunique()
                if unique_dests >= min_destinations:
                    results.append({
                        "source_account": node,
                        "unique_destinations": unique_dests,
                        "total_amount": round(window["amount"].sum(), 2),
                        "time_window_hours": time_window_hours,
                        "destinations": window["dest"].unique().tolist(),
                        "severity": "HIGH" if unique_dests >= 8 else "MEDIUM",
                    })
                    break

        return results

    # ------------------------------------------------------------------
    # First Suspicious Point Detection
    # ------------------------------------------------------------------
    def detect_first_suspicious_point(self, account_id: str) -> Optional[Dict]:
        """Identify the first transaction that deviated from normal behavior."""
        txns = self.txns[
            (self.txns["source_account"] == account_id) |
            (self.txns["dest_account"] == account_id)
        ].sort_values("timestamp")

        if len(txns) < 10:
            return None

        # Rolling statistics
        txns = txns.copy()
        txns["rolling_mean"] = txns["amount"].rolling(window=20, min_periods=5).mean()
        txns["rolling_std"] = txns["amount"].rolling(window=20, min_periods=5).std().clip(lower=1)
        txns["z_score"] = (txns["amount"] - txns["rolling_mean"]) / txns["rolling_std"]

        # Method 1: Amount spike (z-score > 3)
        amount_spikes = txns[txns["z_score"] > 3]

        # Method 2: Velocity spike
        txns["hour_count"] = txns.set_index("timestamp").resample("1h").size().reindex(
            txns.set_index("timestamp").index, method="ffill"
        ).values if len(txns) > 0 else 0

        first_suspicious = None
        if len(amount_spikes) > 0:
            first = amount_spikes.iloc[0]
            first_suspicious = {
                "txn_id": first.get("txn_id", ""),
                "timestamp": str(first["timestamp"]),
                "amount": round(first["amount"], 2),
                "z_score": round(first["z_score"], 2),
                "detection_method": "amount_spike",
                "rolling_mean": round(first["rolling_mean"], 2),
                "rolling_std": round(first["rolling_std"], 2),
            }

        return first_suspicious

    # ------------------------------------------------------------------
    # Repeat Behavior Detection
    # ------------------------------------------------------------------
    def detect_repeat_behavior(self, flagged_accounts: List[str],
                               time_window_days: int = 90) -> List[Dict]:
        """Identify accounts with multiple episodes of suspicious activity."""
        results = []

        for account_id in flagged_accounts:
            acc_txns = self.txns[
                (self.txns["source_account"] == account_id) |
                (self.txns["dest_account"] == account_id)
            ].sort_values("timestamp")

            if len(acc_txns) < 5:
                continue

            # Find suspicious episodes using z-score
            acc_txns = acc_txns.copy()
            mean_amt = acc_txns["amount"].mean()
            std_amt = acc_txns["amount"].std()
            if std_amt == 0:
                continue

            acc_txns["is_suspicious"] = (
                (acc_txns["amount"] - mean_amt) / std_amt
            ).abs() > 2

            suspicious = acc_txns[acc_txns["is_suspicious"]]
            if len(suspicious) < 2:
                continue

            # Group into episodes (within time_window_days of each other)
            episodes = []
            current_episode = [suspicious.iloc[0]]
            for i in range(1, len(suspicious)):
                gap = (suspicious.iloc[i]["timestamp"] - suspicious.iloc[i - 1]["timestamp"]).days
                if gap <= time_window_days:
                    current_episode.append(suspicious.iloc[i])
                else:
                    if len(current_episode) >= 2:
                        episodes.append(current_episode)
                    current_episode = [suspicious.iloc[i]]
            if len(current_episode) >= 2:
                episodes.append(current_episode)

            if len(episodes) >= 2:
                results.append({
                    "account_id": account_id,
                    "episode_count": len(episodes),
                    "episodes": [
                        {
                            "start": str(ep[0]["timestamp"]),
                            "end": str(ep[-1]["timestamp"]),
                            "txn_count": len(ep),
                            "total_amount": round(sum(t["amount"] for t in ep), 2),
                        }
                        for ep in episodes
                    ],
                    "is_escalating": self._check_escalation(episodes),
                    "severity": "CRITICAL" if len(episodes) >= 3 else "HIGH",
                })

        return results

    @staticmethod
    def _check_escalation(episodes: List) -> bool:
        """Check if episode amounts are escalating."""
        if len(episodes) < 2:
            return False
        totals = [sum(t["amount"] for t in ep) for ep in episodes]
        increasing = sum(1 for i in range(1, len(totals)) if totals[i] > totals[i - 1])
        return increasing >= len(totals) // 2

    # ------------------------------------------------------------------
    # Combined Pattern Detection
    # ------------------------------------------------------------------
    def detect_combined_patterns(self, all_patterns: Dict[str, Any]) -> List[Dict]:
        """Find accounts appearing in multiple pattern types."""
        account_patterns: Dict[str, List[str]] = defaultdict(list)

        # Collect accounts from each pattern type
        for chain in all_patterns.get("layering", []):
            for acc in chain.get("accounts", []):
                account_patterns[acc].append("layering")

        for cycle in all_patterns.get("round_tripping", []):
            for acc in cycle.get("cycle_nodes", []):
                account_patterns[acc].append("round_tripping")

        for stype in ["classic", "split"]:
            for item in all_patterns.get("structuring", {}).get(stype, []):
                account_patterns[item.get("account_id", "")].append(f"structuring_{stype}")

        for item in all_patterns.get("dormant_activation", []):
            account_patterns[item.get("account_id", "")].append("dormant_activation")

        for item in all_patterns.get("fan_in", []):
            account_patterns[item.get("sink_account", "")].append("fan_in")

        for item in all_patterns.get("fan_out", []):
            account_patterns[item.get("source_account", "")].append("fan_out")

        # Filter to accounts with 2+ patterns
        combined = []
        for acc, patterns in account_patterns.items():
            unique_patterns = list(set(patterns))
            if len(unique_patterns) >= 2:
                combined.append({
                    "account_id": acc,
                    "patterns": unique_patterns,
                    "pattern_count": len(unique_patterns),
                    "combo_score": min(len(unique_patterns) * 25, 100),
                    "severity": "CRITICAL" if len(unique_patterns) >= 3 else "HIGH",
                })

        return sorted(combined, key=lambda x: x["pattern_count"], reverse=True)

    def get_all_flagged_accounts(self, all_patterns: Dict[str, Any]) -> set:
        """Get all accounts flagged by any pattern."""
        flagged = set()
        for chain in all_patterns.get("layering", []):
            flagged.update(chain.get("accounts", []))
        for cycle in all_patterns.get("round_tripping", []):
            flagged.update(cycle.get("cycle_nodes", []))
        for stype in ["classic", "split"]:
            for item in all_patterns.get("structuring", {}).get(stype, []):
                flagged.add(item.get("account_id", ""))
        for item in all_patterns.get("dormant_activation", []):
            flagged.add(item.get("account_id", ""))
        for item in all_patterns.get("fan_in", []):
            flagged.add(item.get("sink_account", ""))
        for item in all_patterns.get("fan_out", []):
            flagged.add(item.get("source_account", ""))
        flagged.discard("")
        return flagged
