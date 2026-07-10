import json

import pytest  # type: ignore
from agentpulse import config as cfgmod


def write(tmp_path, data):
    p = tmp_path / "c.json"
    p.write_text(json.dumps(data))
    return str(p)


def test_minimal_valid(tmp_path):
    c = cfgmod.load(write(tmp_path, {}))
    assert c.disk.mode == "alert"
    assert c.interval_seconds == 60


def test_full_valid(tmp_path):
    data = {
        "interval_seconds": 30,
        "notify": {"type": "webhook", "webhook_url": "https://example.com/hook"},
        "checks": {
            "disk": {
                "mode": "auto",
                "threshold_percent": 80,
                "paths": ["/"],
                "cleanup_globs": ["/tmp/*"],
            },
            "service": {"mode": "ask", "services": ["nginx", "redis"]},
            "process": {"mode": "alert", "mem_percent_threshold": 90},
        },
    }
    c = cfgmod.load(write(tmp_path, data))
    assert c.disk.mode == "auto"
    assert c.service.services == ["nginx", "redis"]
    assert c.notify.type == "webhook"


def test_bad_mode(tmp_path):
    with pytest.raises(cfgmod.ConfigError):
        cfgmod.load(write(tmp_path, {"checks": {"disk": {"mode": "nuke"}}}))


def test_threshold_over_100(tmp_path):
    with pytest.raises(cfgmod.ConfigError):
        cfgmod.load(write(tmp_path, {"checks": {"disk": {"threshold_percent": 150}}}))


def test_auto_disk_without_globs_rejected(tmp_path):
    with pytest.raises(cfgmod.ConfigError):
        cfgmod.load(
            write(tmp_path, {"checks": {"disk": {"mode": "auto", "cleanup_globs": []}}})
        )


def test_webhook_requires_url(tmp_path):
    with pytest.raises(cfgmod.ConfigError):
        cfgmod.load(write(tmp_path, {"notify": {"type": "webhook"}}))


def test_webhook_rejects_non_http_url(tmp_path):
    # The URL goes to urllib verbatim; anything but http(s) is a misconfiguration.
    with pytest.raises(cfgmod.ConfigError):
        cfgmod.load(
            write(
                tmp_path,
                {"notify": {"type": "webhook", "webhook_url": "file:///etc/passwd"}},
            )
        )


def test_missing_file():
    with pytest.raises(cfgmod.ConfigError):
        cfgmod.load("/no/such/file.json")


def test_bad_json(tmp_path):
    p = tmp_path / "c.json"
    p.write_text("{ not json")
    with pytest.raises(cfgmod.ConfigError):
        cfgmod.load(str(p))


def test_negative_interval(tmp_path):
    with pytest.raises(cfgmod.ConfigError):
        cfgmod.load(write(tmp_path, {"interval_seconds": -5}))


def test_example_config_is_valid():
    import os

    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    c = cfgmod.load(os.path.join(here, "agentpulse.config.example.json"))
    # Ships safe-by-default: nothing in auto.
    assert c.disk.mode == "alert"
    assert c.service.mode == "alert"
    assert c.process.mode == "alert"


def test_checkin_config_valid(tmp_path):
    c = cfgmod.load(
        write(
            tmp_path,
            {
                "checkin": {
                    "endpoint_url": "https://api.example.com/api/agent/checkin",
                    "auth_token": "secret-token",
                    "timeout_seconds": 5,
                }
            },
        )
    )
    assert c.checkin.endpoint_url == "https://api.example.com/api/agent/checkin"
    assert c.checkin.auth_token == "secret-token"
    assert c.checkin.timeout_seconds == 5


def test_checkin_endpoint_rejects_non_http_url(tmp_path):
    with pytest.raises(cfgmod.ConfigError):
        cfgmod.load(
            write(tmp_path, {"checkin": {"endpoint_url": "file:///tmp/checkin"}})
        )


def test_checkin_timeout_must_be_positive(tmp_path):
    with pytest.raises(cfgmod.ConfigError):
        cfgmod.load(write(tmp_path, {"checkin": {"timeout_seconds": 0}}))
