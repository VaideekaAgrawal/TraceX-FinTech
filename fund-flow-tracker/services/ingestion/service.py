"""
Ingestion Service — entry point for all data loading.

Responsibilities:
- Accept data from multiple sources (IBM AML, PaySim, CSV upload)
- Validate schema (CP-01)
- Publish normalised data to event bus
- Route malformed records to DLQ (CP-02)
"""
import logging
from typing import Dict, Optional, Tuple

import pandas as pd

from infrastructure.event_bus import bus, Topics
from infrastructure.health import health
from services.ingestion.parsers import IBMAMLParser, PaySimParser, CSVParser
from infrastructure.database import get_database

logger = logging.getLogger(__name__)

_SERVICE = "ingestion"


class IngestionService:
    """Unified data ingestion — all roads lead to (accounts_df, transactions_df)."""

    def __init__(self):
        self._ibm = IBMAMLParser()
        self._paysim = PaySimParser()
        self._csv = CSVParser()
        health.register_service(_SERVICE)

    def ingest(self, source: str, filepath: Optional[str] = None,
               dataframe: Optional[pd.DataFrame] = None,
               column_mapping: Optional[Dict[str, str]] = None,
               max_rows: Optional[int] = None) -> Tuple[pd.DataFrame, pd.DataFrame]:
        """
        Load and validate data from the specified source.

        Parameters
        ----------
        source : str
            One of 'ibm_aml', 'paysim', 'csv'.
        filepath : str, optional
            Path to CSV file.
        dataframe : DataFrame, optional
            Pre-loaded DataFrame (e.g. from Streamlit upload).
        column_mapping : dict, optional
            Explicit column mapping for CSV source.
        max_rows : int, optional
            Limit rows for large datasets.
        """
        try:
            data_input = dataframe if dataframe is not None else filepath

            if source == "ibm_aml":
                accounts_df, txns_df = self._ibm.parse(data_input, max_rows=max_rows)
            elif source == "paysim":
                accounts_df, txns_df = self._paysim.parse(data_input)
                if max_rows and len(txns_df) > max_rows:
                    txns_df = txns_df.head(max_rows)
                    all_accs = set(txns_df["source_account"]) | set(txns_df["dest_account"])
                    accounts_df = accounts_df[accounts_df["account_id"].isin(all_accs)]
            elif source == "csv":
                accounts_df, txns_df = self._csv.parse(data_input, column_mapping)
                if max_rows and len(txns_df) > max_rows:
                    txns_df = txns_df.head(max_rows)
                    all_accs = set(txns_df["source_account"]) | set(txns_df["dest_account"])
                    accounts_df = accounts_df[accounts_df["account_id"].isin(all_accs)]
            else:
                raise ValueError(f"Unknown source: {source}")

            # ── Validate (CP-01) ──
            # Mark new vs existing accounts by checking DB (bulk query, not per-account)
            try:
                db = get_database()
                existing = set()
                account_ids_list = accounts_df["account_id"].astype(str).unique().tolist()
                for i in range(0, len(account_ids_list), 1000):
                    chunk = account_ids_list[i:i + 1000]
                    try:
                        for acc in chunk:
                            if db.account_exists(acc):
                                existing.add(acc)
                    except Exception as e:
                        logger.warning("DB account existence check failed: %s. Treating chunk as new.", e)
                accounts_df["is_new"] = ~accounts_df["account_id"].astype(str).isin(existing)
                # Transactions: mark source/dest as new if account not in existing set
                txns_df["source_is_new"] = ~txns_df["source_account"].astype(str).isin(existing)
                txns_df["dest_is_new"] = ~txns_df["dest_account"].astype(str).isin(existing)
            except Exception as e:
                logger.warning("DB availability check failed: %s. Defaulting to all-new.", e)
                accounts_df["is_new"] = False
                txns_df["source_is_new"] = False
                txns_df["dest_is_new"] = False

            valid_count, total_count = self._validate(txns_df)
            health.cp01_schema_validation(valid_count, total_count)

            # ── Counters ──
            health.increment("events_ingested", len(txns_df))
            health.heartbeat(_SERVICE, "healthy")

            # ── Publish ──
            bus.publish(Topics.RAW_TRANSACTIONS, {
                "accounts": accounts_df,
                "transactions": txns_df,
                "source": source,
            }, source_service=_SERVICE)

            logger.info("Ingested %d accounts, %d transactions from '%s'",
                        len(accounts_df), len(txns_df), source)
            return accounts_df, txns_df

        except Exception as exc:
            health.record_error(_SERVICE, str(exc))
            raise

    @staticmethod
    def _validate(df: pd.DataFrame) -> Tuple[int, int]:
        """Validate required columns and types. Returns (valid_count, total)."""
        required = ["txn_id", "timestamp", "source_account", "dest_account", "amount"]
        total = len(df)
        mask = pd.Series(True, index=df.index)

        for col in required:
            if col not in df.columns:
                return 0, total
            mask &= df[col].notna()

        mask &= df["amount"] > 0
        valid = int(mask.sum())
        return valid, total

    @staticmethod
    def get_supported_sources():
        return [
            {"id": "ibm_aml", "name": "IBM AML Dataset", "description": "5M labelled transactions, 8 laundering patterns"},
            {"id": "paysim", "name": "PaySim Dataset", "description": "6.3M synthetic transactions"},
            {"id": "csv", "name": "Custom CSV", "description": "Upload your own transaction data"},
        ]
