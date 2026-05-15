"""
ML Detection Engine for TraceX — Isolation Forest (unsupervised) + XGBoost (supervised).
"""
import numpy as np
import pandas as pd
from typing import Dict, Tuple, List, Optional
from sklearn.ensemble import IsolationForest
from sklearn.preprocessing import StandardScaler
from sklearn.model_selection import train_test_split
from sklearn.metrics import (
    precision_score, recall_score, f1_score, roc_auc_score,
    classification_report, confusion_matrix,
)
import xgboost as xgb


class AnomalyDetector:
    """Unsupervised anomaly detection using Isolation Forest."""

    def __init__(self, contamination: float = 0.05, n_estimators: int = 200,
                 random_state: int = 42):
        self.contamination = contamination
        self.model = IsolationForest(
            contamination=contamination,
            n_estimators=n_estimators,
            random_state=random_state,
            n_jobs=-1,
        )
        self.scaler = StandardScaler()
        self._fitted = False
        self.feature_names: List[str] = []

    def fit_predict(self, features_df: pd.DataFrame) -> pd.DataFrame:
        """
        Fit Isolation Forest and return anomaly scores.
        Returns DataFrame with columns: account_id, anomaly_score, is_anomaly.
        """
        self.feature_names = list(features_df.columns)
        X = features_df.values.astype(float)

        # Handle NaN/Inf
        X = np.nan_to_num(X, nan=0.0, posinf=1e10, neginf=-1e10)

        X_scaled = self.scaler.fit_transform(X)
        self.model.fit(X_scaled)
        self._fitted = True

        # score_samples returns negative scores; more negative = more anomalous
        raw_scores = self.model.score_samples(X_scaled)
        # Normalize to 0-100 (higher = more anomalous)
        min_s, max_s = raw_scores.min(), raw_scores.max()
        if max_s - min_s > 0:
            anomaly_scores = (1 - (raw_scores - min_s) / (max_s - min_s)) * 100
        else:
            anomaly_scores = np.zeros(len(raw_scores))

        predictions = self.model.predict(X_scaled)  # 1 = normal, -1 = anomaly

        result = pd.DataFrame({
            "account_id": features_df.index,
            "anomaly_score": anomaly_scores,
            "is_anomaly": (predictions == -1).astype(int),
        })
        return result

    def score_single(self, features: np.ndarray) -> float:
        """Score a single account."""
        if not self._fitted:
            return 0.0
        X_scaled = self.scaler.transform(features.reshape(1, -1))
        raw = self.model.score_samples(X_scaled)[0]
        return float(raw)


class FraudClassifier:
    """Supervised fraud classification using XGBoost."""

    def __init__(self, random_state: int = 42):
        self.model = None
        self.scaler = StandardScaler()
        self.feature_names: List[str] = []
        self.metrics: Dict = {}
        self.random_state = random_state
        self._fitted = False

    def train(self, features_df: pd.DataFrame, labels: pd.Series,
              test_size: float = 0.2) -> Dict:
        """
        Train XGBoost classifier on labeled data.
        Returns metrics dict.
        """
        self.feature_names = list(features_df.columns)
        X = features_df.values.astype(float)
        y = labels.values.astype(int)

        X = np.nan_to_num(X, nan=0.0, posinf=1e10, neginf=-1e10)

        # Temporal split: use last 20% as test (respects time ordering)
        split_idx = int(len(X) * (1 - test_size))
        X_train, X_test = X[:split_idx], X[split_idx:]
        y_train, y_test = y[:split_idx], y[split_idx:]

        # If temporal split gives bad class distribution, fall back to stratified
        if len(np.unique(y_train)) < 2 or len(np.unique(y_test)) < 2:
            X_train, X_test, y_train, y_test = train_test_split(
                X, y, test_size=test_size, random_state=self.random_state,
                stratify=y if len(np.unique(y)) > 1 else None,
            )

        X_train_scaled = self.scaler.fit_transform(X_train)
        X_test_scaled = self.scaler.transform(X_test)

        # Handle class imbalance
        n_pos = (y_train == 1).sum()
        n_neg = (y_train == 0).sum()
        scale_pos_weight = n_neg / max(n_pos, 1)

        self.model = xgb.XGBClassifier(
            n_estimators=200,
            max_depth=6,
            learning_rate=0.1,
            scale_pos_weight=scale_pos_weight,
            eval_metric="aucpr",
            random_state=self.random_state,
            n_jobs=-1,
        )
        self.model.fit(
            X_train_scaled, y_train,
            eval_set=[(X_test_scaled, y_test)],
            verbose=False,
        )
        self._fitted = True

        # Compute metrics
        y_pred = self.model.predict(X_test_scaled)
        y_prob = self.model.predict_proba(X_test_scaled)[:, 1]

        self.metrics = {
            "precision": float(precision_score(y_test, y_pred, zero_division=0)),
            "recall": float(recall_score(y_test, y_pred, zero_division=0)),
            "f1": float(f1_score(y_test, y_pred, zero_division=0)),
            "auc_roc": float(roc_auc_score(y_test, y_prob)) if len(np.unique(y_test)) > 1 else 0.0,
            "confusion_matrix": confusion_matrix(y_test, y_pred).tolist(),
            "train_size": len(y_train),
            "test_size": len(y_test),
            "positive_rate_train": float(y_train.mean()),
            "positive_rate_test": float(y_test.mean()),
        }
        return self.metrics

    def predict(self, features_df: pd.DataFrame) -> pd.DataFrame:
        """Predict fraud probability for accounts."""
        if not self._fitted or self.model is None:
            return pd.DataFrame({
                "account_id": features_df.index,
                "fraud_prob": 0.0,
                "fraud_pred": 0,
            })

        X = features_df.values.astype(float)
        X = np.nan_to_num(X, nan=0.0, posinf=1e10, neginf=-1e10)
        X_scaled = self.scaler.transform(X)

        probs = self.model.predict_proba(X_scaled)[:, 1]
        preds = self.model.predict(X_scaled)

        return pd.DataFrame({
            "account_id": features_df.index,
            "fraud_prob": probs,
            "fraud_pred": preds,
        })

    def get_feature_importance(self) -> Dict[str, float]:
        """Get feature importance from XGBoost model."""
        if not self._fitted or self.model is None:
            return {}
        importance = self.model.feature_importances_
        return dict(zip(self.feature_names, importance.tolist()))

    def get_model_report(self) -> Dict:
        """Return model performance metrics for display."""
        return self.metrics
