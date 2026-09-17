import json
import subprocess
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_fixture_runner_exercises_pipeline_without_external_credentials(tmp_path):
    output_path = tmp_path / "fixture-output.csv"
    env = dict(__import__("os").environ)
    env.pop("YOUTUBE_API_KEY", None)
    env.pop("GEMINI_API_KEY", None)

    completed = subprocess.run(
        [
            sys.executable,
            "scripts/run_fixture_pipeline.py",
            "--output",
            str(output_path),
        ],
        cwd=PROJECT_ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    result = json.loads(completed.stdout.strip().splitlines()[-1])
    assert result["status"] == "success"
    assert result["rows_written"] == 1
    assert output_path.exists()
    candidates = json.loads(
        Path(result["candidates_path"]).read_text(encoding="utf-8")
    )
    assert candidates["candidates"][0]["provenance"]["cv_method"] == "fixture"
