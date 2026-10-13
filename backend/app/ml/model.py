"""Isolation Forest anomaly detector with a rule-based fallback."""
from __future__ import annotations

import json
import logging
import threading
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import joblib
import numpy as np
from sklearn.ensemble import IsolationForest
from sklearn.metrics import (
    confusion_matrix,
    f1_score,
    precision_score,
    recall_score,
    roc_auc_score,
)

from . import synthetic
from .features import FEATURE_NAMES, ReadingContext, extract

log = logging.getLogger(__name__)


@dataclass
class Prediction:
    score: float  # higher = more anomalous. IF: -decision_function; >0 means flagged
    is_anomaly: bool
    method: str  # "isolation_forest" | "rules"
    reasons: list[str]


class RuleBasedDetector:
    """Transparent fallback used when no trained model is available."""

    method = "rules"

    def predict(self, ctx: ReadingContext) -> Prediction:
        f = dict(zip(FEATURE_NAMES, extract(ctx), strict=False))
        reasons: list[str] = []
        score = 0.0
        if f["power_ratio"] > 1.4:
            reasons.append(f"power {f['power_ratio']:.2f}x rated")
            score = max(score, (f["power_ratio"] - 1.4) / 1.4)
        if f["delta_ratio"] > 1.5:
            reasons.append(f"sudden change of {f['delta_ratio']:.2f}x rated")
            score = max(score, (f["delta_ratio"] - 1.5) / 1.5)
        if abs(f["voltage_dev"]) > 0.09:
            reasons.append(f"voltage deviation {f['voltage_dev'] * 100:.1f}%")
            score = max(score, abs(f["voltage_dev"]) - 0.09)
        if f["power_factor"] < 0.6:
            reasons.append(f"power factor {f['power_factor']:.2f}")
            score = max(score, 0.6 - f["power_factor"])
        if f["relay_mismatch"] > 0:
            reasons.append("power drawn while relay reports OFF")
            score = max(score, 0.5)
        return Prediction(round(float(score), 4), bool(reasons), self.method, reasons)


class IsolationForestDetector:
    method = "isolation_forest"

    def __init__(self, model: IsolationForest, version: str):
        self.model = model
        self.version = version

    def predict(self, ctx: ReadingContext) -> Prediction:
        x = extract(ctx).reshape(1, -1)
        score = float(-self.model.decision_function(x)[0])
        is_anom = score > 0
        reasons = []
        if is_anom:
            # Explain using the transparent rules where they agree.
            reasons = RuleBasedDetector().predict(ctx).reasons or ["unusual combination of electrical features"]
        return Prediction(round(score, 4), is_anom, self.method, reasons)


def evaluate_model(model: IsolationForest, ds: synthetic.Dataset) -> dict:
    scores = -model.decision_function(ds.X)
    pred = (scores > 0).astype(int)
    tn, fp, fn, tp = confusion_matrix(ds.y, pred, labels=[0, 1]).ravel()
    per_kind = {}
    for kind in synthetic.ANOMALY_KINDS:
        mask = ds.kinds == kind
        if mask.any():
            per_kind[kind] = round(float(pred[mask].mean()), 4)
    return {
        "precision": round(float(precision_score(ds.y, pred, zero_division=0)), 4),
        "recall": round(float(recall_score(ds.y, pred, zero_division=0)), 4),
        "f1": round(float(f1_score(ds.y, pred, zero_division=0)), 4),
        "roc_auc": round(float(roc_auc_score(ds.y, scores)), 4),
        "confusion_matrix": {"tn": int(tn), "fp": int(fp), "fn": int(fn), "tp": int(tp)},
        "recall_by_anomaly_kind": per_kind,
        "false_positive_rate": round(float(fp / max(fp + tn, 1)), 4),
        "n_test": int(len(ds.y)),
        "n_test_anomalies": int(ds.y.sum()),
        "evaluated_on": synthetic.DATA_LABEL,
    }


@dataclass
class TrainResult:
    version: str
    path: Path
    params: dict
    metrics: dict
    n_train: int
    n_test: int


TRAIN_EPISODE_RATE = 0.01
TEST_EPISODE_RATE = 0.01


def train(model_dir: Path, seed: int = 42, n_estimators: int = 200, contamination: float = 0.04,
          version: str | None = None) -> TrainResult:
    """Unsupervised training on synthetic operation data that contains a small, *unlabelled* share
    of anomaly episodes (as real logs would), then evaluation on an independently-seeded synthetic
    test set with labelled episodes.

    Note: training on normal-only data was evaluated and rejected — Isolation Forest cannot split on
    features that are constant in normal data (e.g. relay mismatch), so recall collapsed."""
    train_ds = synthetic.generate(n_appliances=40, steps=400, anomaly_rate=TRAIN_EPISODE_RATE, seed=seed)
    test_ds = synthetic.generate(n_appliances=20, steps=400, anomaly_rate=TEST_EPISODE_RATE, seed=seed + 1000)
    model = IsolationForest(n_estimators=n_estimators, contamination=contamination, random_state=seed)
    model.fit(train_ds.X)
    metrics = evaluate_model(model, test_ds)
    version = version or f"if-{datetime.now().strftime('%Y%m%d%H%M%S')}-s{seed}"
    model_dir.mkdir(parents=True, exist_ok=True)
    path = model_dir / f"{version}.joblib"
    joblib.dump(model, path)
    params = {"n_estimators": n_estimators, "contamination": contamination, "seed": seed,
              "features": FEATURE_NAMES, "train_episode_start_rate": TRAIN_EPISODE_RATE,
              "test_episode_start_rate": TEST_EPISODE_RATE, "train_anomaly_share": round(float(train_ds.y.mean()), 4)}
    (model_dir / f"{version}.json").write_text(json.dumps({"version": version, "params": params,
                                                          "metrics": metrics}, indent=2))
    log.info("Trained %s: precision=%.3f recall=%.3f f1=%.3f auc=%.3f (synthetic test set)",
             version, metrics["precision"], metrics["recall"], metrics["f1"], metrics["roc_auc"])
    return TrainResult(version, path, params, metrics, len(train_ds.y), len(test_ds.y))


class AnomalyService:
    """Thread-safe holder for the active detector; falls back to rules."""

    def __init__(self):
        self._lock = threading.Lock()
        self._detector: IsolationForestDetector | None = None
        self._fallback = RuleBasedDetector()
        self.last_error: str | None = None

    def load(self, path: str | Path, version: str) -> bool:
        try:
            model = joblib.load(path)
            if not isinstance(model, IsolationForest):
                raise TypeError("artifact is not an IsolationForest")
            with self._lock:
                self._detector = IsolationForestDetector(model, version)
                self.last_error = None
            return True
        except Exception as exc:  # corrupt / missing artifact -> keep running on rules
            log.warning("Could not load model %s: %s — using rule-based fallback", path, exc)
            with self._lock:
                self._detector = None
                self.last_error = str(exc)
            return False

    def unload(self) -> None:
        with self._lock:
            self._detector = None

    @property
    def method(self) -> str:
        return self._detector.method if self._detector else self._fallback.method

    @property
    def version(self) -> str | None:
        return self._detector.version if self._detector else None

    def predict(self, ctx: ReadingContext) -> Prediction:
        with self._lock:
            det = self._detector
        if det is not None:
            try:
                return det.predict(ctx)
            except Exception as exc:  # pragma: no cover - defensive
                log.exception("Model inference failed; falling back to rules: %s", exc)
        return self._fallback.predict(ctx)

    def score_batch(self, X: np.ndarray) -> np.ndarray:
        with self._lock:
            det = self._detector
        if det is None:
            raise RuntimeError("no model loaded")
        return -det.model.decision_function(X)
