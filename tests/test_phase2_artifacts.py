import json
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import pandas as pd
from filelock import FileLock

import main
import nlp_engine


FIXTURES = Path(__file__).parent / "fixtures"
FIXED_NOW = datetime(2026, 9, 16, 12, 30, tzinfo=timezone.utc)
LEGACY_COLUMNS = [
    "video_id",
    "video_title",
    "thumbnail_url",
    "detected_verb",
    "detected_material",
    "action_pair",
    "velocity_score",
    "cv_color_hex",
    "cv_emotion",
    "cv_palette",
    "cv_color_temperature",
    "cv_face_count",
    "cv_expression_confidence",
    "cv_brightness",
    "cv_saturation",
    "cv_contrast",
    "cv_text_like_region_density",
    "cv_visual_clutter",
    "cv_face_area_share",
    "cv_central_face",
    "cv_objects",
    "cv_tools",
    "cv_method",
    "cv_semantic_method",
    "viewer_sentiment",
    "viewer_sentiment_score",
    "viewer_sentiment_confidence",
    "viewer_comments_sampled",
    "viewer_positive_share",
    "viewer_neutral_share",
    "viewer_negative_share",
]


def _fixture_videos():
    return json.loads((FIXTURES / "videos.json").read_text(encoding="utf-8"))


def _fixture_visual_analysis(frame, top_n=10):
    analyzed = frame.head(top_n).copy()
    analyzed["cv_color_hex"] = "#123456"
    analyzed["cv_emotion"] = "Fixture"
    analyzed["cv_method"] = "fixture"
    return analyzed


def _run_success(tmp_path, run_id="run-fixture-001"):
    return main.run_pipeline(
        search_terms=["fixture search"],
        output_path=tmp_path / "dremel_final_output.csv",
        runs_root=tmp_path / "runs",
        run_id=run_id,
        clock=lambda: FIXED_NOW,
        discover_channels_fn=lambda terms, max_results: ["fixture-channel"],
        scrape_videos_fn=lambda channels, max_results: _fixture_videos(),
        process_data_fn=lambda videos: nlp_engine.process_and_score_data(videos, now=FIXED_NOW),
        visual_analysis_fn=_fixture_visual_analysis,
    )


def test_successful_run_writes_immutable_evidence_and_candidate_artifacts(tmp_path):
    result = _run_success(tmp_path)

    assert result.status == "success"
    assert result.run_id == "run-fixture-001"
    assert result.started_at == "2026-09-16T12:30:00Z"
    assert result.completed_at == "2026-09-16T12:30:00Z"

    run_dir = tmp_path / "runs" / result.run_id
    manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
    evidence = json.loads((run_dir / "evidence.json").read_text(encoding="utf-8"))
    candidates = json.loads((run_dir / "candidates.json").read_text(encoding="utf-8"))
    snapshot = pd.read_csv(run_dir / "dashboard_output.csv")
    latest = json.loads((tmp_path / "runs" / "latest_success.json").read_text(encoding="utf-8"))

    assert manifest["schema_version"] == 1
    assert manifest["run_id"] == result.run_id
    assert manifest["status"] == "success"
    assert manifest["counts"] == {
        "channels_discovered": 1,
        "videos_collected": 1,
        "candidates_scored": 1,
        "rows_written": 1,
    }
    assert manifest["partial_failures"] == []

    assert evidence["collected_at"] == "2026-09-16T12:30:00Z"
    assert evidence["channels"] == ["fixture-channel"]
    source = evidence["videos"][0]
    assert source["video_id"] == "fixture-restore-table"
    assert source["source_url"] == "https://www.youtube.com/watch?v=fixture-restore-table"
    assert source["transcript_status"] == "available"
    assert source["transcript"] == "I restored the table."

    candidate = candidates["candidates"][0]
    assert candidate["action_pair"] == "Restore Table"
    assert candidate["source"]["video_id"] == "fixture-restore-table"
    assert candidate["provenance"] == {
        "extraction_source": "transcript",
        "cv_method": "fixture",
        "velocity_method": "age_adjusted_engagement_v1",
    }
    assert list(snapshot.columns) == LEGACY_COLUMNS
    assert latest["run_id"] == result.run_id
    assert latest["status"] == "success"
    assert latest["dashboard_snapshot"] == "run-fixture-001/dashboard_output.csv"


def test_usable_output_with_collection_errors_is_reported_as_partial(tmp_path):
    discovery_failure = {
        "stage": "channel_discovery",
        "source": "failed search",
        "error": "fixture discovery error",
    }
    scrape_failure = {
        "stage": "video_collection",
        "source": "failed-channel",
        "error": "fixture scrape error",
    }

    result = main.run_pipeline(
        search_terms=["fixture search"],
        output_path=tmp_path / "dremel_final_output.csv",
        runs_root=tmp_path / "runs",
        run_id="run-fixture-partial",
        clock=lambda: FIXED_NOW,
        discover_channels_fn=lambda terms, max_results: main.StageResult(
            items=["fixture-channel"],
            failures=[discovery_failure],
        ),
        scrape_videos_fn=lambda channels, max_results: main.StageResult(
            items=_fixture_videos(),
            failures=[scrape_failure],
        ),
        process_data_fn=lambda videos: nlp_engine.process_and_score_data(videos, now=FIXED_NOW),
        visual_analysis_fn=_fixture_visual_analysis,
    )

    assert result.status == "partial"
    assert list(result.partial_failures) == [discovery_failure, scrape_failure]
    manifest = json.loads(Path(result.manifest_path).read_text(encoding="utf-8"))
    latest = json.loads((tmp_path / "runs" / "latest_success.json").read_text(encoding="utf-8"))
    assert manifest["status"] == "partial"
    assert manifest["partial_failures"] == [discovery_failure, scrape_failure]
    assert latest["run_id"] == result.run_id
    assert latest["status"] == "partial"


def test_default_collectors_return_source_level_failure_diagnostics(monkeypatch):
    def discover(search_term, max_results):
        if search_term == "failed search":
            raise RuntimeError("discovery unavailable")
        return [
            {
                "Channel ID": "fixture-channel",
                "Channel Name": "Fixture Channel",
                "Description Snippet": "fixture",
            }
        ]

    def get_videos(channel, max_results):
        if channel == "failed-channel":
            raise RuntimeError("channel unavailable")
        return _fixture_videos()

    monkeypatch.setattr(main.channel_finder, "discover_uk_diy_channels", discover)
    monkeypatch.setattr(main.scraper, "get_channel_videos", get_videos)
    monkeypatch.setattr(
        main.scraper,
        "get_video_transcript",
        lambda video_id: (_ for _ in ()).throw(RuntimeError("no transcript")),
    )

    discovery = main.discover_target_channels_with_diagnostics(
        ["failed search", "working search"],
        max_results=1,
    )
    collection = main.scrape_channel_videos_with_diagnostics(
        ["failed-channel", "fixture-channel"],
        max_results=1,
    )

    assert discovery.items == ["fixture-channel"]
    assert discovery.failures == [
        {
            "stage": "channel_discovery",
            "source": "failed search",
            "error": "discovery unavailable",
        }
    ]
    assert collection.items[0]["channel_id"] == "fixture-channel"
    assert collection.items[0]["transcript"] == ""
    assert collection.failures == [
        {
            "stage": "video_collection",
            "source": "failed-channel",
            "error": "channel unavailable",
        },
        {
            "stage": "transcript_collection",
            "source": "fixture-restore-table",
            "error": "no transcript",
        },
    ]


def test_failed_refresh_records_manifest_and_preserves_last_success(tmp_path):
    successful = _run_success(tmp_path, run_id="run-success")
    output_path = Path(successful.output_path)
    output_before = output_path.read_bytes()
    pointer_path = tmp_path / "runs" / "latest_success.json"
    pointer_before = pointer_path.read_bytes()

    def fail_discovery(terms, max_results):
        raise RuntimeError("refresh unavailable")

    failed = main.run_pipeline(
        search_terms=["fixture search"],
        output_path=output_path,
        runs_root=tmp_path / "runs",
        run_id="run-failed",
        clock=lambda: FIXED_NOW,
        discover_channels_fn=fail_discovery,
    )

    assert failed.status == "failed"
    failed_manifest = json.loads(Path(failed.manifest_path).read_text(encoding="utf-8"))
    assert failed_manifest["status"] == "failed"
    assert failed_manifest["error"] == "refresh unavailable"
    assert output_path.read_bytes() == output_before
    assert pointer_path.read_bytes() == pointer_before


def test_reusing_a_run_id_does_not_overwrite_immutable_artifacts(tmp_path):
    first = _run_success(tmp_path, run_id="run-immutable")
    manifest_path = Path(first.manifest_path)
    manifest_before = manifest_path.read_bytes()

    second = _run_success(tmp_path, run_id="run-immutable")

    assert second.status == "failed"
    assert "already exists" in second.error
    assert second.manifest_path == ""
    assert second.evidence_path == ""
    assert second.candidates_path == ""
    assert manifest_path.read_bytes() == manifest_before


def test_incomplete_collection_without_candidates_is_partial_but_not_latest(tmp_path):
    failure = {
        "stage": "video_collection",
        "source": "failed-channel",
        "error": "incomplete fixture collection",
    }
    result = main.run_pipeline(
        search_terms=["fixture search"],
        output_path=tmp_path / "dremel_final_output.csv",
        runs_root=tmp_path / "runs",
        run_id="run-partial-empty",
        clock=lambda: FIXED_NOW,
        discover_channels_fn=lambda terms, max_results: ["fixture-channel"],
        scrape_videos_fn=lambda channels, max_results: main.StageResult(
            items=_fixture_videos(),
            failures=[failure],
        ),
        process_data_fn=lambda videos: pd.DataFrame(),
        visual_analysis_fn=_fixture_visual_analysis,
    )

    assert result.status == "partial"
    assert result.rows_written == 0
    assert not (tmp_path / "runs" / "latest_success.json").exists()


def test_run_id_rejects_path_traversal(tmp_path):
    result = main.run_pipeline(
        output_path=tmp_path / "dremel_final_output.csv",
        runs_root=tmp_path / "runs",
        run_id="../escaped-run",
        clock=lambda: FIXED_NOW,
    )

    assert result.status == "failed"
    assert result.error == "Invalid run ID: ../escaped-run"
    assert not (tmp_path / "escaped-run").exists()


def test_empty_visual_analysis_does_not_publish_or_replace_latest(tmp_path):
    result = main.run_pipeline(
        search_terms=["fixture search"],
        output_path=tmp_path / "dremel_final_output.csv",
        runs_root=tmp_path / "runs",
        run_id="run-empty-cv",
        clock=lambda: FIXED_NOW,
        discover_channels_fn=lambda terms, max_results: ["fixture-channel"],
        scrape_videos_fn=lambda channels, max_results: _fixture_videos(),
        process_data_fn=lambda videos: nlp_engine.process_and_score_data(videos, now=FIXED_NOW),
        visual_analysis_fn=lambda frame, top_n: frame.iloc[0:0].copy(),
    )

    assert result.status == "empty"
    assert result.candidates_scored == 0
    assert result.rows_written == 0
    assert not Path(result.output_path).exists()
    assert not (tmp_path / "runs" / "latest_success.json").exists()
    manifest = json.loads(Path(result.manifest_path).read_text(encoding="utf-8"))
    assert manifest["artifacts"] == {
        "evidence": "evidence.json",
        "candidates": "candidates.json",
    }


def test_candidate_preserves_source_collection_timestamp(tmp_path):
    times = iter(
        [
            datetime(2026, 9, 16, 12, 0, tzinfo=timezone.utc),
            datetime(2026, 9, 16, 12, 1, tzinfo=timezone.utc),
            datetime(2026, 9, 16, 12, 2, tzinfo=timezone.utc),
            datetime(2026, 9, 16, 12, 3, tzinfo=timezone.utc),
        ]
    )
    result = main.run_pipeline(
        search_terms=["fixture search"],
        output_path=tmp_path / "dremel_final_output.csv",
        runs_root=tmp_path / "runs",
        run_id="run-timestamps",
        clock=lambda: next(times),
        discover_channels_fn=lambda terms, max_results: ["fixture-channel"],
        scrape_videos_fn=lambda channels, max_results: _fixture_videos(),
        process_data_fn=lambda videos: nlp_engine.process_and_score_data(videos, now=FIXED_NOW),
        visual_analysis_fn=_fixture_visual_analysis,
    )

    candidates = json.loads(Path(result.candidates_path).read_text(encoding="utf-8"))
    assert candidates["generated_at"] == "2026-09-16T12:02:00Z"
    assert candidates["candidates"][0]["source"]["collected_at"] == "2026-09-16T12:01:00Z"


def test_candidate_count_matches_deduplicated_candidate_artifact(tmp_path):
    def duplicate_actions(videos):
        frame = nlp_engine.process_and_score_data(videos, now=FIXED_NOW)
        return pd.concat([frame, frame], ignore_index=True)

    result = main.run_pipeline(
        search_terms=["fixture search"],
        output_path=tmp_path / "dremel_final_output.csv",
        runs_root=tmp_path / "runs",
        run_id="run-deduplicated-count",
        clock=lambda: FIXED_NOW,
        discover_channels_fn=lambda terms, max_results: ["fixture-channel"],
        scrape_videos_fn=lambda channels, max_results: _fixture_videos(),
        process_data_fn=duplicate_actions,
        visual_analysis_fn=_fixture_visual_analysis,
    )

    candidates = json.loads(Path(result.candidates_path).read_text(encoding="utf-8"))
    assert result.candidates_scored == 1
    assert len(candidates["candidates"]) == 1


def test_dashboard_output_cannot_overlap_managed_run_artifacts(tmp_path):
    runs_root = tmp_path / "runs"
    result = main.run_pipeline(
        output_path=runs_root / "run-collision" / "manifest.json",
        runs_root=runs_root,
        run_id="run-collision",
        clock=lambda: FIXED_NOW,
    )

    assert result.status == "failed"
    assert "outside the managed runs root" in result.error
    assert not (runs_root / "run-collision").exists()


def test_all_discovery_failures_are_retained_in_failed_manifest(tmp_path, monkeypatch):
    monkeypatch.setattr(
        main.channel_finder,
        "discover_uk_diy_channels",
        lambda search_term, max_results: (_ for _ in ()).throw(
            RuntimeError(f"unavailable for {search_term}")
        ),
    )

    result = main.run_pipeline(
        search_terms=["first search", "second search"],
        output_path=tmp_path / "dremel_final_output.csv",
        runs_root=tmp_path / "runs",
        run_id="run-all-discovery-failed",
        clock=lambda: FIXED_NOW,
    )

    manifest = json.loads(Path(result.manifest_path).read_text(encoding="utf-8"))
    assert result.status == "failed"
    assert [failure["source"] for failure in manifest["partial_failures"]] == [
        "first search",
        "second search",
    ]


def test_final_manifest_failure_does_not_replace_dashboard_output(tmp_path, monkeypatch):
    output_path = tmp_path / "dremel_final_output.csv"
    output_path.write_bytes(b"preserved-dashboard")
    real_write_json = main.run_artifacts.write_json_atomically

    def fail_final_manifest(payload, path):
        if Path(path).name == "manifest.json" and payload.get("status") == "success":
            raise OSError("manifest storage unavailable")
        return real_write_json(payload, path)

    monkeypatch.setattr(main.run_artifacts, "write_json_atomically", fail_final_manifest)
    result = main.run_pipeline(
        search_terms=["fixture search"],
        output_path=output_path,
        runs_root=tmp_path / "runs",
        run_id="run-manifest-failure",
        clock=lambda: FIXED_NOW,
        discover_channels_fn=lambda terms, max_results: ["fixture-channel"],
        scrape_videos_fn=lambda channels, max_results: _fixture_videos(),
        process_data_fn=lambda videos: nlp_engine.process_and_score_data(videos, now=FIXED_NOW),
        visual_analysis_fn=_fixture_visual_analysis,
    )

    assert result.status == "failed"
    assert result.error == "manifest storage unavailable"
    assert output_path.read_bytes() == b"preserved-dashboard"
    assert not (tmp_path / "runs" / "latest_success.json").exists()


def test_latest_pointer_failure_rolls_back_dashboard_output(tmp_path, monkeypatch):
    successful = _run_success(tmp_path, run_id="run-before-pointer-failure")
    output_path = Path(successful.output_path)
    output_before = output_path.read_bytes()
    pointer_path = tmp_path / "runs" / "latest_success.json"
    pointer_before = pointer_path.read_bytes()
    real_write_json = main.run_artifacts.write_json_atomically

    def fail_latest_pointer(payload, path):
        if Path(path).name == "latest_success.json":
            raise OSError("pointer storage unavailable")
        return real_write_json(payload, path)

    monkeypatch.setattr(main.run_artifacts, "write_json_atomically", fail_latest_pointer)
    result = _run_success(tmp_path, run_id="run-pointer-failure")

    assert result.status == "failed"
    assert result.error == "pointer storage unavailable"
    assert output_path.read_bytes() == output_before
    assert pointer_path.read_bytes() == pointer_before


def test_run_directory_storage_failure_returns_structured_result(tmp_path, monkeypatch):
    monkeypatch.setattr(
        main.run_artifacts,
        "create_run_directory",
        lambda runs_root, run_id: (_ for _ in ()).throw(
            PermissionError("run storage denied")
        ),
    )

    result = main.run_pipeline(
        output_path=tmp_path / "dremel_final_output.csv",
        runs_root=tmp_path / "runs",
        run_id="run-storage-denied",
        clock=lambda: FIXED_NOW,
    )

    assert result.status == "failed"
    assert result.error == "run storage denied"
    assert result.manifest_path == ""


def test_initial_manifest_failure_returns_structured_result(tmp_path, monkeypatch):
    monkeypatch.setattr(
        main.run_artifacts,
        "write_json_atomically",
        lambda payload, path: (_ for _ in ()).throw(
            PermissionError("manifest creation denied")
        ),
    )

    result = main.run_pipeline(
        output_path=tmp_path / "dremel_final_output.csv",
        runs_root=tmp_path / "runs",
        run_id="run-manifest-denied",
        clock=lambda: FIXED_NOW,
    )

    assert result.status == "failed"
    assert result.error == "manifest creation denied"
    assert not Path(result.manifest_path).exists()


def test_publish_lock_prevents_cross_run_csv_pointer_interleaving(tmp_path):
    runs_root = tmp_path / "runs"
    runs_root.mkdir()
    output_path = tmp_path / "dremel_final_output.csv"
    output_path.write_bytes(b"preserved-dashboard")

    with FileLock(str(runs_root / ".publish.lock")):
        result = main.run_pipeline(
            search_terms=["fixture search"],
            output_path=output_path,
            runs_root=runs_root,
            run_id="run-lock-contention",
            clock=lambda: FIXED_NOW,
            publish_lock_timeout=0,
            discover_channels_fn=lambda terms, max_results: ["fixture-channel"],
            scrape_videos_fn=lambda channels, max_results: _fixture_videos(),
            process_data_fn=lambda videos: nlp_engine.process_and_score_data(videos, now=FIXED_NOW),
            visual_analysis_fn=_fixture_visual_analysis,
        )

    assert result.status == "failed"
    assert "publish lock" in result.error.lower()
    assert output_path.read_bytes() == b"preserved-dashboard"
    assert not (runs_root / "latest_success.json").exists()


def test_persisted_errors_redact_credentials_and_url_queries(tmp_path):
    secret_error = (
        "request failed https://example.test/path?key=SECRET123 "
        "api_key=SECRET456 Authorization: Bearer SECRET789"
    )

    result = main.run_pipeline(
        search_terms=["fixture search"],
        output_path=tmp_path / "dremel_final_output.csv",
        runs_root=tmp_path / "runs",
        run_id="run-redacted-errors",
        clock=lambda: FIXED_NOW,
        discover_channels_fn=lambda terms, max_results: main.StageResult(
            items=["fixture-channel"],
            failures=[
                {
                    "stage": "channel_discovery",
                    "source": "fixture search",
                    "error": secret_error,
                }
            ],
        ),
        scrape_videos_fn=lambda channels, max_results: _fixture_videos(),
        process_data_fn=lambda videos: nlp_engine.process_and_score_data(videos, now=FIXED_NOW),
        visual_analysis_fn=_fixture_visual_analysis,
    )

    manifest_text = Path(result.manifest_path).read_text(encoding="utf-8")
    assert "SECRET123" not in manifest_text
    assert "SECRET456" not in manifest_text
    assert "SECRET789" not in manifest_text
    assert "[REDACTED]" in manifest_text


def test_run_artifact_references_are_relative_and_relocatable(tmp_path):
    result = _run_success(tmp_path, run_id="run-relocatable")
    manifest = json.loads(Path(result.manifest_path).read_text(encoding="utf-8"))
    latest = json.loads(
        (tmp_path / "runs" / "latest_success.json").read_text(encoding="utf-8")
    )

    assert manifest["artifacts"] == {
        "evidence": "evidence.json",
        "candidates": "candidates.json",
        "dashboard_snapshot": "dashboard_output.csv",
    }
    assert latest["manifest"] == "run-relocatable/manifest.json"
    assert latest["dashboard_snapshot"] == (
        "run-relocatable/dashboard_output.csv"
    )


def test_cli_exits_nonzero_for_partial_run_without_usable_rows(monkeypatch):
    monkeypatch.setattr(
        main,
        "run_pipeline",
        lambda: SimpleNamespace(status="partial", rows_written=0),
    )

    assert main.main_cli() == 1


def test_publish_lock_is_shared_by_runs_roots_targeting_same_output(tmp_path):
    output_path = tmp_path / "shared-dashboard.csv"
    output_path.write_bytes(b"preserved-dashboard")
    output_lock = tmp_path / ".shared-dashboard.csv.publish.lock"

    with FileLock(str(output_lock)):
        result = main.run_pipeline(
            search_terms=["fixture search"],
            output_path=output_path,
            runs_root=tmp_path / "different-runs-root",
            run_id="run-shared-output-lock",
            clock=lambda: FIXED_NOW,
            publish_lock_timeout=0,
            discover_channels_fn=lambda terms, max_results: ["fixture-channel"],
            scrape_videos_fn=lambda channels, max_results: _fixture_videos(),
            process_data_fn=lambda videos: nlp_engine.process_and_score_data(videos, now=FIXED_NOW),
            visual_analysis_fn=_fixture_visual_analysis,
        )

    assert result.status == "failed"
    assert "publish lock" in result.error.lower()
    assert output_path.read_bytes() == b"preserved-dashboard"
