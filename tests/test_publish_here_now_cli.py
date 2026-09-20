import json
import os
import subprocess
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = PROJECT_ROOT / "scripts" / "publish_here_now.py"


def test_publish_cli_fails_cleanly_when_permanent_credentials_are_missing(tmp_path):
    env = os.environ.copy()
    env.pop("HERENOW_API_KEY", None)
    env["HOME"] = str(tmp_path / "home")
    env["USERPROFILE"] = str(tmp_path / "home")

    completed = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--output",
            str(tmp_path / "site"),
            "--state",
            str(tmp_path / "state.json"),
        ],
        cwd=PROJECT_ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 1
    payload = json.loads(completed.stderr)
    assert payload["status"] == "failed"
    assert "credential" in payload["error"].lower()
    assert "api_key" not in completed.stderr.lower()
