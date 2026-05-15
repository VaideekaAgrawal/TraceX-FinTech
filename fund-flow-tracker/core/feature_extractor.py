"""
Feature extraction pipeline for TraceX — 30 graph + behavioral features per account.
"""
import numpy as np
import pandas as pd
from typing import Dict
from collections import Counter
from utils.helpers import safe_ratio, channel_entropy, gini_coefficient


class FeatureExtractor:
    """Extract graph-based and behavioral features for each account."""

    def __init__(self, graph_engine, accounts_df: pd.DataFrame,
                 transactions_df: pd.DataFrame):
        self.graph = graph_engine
        self.accounts_df = accounts_df
        self.txns = transactions_df.copy()
        self.txns["timestamp"] = pd.to_datetime(self.txns["timestamp"])

    def extract_all(self) -> pd.DataFrame:
        """Extract all 30 features for every account. Returns DataFrame indexed by account_id."""
        centrality = self.graph.compute_centrality()
        pr = centrality["pagerank"]
        bc = centrality["betweenness"]

        G = self.graph.G
        records = []

        for node in G.nodes():
            feats = self._extract_single(node, G, pr, bc)
            records.append(feats)

        df = pd.DataFrame(records).set_index("account_id")
        df = df.fillna(0)
        return df

    def _extract_single(self, account_id: str, G, pr: Dict, bc: Dict) -> Dict:
        """Extract features for a single account."""
        src_txns = self.txns[self.txns["source_account"] == account_id]
        dst_txns = self.txns[self.txns["dest_account"] == account_id]
        all_txns = pd.concat([src_txns, dst_txns])

        # Graph features
        in_degree = G.in_degree(account_id)
        out_degree = G.out_degree(account_id)
        total_in = dst_txns["amount"].sum()
        total_out = src_txns["amount"].sum()
        net_flow = total_in - total_out

        pagerank = pr.get(account_id, 0)
        betweenness = bc.get(account_id, 0)

        # Clustering coefficient on undirected projection
        try:
            clustering = float(np.mean(list(
                dict(filter(lambda x: x[0] == account_id,
                            nx.clustering(G.to_undirected(), [account_id]).items())).values()
            )))
        except Exception:
            clustering = 0.0

        # Transaction features
        amounts = all_txns["amount"].values if len(all_txns) > 0 else np.array([0])
        avg_txn = float(np.mean(amounts))
        std_txn = float(np.std(amounts)) if len(amounts) > 1 else 0.0
        max_txn = float(np.max(amounts)) if len(amounts) > 0 else 0.0
        txn_count = len(all_txns)

        # Channel features
        channels = all_txns["channel"].value_counts().to_dict() if len(all_txns) > 0 else {}
        unique_channels = len(channels)
        ch_entropy = channel_entropy(channels)

        # Velocity features
        velocity_10min = self._max_window_count(all_txns, "10min")
        velocity_1hour = self._max_window_count(all_txns, "1h")

        # Near-threshold count (₹9L - ₹10L)
        near_threshold = int(((all_txns["amount"] >= 900_000) & (all_txns["amount"] < 1_000_000)).sum()) if len(all_txns) > 0 else 0

        # Dormancy
        dormancy_days = self._compute_dormancy(all_txns)

        # Income ratio
        acc_row = self.accounts_df[self.accounts_df["account_id"] == account_id]
        declared_income = acc_row["declared_annual_income"].values[0] if len(acc_row) > 0 else 0
        monthly_vol = (total_in + total_out)
        income_volume_ratio = safe_ratio(declared_income / 12, monthly_vol)

        # Weekend/night features
        if len(all_txns) > 0:
            weekend_mask = all_txns["timestamp"].dt.dayofweek >= 5
            is_weekend_heavy = float(weekend_mask.sum() / len(all_txns)) if len(all_txns) > 0 else 0
            night_mask = all_txns["timestamp"].dt.hour.isin(range(23, 24)) | all_txns["timestamp"].dt.hour.isin(range(0, 5))
            night_ratio = float(night_mask.sum() / len(all_txns))
        else:
            is_weekend_heavy = 0.0
            night_ratio = 0.0

        # --- Additional features (22-30) ---
        # Reciprocity
        out_partners = set(src_txns["dest_account"].unique())
        in_partners = set(dst_txns["source_account"].unique())
        reciprocal = out_partners & in_partners
        reciprocity_ratio = safe_ratio(len(reciprocal), len(out_partners | in_partners))

        # Geographic dispersion
        if "branch_city" in self.accounts_df.columns:
            counterparties = list(out_partners | in_partners)
            cp_cities = self.accounts_df[self.accounts_df["account_id"].isin(counterparties)]["branch_city"].nunique()
        else:
            cp_cities = 0
        geographic_dispersion = cp_cities

        # Max daily transaction count
        if len(all_txns) > 0:
            daily_counts = all_txns.groupby(all_txns["timestamp"].dt.date).size()
            max_daily_count = int(daily_counts.max()) if len(daily_counts) > 0 else 0
        else:
            max_daily_count = 0

        # Round number ratio
        if len(all_txns) > 0:
            round_mask = (all_txns["amount"] % 10000 == 0)
            round_number_ratio = float(round_mask.sum() / len(all_txns))
        else:
            round_number_ratio = 0.0

        # Temporal regularity (std of time gaps)
        if len(all_txns) > 1:
            sorted_ts = all_txns["timestamp"].sort_values()
            gaps = sorted_ts.diff().dt.total_seconds().dropna()
            temporal_regularity = float(gaps.std()) if len(gaps) > 0 else 0.0
        else:
            temporal_regularity = 0.0

        # New counterparty ratio (simplified: unique partners / total transactions)
        total_partners = len(out_partners | in_partners)
        new_counterparty_ratio = safe_ratio(total_partners, txn_count)

        # Cross-bank ratio
        if "from_bank" in self.txns.columns and "to_bank" in self.txns.columns:
            cross_bank = src_txns.apply(
                lambda r: r.get("from_bank", "") != r.get("to_bank", ""), axis=1
            ).sum() if len(src_txns) > 0 else 0
            cross_bank_ratio = safe_ratio(cross_bank, len(src_txns))
        else:
            cross_bank_ratio = 0.5  # Default when bank info not available

        # Amount concentration (Gini)
        amount_concentration = gini_coefficient(amounts) if len(amounts) > 1 else 0.0

        return {
            "account_id": account_id,
            # Graph features (1-8)
            "in_degree": in_degree,
            "out_degree": out_degree,
            "total_in_flow": total_in,
            "total_out_flow": total_out,
            "net_flow": net_flow,
            "pagerank": pagerank,
            "betweenness": betweenness,
            "clustering_coeff": clustering,
            # Transaction features (9-17)
            "avg_txn_amount": avg_txn,
            "std_txn_amount": std_txn,
            "max_txn_amount": max_txn,
            "txn_count": txn_count,
            "unique_channels": unique_channels,
            "channel_entropy": ch_entropy,
            "velocity_10min": velocity_10min,
            "velocity_1hour": velocity_1hour,
            "near_threshold_count": near_threshold,
            # Account features (18-21)
            "dormancy_days": dormancy_days,
            "income_volume_ratio": income_volume_ratio,
            "is_weekend_heavy": is_weekend_heavy,
            "night_txn_ratio": night_ratio,
            # Additional features (22-30)
            "reciprocity_ratio": reciprocity_ratio,
            "geographic_dispersion": geographic_dispersion,
            "max_daily_txn_count": max_daily_count,
            "round_number_ratio": round_number_ratio,
            "temporal_regularity": temporal_regularity,
            "new_counterparty_ratio": new_counterparty_ratio,
            "cross_bank_ratio": cross_bank_ratio,
            "amount_concentration": amount_concentration,
        }

    @staticmethod
    def _max_window_count(txns: pd.DataFrame, window: str) -> int:
        """Max transactions in any rolling time window."""
        if len(txns) == 0:
            return 0
        ts = txns["timestamp"].sort_values()
        try:
            counts = ts.groupby(ts.dt.floor(window)).size()
            return int(counts.max()) if len(counts) > 0 else 0
        except Exception:
            return 0

    @staticmethod
    def _compute_dormancy(txns: pd.DataFrame) -> float:
        """Compute max dormancy gap in days."""
        if len(txns) < 2:
            return 0.0
        sorted_ts = txns["timestamp"].sort_values()
        gaps = sorted_ts.diff().dt.total_seconds() / 86400
        return float(gaps.max()) if len(gaps.dropna()) > 0 else 0.0


# Need networkx imported for clustering
import networkx as nx
