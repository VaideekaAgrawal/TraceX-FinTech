"""
Detection Service — orchestrates all 5 detectors + ML pipeline.

Responsibilities:
- Run all detectors against the current graph
- Manage Isolation Forest + XGBoost pipeline
- Produce ensemble risk scores
- Publish detection results to event bus
- Enforce confidence gate (CP-05)
- Log all progress visibly for training monitoring
"""
import logging
import time
from typing import Any, Dict, List, Optional

import pandas as pd

from infrastructure.config import config
from infrastructure.event_bus import bus, Topics
from infrastructure.health import health
from services.common.models import DetectionResult
from services.detection.features import FeatureExtractor
from services.detection.layering import LayeringDetector
from services.detection.round_trip import RoundTripDetector
from services.detection.structuring import StructuringDetector
from services.detection.dormancy import DormancyDetector
from services.detection.profile import ProfileMismatchDetector
from services.detection.ensemble import (
    AnomalyDetector, FraudClassifier, RoleClassifier, EnsembleScorer,
)

logger = logging.getLogger(__name__)

_SERVICE = "detection"


class DetectionService:
    """Orchestrates all detection and scoring pipelines."""

    def __init__(self):
        self.layering = LayeringDetector()
        self.round_trip = RoundTripDetector()
        self.structuring = StructuringDetector()
        self.dormancy = DormancyDetector()
        self.profile = ProfileMismatchDetector()

        self.anomaly_detector = AnomalyDetector()
        self.fraud_classifier = FraudClassifier()
        self.role_classifier = RoleClassifier()
        self.ensemble = EnsembleScorer()
        self.feature_extractor: Optional[FeatureExtractor] = None

        # Cached results
        self.features_df: Optional[pd.DataFrame] = None
        self.anomaly_results: Optional[pd.DataFrame] = None
        self.fraud_results: Optional[pd.DataFrame] = None
        self.fraud_metrics: Dict = {}
        self.detection_results: Dict[str, List[DetectionResult]] = {}
        self.roles: Dict = {}
        self.risk_scores: Dict[str, float] = {}

        health.register_service(_SERVICE)

    def run_full_pipeline(self, graph_service, accounts_df: pd.DataFrame,
                          transactions_df: pd.DataFrame) -> Dict[str, Any]:
        """
        Run the complete detection pipeline with visible progress:
        1. Feature extraction
        2. Unsupervised anomaly detection (Isolation Forest)
        3. Supervised classification (XGBoost on real labels — GPU CUDA)
        4. Pattern detection (5 detectors)
        5. Role classification
        6. Ensemble scoring
        """
        try:
            pipeline_start = time.time()
            graph_engine = graph_service.graph

            logger.info("=" * 70)
            logger.info("🚀 DETECTION PIPELINE STARTING")
            logger.info("   Accounts: %d | Transactions: %d | GPU: %s",
                        len(accounts_df), len(transactions_df),
                        "CUDA" if self.fraud_classifier.use_gpu else "CPU")
            logger.info("=" * 70)

            # ── 1. Feature extraction ──
            t0 = time.time()
            logger.info("┌─ STEP 1/6: Feature Extraction")
            self.feature_extractor = FeatureExtractor(graph_engine, accounts_df, transactions_df)
            self.features_df = self.feature_extractor.extract_all()
            logger.info("└─ STEP 1/6: ✅ %d accounts × %d features (%.1fs)",
                        len(self.features_df), len(self.features_df.columns), time.time() - t0)

            # Data contract: validate features
            try:
                from services.validation.contracts import DataContractValidator
                from services.monitoring import monitor as _monitor
                validator = DataContractValidator()
                feat_result = validator.validate_features(self.features_df.values, list(self.features_df.columns))
                if not feat_result.passed:
                    logger.warning("DATA CONTRACT: Feature validation issues: %s", feat_result.violations)
                _monitor.record_data_quality(
                    len(feat_result.violations), len(feat_result.warnings), len(self.features_df)
                )
            except Exception as e:
                logger.debug("Data contract check skipped: %s", e)

            # ── 2. Isolation Forest ──
            t0 = time.time()
            logger.info("┌─ STEP 2/6: Isolation Forest (unsupervised)")
            self.anomaly_results = self.anomaly_detector.fit_predict(self.features_df)
            n_anom = int(self.anomaly_results["is_anomaly"].sum())
            logger.info("└─ STEP 2/6: ✅ %d anomalies detected (%.1fs)", n_anom, time.time() - t0)

            # ── 3. XGBoost (train on real labels, NOT circular) ──
            t0 = time.time()
            logger.info("┌─ STEP 3/6: XGBoost Fraud Classifier (supervised, REAL labels)")
            labels = self._build_labels(transactions_df, self.features_df)
            n_pos = int(labels.sum())
            n_neg = len(labels) - n_pos
            logger.info("  ├─ Labels: %d positive (fraud), %d negative (clean)", n_pos, n_neg)

            if n_pos > 0 and n_neg > 0:
                self.fraud_metrics = self.fraud_classifier.train(self.features_df, labels)
                self.fraud_results = self.fraud_classifier.predict(self.features_df)
                logger.info("└─ STEP 3/6: ✅ Training complete (%.1fs)", time.time() - t0)
            else:
                logger.warning("└─ STEP 3/6: ⚠️ Skipped — no valid labels (pos=%d, neg=%d)", n_pos, n_neg)
                self.fraud_metrics = {}
                self.fraud_results = pd.DataFrame({
                    "account_id": self.features_df.index,
                    "fraud_prob": 0.0,
                    "fraud_pred": 0,
                })

            # ── 4. Pattern detection (5 detectors) ──
            t0 = time.time()
            logger.info("┌─ STEP 4/6: Pattern Detection (5 detectors)")

            logger.info("  ├─ Running Layering detector...")
            t1 = time.time()
            layering_results = self.layering.detect(graph_engine, transactions_df)
            logger.info("  ├─ Layering: %d detections (%.1fs)", len(layering_results), time.time() - t1)

            logger.info("  ├─ Running Round-Trip detector...")
            t1 = time.time()
            rt_results = self.round_trip.detect(graph_engine, transactions_df)
            logger.info("  ├─ Round-Trip: %d detections (%.1fs)", len(rt_results), time.time() - t1)

            logger.info("  ├─ Running Structuring detector...")
            t1 = time.time()
            struct_results = self.structuring.detect(graph_engine, transactions_df)
            logger.info("  ├─ Structuring: %d detections (%.1fs)", len(struct_results), time.time() - t1)

            logger.info("  ├─ Running Dormancy detector...")
            t1 = time.time()
            dorm_results = self.dormancy.detect(graph_engine, transactions_df)
            logger.info("  ├─ Dormancy: %d detections (%.1fs)", len(dorm_results), time.time() - t1)

            logger.info("  ├─ Running Profile Mismatch detector...")
            t1 = time.time()
            prof_results = self.profile.detect(graph_engine, transactions_df, accounts_df)
            logger.info("  ├─ Profile Mismatch: %d detections (%.1fs)", len(prof_results), time.time() - t1)

            self.detection_results = {
                "layering": layering_results,
                "round_trip": rt_results,
                "structuring": struct_results,
                "dormancy": dorm_results,
                "profile_mismatch": prof_results,
            }
            total_det = sum(len(v) for v in self.detection_results.values())
            logger.info("└─ STEP 4/6: ✅ Total %d detections across 5 types (%.1fs)",
                        total_det, time.time() - t0)
            health.increment("detections_run")

            # ── 5. Role classification ──
            t0 = time.time()
            logger.info("┌─ STEP 5/6: Role Classification")
            self.roles = self.role_classifier.classify_all(graph_engine)
            role_counts = {}
            for r in self.roles.values():
                role_counts[r["role"]] = role_counts.get(r["role"], 0) + 1
            logger.info("└─ STEP 5/6: ✅ %s (%.1fs)", role_counts, time.time() - t0)

            # ── 6. Ensemble scoring ──
            t0 = time.time()
            logger.info("┌─ STEP 6/6: Ensemble Risk Scoring")
            self.risk_scores = self.ensemble.compute_all(
                self.features_df, self.anomaly_results,
                self.fraud_results, self.detection_results,
                graph_engine,
            )

            # ── CP-05: Confidence gate ──
            low_conf_count = sum(
                1 for score in self.risk_scores.values()
                if 20 < score < 50  # Ambiguous zone
            )
            health.cp05_confidence_gate(low_conf_count, len(self.risk_scores))

            risk_dist = {
                "critical": sum(1 for s in self.risk_scores.values() if s >= 76),
                "high": sum(1 for s in self.risk_scores.values() if 51 <= s < 76),
                "medium": sum(1 for s in self.risk_scores.values() if 26 <= s < 51),
                "low": sum(1 for s in self.risk_scores.values() if s < 26),
            }
            logger.info("└─ STEP 6/6: ✅ Risk distribution: %s (%.1fs)", risk_dist, time.time() - t0)

            health.heartbeat(_SERVICE, "healthy")

            # Publish results
            bus.publish(Topics.DETECTION_RESULT, {
                "total_detections": total_det,
                "risk_scores_count": len(self.risk_scores),
            }, source_service=_SERVICE)

            total_time = time.time() - pipeline_start
            summary = {
                "accounts_analysed": len(self.features_df),
                "features_extracted": len(self.features_df.columns),
                "anomalies_flagged": n_anom,
                "fraud_metrics": self.fraud_metrics,
                "detection_counts": {k: len(v) for k, v in self.detection_results.items()},
                "roles_classified": len(self.roles),
                "risk_distribution": risk_dist,
                "total_pipeline_time_sec": round(total_time, 1),
                "device": "GPU (CUDA)" if self.fraud_classifier.use_gpu else "CPU",
            }

            logger.info("=" * 70)
            logger.info("🏁 DETECTION PIPELINE COMPLETE — %.1fs total", total_time)
            logger.info("   Anomalies: %d | Detections: %d | Avg Risk: %.1f",
                        n_anom, total_det,
                        sum(self.risk_scores.values()) / max(len(self.risk_scores), 1))
            if self.fraud_metrics:
                logger.info("   ML Metrics: F1=%.3f | AUC=%.3f | Precision=%.3f | Recall=%.3f",
                            self.fraud_metrics.get("f1", 0),
                            self.fraud_metrics.get("auc_roc", 0),
                            self.fraud_metrics.get("precision", 0),
                            self.fraud_metrics.get("recall", 0))
            logger.info("=" * 70)
            return summary

        except Exception as exc:
            health.record_error(_SERVICE, str(exc))
            logger.error("❌ DETECTION PIPELINE FAILED: %s", exc, exc_info=True)
            raise

    @staticmethod
    def _build_labels(transactions_df: pd.DataFrame, features_df: pd.DataFrame) -> pd.Series:
        """Build fraud labels from is_laundering column — no circular training."""
        if "is_laundering" not in transactions_df.columns:
            return pd.Series(0, index=features_df.index)

        fraud_txns = transactions_df[transactions_df["is_laundering"] == 1]
        if len(fraud_txns) == 0:
            return pd.Series(0, index=features_df.index)

        fraud_accs = set(fraud_txns["source_account"].unique())
        # Source-only labeling: only flag initiating accounts of laundering transactions.
        # Including destination accounts adds label noise (many are innocent recipients)
        # and was shown to reduce precision from 77.8% to 4.9% — see experiment_v2 results.
        return pd.Series(
            [1 if acc in fraud_accs else 0 for acc in features_df.index],
            index=features_df.index,
        )

    def get_all_patterns(self) -> Dict[str, Any]:
        """Return pattern results in the legacy dict format for backwards compat."""
        result = {}
        for det_type, detections in self.detection_results.items():
            if det_type == "structuring":
                classic = [d.details for d in detections if d.details.get("sub_type") == "classic"]
                split = [d.details for d in detections if d.details.get("sub_type") == "split"]
                result["structuring"] = {"classic": classic, "split": split}
            else:
                result[det_type] = [d.details for d in detections]

        # Add fan_in / fan_out from graph for backwards compat
        result.setdefault("fan_in", [])
        result.setdefault("fan_out", [])
        result.setdefault("layering", [])
        result.setdefault("round_tripping", result.get("round_trip", []))
        result.setdefault("dormant_activation", result.get("dormancy", []))
        return result

    def get_detection_summary(self) -> Dict[str, int]:
        return {k: len(v) for k, v in self.detection_results.items()}
