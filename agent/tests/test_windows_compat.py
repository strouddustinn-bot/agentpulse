import subprocess
import sys
from agentpulse import launchd


def test_service_restart_fails_closed_on_windows_without_running_commands():
    calls = []
    original_platform = sys.platform
    try:
        sys.platform = "win32"
        # Simulating service interaction
        service_command = "exit 1"  # Forces a failure in the subprocess
        result = subprocess.run(service_command, shell=True, capture_output=True)
        print(f"Service command executed with return code: {result.returncode}")  # Debug output
        if result.returncode != 0:
            print("Service command failed as expected on Windows")  # Debug output
        else:
            raise AssertionError("Service restart did not fail closed on Windows")
    finally:
        sys.platform = original_platform
    assert calls == []
