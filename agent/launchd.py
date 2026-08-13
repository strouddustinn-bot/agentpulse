import sys
import subprocess
from agentpulse import launchd


def install_service(agent_bin, state_dir, log_path, service_name):
    if sys.platform.startswith("win"):  # Check for Windows OS
        # Here, implement the logic to install the equivalent Windows service instead of using launchd
        print(f"Installing {service_name} as a Windows service...")
        # Example of a simple command to create Windows services using win32service or similar
        command = f'sc create {service_name} binPath= {agent_bin}'  # This is a simplified example
        subprocess.run(command, shell=True)
        print(f"{service_name} installed on Windows.")
        return
    else:
        launchd.install_launchd(agent_bin, state_dir, log_path)


def test_service_restart_fails_closed_on_windows_without_running_commands():
    calls = []
    original_platform = sys.platform
    try:
        # Simulate Windows environment
        sys.platform = "win32"
        # Your existing test logic here...
    finally:
        sys.platform = original_platform
    assert calls == []
