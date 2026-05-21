"""
Case Manager — investigation lifecycle management.

Case states: OPEN → INVESTIGATING → ESCALATED → CLOSED_TP / CLOSED_FP
Resolution feeds back into labelled dataset for model retraining.
"""
import logging
from datetime import datetime
from typing import Dict, List, Optional

from services.common.models import Alert, Case, CaseStatus, Priority

logger = logging.getLogger(__name__)


class CaseManager:
    """Manages the lifecycle of investigation cases."""

    def __init__(self):
        self._alerts: Dict[str, Alert] = {}
        self._cases: Dict[str, Case] = {}
        self._alert_counter = 0
        self._case_counter = 0

    # ── Alerts ────────────────────────────────────────────────────────

    def create_alert(self, account_ids: List[str], detection_type: str,
                     score: float, severity: str) -> Alert:
        self._alert_counter += 1
        alert_id = f"ALT-{datetime.now().strftime('%Y%m%d')}-{self._alert_counter:04d}"
        alert = Alert(
            alert_id=alert_id,
            account_ids=account_ids,
            detection_type=detection_type,
            score=score,
            severity=severity,
        )
        self._alerts[alert_id] = alert
        logger.info("Alert created: %s (%s, score=%.2f)", alert_id, detection_type, score)
        return alert

    def get_alert(self, alert_id: str) -> Optional[Alert]:
        return self._alerts.get(alert_id)

    def list_alerts(self, status: Optional[str] = None) -> List[Alert]:
        alerts = list(self._alerts.values())
        if status:
            alerts = [a for a in alerts if a.status == status]
        return sorted(alerts, key=lambda a: a.score, reverse=True)

    # ── Cases ─────────────────────────────────────────────────────────

    def create_case(self, account_ids: List[str], typology: str,
                    priority: str = Priority.P3.value,
                    alert_ids: Optional[List[str]] = None,
                    notes: str = "") -> Case:
        self._case_counter += 1
        case_id = f"CASE-{datetime.now().strftime('%Y%m%d')}-{self._case_counter:04d}"
        case = Case(
            case_id=case_id,
            alert_ids=alert_ids or [],
            account_ids=account_ids,
            priority=priority,
            typology=typology,
            notes=notes,
        )
        self._cases[case_id] = case

        # Link alerts to case
        for aid in case.alert_ids:
            if aid in self._alerts:
                self._alerts[aid].status = "ASSIGNED"

        logger.info("Case created: %s (typology=%s, priority=%s)", case_id, typology, priority)
        return case

    def update_case_status(self, case_id: str, new_status: str,
                           notes: str = "") -> Optional[Case]:
        case = self._cases.get(case_id)
        if not case:
            return None
        case.status = new_status
        case.updated_at = datetime.utcnow().isoformat()
        if notes:
            case.notes += f"\n[{case.updated_at}] {notes}"
        logger.info("Case %s status → %s", case_id, new_status)
        return case

    def resolve_case(self, case_id: str, resolution: str,
                     is_true_positive: bool) -> Optional[Case]:
        """
        Resolve a case. The resolution feeds back into the labelled dataset
        for model retraining (feedback loop).
        """
        case = self._cases.get(case_id)
        if not case:
            return None
        case.status = CaseStatus.CLOSED_TRUE_POSITIVE.value if is_true_positive else CaseStatus.CLOSED_FALSE_POSITIVE.value
        case.resolution = resolution
        case.updated_at = datetime.utcnow().isoformat()
        logger.info("Case %s resolved: %s (TP=%s)", case_id, resolution, is_true_positive)
        return case

    def get_case(self, case_id: str) -> Optional[Case]:
        return self._cases.get(case_id)

    def list_cases(self, status: Optional[str] = None) -> List[Case]:
        cases = list(self._cases.values())
        if status:
            cases = [c for c in cases if c.status == status]
        return sorted(cases, key=lambda c: c.created_at, reverse=True)

    def get_stats(self) -> Dict[str, int]:
        return {
            "total_alerts": len(self._alerts),
            "total_cases": len(self._cases),
            "open_cases": sum(1 for c in self._cases.values() if c.status == CaseStatus.OPEN.value),
            "investigating": sum(1 for c in self._cases.values() if c.status == CaseStatus.INVESTIGATING.value),
            "escalated": sum(1 for c in self._cases.values() if c.status == CaseStatus.ESCALATED.value),
            "closed_tp": sum(1 for c in self._cases.values() if c.status == CaseStatus.CLOSED_TRUE_POSITIVE.value),
            "closed_fp": sum(1 for c in self._cases.values() if c.status == CaseStatus.CLOSED_FALSE_POSITIVE.value),
        }

    def auto_create_alerts_from_detections(self, detection_results: Dict) -> List[Alert]:
        """Automatically create alerts from detection results."""
        alerts = []
        for det_type, results in detection_results.items():
            for det in results:
                alert = self.create_alert(
                    account_ids=det.account_ids,
                    detection_type=det.detection_type,
                    score=det.score,
                    severity=det.severity,
                )
                alerts.append(alert)
        return alerts
