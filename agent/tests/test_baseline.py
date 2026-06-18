import random

from agentpulse import baseline
from agentpulse.config import BaselineConfig


def test_welford_matches_naive():
    data = [10, 12, 9, 11, 13, 8, 10, 12]
    stat = baseline._new_stat()
    for x in data:
        baseline.update_stat(stat, x)
    mean = sum(data) / len(data)
    assert abs(stat["mean"] - mean) < 1e-9
    var = sum((x - mean) ** 2 for x in data) / len(data)
    assert abs(baseline.stddev(stat) - var ** 0.5) < 1e-9


def test_no_anomaly_during_warmup():
    cfg = BaselineConfig(min_samples=20)
    store = {}
    # Feed a wild value early — must NOT flag while still learning.
    for i in range(10):
        anomalous, _ = baseline.observe(store, "disk:/", 40.0, cfg)
        assert anomalous is False
    anomalous, reason = baseline.observe(store, "disk:/", 99.0, cfg)
    assert anomalous is False
    assert "learning" in reason


def test_flags_clear_anomaly_after_warmup():
    cfg = BaselineConfig(min_samples=20, z_threshold=3.0, min_abs_deviation=2.0)
    store = {}
    # Establish a stable normal around 40% with small noise.
    rng = random.Random(0)
    for _ in range(40):
        baseline.observe(store, "disk:/", 40 + rng.uniform(-1, 1), cfg)
    anomalous, reason = baseline.observe(store, "disk:/", 80.0, cfg)
    assert anomalous is True
    assert "deviates" in reason


def test_no_flap_on_near_constant_metric():
    cfg = BaselineConfig(min_samples=20, z_threshold=3.0, min_abs_deviation=2.0)
    store = {}
    for _ in range(30):
        baseline.observe(store, "mem", 50.0, cfg)  # perfectly constant
    # A tiny 1-point wobble must not flag (below absolute floor of 2.0).
    anomalous, _ = baseline.observe(store, "mem", 50.9, cfg)
    assert anomalous is False
    # A big jump must flag even though historical stddev was ~0.
    anomalous, _ = baseline.observe(store, "mem", 70.0, cfg)
    assert anomalous is True


def test_normal_values_never_flag():
    cfg = BaselineConfig(min_samples=20)
    store = {}
    rng = random.Random(1)
    flags = 0
    for _ in range(500):
        a, _ = baseline.observe(store, "disk:/", 60 + rng.uniform(-1.5, 1.5), cfg)
        flags += int(a)
    # Stable signal should essentially never trip after warmup.
    assert flags <= 3, f"too many false anomalies: {flags}"
