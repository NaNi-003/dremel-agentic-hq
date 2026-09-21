import json
from pathlib import Path

import dashboard_evidence
import pandas as pd


def _write_json(path, payload):
    path.write_text(json.dumps(payload), encoding="utf-8")


def _write_valid_run(
    tmp_path,
    *,
    run_id="run-1",
    status="success",
    candidates=None,
    partial_failures=None,
    collected_at="2026-09-16T12:20:00Z",
):
    runs_root = tmp_path / "runs"
    if candidates is None:
        candidates = [
            {
                "video_id": "video-1",
                "source": {
                    "video_id": "video-1",
                    "source_url": "https://www.youtube.com/watch?v=video-1",
                },
            }
        ]
    valid_video_ids = [
        item["video_id"]
        for item in candidates
        if isinstance(item, dict) and isinstance(item.get("video_id"), str)
    ]
    run_dir = runs_root / run_id
    run_dir.mkdir(parents=True)
    _write_json(
        run_dir / "manifest.json",
        {
            "schema_version": 1,
            "run_id": run_id,
            "status": status,
            "completed_at": "2026-09-16T12:30:00Z",
            "partial_failures": partial_failures or [],
            "counts": {
                "videos_collected": len(candidates),
                "candidates_scored": len(candidates),
                "rows_written": len(candidates),
            },
            "artifacts": {
                "evidence": "evidence.json",
                "candidates": "candidates.json",
                "dashboard_snapshot": "dashboard_output.csv",
            },
        },
    )
    _write_json(
        run_dir / "evidence.json",
        {
            "schema_version": 1,
            "run_id": run_id,
            "collected_at": collected_at,
            "videos": [{"video_id": video_id} for video_id in valid_video_ids],
        },
    )
    _write_json(
        run_dir / "candidates.json",
        {
            "schema_version": 1,
            "run_id": run_id,
            "candidates": candidates,
        },
    )
    csv_rows = "".join(f"{video_id}\n" for video_id in valid_video_ids)
    (run_dir / "dashboard_output.csv").write_text(
        "video_id\n" + csv_rows,
        encoding="utf-8",
    )
    _write_json(
        runs_root / "latest_success.json",
        {
            "schema_version": 1,
            "run_id": run_id,
            "status": status,
            "manifest": f"{run_id}/manifest.json",
            "dashboard_snapshot": f"{run_id}/dashboard_output.csv",
        },
    )
    return runs_root, run_dir


def test_load_latest_evidence_returns_timestamp_status_and_source_links(tmp_path):
    source_url = "https://www.youtube.com/watch?v=video-1"
    runs_root, run_dir = _write_valid_run(
        tmp_path,
        status="partial",
        partial_failures=[{"stage": "transcript_collection"}],
        candidates=[
            {
                "video_id": "video-1",
                "source": {"video_id": "video-1", "source_url": source_url},
            }
        ],
    )

    context = dashboard_evidence.load_latest_evidence(runs_root)

    assert context == {
        "run_id": "run-1",
        "status": "partial",
        "collected_at": "2026-09-16T12:20:00Z",
        "partial_failure_count": 1,
        "videos_collected": 1,
        "candidates_scored": 1,
        "source_urls": {"video-1": source_url},
        "dashboard_snapshot": run_dir / "dashboard_output.csv",
    }


def test_load_latest_evidence_returns_none_without_a_pointer(tmp_path):
    assert dashboard_evidence.load_latest_evidence(tmp_path / "missing") is None


def test_load_latest_evidence_uses_relative_paths_and_collection_timestamp(tmp_path):
    runs_root, run_dir = _write_valid_run(
        tmp_path,
        run_id="run-relative",
        collected_at="2026-09-16T12:01:00Z",
    )

    context = dashboard_evidence.load_latest_evidence(runs_root)

    assert context["collected_at"] == "2026-09-16T12:01:00Z"
    assert context["dashboard_snapshot"] == run_dir / "dashboard_output.csv"


def test_load_latest_evidence_rejects_manifest_outside_runs_root(tmp_path):
    runs_root = tmp_path / "runs"
    runs_root.mkdir()
    outside = tmp_path / "outside.json"
    outside.write_text("{}", encoding="utf-8")
    _write_json(
        runs_root / "latest_success.json",
        {
            "schema_version": 1,
            "run_id": "outside",
            "status": "success",
            "manifest": str(outside),
            "dashboard_snapshot": "outside/dashboard_output.csv",
        },
    )

    assert dashboard_evidence.load_latest_evidence(runs_root) is None


def test_load_latest_evidence_filters_invalid_or_forged_source_links(tmp_path):
    runs_root, _ = _write_valid_run(
        tmp_path,
        run_id="run-links",
        candidates=[
            {
                "video_id": "unsafe",
                "source": {
                    "video_id": "unsafe",
                    "source_url": "https://[",
                },
            },
        ],
    )

    context = dashboard_evidence.load_latest_evidence(runs_root)
    assert context["source_urls"] == {}


def test_load_latest_evidence_rejects_pointer_manifest_run_mismatch(tmp_path):
    runs_root, _ = _write_valid_run(tmp_path, run_id="run-manifest")
    pointer_path = runs_root / "latest_success.json"
    pointer = json.loads(pointer_path.read_text(encoding="utf-8"))
    pointer["run_id"] = "different-run"
    _write_json(pointer_path, pointer)

    assert dashboard_evidence.load_latest_evidence(runs_root) is None


def test_load_latest_evidence_rejects_inconsistent_linked_artifacts(tmp_path):
    runs_root, run_dir = _write_valid_run(tmp_path, run_id="run-inconsistent")
    _write_json(
        run_dir / "evidence.json",
        {
            "schema_version": 99,
            "run_id": "wrong-run",
            "collected_at": "2026-09-16T12:01:00Z",
        },
    )
    pointer_path = runs_root / "latest_success.json"
    pointer = json.loads(pointer_path.read_text(encoding="utf-8"))
    pointer["dashboard_snapshot"] = "different-run/dashboard_output.csv"
    _write_json(pointer_path, pointer)

    assert dashboard_evidence.load_latest_evidence(runs_root) is None


def test_load_latest_evidence_rejects_missing_dashboard_snapshot(tmp_path):
    runs_root, run_dir = _write_valid_run(tmp_path, run_id="run-missing-csv")
    (run_dir / "dashboard_output.csv").unlink()

    assert dashboard_evidence.load_latest_evidence(runs_root) is None


def test_validate_dashboard_dataframe_rejects_missing_or_invalid_values():
    required = {
        "action_pair": ["sand wood"],
        "velocity_score": [12.5],
        "cv_emotion": ["happy"],
        "detected_material": ["wood"],
        "thumbnail_url": ["https://i.ytimg.com/example.jpg"],
        "cv_color_hex": ["#ffffff"],
        "video_id": ["video-1"],
    }

    valid = dashboard_evidence.validate_dashboard_dataframe(pd.DataFrame(required))
    assert not valid.empty
    assert valid.iloc[0]["velocity_score"] == 12.5

    missing = pd.DataFrame(required).drop(columns=["action_pair"])
    assert dashboard_evidence.validate_dashboard_dataframe(missing).empty

    invalid_numeric = pd.DataFrame({**required, "velocity_score": ["not-a-number"]})
    assert dashboard_evidence.validate_dashboard_dataframe(invalid_numeric).empty

    invalid_identifier = pd.DataFrame({**required, "video_id": [["unhashable"]]})
    assert dashboard_evidence.validate_dashboard_dataframe(invalid_identifier).empty

    zero_velocity = pd.DataFrame({**required, "velocity_score": [0]})
    assert dashboard_evidence.validate_dashboard_dataframe(zero_velocity).empty


def test_load_latest_evidence_rejects_cross_artifact_count_and_id_mismatch(tmp_path):
    runs_root, run_dir = _write_valid_run(tmp_path, run_id="run-cross-check")
    manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
    manifest["counts"]["rows_written"] = 999
    _write_json(run_dir / "manifest.json", manifest)

    assert dashboard_evidence.load_latest_evidence(runs_root) is None


def test_latest_pointer_exists_distinguishes_missing_from_invalid_pointer(tmp_path):
    runs_root = tmp_path / "runs"
    assert not dashboard_evidence.latest_pointer_exists(runs_root)
    runs_root.mkdir()
    (runs_root / "latest_success.json").write_text("not-json", encoding="utf-8")
    assert dashboard_evidence.latest_pointer_exists(runs_root)
