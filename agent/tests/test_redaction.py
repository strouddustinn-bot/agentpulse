from agentpulse.redaction import REDACTED, redact, redact_headers, redact_text


def test_redacts_nested_secret_values():
    value = {"outer": [{"Api_Key": "alpha", "safe": "keep"}], "Password": "beta"}
    result = redact(value)
    assert result["outer"][0]["Api_Key"] == REDACTED
    assert result["outer"][0]["safe"] == "keep"
    assert result["Password"] == REDACTED
    assert value["outer"][0]["Api_Key"] == "alpha"


def test_redacts_authorization_headers():
    result = redact_headers({"Authorization": "Bearer abc", "Cookie": "sid=xyz", "X-Trace": "ok"})
    assert result["Authorization"] == REDACTED
    assert result["Cookie"] == REDACTED
    assert result["X-Trace"] == "ok"


def test_redacts_tokens_inside_urls():
    result = redact_text("GET https://user:pass@example.test/a?token=abc&keep=yes")
    assert "user:pass" not in result
    assert "token=[REDACTED]" in result
    assert "keep=yes" in result
    assert "abc" not in result


def test_redaction_preserves_nonsecret_fields():
    result = redact({"Name": "server-1", "status": "healthy", "count": 3})
    assert result == {"Name": "server-1", "status": "healthy", "count": 3}


def test_redacts_environment_and_traceback_text():
    result = redact_text("Traceback: API_TOKEN=secret-value\nraise RuntimeError('safe context')")
    assert "secret-value" not in result
    assert "API_TOKEN=[REDACTED]" in result
    assert "safe context" in result
