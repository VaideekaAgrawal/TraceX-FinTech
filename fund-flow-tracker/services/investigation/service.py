"""
Investigation Service — orchestrates case management + evidence generation.

Responsibilities:
- Create/manage investigation cases
- Generate FIU-IND compliant evidence packs
- Track resolution for feedback loop (model retraining)
"""
import logging
from typing import Any, Dict, List, Optional

import pandas as pd

from infrastructure.event_bus import bus, Topics
from infrastructure.health import health
from services.investigation.case_manager import CaseManager
from services.investigation.evidence import EvidenceGenerator
from services.common.models import Alert, Case, EvidencePack

logger = logging.getLogger(__name__)

_SERVICE = "investigation"


class InvestigationService:
    """Manages investigations, cases, and evidence generation."""

    def __init__(self):
        self.case_manager = CaseManager()
        self.evidence_gen = EvidenceGenerator()
        health.register_service(_SERVICE)

    # ── Alert management ─────────────────────────────────────────────

    def create_alerts_from_detections(self, detection_results: Dict) -> List[Alert]:
        """Auto-create alerts from detection pipeline output."""
        alerts = self.case_manager.auto_create_alerts_from_detections(detection_results)
        health.increment("alerts_created", len(alerts))
        health.heartbeat(_SERVICE, "healthy")

        for alert in alerts:
            bus.publish(Topics.ALERT_CREATED, alert.to_dict(), source_service=_SERVICE)

        logger.info("Created %d alerts from detections", len(alerts))
        return alerts

    def list_alerts(self, status: Optional[str] = None) -> List[Alert]:
        return self.case_manager.list_alerts(status)

    def get_alert(self, alert_id: str) -> Optional[Alert]:
        return self.case_manager.get_alert(alert_id)

    # ── Case management ──────────────────────────────────────────────

    def create_case(self, account_ids: List[str], typology: str,
                    priority: str = "P3", alert_ids: Optional[List[str]] = None,
                    notes: str = "") -> Case:
        case = self.case_manager.create_case(
            account_ids, typology, priority, alert_ids, notes
        )
        health.increment("cases_opened")
        bus.publish(Topics.CASE_UPDATED, case.to_dict(), source_service=_SERVICE)
        return case

    def update_case(self, case_id: str, status: str, notes: str = "") -> Optional[Case]:
        case = self.case_manager.update_case_status(case_id, status, notes)
        if case:
            bus.publish(Topics.CASE_UPDATED, case.to_dict(), source_service=_SERVICE)
        return case

    def resolve_case(self, case_id: str, resolution: str,
                     is_true_positive: bool) -> Optional[Case]:
        case = self.case_manager.resolve_case(case_id, resolution, is_true_positive)
        if case:
            bus.publish(Topics.CASE_UPDATED, case.to_dict(), source_service=_SERVICE)
        return case

    def get_case(self, case_id: str) -> Optional[Case]:
        return self.case_manager.get_case(case_id)

    def list_cases(self, status: Optional[str] = None) -> List[Case]:
        return self.case_manager.list_cases(status)

    def get_case_stats(self) -> Dict[str, int]:
        return self.case_manager.get_stats()

    # ── Evidence generation ──────────────────────────────────────────

    def generate_evidence(self, case_id: str, account_ids: List[str],
                          graph_engine, risk_scores: Dict[str, float],
                          detection_results: Dict,
                          transactions_df: pd.DataFrame,
                          accounts_df: pd.DataFrame,
                          case_notes: str = "") -> EvidencePack:
        """Generate FIU-IND compliant evidence pack."""
        pack = self.evidence_gen.generate(
            case_id, account_ids, graph_engine, risk_scores,
            detection_results, transactions_df, accounts_df, case_notes,
        )

        # Link evidence to case
        case = self.case_manager.get_case(case_id)
        if case:
            case.evidence_hash = pack.json_hash

        return pack
