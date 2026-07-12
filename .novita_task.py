import json
import os
import shutil
import subprocess
import tarfile
import urllib.request
from pathlib import Path

task = "control-plane"
archive_url = "https://paste.c-net.org/ThimbleGolfer"
root = Path("/home/user/agentpulse-src")
archive = Path("/home/user/agentpulse.tar.gz")
urllib.request.urlretrieve(archive_url, archive)
root.mkdir(parents=True, exist_ok=True)
with tarfile.open(archive, "r:gz") as bundle:
    bundle.extractall(root)

plans = {
    "agent": [
        (["python3", "tools/run_tests.py"], root / "agent"),
        (["python3", "-m", "agentpulse", "validate", "agentpulse.config.local.json"], root / "agent"),
        (["python3", "-m", "agentpulse", "run-once", "--dry-run", "agentpulse.config.local.json"], root / "agent"),
    ],
    "backend": [
        (["python3", "-m", "pip", "install", "-e", "."], root / "backend"),
        (["python3", "-m", "unittest", "discover", "tests"], root / "backend"),
    ],
    "dashboard-python": [
        (["python3", "-m", "pip", "install", "-r", "requirements.txt"], root / "dashboard"),
        (["python3", "-m", "unittest", "discover", "tests"], root / "dashboard"),
    ],
    "control-plane": [
        (["npm", "ci"], root / "control-plane"),
        (["npm", "test"], root / "control-plane"),
        (["npm", "run", "typecheck"], root / "control-plane"),
    ],
    "dashboard-frontend": [
        (["npm", "ci"], root / "dashboard" / "frontend"),
        (["npm", "run", "build"], root / "dashboard" / "frontend"),
    ],
    "dashboard-web": [
        (["npm", "ci"], root / "dashboard" / "web"),
        (["npm", "run", "lint"], root / "dashboard" / "web"),
        (["npm", "run", "build"], root / "dashboard" / "web"),
    ],
}
results = []
for argv, cwd in plans[task]:
    proc = subprocess.run(argv, cwd=str(cwd), text=True, capture_output=True, timeout=300)
    results.append({"command": argv, "returncode": proc.returncode, "stdout": proc.stdout[-12000:], "stderr": proc.stderr[-6000:]})
    if proc.returncode:
        break
print(json.dumps({"task": task, "results": results}, separators=(",", ":")))
