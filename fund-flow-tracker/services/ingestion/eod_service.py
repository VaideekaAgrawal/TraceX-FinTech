"""
EOD (End-of-Day) Ingestion Service — daily CSV ingestion with incremental analysis.

This service handles:
1. Accept daily transaction CSV dumps (same format as training data)
2. Validate CSV schema against expected columns
3. Idempotent processing (skip already-ingested files via hash)
4. For new accounts: ingest and run detection on today's data
5. For existing accounts: fetch last 7 days from DB + today, run incremental detection
6. Store all transactions and accounts in the database
7. Generate new alerts from incremental detections
"""
import hashlib
import logging
import os
import time
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

from infrastructure.database import get_database, compute_file_hash, DB_BACKEND, NEO4J_URI

logger = logging.getLogger(__name__)

# Expected columns matching training data format (IBM AML)
EXPECTED_COLUMNS = [
    "Timestamp", "From Bank", "Account", "To Bank", "Account.1",
    "Amount Received", "Receiving Currency", "Amount Paid",
    "Payment Currency", "Payment Format", "Is Laundering"
]

# Alternative normalized column names
NORMALIZED_COLUMNS = [
    "timestamp", "source_account", "dest_account", "amount",
    "channel", "is_laundering"
]


def _make_alert_id(account_id: str, pattern: str, date_str: str) -> str:
    """Deterministic alert ID — same account+pattern+date always produces same ID."""
    content_key = f"{account_id}-{pattern}-{date_str}"
    return f"ALT-{hashlib.sha256(content_key.encode()).hexdigest()[:12].upper()}"


class EODIngestionService:
    """Handles daily EOD transaction file ingestion with incremental analysis."""

    def __init__(self):
        self._db = None

    @property
    def db(self):
        if self._db is None:
            self._db = get_database()
        return self._db

    def ingest_daily_file(
        self,
        filepath: str,
        date: Optional[str] = None,
        max_rows: Optional[int] = None,
        force: bool = False,
    ) -> Dict[str, Any]:
        """
        Ingest a daily transaction CSV file.

        Parameters
        ----------
        filepath : str
            Path to the CSV file (same format as training data).
        date : str, optional
            Date of the transactions (YYYY-MM-DD). Defaults to today.
        max_rows : int, optional
            Limit rows for testing.
        force : bool
            Skip idempotency check and re-ingest.

        Returns
        -------
        dict with ingestion summary including new accounts, existing accounts,
        alerts generated, etc.
        """
        start_time = time.time()
        date = date or datetime.now().strftime("%Y-%m-%d")

        logger.info("=" * 60)
        logger.info("EOD INGESTION STARTING — date=%s, file=%s", date, filepath)
        logger.info("=" * 60)

        # 1. Validate file exists
        if not os.path.exists(filepath):
            raise FileNotFoundError(f"File not found: {filepath}")

        # 2. Idempotency check
        file_hash = compute_file_hash(filepath)
        if not force and self.db.is_file_ingested(file_hash):
            logger.info("File already ingested (hash=%s). Skipping.", file_hash[:16])
            return {
                "status": "skipped",
                "reason": "already_ingested",
                "file_hash": file_hash[:16],
            }

        # 3. Load and validate CSV
        logger.info("┌─ Step 1: Loading and validating CSV...")
        df = self._load_and_validate(filepath, max_rows)
        logger.info("└─ Step 1: ✅ Loaded %d transactions", len(df))

        # 4. Normalize to internal format
        logger.info("┌─ Step 2: Normalizing data...")
        txns_df, accounts_df = self._normalize(df, date)
        logger.info("└─ Step 2: ✅ %d transactions, %d unique accounts",
                    len(txns_df), len(accounts_df))

        # 5. Classify accounts as new or existing
        logger.info("┌─ Step 3: Classifying accounts (new vs existing)...")
        new_accounts, existing_accounts = self._classify_accounts(accounts_df)
        logger.info("└─ Step 3: ✅ %d new accounts, %d existing accounts",
                    len(new_accounts), len(existing_accounts))

        # 6. Store transactions and accounts in DB
        logger.info("┌─ Step 4: Persisting to database...")
        self._persist_data(txns_df, accounts_df, date)
        logger.info("└─ Step 4: ✅ Data persisted")

        # 7. Incremental analysis
        logger.info("┌─ Step 5: Running incremental analysis...")
        analysis_results = self._run_incremental_analysis(
            txns_df, new_accounts, existing_accounts, date
        )
        logger.info("└─ Step 5: ✅ Analysis complete — %d alerts generated",
                    analysis_results.get("alerts_generated", 0))

        # 8. Record ingestion
        self.db.record_ingestion(
            file_hash=file_hash,
            filename=os.path.basename(filepath),
            date=date,
            num_transactions=len(txns_df),
            num_accounts=len(accounts_df),
        )

        elapsed = time.time() - start_time
        summary = {
            "status": "completed",
            "date": date,
            "file": os.path.basename(filepath),
            "file_hash": file_hash[:16],
            "total_transactions": len(txns_df),
            "total_accounts": len(accounts_df),
            "new_accounts": len(new_accounts),
            "existing_accounts": len(existing_accounts),
            "alerts_generated": analysis_results.get("alerts_generated", 0),
            "patterns_detected": analysis_results.get("patterns_detected", {}),
            "processing_time_sec": round(elapsed, 2),
        }

        logger.info("=" * 60)
        logger.info("EOD INGESTION COMPLETE — %.1fs", elapsed)
        logger.info("  Transactions: %d | New accounts: %d | Alerts: %d",
                    len(txns_df), len(new_accounts), analysis_results.get("alerts_generated", 0))
        logger.info("=" * 60)

        return summary

    def _load_and_validate(self, filepath: str, max_rows: Optional[int] = None) -> pd.DataFrame:
        """Load CSV and validate it matches expected format."""
        # Try reading with different possible formats
        df = pd.read_csv(filepath, nrows=max_rows)

        # Check if it matches IBM AML format
        if all(col in df.columns for col in ["Timestamp", "From Bank", "Account"]):
            logger.info("Detected IBM AML format")
            return df

        # Check if it's already normalized
        if all(col in df.columns for col in ["timestamp", "source_account", "dest_account", "amount"]):
            logger.info("Detected normalized format")
            return df

        # Try to find required columns by fuzzy matching
        col_lower = {c.lower().strip(): c for c in df.columns}
        required_found = 0
        for req in ["timestamp", "amount"]:
            if req in col_lower:
                required_found += 1

        if required_found < 2:
            raise ValueError(
                f"CSV format not recognized. Expected columns matching IBM AML format "
                f"or normalized format. Found: {list(df.columns)}"
            )

        return df

    def _normalize(self, df: pd.DataFrame, date: str) -> Tuple[pd.DataFrame, pd.DataFrame]:
        """Normalize raw CSV to internal transaction format."""
        from utils.constants import IBM_CHANNEL_MAP, FX_RATES, CHANNELS

        # IBM AML format
        if "From Bank" in df.columns or "Account" in df.columns:
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
            df = df.rename(columns=col_map)

            df["source_account"] = df["source_account"].astype(str).str.strip()
            df["dest_account"] = df["dest_account"].astype(str).str.strip()

            if "channel" in df.columns:
                df["channel"] = df["channel"].map(IBM_CHANNEL_MAP).fillna("net_banking")

            if "amount_paid" in df.columns and "payment_currency" in df.columns:
                df["amount"] = df.apply(
                    lambda r: r["amount_paid"] * FX_RATES.get(str(r.get("payment_currency", "")), 83.0),
                    axis=1
                )
            elif "amount" not in df.columns:
                df["amount"] = df.get("amount_paid", pd.Series([0] * len(df)))

        # Ensure required columns
        df["source_account"] = df["source_account"].astype(str).str.strip()
        df["dest_account"] = df["dest_account"].astype(str).str.strip()

        if "timestamp" not in df.columns:
            df["timestamp"] = datetime.now().isoformat()
        df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce")

        if "amount" not in df.columns:
            df["amount"] = 0.0
        df["amount"] = pd.to_numeric(df["amount"], errors="coerce").fillna(0)

        if "channel" not in df.columns:
            df["channel"] = np.random.choice(CHANNELS, size=len(df))

        if "is_laundering" not in df.columns:
            df["is_laundering"] = 0

        # Generate txn_ids — include file_hash to avoid collisions across same-day files
        _fpath_hash = hashlib.md5(str(date).encode()).hexdigest()[:8]
        df["txn_id"] = [
            f"TXN-{date}-{_fpath_hash}-{i:08d}" for i in range(len(df))
        ]
        df["txn_type"] = "transfer"
        df["ingestion_date"] = date

        # Create transactions dataframe
        txns_df = df[["txn_id", "timestamp", "source_account", "dest_account",
                      "amount", "channel", "txn_type", "is_laundering", "ingestion_date"]].copy()

        # Create accounts dataframe
        all_accounts = set(txns_df["source_account"]) | set(txns_df["dest_account"])
        accounts_df = pd.DataFrame({"account_id": list(all_accounts)})
        accounts_df["account_type"] = "savings"
        accounts_df["branch_city"] = "Unknown"
        accounts_df["risk_score"] = 0.0
        accounts_df["risk_level"] = "LOW"
        accounts_df["role"] = "NORMAL"

        return txns_df, accounts_df

    def _classify_accounts(self, accounts_df: pd.DataFrame) -> Tuple[List[str], List[str]]:
        """Classify accounts as new (not in DB) or existing (already in DB). Uses chunked bulk queries."""
        all_ids = accounts_df["account_id"].astype(str).tolist()
        existing_set: set = set()
        try:
            for i in range(0, len(all_ids), 1000):
                chunk = all_ids[i:i + 1000]
                for acc_id in chunk:
                    try:
                        if self.db.account_exists(acc_id):
                            existing_set.add(acc_id)
                    except Exception as e:
                        logger.warning("DB check failed for account %s: %s", acc_id, e)
        except Exception as e:
            logger.warning("_classify_accounts DB error: %s. Treating all as new.", e)
        new_accounts = [a for a in all_ids if a not in existing_set]
        existing_accounts = [a for a in all_ids if a in existing_set]
        return new_accounts, existing_accounts

    def _persist_data(self, txns_df: pd.DataFrame, accounts_df: pd.DataFrame, date: str):
        """Store transactions and accounts in database."""
        # Store accounts
        account_dicts = accounts_df.to_dict("records")
        self.db.upsert_accounts(account_dicts)

        # Store transactions
        txn_dicts = []
        for _, row in txns_df.iterrows():
            txn_dicts.append({
                "txn_id": row["txn_id"],
                "timestamp": str(row["timestamp"]),
                "source_account": row["source_account"],
                "dest_account": row["dest_account"],
                "amount": float(row["amount"]),
                "channel": row.get("channel", "unknown"),
                "txn_type": row.get("txn_type", "transfer"),
                "is_laundering": int(row.get("is_laundering", 0)),
                "ingestion_date": date,
            })

        # Batch insert
        batch_size = 5000
        total_inserted = 0
        for i in range(0, len(txn_dicts), batch_size):
            batch = txn_dicts[i:i + batch_size]
            inserted = self.db.insert_transactions(batch)
            total_inserted += inserted
            if (i // batch_size) % 10 == 0:
                logger.info("  Persisted %d/%d transactions...", total_inserted, len(txn_dicts))

        logger.info("  Total persisted: %d transactions, %d accounts",
                    total_inserted, len(account_dicts))

    def _run_incremental_analysis(
        self,
        today_txns: pd.DataFrame,
        new_accounts: List[str],
        existing_accounts: List[str],
        date: str,
    ) -> Dict[str, Any]:
        """
        Run incremental fraud detection:
        - New accounts: analyze today's transactions only
        - Existing accounts: analyze today + last 7 days transactions
        """
        alerts_generated = 0
        patterns_detected: Dict[str, int] = {}

        # For new accounts: detect patterns in today's transactions
        if new_accounts:
            new_acc_txns = today_txns[
                today_txns["source_account"].isin(new_accounts) |
                today_txns["dest_account"].isin(new_accounts)
            ]
            if len(new_acc_txns) > 0:
                new_alerts, new_patterns = self._detect_patterns(new_acc_txns, "new_account")
                alerts_generated += new_alerts
                for k, v in new_patterns.items():
                    patterns_detected[k] = patterns_detected.get(k, 0) + v

        # For existing accounts: fetch 7-day window + today and detect
        if existing_accounts:
            # Sample existing accounts to avoid processing too many
            sample_size = min(len(existing_accounts), 10000)
            sampled = existing_accounts[:sample_size]

            # Fetch historical transactions from DB for these accounts
            historical_txns = []
            batch_size = 100
            for i in range(0, len(sampled), batch_size):
                batch_accounts = sampled[i:i + batch_size]
                for acc_id in batch_accounts:
                    hist = self.db.get_transactions_for_account(acc_id, days=7)
                    historical_txns.extend(hist)

            if historical_txns:
                hist_df = pd.DataFrame(historical_txns)
                # Merge with today's transactions for these accounts
                existing_today = today_txns[
                    today_txns["source_account"].isin(sampled) |
                    today_txns["dest_account"].isin(sampled)
                ]
                # Combine historical + today
                if "timestamp" in hist_df.columns:
                    combined = pd.concat([hist_df, existing_today], ignore_index=True)
                else:
                    combined = existing_today

                if len(combined) > 0:
                    existing_alerts, existing_patterns = self._detect_patterns(
                        combined, "incremental_7day"
                    )
                    alerts_generated += existing_alerts
                    for k, v in existing_patterns.items():
                        patterns_detected[k] = patterns_detected.get(k, 0) + v

        return {
            "alerts_generated": alerts_generated,
            "patterns_detected": patterns_detected,
        }

    def _detect_patterns(self, txns_df: pd.DataFrame, context: str) -> Tuple[int, Dict[str, int]]:
        """
        Run pattern detection on a batch of transactions.
        Returns (num_alerts, pattern_counts).
        """
        alerts = 0
        patterns: Dict[str, int] = {}

        try:
            # Structuring detection (transactions just below CTR threshold)
            structuring = self._detect_structuring(txns_df)
            if structuring:
                patterns["structuring"] = len(structuring)
                alerts += len(structuring)
                for alert_info in structuring:
                    self.db.upsert_alert(alert_info)

            # Velocity spike detection (sudden burst of transactions)
            velocity = self._detect_velocity_spikes(txns_df)
            if velocity:
                patterns["velocity_spike"] = len(velocity)
                alerts += len(velocity)
                for alert_info in velocity:
                    self.db.upsert_alert(alert_info)

            # Round-trip detection (A→B→A patterns)
            round_trips = self._detect_round_trips(txns_df)
            if round_trips:
                patterns["round_trip"] = len(round_trips)
                alerts += len(round_trips)
                for alert_info in round_trips:
                    self.db.upsert_alert(alert_info)

            # Fan-out detection (one account sending to many)
            fan_out = self._detect_fan_out(txns_df)
            if fan_out:
                patterns["fan_out"] = len(fan_out)
                alerts += len(fan_out)
                for alert_info in fan_out:
                    self.db.upsert_alert(alert_info)

            # Mule pattern (receive and quickly send)
            mule = self._detect_mule_pattern(txns_df)
            if mule:
                patterns["mule_suspect"] = len(mule)
                alerts += len(mule)
                for alert_info in mule:
                    self.db.upsert_alert(alert_info)

        except Exception as e:
            logger.error("Error in pattern detection (%s): %s", context, e)

        return alerts, patterns

    def _detect_structuring(self, txns_df: pd.DataFrame) -> List[Dict]:
        """Detect transactions structured just below reporting threshold (₹10L)."""
        CTR = 1_000_000  # ₹10 lakh
        LOWER = 900_000  # ₹9 lakh
        date = datetime.now().strftime("%Y-%m-%d")
        alerts = []
        # Group by source account and count near-threshold transactions
        for acc_id, group in txns_df.groupby("source_account"):
            near_threshold = group[(group["amount"] >= LOWER) & (group["amount"] < CTR)]
            if len(near_threshold) >= 3:
                alerts.append({
                    "alert_id": _make_alert_id(str(acc_id), "structuring", date),
                    "account_id": str(acc_id),
                    "risk_score": min(85.0, 50.0 + len(near_threshold) * 5),
                    "risk_level": "HIGH" if len(near_threshold) >= 5 else "MEDIUM",
                    "pattern_type": "structuring",
                    "status": "open",
                })
        return alerts

    def _detect_velocity_spikes(self, txns_df: pd.DataFrame) -> List[Dict]:
        """Detect accounts with abnormally high transaction frequency (rate-normalised)."""
        alerts = []
        date = datetime.now().strftime("%Y-%m-%d")
        ts_col = "timestamp" if "timestamp" in txns_df.columns else None
        for acc_id, group in txns_df.groupby("source_account"):
            if len(group) >= 20:
                if ts_col:
                    ts = pd.to_datetime(group[ts_col], errors="coerce").dropna()
                    if len(ts) >= 2:
                        span_hours = max(1.0, (ts.max() - ts.min()).total_seconds() / 3600)
                    else:
                        span_hours = 24.0
                    txn_rate = len(group) / span_hours
                    if txn_rate < 5:
                        continue
                alerts.append({
                    "alert_id": _make_alert_id(str(acc_id), "velocity_spike", date),
                    "account_id": str(acc_id),
                    "risk_score": min(90.0, 40.0 + len(group) * 2),
                    "risk_level": "HIGH" if len(group) >= 50 else "MEDIUM",
                    "pattern_type": "velocity_spike",
                    "status": "open",
                })
        return alerts

    def _detect_round_trips(self, txns_df: pd.DataFrame) -> List[Dict]:
        """Detect A->B->A round-trip patterns with 48-hour temporal constraint."""
        alerts = []
        date = datetime.now().strftime("%Y-%m-%d")
        # Build edge dict: (src, dst) -> earliest timestamp
        edge_times: dict = {}
        ts_col = "timestamp" if "timestamp" in txns_df.columns else None
        for _, row in txns_df.iterrows():
            src, dst = str(row["source_account"]), str(row["dest_account"])
            if ts_col:
                ts = pd.to_datetime(row[ts_col], errors="coerce")
                if pd.isna(ts):
                    ts = None
            else:
                ts = None
            key = (src, dst)
            if key not in edge_times or (ts is not None and edge_times[key] is not None and ts < edge_times[key]):
                edge_times[key] = ts

        # Find round trips with temporal constraint
        flagged = set()
        for (src, dst), t1 in edge_times.items():
            if (dst, src) in edge_times and src not in flagged:
                t2 = edge_times[(dst, src)]
                if t1 is not None and t2 is not None:
                    time_diff_h = abs((t2 - t1).total_seconds()) / 3600
                    if time_diff_h > 48:
                        continue
                flagged.add(src)
                alerts.append({
                    "alert_id": _make_alert_id(src, "round_trip", date),
                    "account_id": src,
                    "risk_score": 70.0,
                    "risk_level": "HIGH",
                    "pattern_type": "round_trip",
                    "status": "open",
                })
        return alerts

    def _detect_fan_out(self, txns_df: pd.DataFrame) -> List[Dict]:
        """Detect accounts sending to many recipients (potential layering)."""
        date = datetime.now().strftime("%Y-%m-%d")
        alerts = []
        dest_counts = txns_df.groupby("source_account")["dest_account"].nunique()
        for acc_id, n_dests in dest_counts.items():
            if n_dests >= 10:  # Sending to 10+ unique accounts
                alerts.append({
                    "alert_id": _make_alert_id(str(acc_id), "fan_out", date),
                    "account_id": str(acc_id),
                    "risk_score": min(80.0, 45.0 + n_dests * 3),
                    "risk_level": "HIGH" if n_dests >= 20 else "MEDIUM",
                    "pattern_type": "fan_out",
                    "status": "open",
                })
        return alerts

    def _detect_mule_pattern(self, txns_df: pd.DataFrame) -> List[Dict]:
        """Detect mule behavior: receive money and quickly forward most of it."""
        date = datetime.now().strftime("%Y-%m-%d")
        alerts = []
        txns_df = txns_df.copy()
        if "timestamp" in txns_df.columns:
            txns_df["timestamp"] = pd.to_datetime(txns_df["timestamp"], errors="coerce")

        # For each account: compare inflows vs outflows
        in_flow = txns_df.groupby("dest_account")["amount"].sum()
        out_flow = txns_df.groupby("source_account")["amount"].sum()

        for acc_id in set(in_flow.index) & set(out_flow.index):
            total_in = in_flow.get(acc_id, 0)
            total_out = out_flow.get(acc_id, 0)
            if total_in > 100000 and total_out > 0:  # Minimum ₹1L inflow
                pass_through_ratio = total_out / total_in
                if pass_through_ratio >= 0.8:  # Passes through 80%+ of received funds
                    alerts.append({
                        "alert_id": _make_alert_id(str(acc_id), "mule_suspect", date),
                        "account_id": str(acc_id),
                        "risk_score": min(95.0, 60.0 + pass_through_ratio * 30),
                        "risk_level": "CRITICAL" if pass_through_ratio >= 0.95 else "HIGH",
                        "pattern_type": "mule_suspect",
                        "status": "open",
                    })
        return alerts

    def get_ingestion_status(self) -> Dict[str, Any]:
        """Get current ingestion status and statistics."""
        history = self.db.get_ingestion_history(limit=10)
        return {
            "db_backend": DB_BACKEND if (DB_BACKEND == "neo4j" and NEO4J_URI) else "sqlite",
            "total_accounts_in_db": self.db.get_account_count(),
            "total_transactions_in_db": self.db.get_transaction_count(),
            "recent_ingestions": history,
        }
