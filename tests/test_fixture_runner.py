import json
import os
import subprocess
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_fixture_runner_exercises_pipeline_without_external_credentials(tmp_path):
    output_path = tmp_path / "fixture-output.csv"
    env = os.environ.copy()
    env.pop("YOUTUBE_API_KEY", None)
    env.pop("GEMINI_API_KEY", None)
    env.pop("HERENOW_API_KEY", None)

    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "hq",
            "collect",
            "--fixture",
            "--refresh",
            "--output",
            str(output_path),
            "--runs-root",
            str(tmp_path / "runs"),
        ],
        cwd=PROJECT_ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    result = json.loads(completed.stdout)
    assert result["ok"] is True
    assert result["collection_status"] == "success"
    assert result["counts"]["rows_written"] == 1
    assert output_path.exists()
    assert Path(result["run_dir"]).is_relative_to(tmp_path / "runs")
    candidates = json.loads(Path(result["candidates_path"]).read_text(encoding="utf-8"))
    assert candidates["candidates"][0]["provenance"]["cv_method"] == "fixture"
