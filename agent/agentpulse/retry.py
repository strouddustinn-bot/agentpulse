"""Bounded retry policy for agent-to-backend operations."""
from __future__ import annotations

import random
import time
import urllib.error
from dataclasses import dataclass
from typing import Any, Callable, Optional


class CredentialRecoveryRequired(RuntimeError):
    """A 401 requires credential rotation/re-enrollment, never blind retry."""


class RetryBudgetExhausted(RuntimeError):
    """The operation remained transiently unavailable after its retry budget."""


@dataclass(frozen=True)
class StatusClassification:
    retryable: bool
    credential_recovery: bool = False
    reason: str = ""


_RETRYABLE_STATUS = {408, 429, 500, 502, 503, 504}
_PERMANENT_STATUS = {400, 401, 403, 404}


def _status_from(value: Any) -> Optional[int]:
    if isinstance(value, int):
        return value
    status = getattr(value, "status", getattr(value, "code", None))
    if status is None and isinstance(value, urllib.error.HTTPError):
        status = value.code
    try:
        return int(status) if status is not None else None
    except (TypeError, ValueError):
        return None


def classify_status(value: Any) -> StatusClassification:
    status = _status_from(value)
    if status == 401:
        return StatusClassification(False, True, "credential recovery required")
    if status in _RETRYABLE_STATUS:
        return StatusClassification(True, False, f"transient HTTP {status}")
    if status in _PERMANENT_STATUS:
        return StatusClassification(False, False, f"permanent HTTP {status}")
    if status is None and isinstance(value, (ConnectionError, TimeoutError, OSError, urllib.error.URLError)):
        return StatusClassification(True, False, "transient network failure")
    if getattr(value, "schema_validation", False):
        return StatusClassification(False, False, "schema validation failure")
    return StatusClassification(False, False, "non-retryable failure")


def _retry_after(exc: BaseException) -> Optional[float]:
    headers = getattr(exc, "headers", None)
    if headers is None:
        return None
    value = headers.get("Retry-After") if hasattr(headers, "get") else None
    try:
        delay = float(value)
    except (TypeError, ValueError):
        return None
    return max(0.0, delay)


class RetryPolicy:
    def __init__(
        self,
        *,
        max_attempts: int = 3,
        retry_budget: Optional[int] = None,
        base_delay: float = 0.5,
        max_delay: float = 30.0,
        jitter: float = 0.2,
        sleep: Callable[[float], None] = time.sleep,
        clock: Callable[[], float] = time.monotonic,
        random_fn: Callable[[], float] = random.random,
    ) -> None:
        if max_attempts < 1 or (retry_budget is not None and retry_budget < 1):
            raise ValueError("retry limits must be positive")
        self.max_attempts = max_attempts
        self.retry_budget = retry_budget if retry_budget is not None else max_attempts
        self.base_delay = max(0.0, base_delay)
        self.max_delay = max(0.0, max_delay)
        self.jitter = max(0.0, jitter)
        self.sleep = sleep
        self.clock = clock
        self.random_fn = random_fn

    def run(self, operation: Callable[[], Any]) -> Any:
        last: Optional[BaseException] = None
        attempts = 0
        while attempts < min(self.max_attempts, self.retry_budget):
            attempts += 1
            try:
                return operation()
            except BaseException as exc:
                last = exc
                classification = classify_status(exc)
                if classification.credential_recovery:
                    raise CredentialRecoveryRequired(classification.reason) from exc
                if not classification.retryable:
                    raise
                if attempts >= min(self.max_attempts, self.retry_budget):
                    raise RetryBudgetExhausted("retry budget exhausted") from exc
                delay = _retry_after(exc)
                if delay is None:
                    delay = min(self.max_delay, self.base_delay * (2 ** (attempts - 1)))
                    if self.jitter:
                        delay = min(self.max_delay, delay + (self.random_fn() * self.jitter))
                self.sleep(min(self.max_delay, delay))
        raise RetryBudgetExhausted("retry budget exhausted") from last


__all__ = ["CredentialRecoveryRequired", "RetryBudgetExhausted", "RetryPolicy", "StatusClassification", "classify_status"]
