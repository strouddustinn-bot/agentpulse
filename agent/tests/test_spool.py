import hashlib
import json
import multiprocessing
import os
import time

import pytest

from agentpulse.spool import Spool, SpoolFull


def _replay_in_process(directory, entered, deliveries, delay):
    spool = Spool(directory)

    def acknowledge(event):
        deliveries.put(event["event_id"])
        entered.set()
        time.sleep(delay)
        return True

    spool.replay(acknowledge, max_events=1)


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


def test_failed_oldest_event_stops_fifo_replay(tmp_path):
    spool = Spool(tmp_path / "spool")
    first = spool.enqueue("check_in", {"sequence": 1})
    second = spool.enqueue("check_in", {"sequence": 2})
    attempted = []

    delivered = spool.replay(
        lambda event: attempted.append(event["event_id"]) or False
    )

    assert delivered == 0
    assert attempted == [first]
    assert [event["event_id"] for event in spool.list_pending()] == [first, second]


def test_replay_event_budget_bounds_each_cycle(tmp_path):
    spool = Spool(tmp_path / "spool")
    event_ids = [spool.enqueue("check_in", {"sequence": i}) for i in range(3)]
    attempted = []

    delivered = spool.replay(
        lambda event: attempted.append(event["event_id"]) or True,
        max_events=1,
    )

    assert delivered == 1
    assert attempted == event_ids[:1]
    assert [event["event_id"] for event in spool.list_pending()] == event_ids[1:]


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


def test_concurrent_replayers_deliver_event_once(tmp_path):
    directory = tmp_path / "spool"
    event_id = Spool(directory).enqueue("check_in", {"value": 1})
    context = multiprocessing.get_context("fork")
    entered = context.Event()
    deliveries = context.Queue()
    first = context.Process(
        target=_replay_in_process,
        args=(directory, entered, deliveries, 0.3),
    )
    second = context.Process(
        target=_replay_in_process,
        args=(directory, entered, deliveries, 0),
    )

    first.start()
    assert entered.wait(2)
    second.start()
    first.join(3)
    second.join(3)

    assert first.exitcode == 0
    assert second.exitcode == 0
    delivered = []
    while not deliveries.empty():
        delivered.append(deliveries.get())
    assert delivered == [event_id]


def test_acknowledgement_and_quarantine_retention_is_bounded(tmp_path):
    directory = tmp_path / "spool"
    spool = Spool(directory, max_auxiliary_files=2, max_auxiliary_bytes=4096)

    for index in range(5):
        spool.enqueue("check_in", {"sequence": index}, event_id=f"event-{index}")
        assert spool.replay(lambda event: True) == 1
    assert len(list((directory / "acknowledged").glob("*.ack"))) <= 2

    for index in range(5):
        (directory / f"{index:020d}-corrupt.json").write_text("not json")
    assert spool.list_pending() == []
    quarantined = list((directory / "quarantine").glob("*"))
    assert len(quarantined) <= 2
    assert sum(path.stat().st_size for path in quarantined) <= 4096
