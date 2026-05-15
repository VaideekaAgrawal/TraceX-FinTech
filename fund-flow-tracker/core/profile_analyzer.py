"""
Profile Analyzer for TraceX — detects profile-vs-behavior mismatches.
"""
import numpy as np
import pandas as pd
from typing import Dict, List
from utils.helpers import safe_ratio


class ProfileAnalyzer:
    """Detect accounts where behavior doesn't match their declared profile."""

    def __init__(self, accounts_df: pd.DataFrame, transactions_df: pd.DataFrame):
        self.accounts = accounts_df
        self.txns = transactions_df

    def compute_peer_group(self, account_id: str) -> Dict:
        """Compare account behavior with peer group (same occupation + income bracket)."""
        acc = self.accounts[self.accounts["account_id"] == account_id]
        if len(acc) == 0:
            return {"error": "Account not found"}

        acc = acc.iloc[0]
        occupation = acc.get("occupation", "unknown")
        bracket = acc.get("income_bracket", "medium")

        # Find peers
        peers = self.accounts[
            (self.accounts["occupation"] == occupation) &
            (self.accounts["income_bracket"] == bracket) &
            (self.accounts["account_id"] != account_id)
        ]

        if len(peers) == 0:
            return {"error": "No peer group found", "account_id": account_id}

        # Get actual transaction volume for the account
        acc_txns = self.txns[
            (self.txns["source_account"] == account_id) |
            (self.txns["dest_account"] == account_id)
        ]
        actual_volume = acc_txns["amount"].sum()

        # Get peer volumes
        peer_volumes = []
        for _, peer in peers.iterrows():
            peer_txns = self.txns[
                (self.txns["source_account"] == peer["account_id"]) |
                (self.txns["dest_account"] == peer["account_id"])
            ]
            peer_volumes.append(peer_txns["amount"].sum())

        peer_volumes = np.array(peer_volumes)
        if len(peer_volumes) == 0:
            return {"error": "No peer volume data"}

        peer_mean = np.mean(peer_volumes)
        peer_std = np.std(peer_volumes)

        z_score = (actual_volume - peer_mean) / max(peer_std, 1)

        return {
            "account_id": account_id,
            "occupation": occupation,
            "income_bracket": bracket,
            "declared_income": acc.get("declared_annual_income", 0),
            "actual_volume": round(actual_volume, 2),
            "peer_mean_volume": round(peer_mean, 2),
            "peer_std_volume": round(peer_std, 2),
            "z_score": round(z_score, 2),
            "peer_count": len(peers),
            "is_mismatch": abs(z_score) > 3,
            "mismatch_severity": "CRITICAL" if abs(z_score) > 5 else
                                "HIGH" if abs(z_score) > 3 else "NORMAL",
        }

    def detect_all_mismatches(self, threshold_z: float = 3.0) -> List[Dict]:
        """Detect all profile-behavior mismatches across all accounts."""
        results = []

        for _, acc in self.accounts.iterrows():
            account_id = acc["account_id"]
            acc_txns = self.txns[
                (self.txns["source_account"] == account_id) |
                (self.txns["dest_account"] == account_id)
            ]
            actual_volume = acc_txns["amount"].sum()
            declared_income = acc.get("declared_annual_income", 0)

            # Simple ratio check
            ratio = safe_ratio(actual_volume, declared_income)

            if ratio > 10:  # Volume > 10x declared income
                results.append({
                    "account_id": account_id,
                    "occupation": acc.get("occupation", "unknown"),
                    "income_bracket": acc.get("income_bracket", "unknown"),
                    "declared_income": round(declared_income, 2),
                    "actual_volume": round(actual_volume, 2),
                    "volume_to_income_ratio": round(ratio, 2),
                    "severity": "CRITICAL" if ratio > 50 else
                               "HIGH" if ratio > 20 else "MEDIUM",
                })

        return sorted(results, key=lambda x: x["volume_to_income_ratio"], reverse=True)

    def get_scatter_data(self) -> pd.DataFrame:
        """Get data for income vs volume scatter plot."""
        records = []
        for _, acc in self.accounts.iterrows():
            account_id = acc["account_id"]
            acc_txns = self.txns[
                (self.txns["source_account"] == account_id) |
                (self.txns["dest_account"] == account_id)
            ]
            actual_volume = acc_txns["amount"].sum()
            records.append({
                "account_id": account_id,
                "declared_income": acc.get("declared_annual_income", 0),
                "actual_volume": actual_volume,
                "occupation": acc.get("occupation", "unknown"),
                "income_bracket": acc.get("income_bracket", "unknown"),
                "ratio": safe_ratio(actual_volume, acc.get("declared_annual_income", 1)),
            })
        return pd.DataFrame(records)
