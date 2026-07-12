import urllib.error

import pytest

from agentpulse.retry import (
    CredentialRecoveryRequired,
    RetryBudgetExhausted,
    RetryPolicy,
    classify_status,
)


def test_retry_transient_network_failure():
    attempts = []
    sleeps = []

    def operation():
        attempts.append(1)
        if len(attempts) < 3:
            raise ConnectionError("offline")
        return "ok"

    result = RetryPolicy(max_attempts=3, base_delay=1, jitter=0, sleep=sleeps.append).run(operation)
    assert result == "ok"
    assert len(attempts) == 3
    assert sleeps == [1, 2]


def test_retry_429_respects_retry_after():
    attempts = []
    sleeps = []

    class RateLimited(Exception):
        status = 429
        headers = {"Retry-After": "7"}

    def operation():
        attempts.append(1)
        if len(attempts) == 1:
            raise RateLimited()
        return "ok"

    assert RetryPolicy(max_attempts=2, base_delay=1, jitter=0, sleep=sleeps.append).run(operation) == "ok"
    assert sleeps == [7]


def test_no_retry_401():
    attempts = []

    class Unauthorized(Exception):
        status = 401

    def operation():
        attempts.append(1)
        raise Unauthorized()

    with pytest.raises(CredentialRecoveryRequired):
        RetryPolicy(max_attempts=5, sleep=lambda _: None).run(operation)
    assert len(attempts) == 1


def test_retry_budget_exhaustion():
    attempts = []

    def operation():
        attempts.append(1)
        raise TimeoutError("timed out")

    with pytest.raises(RetryBudgetExhausted):
        RetryPolicy(max_attempts=10, retry_budget=2, base_delay=0, jitter=0, sleep=lambda _: None).run(operation)
    assert len(attempts) == 2


def test_status_classification():
    assert classify_status(408).retryable
    assert classify_status(429).retryable
    assert classify_status(503).retryable
    assert not classify_status(401).retryable
    assert not classify_status(404).retryable


def test_http_error_is_classified():
    error = urllib.error.HTTPError("http://x", 503, "busy", {}, None)
    assert classify_status(error).retryable


def test_schema_validation_is_not_retried():
    class SchemaError(ValueError):
        schema_validation = True

    calls = []
    def operation():
        calls.append(1)
        raise SchemaError("bad payload")

    with pytest.raises(SchemaError):
        RetryPolicy(sleep=lambda _: None).run(operation)
    assert calls == [1]


def test_maximum_delay_is_enforced():
    sleeps = []
    calls = []

    def operation():
        calls.append(1)
        if len(calls) < 3:
            raise ConnectionError()
        return True

    RetryPolicy(max_attempts=3, base_delay=100, max_delay=3, jitter=0, sleep=sleeps.append).run(operation)
    assert sleeps == [3, 3]
