"""
Data loader for TraceX — supports IBM AML dataset, PaySim, and custom CSV upload.
Handles column mapping, currency conversion, and Indian context adaptation.
"""
import os
import pandas as pd
import numpy as np
from typing import Tuple, Optional, Dict
from utils.constants import (
    IBM_CHANNEL_MAP, FX_RATES, ACCOUNT_TYPES, BRANCH_CITIES,
    OCCUPATIONS, INCOME_BRACKETS, CHANNELS,
)


class DataLoader:
    """Unified data loader supporting multiple dataset formats."""

    REQUIRED_COLUMNS = ["source_account", "dest_account", "amount", "timestamp"]

    def load(self, source: str, filepath: Optional[str] = None,
             dataframe: Optional[pd.DataFrame] = None,
             column_mapping: Optional[Dict[str, str]] = None) -> Tuple[pd.DataFrame, pd.DataFrame]:
        """
        Load transaction data and return (accounts_df, transactions_df).

        Parameters
        ----------
        source : str
            One of 'ibm_aml', 'paysim', 'custom_csv'.
        filepath : str, optional
            Path to the CSV file.
        dataframe : pd.DataFrame, optional
            Pre-loaded dataframe (for Streamlit upload).
        column_mapping : dict, optional
            Custom column name mapping for 'custom_csv' source.
        """
        if source == "ibm_aml":
            return self._load_ibm_aml(filepath or dataframe)
        elif source == "paysim":
            return self._load_paysim(filepath or dataframe)
        elif source == "custom_csv":
            return self._load_custom(filepath or dataframe, column_mapping)
        else:
            raise ValueError(f"Unknown data source: {source}")

    # ------------------------------------------------------------------
    # IBM AML Dataset
    # ------------------------------------------------------------------
    def _load_ibm_aml(self, source) -> Tuple[pd.DataFrame, pd.DataFrame]:
        """Load IBM AML Transactions dataset and adapt to Indian bank context."""
        df = self._read_source(source)

        # Normalize column names
        col_map = {
            "Timestamp": "timestamp",
            "From Bank": "from_bank",
            "Account": "source_account",
            "To Bank": "to_bank",
            "Account.1": "dest_account",
            "Amount Received": "amount_received",
            "Receiving Currency": "receiving_currency",
            "Amount Paid": "amount_paid",
            "Payment Currency": "payment_currency",
            "Payment Format": "channel",
            "Is Laundering": "is_laundering",
        }
        # Try both possible column naming conventions
        if "From Bank" in df.columns:
            df = df.rename(columns=col_map)
        else:
            # Alternative column names seen in some IBM AML downloads
            alt_map = {}
            for c in df.columns:
                clean = c.strip()
                alt_map[c] = clean
            df = df.rename(columns=alt_map)
            # Apply standard mapping where possible
            lower_cols = {c.lower().replace(" ", "_"): c for c in df.columns}
            renames = {}
            for target in ["timestamp", "from_bank", "source_account", "to_bank",
                           "dest_account", "amount_received", "receiving_currency",
                           "amount_paid", "payment_currency", "channel", "is_laundering"]:
                if target not in df.columns and target in lower_cols:
                    renames[lower_cols[target]] = target
            df = df.rename(columns=renames)

        # Ensure string account IDs
        df["source_account"] = df["source_account"].astype(str).str.strip()
        df["dest_account"] = df["dest_account"].astype(str).str.strip()

        # Map channels to Indian context
        if "channel" in df.columns:
            df["channel"] = df["channel"].map(IBM_CHANNEL_MAP).fillna("net_banking")
        else:
            df["channel"] = np.random.choice(CHANNELS, size=len(df))

        # Convert currency to INR
        if "amount_paid" in df.columns and "payment_currency" in df.columns:
            df["amount"] = df.apply(
                lambda r: r["amount_paid"] * FX_RATES.get(str(r.get("payment_currency", "")), 83.0),
                axis=1,
            )
        elif "amount_paid" in df.columns:
            df["amount"] = df["amount_paid"] * 83.0
        elif "amount" not in df.columns:
            # Fallback — use first numeric column
            num_cols = df.select_dtypes(include=[np.number]).columns
            if len(num_cols) > 0:
                df["amount"] = df[num_cols[0]] * 83.0
            else:
                raise ValueError("Cannot find amount column in IBM AML data")

        # Parse timestamp
        df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce")
        # Fill NaT with sequential timestamps
        nat_mask = df["timestamp"].isna()
        if nat_mask.any():
            base = pd.Timestamp("2024-01-01")
            df.loc[nat_mask, "timestamp"] = [
                base + pd.Timedelta(minutes=i) for i in range(nat_mask.sum())
            ]

        # Generate txn_id
        df["txn_id"] = [f"TXN_{i:08d}" for i in range(len(df))]

        # Is laundering flag
        if "is_laundering" in df.columns:
            df["is_laundering"] = df["is_laundering"].astype(int)
        else:
            df["is_laundering"] = 0

        # Build transactions_df
        transactions_df = df[["txn_id", "timestamp", "source_account", "dest_account",
                              "amount", "channel", "is_laundering"]].copy()
        transactions_df["txn_type"] = "transfer"
        if "from_bank" in df.columns:
            transactions_df["from_bank"] = df["from_bank"].astype(str)
        if "to_bank" in df.columns:
            transactions_df["to_bank"] = df["to_bank"].astype(str)

        # Build accounts_df from unique accounts
        accounts_df = self._build_accounts_from_transactions(transactions_df)

        return accounts_df, transactions_df

    # ------------------------------------------------------------------
    # PaySim Dataset
    # ------------------------------------------------------------------
    def _load_paysim(self, source) -> Tuple[pd.DataFrame, pd.DataFrame]:
        """Load PaySim dataset."""
        df = self._read_source(source)

        # Normalize columns
        col_map = {
            "step": "step",
            "type": "txn_type",
            "amount": "amount",
            "nameOrig": "source_account",
            "oldbalanceOrg": "old_balance_orig",
            "newbalanceOrig": "new_balance_orig",
            "nameDest": "dest_account",
            "oldbalanceDest": "old_balance_dest",
            "newbalanceDest": "new_balance_dest",
            "isFraud": "is_laundering",
            "isFlaggedFraud": "is_flagged",
        }
        df = df.rename(columns={k: v for k, v in col_map.items() if k in df.columns})

        # Convert step (hour) to timestamp
        base = pd.Timestamp("2024-01-01")
        df["timestamp"] = df["step"].apply(lambda s: base + pd.Timedelta(hours=int(s)))

        # Add channel (simulated)
        rng = np.random.default_rng(42)
        type_channel = {
            "CASH_IN": "branch_cash", "CASH_OUT": "ATM",
            "DEBIT": "net_banking", "PAYMENT": "UPI", "TRANSFER": "NEFT",
        }
        df["channel"] = df["txn_type"].map(type_channel).fillna("net_banking")

        df["txn_id"] = [f"TXN_{i:08d}" for i in range(len(df))]
        df["source_account"] = df["source_account"].astype(str)
        df["dest_account"] = df["dest_account"].astype(str)

        # Convert to INR (PaySim uses abstract units; assume 1 unit = ₹1)
        # No conversion needed

        transactions_df = df[["txn_id", "timestamp", "source_account", "dest_account",
                              "amount", "channel", "txn_type", "is_laundering"]].copy()

        accounts_df = self._build_accounts_from_transactions(transactions_df)

        return accounts_df, transactions_df

    # ------------------------------------------------------------------
    # Custom CSV Upload
    # ------------------------------------------------------------------
    def _load_custom(self, source, column_mapping: Optional[Dict] = None) -> Tuple[pd.DataFrame, pd.DataFrame]:
        """Load a custom CSV with user-provided or auto-detected column mapping."""
        df = self._read_source(source)

        if column_mapping:
            df = df.rename(columns=column_mapping)
        else:
            df = self._auto_detect_columns(df)

        # Validate required columns
        missing = [c for c in self.REQUIRED_COLUMNS if c not in df.columns]
        if missing:
            raise ValueError(f"Missing required columns after mapping: {missing}")

        df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce")
        df["amount"] = pd.to_numeric(df["amount"], errors="coerce").fillna(0)
        df["source_account"] = df["source_account"].astype(str)
        df["dest_account"] = df["dest_account"].astype(str)

        if "txn_id" not in df.columns:
            df["txn_id"] = [f"TXN_{i:08d}" for i in range(len(df))]
        if "channel" not in df.columns:
            df["channel"] = "unknown"
        if "is_laundering" not in df.columns:
            df["is_laundering"] = 0
        if "txn_type" not in df.columns:
            df["txn_type"] = "transfer"

        transactions_df = df[["txn_id", "timestamp", "source_account", "dest_account",
                              "amount", "channel", "txn_type", "is_laundering"]].copy()
        accounts_df = self._build_accounts_from_transactions(transactions_df)

        return accounts_df, transactions_df

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    @staticmethod
    def _read_source(source) -> pd.DataFrame:
        """Read from filepath string or pass-through a DataFrame."""
        if isinstance(source, pd.DataFrame):
            return source.copy()
        if isinstance(source, str):
            if not os.path.isfile(source):
                raise FileNotFoundError(f"Data file not found: {source}")
            return pd.read_csv(source)
        raise TypeError(f"Expected str path or DataFrame, got {type(source)}")

    @staticmethod
    def _auto_detect_columns(df: pd.DataFrame) -> pd.DataFrame:
        """Heuristically map CSV columns to required field names."""
        mapping = {}
        for col in df.columns:
            cl = col.lower().replace(" ", "_").replace("-", "_")
            if any(k in cl for k in ["source", "from_account", "sender", "nameorig", "originator"]):
                mapping[col] = "source_account"
            elif any(k in cl for k in ["dest", "to_account", "receiver", "namedest", "beneficiary", "target"]):
                mapping[col] = "dest_account"
            elif any(k in cl for k in ["amount", "value", "sum", "amt"]):
                if "amount" not in mapping.values():
                    mapping[col] = "amount"
            elif any(k in cl for k in ["time", "date", "ts", "timestamp"]):
                if "timestamp" not in mapping.values():
                    mapping[col] = "timestamp"
            elif any(k in cl for k in ["channel", "type", "method", "mode", "payment_format"]):
                if "channel" not in mapping.values():
                    mapping[col] = "channel"
            elif any(k in cl for k in ["fraud", "laundering", "suspicious", "label"]):
                mapping[col] = "is_laundering"
        return df.rename(columns=mapping)

    @staticmethod
    def _build_accounts_from_transactions(txns: pd.DataFrame) -> pd.DataFrame:
        """Derive account metadata from transaction records."""
        all_accounts = set(txns["source_account"].unique()) | set(txns["dest_account"].unique())
        rng = np.random.default_rng(42)

        records = []
        for acc_id in all_accounts:
            src_txns = txns[txns["source_account"] == acc_id]
            dst_txns = txns[txns["dest_account"] == acc_id]
            all_txns = pd.concat([src_txns, dst_txns])

            total_out = src_txns["amount"].sum()
            total_in = dst_txns["amount"].sum()
            txn_count = len(all_txns)
            avg_monthly_volume = total_out + total_in

            # Assign realistic Indian bank metadata
            acc_type = rng.choice(ACCOUNT_TYPES)
            city = rng.choice(BRANCH_CITIES)
            occupation = rng.choice(OCCUPATIONS)

            # Income bracket based on transaction volume
            if avg_monthly_volume > 5_000_000:
                bracket = "very_high"
            elif avg_monthly_volume > 1_500_000:
                bracket = "high"
            elif avg_monthly_volume > 500_000:
                bracket = "medium"
            else:
                bracket = "low"

            income_range = INCOME_BRACKETS[bracket]
            declared_income = rng.uniform(income_range[0], income_range[1])

            records.append({
                "account_id": acc_id,
                "account_type": acc_type,
                "branch_city": city,
                "occupation": occupation,
                "income_bracket": bracket,
                "declared_annual_income": round(declared_income, 2),
                "total_in_flow": round(total_in, 2),
                "total_out_flow": round(total_out, 2),
                "txn_count": txn_count,
                "avg_monthly_txn_volume": round(avg_monthly_volume, 2),
            })

        return pd.DataFrame(records)


def generate_demo_data(n_accounts: int = 200, n_transactions: int = 5000,
                       seed: int = 42) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """
    Generate realistic synthetic Indian bank transaction data with embedded
    fraud scenarios for demo purposes. NOT for ML training — use IBM AML for that.
    """
    rng = np.random.default_rng(seed)
    base_time = pd.Timestamp("2024-01-01")

    # Generate accounts
    accounts = []
    for i in range(n_accounts):
        acc_type = rng.choice(ACCOUNT_TYPES)
        city = rng.choice(BRANCH_CITIES)
        occ = rng.choice(OCCUPATIONS)
        bracket = rng.choice(list(INCOME_BRACKETS.keys()), p=[0.4, 0.3, 0.2, 0.1])
        inc_range = INCOME_BRACKETS[bracket]

        accounts.append({
            "account_id": f"ACC_{i:04d}",
            "account_type": acc_type,
            "branch_city": city,
            "occupation": occ,
            "income_bracket": bracket,
            "declared_annual_income": round(rng.uniform(inc_range[0], inc_range[1]), 2),
        })

    accounts_df = pd.DataFrame(accounts)
    acc_ids = accounts_df["account_id"].tolist()

    # Generate normal transactions
    transactions = []
    for i in range(n_transactions):
        src = rng.choice(acc_ids)
        dst = rng.choice([a for a in acc_ids if a != src])
        amt = round(float(rng.lognormal(mean=10, sigma=1.5)), 2)
        amt = min(amt, 50_000_000)  # Cap at ₹5 Cr
        ts = base_time + pd.Timedelta(minutes=int(rng.uniform(0, 525_600)))  # 1 year
        ch = rng.choice(CHANNELS)

        transactions.append({
            "txn_id": f"TXN_{i:08d}",
            "timestamp": ts,
            "source_account": src,
            "dest_account": dst,
            "amount": amt,
            "channel": ch,
            "txn_type": "transfer",
            "is_laundering": 0,
        })

    # Embed fraud scenario 1: Layering chain
    layering_accs = [f"ACC_{i:04d}" for i in range(n_accounts, n_accounts + 6)]
    for acc_id in layering_accs:
        accounts.append({
            "account_id": acc_id,
            "account_type": "current",
            "branch_city": rng.choice(BRANCH_CITIES),
            "occupation": "business_owner",
            "income_bracket": "high",
            "declared_annual_income": 3_000_000.0,
        })
    t_base = base_time + pd.Timedelta(days=30)
    amt = 800_000.0
    for j in range(len(layering_accs) - 1):
        transactions.append({
            "txn_id": f"TXN_L{j:04d}",
            "timestamp": t_base + pd.Timedelta(minutes=j * 3),
            "source_account": layering_accs[j],
            "dest_account": layering_accs[j + 1],
            "amount": round(amt * (0.97 ** j), 2),
            "channel": rng.choice(["NEFT", "RTGS", "IMPS"]),
            "txn_type": "transfer",
            "is_laundering": 1,
        })

    # Embed fraud scenario 2: Round-tripping cycle
    cycle_accs = [f"ACC_{i:04d}" for i in range(n_accounts + 6, n_accounts + 9)]
    for acc_id in cycle_accs:
        accounts.append({
            "account_id": acc_id,
            "account_type": "current",
            "branch_city": rng.choice(BRANCH_CITIES),
            "occupation": "self_employed",
            "income_bracket": "medium",
            "declared_annual_income": 1_000_000.0,
        })
    for iteration in range(3):
        for j in range(len(cycle_accs)):
            src_idx = j
            dst_idx = (j + 1) % len(cycle_accs)
            transactions.append({
                "txn_id": f"TXN_R{iteration}_{j:04d}",
                "timestamp": t_base + pd.Timedelta(days=iteration * 7, hours=j * 2),
                "source_account": cycle_accs[src_idx],
                "dest_account": cycle_accs[dst_idx],
                "amount": round(500_000 + rng.normal(0, 5000), 2),
                "channel": "NEFT",
                "txn_type": "transfer",
                "is_laundering": 1,
            })

    # Embed fraud scenario 3: Structuring
    struct_acc = f"ACC_{n_accounts + 9:04d}"
    accounts.append({
        "account_id": struct_acc,
        "account_type": "savings",
        "branch_city": "Mumbai",
        "occupation": "business_owner",
        "income_bracket": "medium",
        "declared_annual_income": 800_000.0,
    })
    for j in range(12):
        transactions.append({
            "txn_id": f"TXN_S{j:04d}",
            "timestamp": t_base + pd.Timedelta(days=j, hours=rng.integers(9, 17)),
            "source_account": struct_acc,
            "dest_account": rng.choice(acc_ids[:20]),
            "amount": round(float(rng.uniform(900_000, 999_000)), 2),
            "channel": rng.choice(["branch_cash", "NEFT"]),
            "txn_type": "transfer",
            "is_laundering": 1,
        })

    # Embed fraud scenario 4: Dormant account activation
    dormant_acc = f"ACC_{n_accounts + 10:04d}"
    accounts.append({
        "account_id": dormant_acc,
        "account_type": "savings",
        "branch_city": "Delhi",
        "occupation": "homemaker",
        "income_bracket": "low",
        "declared_annual_income": 200_000.0,
    })
    # One old transaction
    transactions.append({
        "txn_id": "TXN_D_OLD",
        "timestamp": base_time - pd.Timedelta(days=300),
        "source_account": dormant_acc,
        "dest_account": rng.choice(acc_ids[:5]),
        "amount": 5000.0,
        "channel": "ATM",
        "txn_type": "transfer",
        "is_laundering": 0,
    })
    # Burst of high-value transactions
    for j in range(15):
        transactions.append({
            "txn_id": f"TXN_D{j:04d}",
            "timestamp": t_base + pd.Timedelta(hours=j * 4),
            "source_account": rng.choice(acc_ids[:10]),
            "dest_account": dormant_acc,
            "amount": round(float(rng.uniform(200_000, 2_000_000)), 2),
            "channel": rng.choice(["RTGS", "NEFT"]),
            "txn_type": "transfer",
            "is_laundering": 1,
        })

    # Embed fraud scenario 5: Fan-in (multiple sources to one sink)
    sink_acc = f"ACC_{n_accounts + 11:04d}"
    accounts.append({
        "account_id": sink_acc,
        "account_type": "current",
        "branch_city": "Bengaluru",
        "occupation": "business_owner",
        "income_bracket": "high",
        "declared_annual_income": 4_000_000.0,
    })
    for j in range(10):
        transactions.append({
            "txn_id": f"TXN_FI{j:04d}",
            "timestamp": t_base + pd.Timedelta(days=1, hours=j),
            "source_account": rng.choice(acc_ids[:30]),
            "dest_account": sink_acc,
            "amount": round(float(rng.uniform(100_000, 500_000)), 2),
            "channel": rng.choice(CHANNELS),
            "txn_type": "transfer",
            "is_laundering": 1,
        })

    accounts_df = pd.DataFrame(accounts)
    transactions_df = pd.DataFrame(transactions)
    transactions_df["timestamp"] = pd.to_datetime(transactions_df["timestamp"])

    return accounts_df, transactions_df
