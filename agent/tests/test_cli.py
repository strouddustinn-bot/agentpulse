import io
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from agentpulse import cli


def _config():
    return SimpleNamespace(
        control_plane=SimpleNamespace(
            enabled=True,
            base_url="https://control.example",
            local_policy_ceiling="alert",
            credential_file="/tmp/agentpulse-test-credential",
            timeout_seconds=1,
        ),
        resolved_hostname=lambda: "host-1",
    )


def test_enroll_rejects_token_as_positional_process_argument():
    with pytest.raises(SystemExit):
        cli.build_parser().parse_args(["enroll", "config.json", "secret-on-argv"])


def test_enroll_reads_token_from_stdin():
    result = {"agent_id": "agent-1", "agent_key": "host-1"}
    with (
        patch.object(cli.config_mod, "load", return_value=_config()),
        patch.object(cli.control_plane, "enroll", return_value=result) as enroll,
        patch.object(cli.sys, "stdin", io.StringIO("one-time-token\n")),
    ):
        assert cli.main(["enroll", "config.json", "--token-stdin"]) == 0
    assert enroll.call_args.kwargs["enrollment_token"] == "one-time-token"


def test_enroll_rejects_empty_stdin_token():
    with (
        patch.object(cli.config_mod, "load", return_value=_config()),
        patch.object(cli.sys, "stdin", io.StringIO("\n")),
    ):
        assert cli.main(["enroll", "config.json", "--token-stdin"]) == 2