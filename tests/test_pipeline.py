import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

import main
import nlp_engine


FIXTURES = Path(__file__).parent / "fixtures"


def _fixture_videos():
    return json.loads((FIXTURES / "videos.json").read_text(encoding="utf-8"))


def _fixture_visual_analysis(frame, top_n=10):
    analyzed = frame.head(top_n).copy()
    analyzed["cv_color_hex"] = "#123456"
    analyzed["cv_emotion"] = "Fixture"
    return analyzed


def test_run_pipeline_returns_a_structured_success_result_and_legacy_csv(tmp_path):
    output_path = tmp_path / "dremel_final_output.csv"
    fixed_now = datetime(2026, 9, 16, tzinfo=timezone.utc)

    result = main.run_pipeline(
        search_terms=["fixture search"],
        output_path=output_path,
        runs_root=tmp_path / "runs",
        discover_channels_fn=lambda terms, max_results: ["fixture-channel"],
        scrape_videos_fn=lambda channels, max_results: _fixture_videos(),
        process_data_fn=lambda videos: nlp_engine.process_and_score_data(videos, now=fixed_now),
        visual_analysis_fn=_fixture_visual_analysis,
    )

    assert result.status == "success"
    assert result.output_path == str(output_path.resolve())
    assert result.channels_discovered == 1
    assert result.videos_collected == 1
    assert result.candidates_scored == 1
    assert result.rows_written == 1
    assert result.error is None

    saved = pd.read_csv(output_path)
    assert saved.to_dict("records") == [
        {
            "video_id": "fixture-restore-table",
            "video_title": "Restoring a table",
            "thumbnail_url": "https://example.invalid/table.jpg",
            "detected_verb": "Restore",
            "detected_material": "Table",
            "action_pair": "Restore Table",
            "velocity_score": 90.37,
            "cv_color_hex": "#123456",
            "cv_emotion": "Fixture",
        }
    ]


def test_run_pipeline_returns_a_structured_failure_result(tmp_path):
    output_path = tmp_path / "dremel_final_output.csv"

    def fail_discovery(terms, max_results):
        raise RuntimeError("fixture discovery failure")

    result = main.run_pipeline(
        search_terms=["fixture search"],
        output_path=output_path,
        runs_root=tmp_path / "runs",
        discover_channels_fn=fail_discovery,
    )

    assert result.status == "failed"
    assert result.output_path == str(output_path.resolve())
    assert result.channels_discovered == 0
    assert result.videos_collected == 0
    assert result.candidates_scored == 0
    assert result.rows_written == 0
    assert result.error == "fixture discovery failure"
    assert not output_path.exists()


def test_empty_pipeline_result_preserves_the_existing_output(tmp_path):
    output_path = tmp_path / "dremel_final_output.csv"
    original = b"existing-output\n"
    output_path.write_bytes(original)

    result = main.run_pipeline(
        search_terms=["fixture search"],
        output_path=output_path,
        runs_root=tmp_path / "runs",
        discover_channels_fn=lambda terms, max_results: ["fixture-channel"],
        scrape_videos_fn=lambda channels, max_results: _fixture_videos(),
        process_data_fn=lambda videos: pd.DataFrame(),
        visual_analysis_fn=_fixture_visual_analysis,
    )

    assert result.status == "empty"
    assert result.rows_written == 0
    assert result.error is None
    assert output_path.read_bytes() == original


def test_late_pipeline_failure_reports_completed_stage_counts_and_preserves_output(tmp_path):
    output_path = tmp_path / "dremel_final_output.csv"
    original = b"existing-output\n"
    output_path.write_bytes(original)
    fixed_now = datetime(2026, 9, 16, tzinfo=timezone.utc)

    def fail_visual_analysis(frame, top_n=10):
        raise RuntimeError("fixture visual failure")

    result = main.run_pipeline(
        search_terms=["fixture search"],
        output_path=output_path,
        runs_root=tmp_path / "runs",
        discover_channels_fn=lambda terms, max_results: ["fixture-channel"],
        scrape_videos_fn=lambda channels, max_results: _fixture_videos(),
        process_data_fn=lambda videos: nlp_engine.process_and_score_data(videos, now=fixed_now),
        visual_analysis_fn=fail_visual_analysis,
    )

    assert result.status == "failed"
    assert result.channels_discovered == 1
    assert result.videos_collected == 1
    assert result.candidates_scored == 0
    assert result.rows_written == 0
    assert result.error == "fixture visual failure"
    assert output_path.read_bytes() == original


def test_pipeline_creates_parent_directory_for_a_custom_output_path(tmp_path):
    output_path = tmp_path / "nested" / "results" / "dremel_final_output.csv"
    fixed_now = datetime(2026, 9, 16, tzinfo=timezone.utc)

    result = main.run_pipeline(
        search_terms=["fixture search"],
        output_path=output_path,
        runs_root=tmp_path / "runs",
        discover_channels_fn=lambda terms, max_results: ["fixture-channel"],
        scrape_videos_fn=lambda channels, max_results: _fixture_videos(),
        process_data_fn=lambda videos: nlp_engine.process_and_score_data(videos, now=fixed_now),
        visual_analysis_fn=_fixture_visual_analysis,
    )

    assert result.status == "success"
    assert output_path.exists()


def test_csv_write_failure_preserves_existing_output(tmp_path, monkeypatch):
    output_path = tmp_path / "dremel_final_output.csv"
    original = b"existing-output\n"
    output_path.write_bytes(original)
    fixed_now = datetime(2026, 9, 16, tzinfo=timezone.utc)

    def fail_after_partial_write(frame, path, *args, **kwargs):
        Path(path).write_bytes(b"partial-output")
        raise OSError("fixture disk failure")

    monkeypatch.setattr(pd.DataFrame, "to_csv", fail_after_partial_write)

    result = main.run_pipeline(
        search_terms=["fixture search"],
        output_path=output_path,
        runs_root=tmp_path / "runs",
        discover_channels_fn=lambda terms, max_results: ["fixture-channel"],
        scrape_videos_fn=lambda channels, max_results: _fixture_videos(),
        process_data_fn=lambda videos: nlp_engine.process_and_score_data(videos, now=fixed_now),
        visual_analysis_fn=_fixture_visual_analysis,
    )

    assert result.status == "failed"
    assert result.channels_discovered == 1
    assert result.videos_collected == 1
    assert result.candidates_scored == 1
    assert result.rows_written == 0
    assert result.error == "fixture disk failure"
    assert output_path.read_bytes() == original
