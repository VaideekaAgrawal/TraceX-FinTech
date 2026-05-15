"""
Risk Scoring Engine for TraceX — composite risk scores + fraud confidence meter
+ investigation priority scoring.
"""
import numpy as np
from typing import Dict, List, Tuple, Any
from utils.constants import RISK_LEVELS, CONFIDENCE_LEVELS


class RiskScorer:
    """Composite risk scoring combining ML + patterns + graph metrics."""

    def compute_composite_score(self, account_id: str,
                                 ml_anomaly_score: float = 0,
                                 fraud_prob: float = 0,
                                 pattern_flags: Dict[str, bool] = None,
                                 graph_metrics: Dict[str, float] = None) -> float:
        """
        Compute a 0-100 composite risk score.
        Weights: ML=30%, Patterns=40%, Graph=30%.
        """
        if pattern_flags is None:
            pattern_flags = {}
        if graph_metrics is None:
            graph_metrics = {}

        # ML component (0-100)
        ml_score = max(ml_anomaly_score, fraud_prob * 100) * 0.3

        # Pattern component (0-100)
        pattern_weights = {
            "layering": 25,
            "round_tripping": 30,
            "structuring_classic": 20,
            "structuring_split": 15,
            "dormant_activation": 20,
            "fan_in": 15,
            "fan_out": 15,
        }
        pattern_score = sum(
            pattern_weights.get(p, 10) for p, flagged in pattern_flags.items() if flagged
        )
        pattern_score = min(pattern_score, 100) * 0.4

        # Graph component (0-100)
        pagerank = graph_metrics.get("pagerank", 0)
        betweenness = graph_metrics.get("betweenness", 0)
        # Normalize: higher centrality → higher risk
        graph_score = (
            min(pagerank * 10000, 50) +
            min(betweenness * 100, 50)
        ) * 0.3

        composite = min(ml_score + pattern_score + graph_score, 100)
        return round(composite, 2)

    def compute_all_scores(self, features_df, anomaly_results,
                           fraud_results, all_patterns, graph_engine) -> Dict[str, float]:
        """Compute risk scores for all accounts."""
        risk_scores = {}
        centrality = graph_engine.compute_centrality()
        pr = centrality["pagerank"]
        bc = centrality["betweenness"]

        # Build pattern flags per account
        pattern_flags = self._build_pattern_flags(all_patterns)

        # Merge anomaly and fraud scores
        anomaly_map = {}
        if anomaly_results is not None:
            for _, row in anomaly_results.iterrows():
                anomaly_map[row["account_id"]] = row["anomaly_score"]

        fraud_map = {}
        if fraud_results is not None:
            for _, row in fraud_results.iterrows():
                fraud_map[row["account_id"]] = row["fraud_prob"]

        for account_id in features_df.index:
            risk_scores[account_id] = self.compute_composite_score(
                account_id,
                ml_anomaly_score=anomaly_map.get(account_id, 0),
                fraud_prob=fraud_map.get(account_id, 0),
                pattern_flags=pattern_flags.get(account_id, {}),
                graph_metrics={"pagerank": pr.get(account_id, 0),
                               "betweenness": bc.get(account_id, 0)},
            )

        return risk_scores

    def compute_confidence(self, account_id: str,
                           pattern_results: Dict,
                           ml_scores: Dict,
                           graph_metrics: Dict) -> Tuple[str, int, List[str]]:
        """
        Compute confidence level based on independent indicator count.
        Returns: (level_label, indicator_count, indicator_list)
        """
        indicators = []

        # ML indicator
        if ml_scores.get("anomaly_score", 0) > 50:
            indicators.append("ML anomaly detection (Isolation Forest)")
        if ml_scores.get("fraud_prob", 0) > 0.5:
            indicators.append("ML fraud classifier (XGBoost)")

        # Pattern indicators
        for pattern_name, flagged in pattern_results.items():
            if flagged:
                indicators.append(f"Pattern: {pattern_name}")

        # Graph indicators
        if graph_metrics.get("pagerank", 0) > np.percentile(
            list(graph_metrics.get("all_pageranks", {0: 0}).values()), 90
        ) if graph_metrics.get("all_pageranks") else False:
            indicators.append("High PageRank centrality")

        if graph_metrics.get("betweenness", 0) > 0.01:
            indicators.append("High betweenness centrality")

        count = len(indicators)
        if count >= 4:
            level = "Very Strong"
        elif count >= 3:
            level = "Strong"
        elif count >= 2:
            level = "Moderate"
        elif count >= 1:
            level = "Weak"
        else:
            level = "None"

        return level, count, indicators

    def compute_investigation_priority(self, risk_score: float,
                                        confidence_level: str,
                                        amount_involved: float,
                                        accounts_involved: int) -> str:
        """Compute investigation priority (P1-P4)."""
        priority_score = 0

        # Risk score contribution
        if risk_score >= 76:
            priority_score += 40
        elif risk_score >= 51:
            priority_score += 25
        elif risk_score >= 26:
            priority_score += 10

        # Confidence contribution
        conf_scores = {"Very Strong": 30, "Strong": 20, "Moderate": 10, "Weak": 5}
        priority_score += conf_scores.get(confidence_level, 0)

        # Amount contribution
        if amount_involved >= 10_000_000:  # ₹1 Cr+
            priority_score += 20
        elif amount_involved >= 1_000_000:  # ₹10L+
            priority_score += 10

        # Network size
        if accounts_involved >= 5:
            priority_score += 10

        if priority_score >= 70:
            return "P1"
        elif priority_score >= 45:
            return "P2"
        elif priority_score >= 20:
            return "P3"
        return "P4"

    @staticmethod
    def _build_pattern_flags(all_patterns: Dict) -> Dict[str, Dict[str, bool]]:
        """Build per-account pattern flag dicts from all pattern results."""
        flags: Dict[str, Dict[str, bool]] = {}

        for chain in all_patterns.get("layering", []):
            for acc in chain.get("accounts", []):
                flags.setdefault(acc, {})["layering"] = True

        for cycle in all_patterns.get("round_tripping", []):
            for acc in cycle.get("cycle_nodes", []):
                flags.setdefault(acc, {})["round_tripping"] = True

        structuring = all_patterns.get("structuring", {})
        for item in structuring.get("classic", []):
            acc = item.get("account_id", "")
            if acc:
                flags.setdefault(acc, {})["structuring_classic"] = True
        for item in structuring.get("split", []):
            acc = item.get("account_id", "")
            if acc:
                flags.setdefault(acc, {})["structuring_split"] = True

        for item in all_patterns.get("dormant_activation", []):
            acc = item.get("account_id", "")
            if acc:
                flags.setdefault(acc, {})["dormant_activation"] = True

        for item in all_patterns.get("fan_in", []):
            acc = item.get("sink_account", "")
            if acc:
                flags.setdefault(acc, {})["fan_in"] = True

        for item in all_patterns.get("fan_out", []):
            acc = item.get("source_account", "")
            if acc:
                flags.setdefault(acc, {})["fan_out"] = True

        return flags
