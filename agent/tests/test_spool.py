import hashlib
import json
import os
import time

import pytest

from agentpulse.spool import Spool, SpoolFull


def test_failed_checkin_is_spooled(tmp_path):
    spool = Spool(tmp_path / "spool")
    event_id = spool.enqueue("check_in", {"password": "secret", "ok": "yes"})
    items = spool.list_pending()
    assert len(items) == 1
    assert items[0]["event_id"] == event_id
    assert items[0]["payload"]["password"] == "[REDACTED]"


def test_spool_survives_restart(tmp_path):
    first = Spool(tmp_path / "spool")
    first.enqueue("check_in", {"value": 1})
    second = Spool(tmp_path / "spool")
    assert second.list_pending()[0]["payload"] == {"value": 1}


def test_spool_replays_in_order(tmp_path):
    spool = Spool(tmp_path / "spool")
    first = spool.enqueue("check_in", {"sequence": 1})
    second = spool.enqueue("check_in", {"sequence": 2})
    replayed = []
    acknowledged = spool.replay(lambda event: replayed.append(event["event_id"]) or True)
    assert acknowledged == 2
    assert replayed == [first, second]
    assert spool.list_pending() == []


def test_spool_duplicate_is_not_replayed_twice(tmp_path):
    spool = Spool(tmp_path / "spool")
    event_id = spool.enqueue("check_in", {"value": 1}, event_id="fixed-event")
    assert spool.replay(lambda event: True) == 1
    with pytest.raises(ValueError):
        spool.enqueue("check_in", {"value": 1}, event_id=event_id)


def test_corrupt_spool_entry_is_quarantined(tmp_path):
    spool = Spool(tmp_path / "spool")
    path = tmp_path / "spool" / "00000000000000000001-corrupt.json"
    path.write_text("not json")
    assert spool.replay(lambda event: True) == 0
    assert not path.exists()
    assert len(list((tmp_path / "spool" / "quarantine").glob("*.json"))) == 1


def test_payload_hash_validation_quarantines_tampering(tmp_path):
    spool = Spool(tmp_path / "spool")
    spool.enqueue("check_in", {"value": 1})
    path = next((tmp_path / "spool").glob("*.json"))
    data = json.loads(path.read_text())
    data["payload"]["value"] = 2
    path.write_text(json.dumps(data))
    assert spool.replay(lambda event: True) == 0
    assert len(list((tmp_path / "spool" / "quarantine").glob("*.json"))) == 1


def test_spool_limit_is_enforced(tmp_path):
    spool = Spool(tmp_path / "spool", max_events=1)
    spool.enqueue("check_in", {})
    with pytest.raises(SpoolFull):
        spool.enqueue("check_in", {})


def test_failed_ack_keeps_event_for_retry(tmp_path):
    spool = Spool(tmp_path / "spool")
    spool.enqueue("check_in", {"value": 1})
    assert spool.replay(lambda event: False) == 0
    assert len(spool.list_pending()) == 1


def test_old_events_are_quarantined(tmp_path):
    spool = Spool(tmp_path / "spool", max_age_seconds=1)
    spool.enqueue("check_in", {})
    path = next((tmp_path / "spool").glob("*.json"))
    old = time.time() - 100
    os.utime(path, (old, old))
    assert spool.list_pending() == []
    assert len(list((tmp_path / "spool" / "quarantine").glob("*.json"))) == 1


def test_event_envelope_and_hash(tmp_path):
    spool = Spool(tmp_path / "spool")
    spool.enqueue("check_in", {"value": 1})
    event = spool.list_pending()[0]
    assert set(event) == {"event_id", "event_type", "created_at", "attempts", "payload", "payload_hash"}
    expected = hashlib.sha256(json.dumps(event["payload"], sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    assert event["payload_hash"] == expected


def test_redaction_happens_before_serialization(tmp_path):
    spool = Spool(tmp_path / "spool")
    spool.enqueue("check_in", {"nested": ["Bearer secret-token"]})
    raw = next((tmp_path / "spool").glob("*.json")).read_text()
    assert "secret-token" not in raw
