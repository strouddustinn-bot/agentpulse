"""Statistical baseline learning.

Per metric, the agent maintains an online mean and variance (Welford's
algorithm) and flags a new sample as anomalous when it sits far enough from the
learned mean. This is what lets AgentPulse catch "this server is behaving
abnormally" *before* a value crosses a hard threshold — and it lowers false
alerts on hosts whose "normal" is just naturally high.

It is statistical, deterministic, and dependency-free — NOT a neural model.
Anomalies are advisory: they raise an alert and never trigger an auto-fix.
"""

from __future__ import annotations

import math
from typing import Any, Dict, Tuple

from .config import BaselineConfig


def _new_stat() -> Dict[str, float]:
    return {"count": 0, "mean": 0.0, "m2": 0.0}


def update_stat(stat: Dict[str, float], value: float) -> None:
    """Welford online update of count/mean/M2 (in place)."""
    stat["count"] += 1
    delta = value - stat["mean"]
    stat["mean"] += delta / stat["count"]
    delta2 = value - stat["mean"]
    stat["m2"] += delta * delta2


def stddev(stat: Dict[str, float]) -> float:
    if stat["count"] < 2:
        return 0.0
    return math.sqrt(stat["m2"] / stat["count"])


def is_anomalous(stat: Dict[str, float], value: float, cfg: BaselineConfig) -> Tuple[bool, str]:
    """Decide if `value` is anomalous vs the CURRENT baseline (before updating)."""
    count = stat["count"]
    if count < cfg.min_samples:
        return False, f"learning ({count}/{cfg.min_samples} samples)"
    mean = stat["mean"]
    sd = stddev(stat)
    dev = abs(value - mean)
    if sd < 1e-6:
        anomalous = dev >= max(cfg.min_abs_deviation, 1.0)
    else:
        anomalous = (dev >= cfg.z_threshold * sd) and (dev >= cfg.min_abs_deviation)
    if anomalous:
        z = dev / sd if sd > 1e-6 else float("inf")
        return True, (
            f"value {value:.1f} deviates from learned normal "
            f"{mean:.1f}±{sd:.1f} (z={z:.1f}, n={count})"
        )
    return False, f"within normal {mean:.1f}±{sd:.1f}"


def observe(
    store: Dict[str, Any], key: str, value: float, cfg: BaselineConfig
) -> Tuple[bool, str]:
    """Check anomaly against the baseline for `key`, then fold the sample in.

    `store` is the persisted baselines dict (mutated in place).
    Returns (anomalous, human-readable reason).
    """
    stat = store.get(key)
    if stat is None:
        stat = _new_stat()
        store[key] = stat
    anomalous, reason = is_anomalous(stat, value, cfg)
    update_stat(stat, value)  # learn from every sample, including outliers
    return anomalous, reason
