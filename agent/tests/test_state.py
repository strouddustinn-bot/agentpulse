from agentpulse.state import State


def test_load_recovers_from_corrupt_json(tmp_path):
    p = tmp_path / "state.json"
    p.write_text("{ not json")
    st = State.load(str(p))
    assert st.list_pending() == []
    assert st.baselines == {}


def test_load_recovers_from_non_object_json(tmp_path):
    # Valid JSON that isn't an object must reset like corruption, not crash.
    p = tmp_path / "state.json"
    p.write_text('["not", "a", "dict"]')
    st = State.load(str(p))
    assert st.list_pending() == []
    st.mark_run()
    st.save()
    assert State.load(str(p)).data["last_run"] is not None


def test_save_keeps_state_file_private(tmp_path):
    p = tmp_path / "state.json"
    st = State.load(str(p))
    st.mark_run()

    st.save()

    assert oct(p.stat().st_mode & 0o777) == "0o600"
