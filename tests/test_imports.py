import os
import subprocess
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_data_modules_import_without_youtube_credentials():
    env = os.environ.copy()
    env.pop("YOUTUBE_API_KEY", None)

    completed = subprocess.run(
        [sys.executable, "-c", "import channel_finder, scraper, main"],
        cwd=PROJECT_ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr


def test_importing_pipeline_does_not_load_optional_deepface_stack():
    completed = subprocess.run(
        [
            sys.executable,
            "-c",
            "import main, sys; print(any(name == 'deepface' or name.startswith(('deepface.', 'tensorflow.')) for name in sys.modules))",
        ],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    assert completed.stdout.strip() == "False"


def test_main_cli_exits_nonzero_when_live_credentials_are_missing():
    env = os.environ.copy()
    env.pop("YOUTUBE_API_KEY", None)

    completed = subprocess.run(
        [sys.executable, "main.py"],
        cwd=PROJECT_ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode != 0
    assert "Missing YouTube API Key" in completed.stdout
