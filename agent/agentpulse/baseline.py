"""Baseline learning — statistical and ML-based anomaly detection.

Two tiers:
  1. Welford (online mean/variance) — fast, stateless, works from sample 1.
  2. Holt-Winters + hourly/daily seasonality — learns trends and cyclic patterns
     so a nightly backup spike at 3 AM never wakes you up.

Both tiers are pure-stdlib, zero-dependency, and JSON-serialisable so state
persists across restarts.

Anomalies are advisory: they raise alerts but never trigger auto-fix.
"""

from __future__ import annotations

import math
import time
from typing import Any, Dict, Optional, Tuple

from .config import BaselineConfig


# ---------------------------------------------------------------------------
# Tier 1 — Welford online mean/variance
# ---------------------------------------------------------------------------

def _new_stat() -> Dict[str, float]:
    return {"count": 0, "mean": 0.0, "m2": 0.0}


def update_stat(stat: Dict[str, float], value: float) -> None:
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


# ---------------------------------------------------------------------------
# Tier 2 — Holt-Winters double exponential smoothing (level + trend)
# ---------------------------------------------------------------------------

def _new_hw() -> Dict[str, Any]:
    return {"level": None, "trend": 0.0, "count": 0}


def hw_update(hw: Dict[str, Any], value: float, alpha: float, beta: float) -> float:
    """Update Holt-Winters state. Returns the one-step-ahead prediction."""
    if hw["level"] is None:
        hw["level"] = value
        hw["trend"] = 0.0
        hw["count"] = 1
        return value
    old_level = hw["level"]
    old_trend = hw["trend"]
    new_level = alpha * value + (1 - alpha) * (old_level + old_trend)
    new_trend = beta * (new_level - old_level) + (1 - beta) * old_trend
    hw["level"] = new_level
    hw["trend"] = new_trend
    hw["count"] = hw.get("count", 0) + 1
    return new_level + new_trend  # next-step prediction


def hw_is_anomalous(
    hw: Dict[str, Any],
    value: float,
    cfg: BaselineConfig,
    min_samples: int = 10,
) -> Tuple[bool, str]:
    """True if value deviates significantly from the Holt-Winters prediction."""
    count = hw.get("count", 0)
    if count < min_samples:
        return False, f"hw warming up ({count}/{min_samples})"
    level = hw.get("level", value)
    trend = hw.get("trend", 0.0)
    prediction = level + trend
    dev = abs(value - prediction)
    threshold = max(cfg.min_abs_deviation, cfg.z_threshold * max(abs(prediction) * 0.15, 2.0))
    if dev > threshold:
        return True, (
            f"trend anomaly: value {value:.1f} vs predicted {prediction:.1f} "
            f"(level={level:.1f} trend={trend:+.2f} dev={dev:.1f})"
        )
    return False, f"on-trend (predicted {prediction:.1f}, got {value:.1f})"


# ---------------------------------------------------------------------------
# Tier 2 — Per-hour-of-day seasonal buckets (24 bins)
# ---------------------------------------------------------------------------

def _new_hourly() -> Dict[str, Any]:
    return {"bins": [_new_stat() for _ in range(24)]}


def hourly_update(hourly: Dict[str, Any], value: float, hour: int) -> None:
    update_stat(hourly["bins"][hour % 24], value)


def hourly_is_anomalous(
    hourly: Dict[str, Any],
    value: float,
    hour: int,
    cfg: BaselineConfig,
) -> Tuple[bool, str]:
    bin_stat = hourly["bins"][hour % 24]
    count = bin_stat["count"]
    if count < max(3, cfg.min_samples // 6):
        return False, f"hourly bin {hour}h warming up ({count} samples)"
    mean = bin_stat["mean"]
    sd = stddev(bin_stat)
    dev = abs(value - mean)
    threshold_sd = cfg.z_threshold * sd if sd > 1e-6 else float("inf")
    anomalous = (dev >= cfg.min_abs_deviation) and (sd < 1e-6 or dev >= threshold_sd)
    if anomalous:
        return True, (
            f"seasonal anomaly at hour {hour}: value {value:.1f} vs "
            f"typical {mean:.1f}±{sd:.1f} for this time of day"
        )
    return False, f"seasonal normal at hour {hour} ({mean:.1f}±{sd:.1f})"


# ---------------------------------------------------------------------------
# Tier 2 — Per-day-of-week buckets (7 bins, 0=Monday)
# ---------------------------------------------------------------------------

def _new_weekly() -> Dict[str, Any]:
    return {"bins": [_new_stat() for _ in range(7)]}


def weekly_update(weekly: Dict[str, Any], value: float, weekday: int) -> None:
    update_stat(weekly["bins"][weekday % 7], value)


def weekly_is_anomalous(
    weekly: Dict[str, Any],
    value: float,
    weekday: int,
    cfg: BaselineConfig,
) -> Tuple[bool, str]:
    bin_stat = weekly["bins"][weekday % 7]
    count = bin_stat["count"]
    if count < 3:
        return False, f"weekly bin {weekday} warming up ({count} samples)"
    mean = bin_stat["mean"]
    sd = stddev(bin_stat)
    dev = abs(value - mean)
    threshold_sd = cfg.z_threshold * sd if sd > 1e-6 else float("inf")
    anomalous = (dev >= cfg.min_abs_deviation) and (sd < 1e-6 or dev >= threshold_sd)
    if anomalous:
        day_names = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
        return True, (
            f"weekly anomaly on {day_names[weekday % 7]}: value {value:.1f} vs "
            f"typical {mean:.1f}±{sd:.1f} for this day"
        )
    return False, ""


# ---------------------------------------------------------------------------
# Combined ML baseline entry — one per metric key
# ---------------------------------------------------------------------------

def _new_ml_entry() -> Dict[str, Any]:
    return {
        "global": _new_stat(),
        "hw": _new_hw(),
        "hourly": _new_hourly(),
        "weekly": _new_weekly(),
    }


def ml_observe(
    store: Dict[str, Any],
    key: str,
    value: float,
    cfg: BaselineConfig,
    now: Optional[float] = None,
) -> Tuple[bool, str]:
    """Check + update ML baseline for a metric. Returns (anomalous, reason).

    Anomaly requires agreement from at least 2 of 3 methods (Welford, HW,
    hourly seasonal) so single-method noise doesn't page you.
    """
    if now is None:
        now = time.time()

    import datetime as _dt
    dt = _dt.datetime.utcfromtimestamp(now)
    hour = dt.hour
    weekday = dt.weekday()

    ml_key = f"ml:{key}"
    entry = store.get(ml_key)
    if entry is None:
        entry = _new_ml_entry()
        store[ml_key] = entry

    # Enforce global warmup: no anomaly fires until min_samples have been seen.
    # This preserves the invariant that the agent never alerts during the
    # learning phase, regardless of which sub-method would otherwise trigger.
    global_count = entry["global"]["count"]
    if global_count < cfg.min_samples:
        # Still learning — update all models but never flag.
        update_stat(entry["global"], value)
        hw_update(entry["hw"], value, cfg.hw_alpha, cfg.hw_beta)
        hourly_update(entry["hourly"], value, hour)
        weekly_update(entry["weekly"], value, weekday)
        return False, f"ml learning ({global_count + 1}/{cfg.min_samples} samples)"

    # Check anomaly BEFORE updating (so we flag the current sample against
    # what was already learned, not including itself).
    welford_anomalous, welford_reason = is_anomalous(entry["global"], value, cfg)
    hw_anomalous, hw_reason = hw_is_anomalous(entry["hw"], value, cfg)
    hourly_anomalous, hourly_reason = hourly_is_anomalous(entry["hourly"], value, hour, cfg)
    weekly_anomalous, _ = weekly_is_anomalous(entry["weekly"], value, weekday, cfg)

    # Update all models with the new sample.
    update_stat(entry["global"], value)
    hw_update(entry["hw"], value, cfg.hw_alpha, cfg.hw_beta)
    hourly_update(entry["hourly"], value, hour)
    weekly_update(entry["weekly"], value, weekday)

    # Vote: flag only if at least 2 independent methods agree.
    votes = [welford_anomalous, hw_anomalous, hourly_anomalous or weekly_anomalous]
    if sum(votes) >= 2:
        reasons = [r for r, a in [
            (welford_reason, welford_anomalous),
            (hw_reason, hw_anomalous),
            (hourly_reason, hourly_anomalous),
        ] if a and r]
        return True, "; ".join(reasons) if reasons else "ml anomaly (multi-method agreement)"

    return False, ""


# ---------------------------------------------------------------------------
# Unified observe() — called by the runner
# ---------------------------------------------------------------------------

def observe(
    store: Dict[str, Any],
    key: str,
    value: float,
    cfg: BaselineConfig,
    now: Optional[float] = None,
) -> Tuple[bool, str]:
    """Check anomaly then fold the sample in. Returns (anomalous, reason).

    When ml_enabled, runs both the Welford check AND the full ML suite and
    returns true only when multiple methods agree (fewer false positives).
    When ml_enabled is off, falls back to the original Welford-only path.
    """
    if cfg.ml_enabled:
        return ml_observe(store, key, value, cfg, now=now)

    # Welford-only path (original behavior).
    stat = store.get(key)
    if stat is None:
        stat = _new_stat()
        store[key] = stat
    anomalous, reason = is_anomalous(stat, value, cfg)
    update_stat(stat, value)
    return anomalous, reason
