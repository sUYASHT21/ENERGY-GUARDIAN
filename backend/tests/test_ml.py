import numpy as np
import pytest

from app.ml import model as ml
from app.ml import synthetic
from app.ml.features import FEATURE_NAMES, ReadingContext, extract


@pytest.fixture(scope="module")
def trained(tmp_path_factory):
    d = tmp_path_factory.mktemp("models")
    return ml.train(d, seed=42, version="test-v1"), d


def test_synthetic_data_is_labelled_and_reproducible():
    a = synthetic.generate(n_appliances=5, steps=100, seed=1)
    b = synthetic.generate(n_appliances=5, steps=100, seed=1)
    assert np.array_equal(a.X, b.X) and np.array_equal(a.y, b.y)
    assert "synthetic" in a.label
    assert a.X.shape[1] == len(FEATURE_NAMES)
    assert set(np.unique(a.kinds)) <= {"normal", *synthetic.ANOMALY_KINDS}
    assert 0 < a.y.mean() < 0.15


def test_training_is_reproducible(tmp_path, trained):
    res1, _ = trained
    res2 = ml.train(tmp_path, seed=42, version="test-v2")
    assert res1.metrics == res2.metrics


def test_metrics_are_reported_and_reasonable(trained):
    m = trained[0].metrics
    for key in ("precision", "recall", "f1", "roc_auc", "confusion_matrix", "recall_by_anomaly_kind"):
        assert key in m
    assert "synthetic" in m["evaluated_on"]
    # Regression guard for the pipeline on its own synthetic benchmark (not a real-world claim).
    assert m["roc_auc"] > 0.9
    assert m["recall"] > 0.8
    cm = m["confusion_matrix"]
    assert cm["tp"] + cm["fn"] == m["n_test_anomalies"]


def _service(trained) -> ml.AnomalyService:
    res, _ = trained
    svc = ml.AnomalyService()
    assert svc.load(res.path, res.version)
    return svc


def test_detects_reproducible_injected_anomalies(trained):
    svc = _service(trained)
    assert svc.method == "isolation_forest"
    cases = {
        "overconsumption": ReadingContext(3000, 1000, 30, 230, 3000 / (230 * 0.9), True, 2950),
        "spike": ReadingContext(4500, 1000, 30, 230, 4500 / (230 * 0.9), True, 950),
        "low_power_factor": ReadingContext(950, 1000, 30, 230, 950 / (230 * 0.3), True, 940),
        "phantom_load": ReadingContext(400, 1000, 30, 230, 400 / (230 * 0.9), False, 410),
    }
    for name, ctx in cases.items():
        p = svc.predict(ctx)
        assert p.is_anomaly, name
        assert p.score > 0
        assert p.reasons


def test_voltage_faults_score_higher_than_normal_but_are_a_known_weak_class(trained):
    # Documented limitation: voltage-fault recall is the lowest class on the synthetic benchmark.
    svc = _service(trained)
    sag = svc.predict(ReadingContext(950, 1000, 30, 180, 950 / (180 * 0.9), True, 950))
    normal = svc.predict(ReadingContext(950, 1000, 30, 230, 950 / (230 * 0.92), True, 940))
    assert sag.score > normal.score
    assert trained[0].metrics["recall_by_anomaly_kind"]["voltage_fault"] < trained[0].metrics["recall"]


def test_normal_readings_are_not_flagged(trained):
    svc = _service(trained)
    normal = [
        ReadingContext(950, 1000, 30, 230, 950 / (230 * 0.92), True, 940),
        ReadingContext(0, 1000, 30, 231, 0, False, 0),
        ReadingContext(38, 40, 5, 229, 38 / (229 * 0.95), True, 39),
    ]
    for ctx in normal:
        assert not svc.predict(ctx).is_anomaly, ctx


def test_same_input_same_score(trained):
    svc = _service(trained)
    ctx = ReadingContext(2800, 1000, 30, 230, 13.0, True, 2700)
    assert svc.predict(ctx).score == svc.predict(ctx).score


def test_rule_fallback_when_no_model():
    svc = ml.AnomalyService()
    assert svc.method == "rules"
    assert svc.predict(ReadingContext(3000, 1000, 30, 230, 14, True, 2900)).is_anomaly
    assert not svc.predict(ReadingContext(950, 1000, 30, 230, 4.4, True, 940)).is_anomaly
    p = svc.predict(ReadingContext(300, 1000, 30, 230, 1.4, False, 300))
    assert p.is_anomaly and any("relay" in r for r in p.reasons)


def test_corrupt_model_falls_back_to_rules(tmp_path):
    bad = tmp_path / "bad.joblib"
    bad.write_bytes(b"not a model")
    svc = ml.AnomalyService()
    assert not svc.load(bad, "bad")
    assert svc.method == "rules" and svc.last_error
    assert svc.predict(ReadingContext(100, 100, 5)).method == "rules"


def test_feature_extraction():
    f = dict(zip(FEATURE_NAMES, extract(ReadingContext(500, 1000, 10, 253, 500 / (253 * 0.5), False, 0)), strict=True))
    assert f["power_ratio"] == pytest.approx(0.5)
    assert f["delta_ratio"] == pytest.approx(0.5)
    assert f["voltage_dev"] == pytest.approx(0.1)
    assert f["power_factor"] == pytest.approx(0.5)
    assert f["relay_mismatch"] == 1.0


def test_missing_artifact_is_rebuilt_identically(ctx, tmp_path):
    """Simulates a restart on an ephemeral host: registry in the DB, model file gone."""
    import shutil

    from app.models import MLModelRecord
    from app.services import ml_service

    with ctx.db.session() as db:
        rec = ml_service.train_and_activate(ctx, db, seed=11)
        version, metrics = rec.version, rec.metrics
    shutil.rmtree(ctx.settings.model_dir)  # "restart": local disk wiped
    ctx.anomaly.unload()
    with ctx.db.session() as db:
        assert ml_service.load_active(ctx, db)
        assert db.query(MLModelRecord).count() == 1  # no duplicate registration
    assert ctx.anomaly.method == "isolation_forest" and ctx.anomaly.version == version
    ml_reloaded = ml.train(tmp_path, seed=11, version="check")
    assert ml_reloaded.metrics == metrics
