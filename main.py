from dataclasses import dataclass, replace
from contextlib import ExitStack
from datetime import datetime, timezone
from pathlib import Path
import json
import re
from tempfile import NamedTemporaryFile
from typing import Optional
from uuid import uuid4

import pandas as pd
from filelock import FileLock, Timeout

import channel_finder
import comment_analysis
import cv_layer
import nlp_engine
import run_artifacts
import scraper


DEFAULT_SEARCH_TERMS = [
    "UK furniture upcycling",
    "UK woodworking restoration",
    "DIY upcycling UK",
    "UK furniture makeover",
]


@dataclass(frozen=True)
class PipelineResult:
    status: str
    output_path: str
    channels_discovered: int
    videos_collected: int
    candidates_scored: int
    rows_written: int
    message: str
    run_id: str
    run_dir: str
    started_at: str
    completed_at: str
    manifest_path: str
    evidence_path: str
    candidates_path: str
    partial_failures: tuple
    error: Optional[str] = None


@dataclass(frozen=True)
class StageResult:
    items: list
    failures: list


class StageFailure(RuntimeError):
    def __init__(self, message, failures):
        super().__init__(message)
        self.failures = list(failures)


def _sanitize_error_text(error):
    text = str(error)
    text = re.sub(
        r"(https?://[^\s?]+)\?[^\s]+",
        r"\1?[REDACTED]",
        text,
    )
    text = re.sub(
        r"(?i)\b(api[_-]?key|token|secret|authorization)\s*[:=]\s*"
        r"(?:bearer\s+)?[^\s,;]+",
        r"\1=[REDACTED]",
        text,
    )
    return text[:500]


def _sanitize_failures(failures):
    sanitized = []
    for failure in failures:
        record = dict(failure)
        record["error"] = _sanitize_error_text(record.get("error", ""))
        sanitized.append(record)
    return sanitized


def discover_target_channels_with_diagnostics(search_terms, max_results=3):
    discovered_data = []
    seen_channel_ids = set()
    failures = []

    for search_term in search_terms:
        try:
            results = channel_finder.discover_uk_diy_channels(
                search_term,
                max_results=max_results,
            )
        except Exception as exc:
            safe_error = _sanitize_error_text(exc)
            print(f"Channel discovery failed for '{search_term}': {safe_error}")
            failures.append(
                {
                    "stage": "channel_discovery",
                    "source": search_term,
                    "error": safe_error,
                }
            )
            continue

        for channel in results:
            channel_id = channel["Channel ID"]
            if channel_id in seen_channel_ids:
                continue
            seen_channel_ids.add(channel_id)
            discovered_data.append(channel)

    if not discovered_data:
        raise StageFailure(
            (
                "Automated channel discovery returned no channels. "
                "Try broader keywords or verify the YouTube API key."
            ),
            failures,
        )

    return StageResult(
        items=[channel["Channel ID"] for channel in discovered_data],
        failures=failures,
    )


def discover_target_channels(search_terms, max_results=3):
    return discover_target_channels_with_diagnostics(
        search_terms,
        max_results=max_results,
    ).items


def scrape_channel_videos_with_diagnostics(target_channels, max_results=5):
    raw_data = []
    failures = []

    for channel in target_channels:
        try:
            videos = scraper.get_channel_videos(channel, max_results=max_results)
        except Exception as exc:
            safe_error = _sanitize_error_text(exc)
            print(f"Skipping channel {channel} due to scrape error: {safe_error}")
            failures.append(
                {
                    "stage": "video_collection",
                    "source": channel,
                    "error": safe_error,
                }
            )
            continue

        for vid in videos:
            vid.setdefault("channel_id", channel)
            try:
                vid["transcript"] = scraper.get_video_transcript(vid["video_id"])
            except Exception as exc:
                vid["transcript"] = ""
                failures.append(
                    {
                        "stage": "transcript_collection",
                        "source": vid["video_id"],
                        "error": _sanitize_error_text(exc),
                    }
                )

            vid["content_text"] = " ".join(
                part
                for part in [
                    vid.get("transcript", ""),
                    vid.get("title", ""),
                    vid.get("description", ""),
                ]
                if part
            )
            raw_data.append(vid)

    return StageResult(items=raw_data, failures=failures)


def enrich_primary_comments_with_diagnostics(
    raw_data,
    primary_video_ids,
    max_results=100,
    get_comments_fn=None,
):
    """Collect one bounded comment sample for primary candidates only."""
    get_comments_fn = get_comments_fn or scraper.get_video_comments
    primary_video_ids = set(primary_video_ids)
    enriched = [dict(video) for video in raw_data]
    failures = []
    for video in enriched:
        video_id = video.get("video_id")
        if video_id not in primary_video_ids:
            continue
        try:
            comments = get_comments_fn(video_id, max_results=max_results)
        except Exception as exc:
            comments = []
            failures.append(
                {
                    "stage": "comment_collection",
                    "source": video_id,
                    "error": _sanitize_error_text(exc),
                }
            )
        video["comment_sample"] = comments
        video["comment_sentiment"] = comment_analysis.analyze_comments(comments)
    return StageResult(items=enriched, failures=failures)


def scrape_channel_videos(target_channels, max_results=5):
    return scrape_channel_videos_with_diagnostics(
        target_channels,
        max_results=max_results,
    ).items


def normalize_output_frame(final_df):
    expected_columns = [
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

    final_df = final_df.copy()
    for column in expected_columns:
        if column not in final_df.columns:
            final_df[column] = pd.NA

    for column in ("cv_palette", "cv_objects", "cv_tools"):
        final_df[column] = final_df[column].map(
            lambda value: json.dumps(value, ensure_ascii=False)
            if isinstance(value, (list, tuple))
            else value
        )

    return final_df[expected_columns]


def _viewer_sentiment_label(sentiment):
    if not isinstance(sentiment, dict) or not sentiment.get("comments_sampled"):
        return "Unavailable"
    shares = sentiment.get("shares") or {}
    positive = float(shares.get("positive", 0) or 0)
    negative = float(shares.get("negative", 0) or 0)
    if positive >= 0.25 and negative >= 0.25:
        return "Mixed"
    score = sentiment.get("sentiment_score")
    if not isinstance(score, (int, float)):
        return "Unavailable"
    if score >= 0.05:
        return "Positive"
    if score <= -0.05:
        return "Negative"
    return "Neutral"


def attach_viewer_sentiment(candidate_df, videos):
    """Flatten primary-candidate comment evidence for dashboard display."""
    result = candidate_df.copy()
    by_video = {
        video.get("video_id"): video.get("comment_sentiment")
        for video in videos
        if isinstance(video, dict) and video.get("video_id")
    }
    sentiments = [by_video.get(video_id) for video_id in result["video_id"]]
    result["viewer_sentiment"] = [_viewer_sentiment_label(item) for item in sentiments]
    result["viewer_sentiment_score"] = [
        item.get("sentiment_score") if isinstance(item, dict) else None
        for item in sentiments
    ]
    result["viewer_sentiment_confidence"] = [
        item.get("confidence", "unavailable") if isinstance(item, dict) else "unavailable"
        for item in sentiments
    ]
    result["viewer_comments_sampled"] = [
        item.get("comments_sampled", 0) if isinstance(item, dict) else 0
        for item in sentiments
    ]
    for label in ("positive", "neutral", "negative"):
        result[f"viewer_{label}_share"] = [
            (item.get("shares") or {}).get(label) if isinstance(item, dict) else None
            for item in sentiments
        ]
    return result


def keep_top_unique_rows(final_df, limit=10):
    if final_df.empty:
        return final_df
    deduped = final_df.drop_duplicates(subset=["video_id"])
    return deduped.head(limit)


def prepare_ranked_candidates(
    structured_df,
    visual_analysis_fn,
    *,
    primary_limit=15,
    total_limit=50,
):
    """Deeply enrich primary candidates and retain lighter secondary results."""
    if structured_df.empty:
        return structured_df
    ranked = (
        structured_df.drop_duplicates(subset=["video_id"])
        .head(total_limit)
        .copy()
    )
    primary = visual_analysis_fn(ranked, top_n=min(primary_limit, len(ranked))).copy()
    primary["candidate_tier"] = "primary"
    if primary.empty:
        return primary

    secondary = ranked.iloc[len(primary):].copy()
    if not secondary.empty:
        secondary["cv_color_hex"] = "#cccccc"
        secondary["cv_emotion"] = "Not analyzed"
        secondary["cv_method"] = "not_analyzed_secondary"
        secondary["candidate_tier"] = "secondary"

    candidates = pd.concat([primary, secondary], ignore_index=True)
    candidates["candidate_rank"] = range(1, len(candidates) + 1)
    return candidates


def write_csv_atomically(final_df, output_path):
    """Replace the output only after a complete CSV has been written."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with NamedTemporaryFile(
        dir=output_path.parent,
        prefix=f".{output_path.name}.",
        suffix=".tmp",
        delete=False,
    ) as temporary_file:
        temporary_path = Path(temporary_file.name)

    try:
        final_df.to_csv(temporary_path, index=False)
        temporary_path.replace(output_path)
    finally:
        temporary_path.unlink(missing_ok=True)


def write_bytes_atomically(data, output_path):
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with NamedTemporaryFile(
        dir=output_path.parent,
        prefix=f".{output_path.name}.",
        suffix=".tmp",
        delete=False,
    ) as temporary_file:
        temporary_path = Path(temporary_file.name)
        temporary_file.write(data)
    try:
        temporary_path.replace(output_path)
    finally:
        temporary_path.unlink(missing_ok=True)


def copy_file_atomically(source_path, output_path):
    write_bytes_atomically(Path(source_path).read_bytes(), output_path)


def _new_run_id(started_at):
    return f"{started_at.strftime('%Y%m%dT%H%M%SZ')}-{uuid4().hex[:8]}"


def _valid_run_id(run_id):
    return bool(re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}", run_id))


def _artifact_paths(run_dir):
    return {
        "manifest": run_dir / "manifest.json",
        "evidence": run_dir / "evidence.json",
        "candidates": run_dir / "candidates.json",
        "dashboard_snapshot": run_dir / "dashboard_output.csv",
    }


def _unwrap_stage_result(value, partial_failures):
    if isinstance(value, StageResult):
        partial_failures.extend(_sanitize_failures(value.failures))
        return value.items
    return value


def _build_result(
    *,
    status,
    output_path,
    progress,
    message,
    run_id,
    run_dir,
    started_at,
    completed_at,
    partial_failures,
    error=None,
    artifacts_available=True,
):
    paths = _artifact_paths(run_dir) if artifacts_available else None
    return PipelineResult(
        status=status,
        output_path=str(output_path),
        channels_discovered=progress["channels_discovered"],
        videos_collected=progress["videos_collected"],
        candidates_scored=progress["candidates_scored"],
        rows_written=progress["rows_written"],
        message=message,
        run_id=run_id,
        run_dir=str(run_dir) if artifacts_available else "",
        started_at=run_artifacts.isoformat_utc(started_at),
        completed_at=run_artifacts.isoformat_utc(completed_at),
        manifest_path=str(paths["manifest"]) if paths else "",
        evidence_path=str(paths["evidence"]) if paths else "",
        candidates_path=str(paths["candidates"]) if paths else "",
        partial_failures=tuple(partial_failures),
        error=error,
    )


def _preflight_failure(*, error, output_path, run_id, started_at, completed_at):
    return _build_result(
        status="failed",
        output_path=output_path,
        progress={
            "channels_discovered": 0,
            "videos_collected": 0,
            "candidates_scored": 0,
            "rows_written": 0,
        },
        message=f"Pipeline failed: {error}",
        run_id=run_id,
        run_dir="",
        started_at=started_at,
        completed_at=completed_at,
        partial_failures=[],
        error=error,
        artifacts_available=False,
    )


def _write_manifest(result, search_terms, dashboard_snapshot):
    artifact_candidates = {
        "evidence": Path(result.evidence_path),
        "candidates": Path(result.candidates_path),
        "dashboard_snapshot": Path(dashboard_snapshot),
    }
    artifacts = {
        name: path.name
        for name, path in artifact_candidates.items()
        if path.is_file()
    }
    manifest = {
        "schema_version": run_artifacts.SCHEMA_VERSION,
        "run_id": result.run_id,
        "status": result.status,
        "started_at": result.started_at,
        "completed_at": result.completed_at,
        "search_terms": list(search_terms),
        "output_path": result.output_path,
        "counts": {
            "channels_discovered": result.channels_discovered,
            "videos_collected": result.videos_collected,
            "candidates_scored": result.candidates_scored,
            "rows_written": result.rows_written,
        },
        "partial_failures": list(result.partial_failures),
        "message": result.message,
        "error": result.error,
        "artifacts": artifacts,
    }
    run_artifacts.write_json_atomically(manifest, result.manifest_path)


def _write_latest_success(result, runs_root, dashboard_snapshot):
    payload = {
        "schema_version": run_artifacts.SCHEMA_VERSION,
        "run_id": result.run_id,
        "status": result.status,
        "completed_at": result.completed_at,
        "manifest": f"{result.run_id}/manifest.json",
        "dashboard_snapshot": f"{result.run_id}/{Path(dashboard_snapshot).name}",
    }
    run_artifacts.write_json_atomically(payload, runs_root / "latest_success.json")


def _run_pipeline_impl(
    *,
    search_terms,
    output_path,
    discover_channels_fn,
    scrape_videos_fn,
    process_data_fn,
    visual_analysis_fn,
    comment_enrichment_fn,
    progress,
    run_id,
    run_dir,
    started_at,
    clock,
    partial_failures,
):
    print("--- DREMEL PREDICTIVE TREND ENGINE ---")
    paths = _artifact_paths(run_dir)

    print("Executing Automated UK Channel Discovery...")
    target_channels = _unwrap_stage_result(
        discover_channels_fn(search_terms, max_results=5),
        partial_failures,
    )
    progress["channels_discovered"] = len(target_channels)

    print(
        f"Successfully automated {len(target_channels)} target channels. "
        "Beginning scrape..."
    )
    raw_data = _unwrap_stage_result(
        scrape_videos_fn(target_channels, max_results=10),
        partial_failures,
    )
    progress["videos_collected"] = len(raw_data)
    collected_at = run_artifacts.isoformat_utc(clock())
    evidence = run_artifacts.build_evidence_document(
        run_id,
        target_channels,
        raw_data,
        collected_at,
    )
    run_artifacts.write_json_atomically(evidence, paths["evidence"])

    print("Running Semantic Parser...")
    structured_df = process_data_fn(raw_data)
    extraction_sources = structured_df.attrs.get("extraction_sources", {})

    if not structured_df.empty:
        structured_df = structured_df.drop_duplicates(subset=["video_id"])

    if structured_df.empty:
        generated_at = run_artifacts.isoformat_utc(clock())
        candidates = run_artifacts.build_candidates_document(
            run_id,
            structured_df,
            evidence["videos"],
            generated_at,
            extraction_sources,
        )
        run_artifacts.write_json_atomically(candidates, paths["candidates"])
        print(
            "\n[ERROR] Pipeline resulted in 0 matches. "
            "No videos mentioned a valid surface material."
        )
        empty_status = "partial" if partial_failures else "empty"
        empty_message = (
            "Pipeline produced no candidates after a partial collection."
            if partial_failures
            else "Pipeline resulted in 0 matches."
        )
        return _build_result(
            status=empty_status,
            output_path=output_path,
            progress=progress,
            message=empty_message,
            run_id=run_id,
            run_dir=run_dir,
            started_at=started_at,
            completed_at=clock(),
            partial_failures=partial_failures,
        )

    print(f"Isolated {len(structured_df)} unique, high-velocity surface trends.")
    candidate_df = prepare_ranked_candidates(structured_df, visual_analysis_fn)
    progress["candidates_scored"] = len(candidate_df)
    primary_ids = candidate_df.loc[
        candidate_df["candidate_tier"] == "primary", "video_id"
    ].tolist()
    raw_data = _unwrap_stage_result(
        comment_enrichment_fn(raw_data, primary_ids, max_results=100),
        partial_failures,
    )
    candidate_df = attach_viewer_sentiment(candidate_df, raw_data)
    evidence = run_artifacts.build_evidence_document(
        run_id,
        target_channels,
        raw_data,
        collected_at,
    )
    run_artifacts.write_json_atomically(evidence, paths["evidence"])
    generated_at = run_artifacts.isoformat_utc(clock())
    candidates = run_artifacts.build_candidates_document(
        run_id,
        candidate_df,
        evidence["videos"],
        generated_at,
        extraction_sources,
    )
    run_artifacts.write_json_atomically(candidates, paths["candidates"])

    if candidate_df.empty:
        status = "partial" if partial_failures else "empty"
        message = (
            "Visual analysis produced no usable candidates after a partial collection."
            if partial_failures
            else "Visual analysis produced no usable candidates."
        )
        return _build_result(
            status=status,
            output_path=output_path,
            progress=progress,
            message=message,
            run_id=run_id,
            run_dir=run_dir,
            started_at=started_at,
            completed_at=clock(),
            partial_failures=partial_failures,
        )

    legacy_df = normalize_output_frame(candidate_df)
    write_csv_atomically(legacy_df, paths["dashboard_snapshot"])
    progress["rows_written"] = len(legacy_df)
    print(f"\nPipeline Complete! {len(legacy_df)} unique videos saved to {output_path}.")
    print(
        "You may now build the dashboard: "
        "'python static_dashboard.py --output dist/dashboard'"
    )
    final_status = "partial" if partial_failures else "success"
    final_message = (
        "Pipeline completed with partial collection failures."
        if partial_failures
        else "Pipeline completed successfully."
    )
    return _build_result(
        status=final_status,
        output_path=output_path,
        progress=progress,
        message=final_message,
        run_id=run_id,
        run_dir=run_dir,
        started_at=started_at,
        completed_at=clock(),
        partial_failures=partial_failures,
    )


def run_pipeline(
    search_terms=None,
    output_path="dremel_final_output.csv",
    discover_channels_fn=None,
    scrape_videos_fn=None,
    process_data_fn=None,
    visual_analysis_fn=None,
    comment_enrichment_fn=None,
    runs_root="artifacts/runs",
    run_id=None,
    clock=None,
    publish_lock_timeout=10,
):
    """Run the pipeline and return status plus immutable evidence artifacts."""
    clock = clock or (lambda: datetime.now(timezone.utc))
    started_at = clock()
    resolved_output_path = Path(output_path).resolve()
    resolved_runs_root = Path(runs_root).resolve()
    resolved_run_id = run_id or _new_run_id(started_at)
    if resolved_output_path.is_relative_to(resolved_runs_root):
        error = "Dashboard output must be outside the managed runs root."
        return _preflight_failure(
            error=error,
            output_path=resolved_output_path,
            run_id=resolved_run_id,
            started_at=started_at,
            completed_at=clock(),
        )
    if not _valid_run_id(resolved_run_id):
        error = f"Invalid run ID: {resolved_run_id}"
        return _preflight_failure(
            error=error,
            output_path=resolved_output_path,
            run_id=resolved_run_id,
            started_at=started_at,
            completed_at=clock(),
        )
    expected_run_dir = resolved_runs_root / resolved_run_id
    try:
        run_dir = run_artifacts.create_run_directory(
            resolved_runs_root,
            resolved_run_id,
        )
    except FileExistsError:
        error = f"Run ID already exists and is immutable: {resolved_run_id}"
        return _preflight_failure(
            error=error,
            output_path=resolved_output_path,
            run_id=resolved_run_id,
            started_at=started_at,
            completed_at=clock(),
        )
    except OSError as exc:
        return _preflight_failure(
            error=str(exc),
            output_path=resolved_output_path,
            run_id=resolved_run_id,
            started_at=started_at,
            completed_at=clock(),
        )
    search_terms = list(search_terms or DEFAULT_SEARCH_TERMS)
    discover_channels_fn = (
        discover_channels_fn or discover_target_channels_with_diagnostics
    )
    custom_scrape = scrape_videos_fn is not None
    scrape_videos_fn = scrape_videos_fn or scrape_channel_videos_with_diagnostics
    process_data_fn = process_data_fn or nlp_engine.process_and_score_data
    visual_analysis_fn = visual_analysis_fn or cv_layer.run_visual_analysis
    if comment_enrichment_fn is None:
        comment_enrichment_fn = (
            (lambda videos, primary_ids, max_results: StageResult(videos, []))
            if custom_scrape
            else enrich_primary_comments_with_diagnostics
        )
    progress = {
        "channels_discovered": 0,
        "videos_collected": 0,
        "candidates_scored": 0,
        "rows_written": 0,
    }
    partial_failures = []
    paths = _artifact_paths(run_dir)

    running_manifest = {
        "schema_version": run_artifacts.SCHEMA_VERSION,
        "run_id": resolved_run_id,
        "status": "running",
        "started_at": run_artifacts.isoformat_utc(started_at),
        "search_terms": search_terms,
        "output_path": str(resolved_output_path),
    }
    try:
        run_artifacts.write_json_atomically(running_manifest, paths["manifest"])
    except Exception as exc:
        error = _sanitize_error_text(exc)
        return _build_result(
            status="failed",
            output_path=resolved_output_path,
            progress=progress,
            message=f"Pipeline failed while creating the run manifest: {error}",
            run_id=resolved_run_id,
            run_dir=run_dir,
            started_at=started_at,
            completed_at=clock(),
            partial_failures=partial_failures,
            error=error,
        )

    try:
        result = _run_pipeline_impl(
            search_terms=search_terms,
            output_path=resolved_output_path,
            discover_channels_fn=discover_channels_fn,
            scrape_videos_fn=scrape_videos_fn,
            process_data_fn=process_data_fn,
            visual_analysis_fn=visual_analysis_fn,
            comment_enrichment_fn=comment_enrichment_fn,
            progress=progress,
            run_id=resolved_run_id,
            run_dir=run_dir,
            started_at=started_at,
            clock=clock,
            partial_failures=partial_failures,
        )
    except Exception as exc:
        if isinstance(exc, StageFailure):
            partial_failures.extend(_sanitize_failures(exc.failures))
        safe_error = _sanitize_error_text(exc)
        message = f"Pipeline failed: {safe_error}"
        print(f"\n[ERROR] {message}")
        result = _build_result(
            status="failed",
            output_path=resolved_output_path,
            progress=progress,
            message=message,
            run_id=resolved_run_id,
            run_dir=run_dir,
            started_at=started_at,
            completed_at=clock(),
            partial_failures=partial_failures,
            error=safe_error,
        )

    try:
        _write_manifest(result, search_terms, paths["dashboard_snapshot"])
    except Exception as exc:
        error = _sanitize_error_text(exc)
        failed_result = replace(
            result,
            status="failed",
            rows_written=0,
            message=f"Pipeline failed while finalizing the manifest: {error}",
            error=error,
        )
        try:
            _write_manifest(
                failed_result,
                search_terms,
                paths["dashboard_snapshot"],
            )
        except Exception:
            pass
        return failed_result

    if result.status == "success" or (
        result.status == "partial" and result.rows_written > 0
    ):
        try:
            lock_paths = {
                resolved_runs_root / ".publish.lock",
                resolved_output_path.parent
                / f".{resolved_output_path.name}.publish.lock",
            }
            with ExitStack() as lock_stack:
                for lock_path in sorted(lock_paths, key=str):
                    lock_stack.enter_context(
                        FileLock(str(lock_path), timeout=publish_lock_timeout)
                    )
                previous_output = (
                    resolved_output_path.read_bytes()
                    if resolved_output_path.exists()
                    else None
                )
                try:
                    copy_file_atomically(
                        paths["dashboard_snapshot"],
                        resolved_output_path,
                    )
                    _write_latest_success(
                        result,
                        resolved_runs_root,
                        paths["dashboard_snapshot"],
                    )
                except Exception:
                    if previous_output is None:
                        resolved_output_path.unlink(missing_ok=True)
                    else:
                        write_bytes_atomically(previous_output, resolved_output_path)
                    raise
        except Exception as exc:
            error = (
                "Could not acquire the publish lock."
                if isinstance(exc, Timeout)
                else _sanitize_error_text(exc)
            )
            failed_result = replace(
                result,
                status="failed",
                rows_written=0,
                message=f"Pipeline failed while publishing latest output: {error}",
                error=error,
            )
            try:
                _write_manifest(
                    failed_result,
                    search_terms,
                    paths["dashboard_snapshot"],
                )
            except Exception:
                pass
            return failed_result
    return result


def main_cli():
    result = run_pipeline()
    usable = result.status == "success" or (
        result.status == "partial" and result.rows_written > 0
    )
    return 0 if usable else 1


if __name__ == "__main__":
    raise SystemExit(main_cli())
