# TraceX AML Pipeline — Incident Playbook & Operations Guide

## Model Artifact Format

Each trained model produces the following metadata (stored in memory / exportable):

| Field | Type | Description |
|-------|------|-------------|
| `auc_roc` | float | Area under ROC curve on test set |
| `precision` | float | Precision at optimal threshold |
| `recall` | float | Recall at optimal threshold |
| `f1` | float | F1 score at optimal threshold |
| `optimal_threshold` | float | PR-curve optimised classification threshold |
| `confusion_matrix` | [[TN,FP],[FN,TP]] | Confusion matrix on test |
| `train_size` | int | Number of training samples |
| `val_size` | int | Validation set size |
| `test_size` | int | Test set size |
| `positive_rate` | float | Positive rate in training data |
| `training_time_sec` | float | Training wall-clock time |
| `device` | str | GPU/CPU used |
| `best_iteration` | int | Early stopping best iteration |

### XGBoost Parameters (Current Production)
```json
{
  "n_estimators": 500,
  "max_depth": 6,
  "learning_rate": 0.03,
  "min_child_weight": 5,
  "subsample": 0.8,
  "colsample_bytree": 0.7,
  "gamma": 2.0,
  "reg_alpha": 0.5,
  "reg_lambda": 2.0,
  "scale_pos_weight": 15.0,
  "early_stopping_rounds": 50,
  "label_mode": "source_only"
}
```

---

## Incident Response Playbook

### P1: Model Metric Regression (AUC drop > 5%)

**Detection:** `GET /api/metrics` → check `alerts` for `METRIC_REGRESSION_*`

**Response Steps:**
1. **Verify**: Check `/api/model-metrics` — confirm AUC/PR-AUC values
2. **Isolate**: Is it a data issue or model issue?
   - Run `python tests/test_smoke_pipeline.py --max-rows 100000`
   - Check data contracts: look for `data_schema_violations` in metrics
3. **Rollback**: If regression confirmed:
   - Stop current API server
   - Revert `infrastructure/config.py` to last known good commit
   - Restart: `uvicorn api.server:app --port 8000`
4. **Investigate**: Review recent changes to:
   - `services/detection/service.py` (label logic)
   - `services/detection/ensemble.py` (training params)
   - Input data (schema drift, new columns, null spikes)
5. **Resolve**: Fix root cause, add regression test, redeploy

---

### P1: Positive Rate Drift (>50% deviation from baseline)

**Detection:** `GET /api/metrics` → `positive_rate_drift_pct` > 50

**Response Steps:**
1. **Verify**: Compare live positive rate vs baseline (0.65% for source-only labels)
2. **Check data**: Has the input data distribution changed?
   - New laundering patterns?
   - Schema change in `is_laundering` column?
3. **Check threshold**: Was `optimal_threshold` accidentally changed?
4. **Temporary mitigation**: If false positive flood:
   - Increase threshold temporarily in `infrastructure/config.py`
   - Restart API
5. **Root cause**: Retrain on updated data if distribution genuinely shifted

---

### P2: Data Contract Violation

**Detection:** `GET /api/metrics` → `data_schema_violations` > 0

**Response Steps:**
1. **Identify**: Which contract failed? Check API logs for `DATA CONTRACT [ERROR]`
2. **Common causes**:
   - Schema change in source data (new CSV format)
   - Encoding issues (timestamps, currency symbols)
   - Upstream data pipeline producing nulls
3. **Fix**: Adjust ingestion service or reject the bad batch
4. **Verify**: Re-run `DataContractValidator.validate_transactions()` on fixed data

---

### P3: Training Failure

**Detection:** Pipeline logs show `DETECTION PIPELINE FAILED` or training metrics are all zeros

**Response Steps:**
1. **Check GPU**: `nvidia-smi` — is GPU available?
2. **Check memory**: Large dataset may OOM
3. **Check labels**: Are there enough positives? (min 5 for smoke, 50+ for production)
4. **Fallback**: Set `use_gpu = False` in ensemble.py and retry on CPU

---

## Safe Deployment Procedure

### Pre-deployment Checklist
- [ ] All unit tests pass: `pytest tests/test_reliability.py -v`
- [ ] Smoke test passes: `python tests/test_smoke_pipeline.py`
- [ ] No P1 alerts in `/api/metrics`
- [ ] `CHANGELOGS.md` updated
- [ ] Config changes documented in PR

### Deployment Steps
1. Stop current server gracefully
2. Pull latest code
3. Run tests: `pytest tests/ -v`
4. Start server: `uvicorn api.server:app --host 0.0.0.0 --port 8000`
5. Verify health: `curl http://localhost:8000/api/health`
6. Initialize pipeline: `curl -X POST http://localhost:8000/api/init -H "Content-Type: application/json" -d '{"source":"ibm_aml"}'`
7. Check metrics: `curl http://localhost:8000/api/metrics`
8. Verify frontend loads: `http://localhost:3000`

### Rollback Steps
1. Stop server
2. `git checkout <last-known-good-commit>`
3. Restart server
4. Re-initialize pipeline
5. Verify metrics are back to baseline

---

## Monitoring Endpoints

| Endpoint | Purpose |
|----------|---------|
| `GET /api/health` | System liveness + initialization state |
| `GET /api/metrics` | Full metrics, baseline comparison, alerts |
| `GET /api/model-metrics` | XGBoost + IsolationForest performance |
| `POST /api/metrics/acknowledge/{idx}` | Acknowledge an alert |

---

## Data Pipeline Architecture

```
CSV/Upload → IngestionService → DataContractValidator → GraphService.build()
                                                              ↓
                                                    DetectionService.run_full_pipeline()
                                                              ↓
                                     ┌────────────────────────┼────────────────────────┐
                                     ↓                        ↓                        ↓
                              FeatureExtractor         IsolationForest           5 Pattern Detectors
                                     ↓                        ↓                        ↓
                              FraudClassifier          AnomalyScores            DetectionResults
                              (XGBoost+GPU)                                           ↓
                                     ↓                                         RoleClassifier
                              FraudPredictions                                        ↓
                                     └────────────────────────┼────────────────────────┘
                                                              ↓
                                                      EnsembleScorer → RiskScores
                                                              ↓
                                                    MonitoringCollector → Alerts
                                                              ↓
                                                         API Layer → Frontend
```
