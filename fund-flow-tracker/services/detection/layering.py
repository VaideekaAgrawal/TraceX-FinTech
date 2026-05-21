"""
Layering Detector — detects rapid multi-hop fund transfers with amount decay.

Detection method:
- Extract temporal transaction chains from the graph
- Check for consistently decreasing amounts across hops (fees/commissions skimmed)
- Flag chains with high hop count + short time window
"""
import logging
from typing import Any, Dict, List

import pandas as pd

from infrastructure.config import config
from services.common.models import DetectionResult

logger = logging.getLogger(__name__)


class LayeringDetector:
    """Detect layering: A→B→C→D with decreasing amounts in short time."""

    def __init__(self):
        self.cfg = config.detection

    def detect(self, graph_engine, transactions_df: pd.DataFrame) -> List[DetectionResult]:
        chains = graph_engine.get_transaction_chains(
            min_hops=self.cfg.layering_min_hops,
            time_window_minutes=self.cfg.layering_time_window_minutes,
        )

        results = []
        for chain in chains:
            amounts = [step["amount"] for step in chain]
            if len(amounts) < 2:
                continue

            # Consistently decreasing amounts = layering signal
            decreasing = sum(1 for i in range(1, len(amounts)) if amounts[i] < amounts[i - 1])
            decay_ratio = decreasing / (len(amounts) - 1)

            timestamps = [step["timestamp"] for step in chain if step.get("timestamp") is not None]
            time_span = 0.0
            if len(timestamps) >= 2:
                time_span = (max(timestamps) - min(timestamps)).total_seconds() / 60

            total_decay = (amounts[0] - amounts[-1]) / amounts[0] if amounts[0] > 0 else 0

            # Amount preservation check
            preservation = amounts[-1] / amounts[0] if amounts[0] > 0 else 0

            if decay_ratio >= 0.5 and time_span <= self.cfg.layering_time_window_minutes:
                accounts = []
                for step in chain:
                    accounts.append(step["from"])
                accounts.append(chain[-1]["to"])
                accounts = list(dict.fromkeys(accounts))

                score = min(1.0, decay_ratio * 0.4 + min(len(chain) / 10, 0.3) + (1 - preservation) * 0.3)

                severity = "CRITICAL" if len(chain) >= 5 and preservation >= self.cfg.layering_amount_preservation_ratio else \
                           "HIGH" if len(chain) >= 4 else "MEDIUM"

                results.append(DetectionResult(
                    detection_type="layering",
                    account_ids=accounts,
                    score=round(score, 3),
                    severity=severity,
                    details={
                        "chain": chain,
                        "hops": len(chain),
                        "time_span_minutes": round(time_span, 2),
                        "total_amount": sum(amounts),
                        "amount_decay": round(total_decay, 4),
                        "preservation_ratio": round(preservation, 4),
                        "start_amount": amounts[0],
                        "end_amount": amounts[-1],
                    },
                    indicators=[
                        f"{len(chain)}-hop chain in {time_span:.0f} minutes",
                        f"Amount decay: {total_decay:.1%}",
                        f"Preservation ratio: {preservation:.1%}",
                    ],
                ))

        results.sort(key=lambda r: r.score, reverse=True)
        logger.info("Layering: found %d suspicious chains", len(results))
        return results
