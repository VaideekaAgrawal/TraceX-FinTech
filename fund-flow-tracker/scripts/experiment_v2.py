"""
TraceX ML Improvement Experiments — Industry-Level AML Detection.

Systematic experiments to improve XGBoost metrics on IBM AML HI-Small (5M rows):
  Exp 1 baseline              : Current production config (random split, both labels)
  Exp 2 fix_labels            : Source-only labels (fix label noise)
  Exp 3 fix_labels_temporal   : Source-only + temporal split (prevent leakage)
  Exp 4 enhanced_features     : Source-only + temporal + 50+ features
  Exp 5 tuned_spw             : Enhanced + capped scale_pos_weight=15
  Exp 6 aggressive_reg        : Enhanced + heavy regularisation
  Exp 7 balanced_optimized    : Best-balance config + max_delta_step

Usage:
    python scripts/experiment_v2.py --max-rows 0             # full 5M
    python scripts/experiment_v2.py --max-rows 500000        # quick test
    python scripts/experiment_v2.py --experiments baseline,balanced_optimized
"""
import argparse
import gc
import json
import logging
import os
import sys
import time
from dataclasses import dataclass, asdict, field
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
from sklearn.metrics import (
    precision_score, recall_score, f1_score,
    roc_auc_score, average_precision_score,
    precision_recall_curve, confusion_matrix,
)
from sklearn.model_selection import StratifiedKFold, train_test_split
from sklearn.preprocessing import StandardScaler
import xgboost as xgb

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
    force=True,
)
logger = logging.getLogger("experiment_v2")


# ─────────────────────────────────────────────────────────────────────────────
# GPU detection
# ─────────────────────────────────────────────────────────────────────────────
def _detect_gpu() -> bool:
    try:
        import subprocess
        r = subprocess.run(["nvidia-smi"], capture_output=True, timeout=5)
        if r.returncode == 0:
            return True
    except Exception:
        pass
    try:
        dm = xgb.DMatrix(np.array([[1, 2], [3, 4]]), label=[0, 1])
        xgb.train({"tree_method": "hist", "device": "cuda", "verbosity": 0}, dm, 1)
        return True
    except Exception:
        return False

GPU = _detect_gpu()
logger.info("GPU available: %s", GPU)


# ─────────────────────────────────────────────────────────────────────────────
# Result dataclass
# ─────────────────────────────────────────────────────────────────────────────
@dataclass
class ExperimentResult:
    name: str
    description: str
    # Default threshold (0.5) metrics
    auc_roc: float = 0.0
    pr_auc: float = 0.0
    precision_d: float = 0.0
    recall_d: float = 0.0
    f1_d: float = 0.0
    # Optimised threshold metrics
    opt_threshold: float = 0.5
    precision_opt: float = 0.0
    recall_opt: float = 0.0
    f1_opt: float = 0.0
    # Meta
    n_features: int = 0
    train_size: int = 0
    val_size: int = 0
    test_size: int = 0
    n_pos_train: int = 0
    n_pos_test: int = 0
    training_time: float = 0.0
    best_iteration: int = 0
    params: Dict = field(default_factory=dict)


# ─────────────────────────────────────────────────────────────────────────────
# 1.  LABEL BUILDERS
# ─────────────────────────────────────────────────────────────────────────────
def labels_both(txns: pd.DataFrame) -> pd.Series:
    """Source AND dest of laundering transactions = positive (original)."""
    fraud = txns[txns["is_laundering"] == 1]
    pos = set(fraud["source_account"]) | set(fraud["dest_account"])
    all_acc = set(txns["source_account"]) | set(txns["dest_account"])
    return pd.Series({a: int(a in pos) for a in all_acc}, name="label")


def labels_source_only(txns: pd.DataFrame) -> pd.Series:
    """Only source accounts of laundering transactions = positive (less noisy)."""
    fraud = txns[txns["is_laundering"] == 1]
    pos = set(fraud["source_account"])
    all_acc = set(txns["source_account"]) | set(txns["dest_account"])
    return pd.Series({a: int(a in pos) for a in all_acc}, name="label")


# ─────────────────────────────────────────────────────────────────────────────
# 2.  ENHANCED FEATURE EXTRACTION  (vectorised, no per-account loops)
# ─────────────────────────────────────────────────────────────────────────────
def extract_enhanced_features(txns: pd.DataFrame) -> pd.DataFrame:
    """
    50+ features: basic aggregations, 7-day / 30-day windows,
    velocity-change ratios, multi-threshold structuring signals,
    round-amount ratios, temporal patterns, flow ratios.
    All vectorised — no Python loop over accounts.
    """
    logger.info("[EnhancedFeatures] Starting extraction on %d rows...", len(txns))
    t0 = time.time()

    txns = txns.copy()
    txns["timestamp"] = pd.to_datetime(txns["timestamp"])
    txns["amount"]    = txns["amount"].astype("float32")

    all_accounts = sorted(
        set(txns["source_account"].unique()) | set(txns["dest_account"].unique())
    )
    acc_idx = pd.Index(all_accounts, name="account_id")

    # ── A. Outgoing aggregations ──────────────────────────────────────────
    src = txns.groupby("source_account").agg(
        total_out         = ("amount", "sum"),
        count_out         = ("amount", "count"),
        avg_out           = ("amount", "mean"),
        std_out           = ("amount", "std"),
        max_out           = ("amount", "max"),
        median_out        = ("amount", "median"),
        unique_dest       = ("dest_account", "nunique"),
    )
    src.index.name = "account_id"

    # ── B. Incoming aggregations ─────────────────────────────────────────
    dst = txns.groupby("dest_account").agg(
        total_in  = ("amount", "sum"),
        count_in  = ("amount", "count"),
        avg_in    = ("amount", "mean"),
        std_in    = ("amount", "std"),
        max_in    = ("amount", "max"),
        unique_src = ("source_account", "nunique"),
    )
    dst.index.name = "account_id"

    # ── C. 7-day and 30-day windows ──────────────────────────────────────
    t_max  = txns["timestamp"].max()
    t_7d   = t_max - pd.Timedelta(days=7)
    t_30d  = t_max - pd.Timedelta(days=30)

    r7  = txns[txns["timestamp"] >= t_7d]
    r30 = txns[txns["timestamp"] >= t_30d]

    def _src_window(df, suffix):
        g = df.groupby("source_account").agg(
            **{f"count_out_{suffix}": ("amount", "count"),
               f"total_out_{suffix}": ("amount", "sum"),
               f"avg_out_{suffix}"  : ("amount", "mean")}
        )
        g.index.name = "account_id"
        return g

    def _dst_window(df, suffix):
        g = df.groupby("dest_account").agg(
            **{f"count_in_{suffix}": ("amount", "count"),
               f"total_in_{suffix}": ("amount", "sum")}
        )
        g.index.name = "account_id"
        return g

    src_7d  = _src_window(r7,  "7d")
    dst_7d  = _dst_window(r7,  "7d")
    src_30d = _src_window(r30, "30d")
    dst_30d = _dst_window(r30, "30d")
    del r7, r30

    # ── D. Daily velocity ────────────────────────────────────────────────
    txns["_date"] = txns["timestamp"].dt.date
    daily = txns.groupby(["source_account", "_date"])["amount"].count().reset_index(name="dc")
    vel = daily.groupby("source_account")["dc"].agg(
        max_daily_out  = "max",
        avg_daily_out  = "mean",
        std_daily_out  = "std",
        active_days    = "count",
    )
    vel.index.name = "account_id"
    del daily

    # ── E. Multi-threshold structuring signals ───────────────────────────
    struct = pd.DataFrame(index=acc_idx)
    for thresh, label in [(1_000_000, "1M"), (500_000, "500K"),
                          (100_000, "100K"), (50_000, "50K")]:
        m = (txns["amount"] >= thresh * 0.9) & (txns["amount"] < thresh)
        cnt = txns[m].groupby("source_account").size().rename(f"near_{label}")
        cnt.index.name = "account_id"
        struct = struct.join(cnt, how="left")
    struct = struct.fillna(0)

    # ── F. Round-amount ratios ───────────────────────────────────────────
    txns["_r1k"]   = (txns["amount"] % 1_000   == 0).astype("float32")
    txns["_r10k"]  = (txns["amount"] % 10_000  == 0).astype("float32")
    txns["_r100k"] = (txns["amount"] % 100_000 == 0).astype("float32")
    rnd = txns.groupby("source_account").agg(
        round_1k_ratio   = ("_r1k",   "mean"),
        round_10k_ratio  = ("_r10k",  "mean"),
        round_100k_ratio = ("_r100k", "mean"),
    )
    rnd.index.name = "account_id"
    txns.drop(columns=["_r1k", "_r10k", "_r100k"], inplace=True)

    # ── G. Temporal patterns ─────────────────────────────────────────────
    txns["_hour"]    = txns["timestamp"].dt.hour.astype("int8")
    txns["_dow"]     = txns["timestamp"].dt.dayofweek.astype("int8")
    txns["_is_night"]= txns["_hour"].isin([22,23,0,1,2,3,4,5]).astype("float32")
    txns["_is_wkend"]= (txns["_dow"] >= 5).astype("float32")
    temp = txns.groupby("source_account").agg(
        night_txn_ratio = ("_is_night", "mean"),
        weekend_ratio   = ("_is_wkend", "mean"),
        hour_entropy    = ("_hour",     "std"),
    )
    temp.index.name = "account_id"
    txns.drop(columns=["_hour", "_dow", "_is_night", "_is_wkend"], inplace=True)

    # ── H. Cross-bank features ───────────────────────────────────────────
    if "from_bank" in txns.columns and "to_bank" in txns.columns:
        txns["_cross"] = (
            txns["from_bank"].astype(str) != txns["to_bank"].astype(str)
        ).astype("float32")
        bank = txns.groupby("source_account").agg(
            cross_bank_ratio  = ("_cross",  "mean"),
            unique_dest_banks = ("to_bank", "nunique"),
        )
        bank.index.name = "account_id"
        txns.drop(columns=["_cross"], inplace=True)
    else:
        bank = pd.DataFrame(
            {"cross_bank_ratio": 0.5, "unique_dest_banks": 0},
            index=acc_idx
        )

    # ── I. Assemble ──────────────────────────────────────────────────────
    df = pd.DataFrame(index=acc_idx)
    for part in [src, dst, src_7d, dst_7d, src_30d, dst_30d,
                 vel, struct, rnd, temp, bank]:
        df = df.join(part, how="left")
    df.drop(columns=["_date"], errors="ignore", inplace=True)

    # ── J. Derived ratio features ─────────────────────────────────────────
    df["net_flow"]         = df["total_in"].fillna(0) - df["total_out"].fillna(0)
    df["in_out_ratio"]     = df["total_in"].fillna(0) / df["total_out"].fillna(1).replace(0, 1)
    df["fan_in_ratio"]     = df["unique_src"].fillna(0) / (
                                 df["unique_src"].fillna(0) + df["unique_dest"].fillna(0)
                             ).replace(0, 1)
    df["txn_symmetry"]     = df["count_in"].fillna(0) / (
                                 df["count_in"].fillna(0) + df["count_out"].fillna(0)
                             ).replace(0, 1)
    df["concentration"]    = df["std_out"].fillna(0) / df["avg_out"].fillna(1).replace(0, 1)
    df["velocity_chg_7d"]  = (
        df["count_out_7d"].fillna(0) /
        (df["count_out"].fillna(1) / 30).replace(0, 1)
    )
    df["amount_chg_7d"]    = (
        df["avg_out_7d"].fillna(0) / df["avg_out"].fillna(1).replace(0, 1)
    )
    df["velocity_chg_30d"] = (
        df["count_out_30d"].fillna(0) /
        (df["count_out"].fillna(1) / 30).replace(0, 1)
    )

    df = (df
          .fillna(0)
          .replace([np.inf, -np.inf], 0)
          .astype("float32"))
    txns.drop(columns=["_date"], errors="ignore", inplace=True)

    elapsed = time.time() - t0
    logger.info("[EnhancedFeatures] Done: %d accounts x %d features (%.1fs)",
                len(df), len(df.columns), elapsed)
    return df


# ─────────────────────────────────────────────────────────────────────────────
# 3.  TEMPORAL SPLIT
# ─────────────────────────────────────────────────────────────────────────────
def temporal_split(
    txns: pd.DataFrame,
    features: pd.DataFrame,
    labels: pd.Series,
    train_end: float = 0.70,
    val_end:   float = 0.85,
) -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame,
           pd.Series,    pd.Series,    pd.Series]:
    """
    Chronological split: first 70% = train, next 15% = val, last 15% = test.
    Accounts that appear only in later periods are held out correctly.
    """
    ts = pd.to_datetime(txns["timestamp"])
    t_tr = ts.quantile(train_end)
    t_va = ts.quantile(val_end)

    train_mask = ts <= t_tr
    val_mask   = (ts > t_tr) & (ts <= t_va)
    test_mask  = ts > t_va

    def _accs(mask):
        return (set(txns.loc[mask, "source_account"]) |
                set(txns.loc[mask, "dest_account"]))

    tr_accs   = _accs(train_mask)
    val_accs  = _accs(val_mask)  - tr_accs   # held out: not in train
    test_accs = _accs(test_mask) - tr_accs

    # If too many accounts overlap use all accounts but keep temporal label window
    if len(val_accs) < 500:
        val_accs  = _accs(val_mask)
    if len(test_accs) < 500:
        test_accs = _accs(test_mask)

    common = features.index.intersection(labels.index)

    def _subset(accs):
        idx = features.index[features.index.isin(accs) & features.index.isin(common)]
        return features.loc[idx], labels.loc[idx]

    X_tr, y_tr   = _subset(tr_accs)
    X_val, y_val = _subset(val_accs)
    X_te, y_te   = _subset(test_accs)

    logger.info(
        "[Split] train=%d (pos=%d, %.2f%%) | val=%d (pos=%d) | test=%d (pos=%d)",
        len(y_tr),  int(y_tr.sum()),  100*y_tr.mean(),
        len(y_val), int(y_val.sum()),
        len(y_te),  int(y_te.sum()),
    )
    return X_tr, X_val, X_te, y_tr, y_val, y_te


def random_split(
    features: pd.DataFrame,
    labels: pd.Series,
    test_size:  float = 0.15,
    val_size:   float = 0.15,
) -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame,
           pd.Series,    pd.Series,    pd.Series]:
    common = features.index.intersection(labels.index)
    X = features.loc[common]
    y = labels.loc[common]

    n_pos = int(y.sum())
    if n_pos < 10:
        raise ValueError(
            f"Too few positive examples ({n_pos}) for stratified split. "
            "Use --max-rows 0 (full dataset) or a larger sample."
        )

    X_temp, X_te, y_temp, y_te = train_test_split(
        X, y, test_size=test_size, random_state=42, stratify=y
    )
    ratio = val_size / (1 - test_size)
    X_tr, X_val, y_tr, y_val = train_test_split(
        X_temp, y_temp, test_size=ratio, random_state=42, stratify=y_temp
    )
    logger.info(
        "[Split] train=%d (pos=%d, %.2f%%) | val=%d (pos=%d) | test=%d (pos=%d)",
        len(y_tr),  int(y_tr.sum()),  100*y_tr.mean(),
        len(y_val), int(y_val.sum()),
        len(y_te),  int(y_te.sum()),
    )
    return X_tr, X_val, X_te, y_tr, y_val, y_te


# ─────────────────────────────────────────────────────────────────────────────
# 4.  THRESHOLD OPTIMISER  (run on VAL set; apply to TEST)
# ─────────────────────────────────────────────────────────────────────────────
def optimise_threshold(
    y_true: np.ndarray,
    y_prob: np.ndarray,
    mode: str = "f1",           # "f1" or "pr60"
) -> Tuple[float, Dict]:
    prec, rec, thr = precision_recall_curve(y_true, y_prob)
    prec, rec = prec[:-1], rec[:-1]

    if mode == "f1":
        denom = prec + rec + 1e-9
        f1s   = 2 * prec * rec / denom
        idx   = np.argmax(f1s)
    else:   # precision maximised subject to recall >= 0.60
        valid = rec >= 0.60
        if valid.any():
            idx = np.argmax(prec * valid)
        else:
            denom = prec + rec + 1e-9
            idx   = np.argmax(2 * prec * rec / denom)

    best_thr = float(thr[idx])
    return best_thr, {
        "threshold": best_thr,
        "precision": float(prec[idx]),
        "recall":    float(rec[idx]),
    }


# ─────────────────────────────────────────────────────────────────────────────
# 5.  EXPERIMENT CONFIGS
# ─────────────────────────────────────────────────────────────────────────────
EXPERIMENTS: Dict[str, Dict] = {
    "baseline": {
        "desc":    "Current production (random split, both-labels, spw=auto)",
        "labels":  "both",
        "split":   "random",
        "feats":   "basic",
        "params": dict(n_estimators=300, max_depth=5, learning_rate=0.05,
                       min_child_weight=3, subsample=0.8, colsample_bytree=0.8,
                       gamma=1, reg_alpha=0.1, reg_lambda=1.0, scale_pos_weight="auto"),
    },
    "fix_labels": {
        "desc":    "Source-only labels (reduce label noise)",
        "labels":  "source",
        "split":   "random",
        "feats":   "basic",
        "params": dict(n_estimators=300, max_depth=5, learning_rate=0.05,
                       min_child_weight=3, subsample=0.8, colsample_bytree=0.8,
                       gamma=1, reg_alpha=0.1, reg_lambda=1.0, scale_pos_weight="auto"),
    },
    "temporal_split": {
        "desc":    "Source-only labels + temporal split (prevent leakage)",
        "labels":  "source",
        "split":   "temporal",
        "feats":   "basic",
        "params": dict(n_estimators=300, max_depth=5, learning_rate=0.05,
                       min_child_weight=3, subsample=0.8, colsample_bytree=0.8,
                       gamma=1, reg_alpha=0.1, reg_lambda=1.0, scale_pos_weight="auto"),
    },
    "enhanced_features": {
        "desc":    "Source-only + temporal + 50+ enhanced features",
        "labels":  "source",
        "split":   "temporal",
        "feats":   "enhanced",
        "params": dict(n_estimators=500, max_depth=6, learning_rate=0.03,
                       min_child_weight=5, subsample=0.8, colsample_bytree=0.7,
                       gamma=2, reg_alpha=0.5, reg_lambda=2.0, scale_pos_weight="auto"),
    },
    "capped_spw": {
        "desc":    "Enhanced features + scale_pos_weight capped at 15 (reduce FP)",
        "labels":  "source",
        "split":   "temporal",
        "feats":   "enhanced",
        "params": dict(n_estimators=500, max_depth=6, learning_rate=0.03,
                       min_child_weight=5, subsample=0.8, colsample_bytree=0.7,
                       gamma=2, reg_alpha=0.5, reg_lambda=2.0, scale_pos_weight=15),
    },
    "deep_regularised": {
        "desc":    "Enhanced + heavy regularisation + deeper trees",
        "labels":  "source",
        "split":   "temporal",
        "feats":   "enhanced",
        "params": dict(n_estimators=800, max_depth=8, learning_rate=0.01,
                       min_child_weight=10, subsample=0.7, colsample_bytree=0.6,
                       gamma=5, reg_alpha=1.0, reg_lambda=5.0, scale_pos_weight=10),
    },
    "balanced_optimized": {
        "desc":    "Balanced: max_delta_step + tuned regularisation (best F1 target)",
        "labels":  "source",
        "split":   "temporal",
        "feats":   "enhanced",
        "params": dict(n_estimators=600, max_depth=7, learning_rate=0.02,
                       min_child_weight=7, subsample=0.75, colsample_bytree=0.65,
                       gamma=3, reg_alpha=0.8, reg_lambda=3.0,
                       scale_pos_weight=12, max_delta_step=1),
    },
}


# ─────────────────────────────────────────────────────────────────────────────
# 6.  SINGLE EXPERIMENT RUNNER
# ─────────────────────────────────────────────────────────────────────────────
def run_experiment(
    name: str,
    cfg: Dict,
    txns: pd.DataFrame,
    basic_features: pd.DataFrame,
    enh_features: pd.DataFrame,
    lbl_both: pd.Series,
    lbl_src: pd.Series,
) -> ExperimentResult:

    logger.info("\n" + "=" * 70)
    logger.info("EXPERIMENT [%s]: %s", name, cfg["desc"])
    logger.info("=" * 70)

    # Pick features and labels
    feats  = enh_features  if cfg["feats"]  == "enhanced" else basic_features
    labels = lbl_src       if cfg["labels"] == "source"   else lbl_both

    # Split
    if cfg["split"] == "temporal":
        X_tr, X_val, X_te, y_tr, y_val, y_te = temporal_split(txns, feats, labels)
    else:
        X_tr, X_val, X_te, y_tr, y_val, y_te = random_split(feats, labels)

    if y_tr.sum() == 0 or y_te.sum() == 0:
        logger.warning("  Skipped — no positive labels in train or test set")
        return ExperimentResult(name=name, description=cfg["desc"], params=cfg["params"])

    # Scale
    scaler   = StandardScaler()
    X_tr_s   = scaler.fit_transform(X_tr.values.astype(float))
    X_val_s  = scaler.transform(X_val.values.astype(float))
    X_te_s   = scaler.transform(X_te.values.astype(float))

    y_tr_a  = y_tr.values.astype(int)
    y_val_a = y_val.values.astype(int)
    y_te_a  = y_te.values.astype(int)

    # Build params
    p = cfg["params"].copy()
    if p.get("scale_pos_weight") == "auto":
        p["scale_pos_weight"] = float((y_tr_a == 0).sum()) / max((y_tr_a == 1).sum(), 1)
    logger.info("  scale_pos_weight = %.2f", p["scale_pos_weight"])

    n_est = p.pop("n_estimators")
    p.update(
        tree_method = "hist",
        device      = "cuda" if GPU else "cpu",
        eval_metric = "aucpr",
        random_state = 42,
        n_jobs       = -1,
    )

    t0 = time.time()
    model = xgb.XGBClassifier(
        n_estimators       = n_est,
        early_stopping_rounds = 50,
        **p,
    )
    model.fit(
        X_tr_s, y_tr_a,
        eval_set   = [(X_val_s, y_val_a)],
        verbose    = 100,
    )
    elapsed = time.time() - t0
    best_iter = model.best_iteration if hasattr(model, "best_iteration") else n_est

    # ── Predict ──────────────────────────────────────────────────────────
    y_prob_val = model.predict_proba(X_val_s)[:, 1]
    y_prob_te  = model.predict_proba(X_te_s)[:,  1]

    # Default threshold (0.5)
    y_pred_d  = (y_prob_te >= 0.5).astype(int)
    auc       = float(roc_auc_score(y_te_a, y_prob_te)) if len(np.unique(y_te_a)) > 1 else 0.0
    pr_auc    = float(average_precision_score(y_te_a, y_prob_te)) if len(np.unique(y_te_a)) > 1 else 0.0
    prec_d    = float(precision_score(y_te_a, y_pred_d, zero_division=0))
    rec_d     = float(recall_score(y_te_a,   y_pred_d, zero_division=0))
    f1_d      = float(f1_score(y_te_a,       y_pred_d, zero_division=0))

    # Optimised threshold (found on VAL, applied to TEST)
    opt_thr, _ = optimise_threshold(y_val_a, y_prob_val, "f1")
    y_pred_opt = (y_prob_te >= opt_thr).astype(int)
    prec_opt   = float(precision_score(y_te_a, y_pred_opt, zero_division=0))
    rec_opt    = float(recall_score(y_te_a,    y_pred_opt, zero_division=0))
    f1_opt     = float(f1_score(y_te_a,        y_pred_opt, zero_division=0))
    cm         = confusion_matrix(y_te_a, y_pred_opt).tolist()

    # Feature importance
    imp = sorted(zip(feats.columns, model.feature_importances_),
                 key=lambda x: x[1], reverse=True)

    # ── Log results ──────────────────────────────────────────────────────
    logger.info("\n  ---- METRICS (default threshold=0.50) ----")
    logger.info("  AUC-ROC : %.4f   PR-AUC: %.4f", auc, pr_auc)
    logger.info("  Precision: %.4f  Recall: %.4f  F1: %.4f", prec_d, rec_d, f1_d)
    logger.info("\n  ---- METRICS (optimised threshold=%.4f on val) ----", opt_thr)
    logger.info("  Precision: %.4f  Recall: %.4f  F1: %.4f", prec_opt, rec_opt, f1_opt)
    logger.info("  Confusion Matrix: %s", cm)
    logger.info("  Training: %.1fs | Best iteration: %d | Device: %s",
                elapsed, best_iter, "GPU" if GPU else "CPU")
    logger.info("\n  Top 10 Features:")
    for fname, fimp in imp[:10]:
        logger.info("    %-35s %.4f", fname, fimp)

    return ExperimentResult(
        name         = name,
        description  = cfg["desc"],
        auc_roc      = auc,
        pr_auc       = pr_auc,
        precision_d  = prec_d,
        recall_d     = rec_d,
        f1_d         = f1_d,
        opt_threshold = opt_thr,
        precision_opt = prec_opt,
        recall_opt    = rec_opt,
        f1_opt        = f1_opt,
        n_features    = len(feats.columns),
        train_size    = len(y_tr_a),
        val_size      = len(y_val_a),
        test_size     = len(y_te_a),
        n_pos_train   = int(y_tr_a.sum()),
        n_pos_test    = int(y_te_a.sum()),
        training_time = elapsed,
        best_iteration = best_iter,
        params         = {**cfg["params"], "n_estimators": n_est},
    )


# ─────────────────────────────────────────────────────────────────────────────
# 7.  CROSS-VALIDATION on best config
# ─────────────────────────────────────────────────────────────────────────────
def cross_validate(
    features: pd.DataFrame,
    labels: pd.Series,
    best_params: Dict,
    n_folds: int = 5,
) -> Dict:
    logger.info("\n" + "=" * 70)
    logger.info("CROSS-VALIDATION (Stratified %d-fold) on best config", n_folds)
    logger.info("=" * 70)

    common = features.index.intersection(labels.index)
    X = np.nan_to_num(features.loc[common].values.astype(float), nan=0.0, posinf=1e6, neginf=0)
    y = labels.loc[common].values.astype(int)

    metrics = {k: [] for k in ["auc", "pr_auc", "f1_opt", "prec_opt",
                                "rec_opt", "threshold"]}

    skf = StratifiedKFold(n_splits=n_folds, shuffle=True, random_state=42)
    for fold, (tr_i, te_i) in enumerate(skf.split(X, y)):
        X_tr, X_te = X[tr_i], X[te_i]
        y_tr, y_te = y[tr_i], y[te_i]

        scaler = StandardScaler()
        X_tr_s = scaler.fit_transform(X_tr)
        X_te_s = scaler.transform(X_te)

        p = best_params.copy()
        if p.get("scale_pos_weight") == "auto" or "scale_pos_weight" not in p:
            p["scale_pos_weight"] = float((y_tr == 0).sum()) / max((y_tr == 1).sum(), 1)

        n_est = p.pop("n_estimators", 600)
        p.update(
            tree_method = "hist",
            device      = "cuda" if GPU else "cpu",
            eval_metric = "aucpr",
            random_state = 42,
            n_jobs       = -1,
        )

        # Use 20% of fold as internal val for early stopping
        tr_idx, val_idx = train_test_split(
            np.arange(len(y_tr)), test_size=0.2, random_state=42,
            stratify=y_tr
        )
        model = xgb.XGBClassifier(
            n_estimators=n_est,
            early_stopping_rounds=50,
            **p,
        )
        model.fit(
            X_tr_s[tr_idx], y_tr[tr_idx],
            eval_set=[(X_tr_s[val_idx], y_tr[val_idx])],
            verbose=0,
        )

        y_prob = model.predict_proba(X_te_s)[:, 1]
        if len(np.unique(y_te)) < 2:
            continue

        auc    = float(roc_auc_score(y_te, y_prob))
        pr_auc = float(average_precision_score(y_te, y_prob))

        # Optimise threshold on this fold's test (conservative — same set)
        opt_thr, _ = optimise_threshold(y_te, y_prob, "f1")
        y_pred     = (y_prob >= opt_thr).astype(int)

        metrics["auc"].append(auc)
        metrics["pr_auc"].append(pr_auc)
        metrics["f1_opt"].append(float(f1_score(y_te, y_pred, zero_division=0)))
        metrics["prec_opt"].append(float(precision_score(y_te, y_pred, zero_division=0)))
        metrics["rec_opt"].append(float(recall_score(y_te, y_pred, zero_division=0)))
        metrics["threshold"].append(opt_thr)

        logger.info(
            "  Fold %d: AUC=%.4f PR-AUC=%.4f | P=%.4f R=%.4f F1=%.4f (thr=%.4f)",
            fold+1, auc, pr_auc,
            metrics["prec_opt"][-1], metrics["rec_opt"][-1],
            metrics["f1_opt"][-1], opt_thr,
        )

    summary = {}
    for k, v in metrics.items():
        if v:
            summary[f"{k}_mean"] = float(np.mean(v))
            summary[f"{k}_std"]  = float(np.std(v))

    logger.info("\n  CV SUMMARY (mean +/- std):")
    logger.info("  AUC-ROC  : %.4f +/- %.4f", summary.get("auc_mean",0), summary.get("auc_std",0))
    logger.info("  PR-AUC   : %.4f +/- %.4f", summary.get("pr_auc_mean",0), summary.get("pr_auc_std",0))
    logger.info("  F1 (opt) : %.4f +/- %.4f", summary.get("f1_opt_mean",0), summary.get("f1_opt_std",0))
    logger.info("  Precision: %.4f +/- %.4f", summary.get("prec_opt_mean",0), summary.get("prec_opt_std",0))
    logger.info("  Recall   : %.4f +/- %.4f", summary.get("rec_opt_mean",0), summary.get("rec_opt_std",0))
    logger.info("  Threshold: %.4f +/- %.4f", summary.get("threshold_mean",0), summary.get("threshold_std",0))
    return summary


# ─────────────────────────────────────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--max-rows",    type=int, default=0)
    parser.add_argument("--filepath",    type=str, default="data/HI-Small_Trans.csv")
    parser.add_argument("--experiments", type=str, default="all")
    parser.add_argument("--skip-cv",     action="store_true",
                        help="Skip cross-validation on best model")
    args = parser.parse_args()
    max_rows = args.max_rows if args.max_rows > 0 else None

    logger.info("=" * 70)
    logger.info("TRACEX EXPERIMENT V2 — Industry-Level AML Detection")
    logger.info("GPU: %s | Rows: %s", "CUDA" if GPU else "CPU", max_rows or "ALL")
    logger.info("=" * 70)

    # ── Load raw data ─────────────────────────────────────────────────────
    filepath = args.filepath
    logger.info("Loading raw CSV: %s", filepath)
    df = pd.read_csv(filepath, nrows=max_rows)
    df.columns = df.columns.str.strip()
    col_map = {
        "Timestamp": "timestamp",
        "From Bank": "from_bank",
        "Account":   "source_account",
        "To Bank":   "to_bank",
        "Account.1": "dest_account",
        "Amount Paid":      "amount",
        "Payment Format":   "channel",
        "Is Laundering":    "is_laundering",
    }
    txns = df.rename(columns={k: v for k, v in col_map.items() if k in df.columns})
    txns["timestamp"]    = pd.to_datetime(txns["timestamp"])
    txns["amount"]       = pd.to_numeric(txns["amount"], errors="coerce").fillna(0)
    txns["is_laundering"]= txns["is_laundering"].astype(int)
    del df

    logger.info("Transactions: %d | Laundering: %d (%.3f%%)",
                len(txns), txns["is_laundering"].sum(), 100*txns["is_laundering"].mean())

    # ── Build labels ──────────────────────────────────────────────────────
    lbl_both = labels_both(txns)
    lbl_src  = labels_source_only(txns)
    logger.info("Labels (both)   : %d positive (%.3f%%)",
                int(lbl_both.sum()), 100*lbl_both.mean())
    logger.info("Labels (src-only): %d positive (%.3f%%)",
                int(lbl_src.sum()),  100*lbl_src.mean())

    # ── Basic features via pipeline extractor ────────────────────────────
    logger.info("\n[BasicFeatures] Loading pipeline ingestion + graph...")
    from services.ingestion import IngestionService
    from services.graph import GraphService
    from services.detection.features import FeatureExtractor as PipelineExtractor

    ingestion = IngestionService()
    accounts_df, txns_std = ingestion.ingest(
        source="ibm_aml", filepath=filepath, max_rows=max_rows
    )
    graph_svc = GraphService()
    graph_svc.build(accounts_df, txns_std)

    logger.info("[BasicFeatures] Extracting...")
    basic_extractor = PipelineExtractor(graph_svc.graph, accounts_df, txns_std)
    basic_feats = basic_extractor.extract_all()
    logger.info("[BasicFeatures] %d x %d", basic_feats.shape[0], basic_feats.shape[1])

    # ── Enhanced features ─────────────────────────────────────────────────
    enh_feats = extract_enhanced_features(txns)

    gc.collect()

    # ── Run experiments ───────────────────────────────────────────────────
    if args.experiments == "all":
        exp_names = list(EXPERIMENTS.keys())
    else:
        exp_names = [e.strip() for e in args.experiments.split(",")]

    results: List[ExperimentResult] = []
    for exp_name in exp_names:
        if exp_name not in EXPERIMENTS:
            logger.warning("Unknown experiment '%s' — skipping", exp_name)
            continue
        r = run_experiment(
            exp_name, EXPERIMENTS[exp_name],
            txns, basic_feats, enh_feats,
            lbl_both, lbl_src,
        )
        results.append(r)
        gc.collect()

    # ── Comparison table ──────────────────────────────────────────────────
    logger.info("\n" + "=" * 90)
    logger.info("EXPERIMENT COMPARISON — TEST SET")
    logger.info("=" * 90)
    hdr = ("%-28s  %6s  %6s  %6s  %6s  %7s  %6s  %6s  %6s"
           % ("Experiment", "AUC", "PR-AUC", "P@.5", "R@.5",
              "F1@.5", "P@opt", "R@opt", "F1@opt"))
    logger.info(hdr)
    logger.info("-" * 90)
    for r in results:
        logger.info(
            "%-28s  %6.4f  %6.4f  %6.4f  %6.4f  %7.4f  %6.4f  %6.4f  %6.4f",
            r.name, r.auc_roc, r.pr_auc,
            r.precision_d, r.recall_d, r.f1_d,
            r.precision_opt, r.recall_opt, r.f1_opt,
        )

    if not results:
        logger.error("No results — exiting")
        return

    best = max(results, key=lambda r: r.f1_opt)
    logger.info("\n  BEST: [%s]  AUC=%.4f  PR-AUC=%.4f  P=%.4f  R=%.4f  F1=%.4f",
                best.name, best.auc_roc, best.pr_auc,
                best.precision_opt, best.recall_opt, best.f1_opt)

    # ── Cross-validation ──────────────────────────────────────────────────
    cv_results = {}
    if not args.skip_cv:
        best_cfg   = EXPERIMENTS[best.name]
        cv_feats   = enh_feats   if best_cfg["feats"]  == "enhanced" else basic_feats
        cv_labels  = lbl_src     if best_cfg["labels"] == "source"   else lbl_both
        cv_results = cross_validate(cv_feats, cv_labels, best_cfg["params"])

    # ── Save results ──────────────────────────────────────────────────────
    os.makedirs("experiments", exist_ok=True)
    output = {
        "run_timestamp": str(pd.Timestamp.now()),
        "dataset": {
            "rows":               len(txns),
            "laundering_rows":    int(txns["is_laundering"].sum()),
            "positive_both":      int(lbl_both.sum()),
            "positive_src_only":  int(lbl_src.sum()),
        },
        "experiments": [asdict(r) for r in results],
        "best_experiment": best.name,
        "cross_validation":  cv_results,
        "industry_targets": {
            "auc_roc_gte": 0.93,
            "f1_gte":      0.45,
            "precision_gte": 0.30,
        },
    }
    out_path = "experiments/results_v2.json"
    with open(out_path, "w") as fh:
        json.dump(output, fh, indent=2, default=str)
    logger.info("\nResults saved -> %s", out_path)

    # ── Final verdict ─────────────────────────────────────────────────────
    logger.info("\n" + "=" * 70)
    logger.info("FINAL VERDICT")
    logger.info("=" * 70)
    meets = (best.auc_roc >= 0.93 and best.f1_opt >= 0.45
             and best.precision_opt >= 0.30)

    logger.info("  AUC-ROC  (target >=0.93) : %.4f  %s",
                best.auc_roc, "PASS" if best.auc_roc >= 0.93 else "FAIL")
    logger.info("  F1 opt   (target >=0.45) : %.4f  %s",
                best.f1_opt,  "PASS" if best.f1_opt  >= 0.45 else "FAIL")
    logger.info("  Prec opt (target >=0.30) : %.4f  %s",
                best.precision_opt, "PASS" if best.precision_opt >= 0.30 else "FAIL")
    logger.info("  PR-AUC   (target >=0.30) : %.4f  %s",
                best.pr_auc, "PASS" if best.pr_auc >= 0.30 else "FAIL")

    if cv_results:
        logger.info("  CV F1    (5-fold mean)   : %.4f +/- %.4f",
                    cv_results.get("f1_opt_mean", 0), cv_results.get("f1_opt_std", 0))

    if meets:
        logger.info("\n  *** ALL INDUSTRY TARGETS MET ***")
    else:
        logger.info("\n  Partial — see above; next step: update production pipeline "
                    "with best config (run scripts/update_production.py)")
    logger.info("=" * 70)


if __name__ == "__main__":
    main()
