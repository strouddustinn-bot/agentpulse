import json
import shutil
import subprocess
import tarfile
import urllib.request
from pathlib import Path

ARCHIVE_URL = "https://paste.c-net.org/ThimbleGolfer"
ROOT = Path("/home/user/agentpulse-src")
ARCHIVE = Path("/home/user/agentpulse.tar.gz")


def run(name, argv, cwd, timeout=300):
    try:
        proc = subprocess.run(argv, cwd=str(cwd), text=True, capture_output=True, timeout=timeout)
        return {"name": name, "returncode": proc.returncode, "stdout": proc.stdout[-20000:], "stderr": proc.stderr[-10000:]}
    except Exception as exc:
        return {"name": name, "error": repr(exc)}


def main():
    urllib.request.urlretrieve(ARCHIVE_URL, ARCHIVE)
    if ROOT.exists():
        shutil.rmtree(ROOT)
    ROOT.mkdir(parents=True)
    with tarfile.open(ARCHIVE, "r:gz") as bundle:
        bundle.extractall(ROOT)

    results = []
    results.append(run("agent-tests", ["python3", "tools/run_tests.py"], ROOT / "agent"))
    results.append(run("agent-config", ["python3", "-m", "agentpulse", "validate", "agentpulse.config.local.json"], ROOT / "agent"))
    results.append(run("agent-dry-run", ["python3", "-m", "agentpulse", "run-once", "--dry-run", "agentpulse.config.local.json"], ROOT / "agent"))
    results.append(run("backend-install", ["python3", "-m", "pip", "install", "-e", "."], ROOT / "backend"))
    results.append(run("backend-tests", ["python3", "-m", "unittest", "discover", "tests"], ROOT / "backend"))
    results.append(run("dashboard-install", ["python3", "-m", "pip", "install", "-r", "requirements.txt"], ROOT / "dashboard"))
    results.append(run("dashboard-tests", ["python3", "-m", "unittest", "discover", "tests"], ROOT / "dashboard"))
    results.append(run("control-plane-install", ["npm", "ci"], ROOT / "control-plane"))
    results.append(run("control-plane-tests", ["npm", "test"], ROOT / "control-plane"))
    results.append(run("control-plane-typecheck", ["npm", "run", "typecheck"], ROOT / "control-plane"))
    results.append(run("dashboard-frontend-install", ["npm", "ci"], ROOT / "dashboard" / "frontend"))
    results.append(run("dashboard-frontend-build", ["npm", "run", "build"], ROOT / "dashboard" / "frontend"))
    results.append(run("dashboard-web-install", ["npm", "ci"], ROOT / "dashboard" / "web"))
    results.append(run("dashboard-web-lint", ["npm", "run", "lint"], ROOT / "dashboard" / "web"))
    results.append(run("dashboard-web-build", ["npm", "run", "build"], ROOT / "dashboard" / "web"))
    print(json.dumps({"results": results, "failed": [r["name"] for r in results if r.get("returncode", 1) != 0 or "error" in r]}, separators=(",", ":")))


main()
