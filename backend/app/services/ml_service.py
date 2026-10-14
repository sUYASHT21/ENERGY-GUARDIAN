"""Model registry: training, activation and loading of anomaly-detection models."""
from __future__ import annotations

import logging
from pathlib import Path

from sqlalchemy.orm import Session

from ..context import AppContext
from ..ml import model as ml
from ..ml.synthetic import DATA_LABEL
from ..models import MLModelRecord
from .events import log_event

log = logging.getLogger(__name__)


def record_to_dict(r: MLModelRecord) -> dict:
    return {"id": r.id, "version": r.version, "algorithm": r.algorithm, "trained_at": r.trained_at.isoformat(),
            "data_source": r.data_source, "n_train": r.n_train, "n_test": r.n_test, "params": r.params,
            "metrics": r.metrics, "active": r.active}


def activate(ctx: AppContext, db: Session, rec: MLModelRecord, actor: str = "system") -> bool:
    if not ctx.anomaly.load(rec.path, rec.version):
        return False
    for other in db.query(MLModelRecord).filter(MLModelRecord.active.is_(True)).all():
        other.active = False
    rec.active = True
    log_event(db, "ml", f"Model {rec.version} activated", now=ctx.clock.now(), actor=actor)
    return True


def train_and_activate(ctx: AppContext, db: Session, *, seed: int = 42, n_estimators: int = 200,
                       contamination: float = 0.04, actor: str = "system") -> MLModelRecord:
    existing = db.query(MLModelRecord).count()
    version = f"if-v{existing + 1}-s{seed}"
    while db.query(MLModelRecord).filter(MLModelRecord.version == version).first():
        existing += 1
        version = f"if-v{existing + 1}-s{seed}"
    res = ml.train(ctx.settings.model_dir, seed=seed, n_estimators=n_estimators, contamination=contamination,
                   version=version)
    rec = MLModelRecord(version=res.version, algorithm="isolation_forest", trained_at=ctx.clock.now(),
                        data_source=DATA_LABEL, n_train=res.n_train, n_test=res.n_test, params=res.params,
                        metrics=res.metrics, path=str(res.path))
    db.add(rec)
    db.flush()
    log_event(db, "ml", f"Model {rec.version} trained on synthetic data — F1 {res.metrics['f1']:.3f}, "
                        f"ROC-AUC {res.metrics['roc_auc']:.3f} (synthetic test set)", now=ctx.clock.now(), actor=actor,
              details={"metrics": res.metrics})
    activate(ctx, db, rec, actor)
    return rec


def load_active(ctx: AppContext, db: Session) -> bool:
    rec = db.query(MLModelRecord).filter(MLModelRecord.active.is_(True)).first()
    if rec is None:
        return False
    if not Path(rec.path).exists():
        # Ephemeral hosts (e.g. Render free tier) lose local files on restart while the registry
        # lives on in Postgres. Training is deterministic for a given seed, so rebuild the exact
        # same model from the stored parameters instead of registering a new one.
        p = rec.params or {}
        log.info("Model artifact for %s missing — rebuilding it from stored parameters", rec.version)
        try:
            res = ml.train(ctx.settings.model_dir, seed=int(p.get("seed", 42)),
                           n_estimators=int(p.get("n_estimators", 200)),
                           contamination=float(p.get("contamination", 0.04)), version=rec.version)
        except Exception:  # pragma: no cover - fall back to rules, bootstrap may retrain
            log.exception("Rebuilding model %s failed", rec.version)
            return False
        if res.metrics != rec.metrics:
            log.warning("Rebuilt model %s differs from the recorded metrics (library version change?)", rec.version)
        rec.path = str(res.path)
    return ctx.anomaly.load(rec.path, rec.version)
