import json
import math
from pathlib import Path
from urllib.parse import urlparse

import pandas as pd


SCHEMA_VERSION = 1
ALLOWED_YOUTUBE_HOSTS = {"youtube.com", "www.youtube.com", "m.youtube.com", "youtu.be"}
DASHBOARD_REQUIRED_COLUMNS = {
    "action_pair",
    "velocity_score",
    "cv_emotion",
    "detected_material",
    "thumbnail_url",
    "cv_color_hex",
}


def _read_json(path):
    value = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise TypeError("JSON artifact must contain an object")
    return value


def _resolve_contained(base, reference, boundary):
    if not isinstance(reference, str) or not reference:
        raise TypeError("Artifact reference must be a non-empty string")
    candidate = Path(reference)
    if not candidate.is_absolute():
        candidate = Path(base) / candidate
    candidate = candidate.resolve()
    if not candidate.is_relative_to(Path(boundary).resolve()):
        raise ValueError("Artifact reference escapes the managed runs root")
    return candidate


def _youtube_source_url(value):
    if not isinstance(value, str):
        return None
    try:
        parsed = urlparse(value)
        hostname = parsed.hostname
    except ValueError:
        return None
    if parsed.scheme != "https" or hostname not in ALLOWED_YOUTUBE_HOSTS:
        return None
    return value


def latest_pointer_exists(runs_root="artifacts/runs"):
    return (Path(runs_root).resolve() / "latest_success.json").is_file()


def validate_dashboard_dataframe(frame):
    """Return a safe dashboard frame, or an empty frame for an invalid snapshot."""
    if not isinstance(frame, pd.DataFrame) or frame.empty:
        return pd.DataFrame()
    if not DASHBOARD_REQUIRED_COLUMNS.issubset(frame.columns):
        return pd.DataFrame()

    validated = frame.copy()
    numeric_velocity = pd.to_numeric(validated["velocity_score"], errors="coerce")
    if numeric_velocity.isna().any() or not numeric_velocity.map(math.isfinite).all():
        return pd.DataFrame()
    if (numeric_velocity < 0).any() or numeric_velocity.max() <= 0:
        return pd.DataFrame()
    validated["velocity_score"] = numeric_velocity

    text_columns = DASHBOARD_REQUIRED_COLUMNS - {"velocity_score"}
    if "video_id" in validated.columns:
        text_columns.add("video_id")
    for column in text_columns:
        if not validated[column].map(
            lambda value: isinstance(value, str) and bool(value.strip())
        ).all():
            return pd.DataFrame()
    return validated


def load_latest_evidence(runs_root="artifacts/runs"):
    """Load a validated latest-run summary without failing the dashboard."""
    runs_root = Path(runs_root).resolve()
    try:
        pointer = _read_json(runs_root / "latest_success.json")
        manifest_path = _resolve_contained(
            runs_root,
            pointer["manifest"],
            runs_root,
        )
        manifest = _read_json(manifest_path)
        run_dir = manifest_path.parent
        if pointer.get("schema_version") != SCHEMA_VERSION:
            raise ValueError("Unsupported pointer schema")
        if manifest.get("schema_version") != SCHEMA_VERSION:
            raise ValueError("Unsupported manifest schema")
        if pointer.get("run_id") != manifest.get("run_id"):
            raise ValueError("Latest pointer and manifest run IDs differ")
        if run_dir.name != manifest.get("run_id"):
            raise ValueError("Manifest path does not match its run ID")
        if manifest.get("status") not in {"success", "partial"}:
            raise ValueError("Latest pointer does not reference a usable run")
        if pointer.get("status") != manifest.get("status"):
            raise ValueError("Latest pointer and manifest statuses differ")
        artifacts = manifest["artifacts"]
        if not isinstance(artifacts, dict):
            raise TypeError("Manifest artifacts must be an object")
        evidence_path = _resolve_contained(
            run_dir,
            artifacts["evidence"],
            run_dir,
        )
        candidates_path = _resolve_contained(
            run_dir,
            artifacts["candidates"],
            run_dir,
        )
        dashboard_snapshot = _resolve_contained(
            run_dir,
            artifacts["dashboard_snapshot"],
            run_dir,
        )
        expected_snapshot_ref = (
            Path(manifest["run_id"]) / artifacts["dashboard_snapshot"]
        ).as_posix()
        if Path(pointer.get("dashboard_snapshot", "")).as_posix() != expected_snapshot_ref:
            raise ValueError("Latest pointer and manifest snapshots differ")
        if not dashboard_snapshot.is_file():
            raise OSError("Dashboard snapshot is missing")
        with dashboard_snapshot.open("rb") as snapshot_file:
            snapshot_file.read(1)
        evidence = _read_json(evidence_path)
        candidates = _read_json(candidates_path)
        for artifact in (evidence, candidates):
            if artifact.get("schema_version") != SCHEMA_VERSION:
                raise ValueError("Unsupported linked artifact schema")
            if artifact.get("run_id") != manifest.get("run_id"):
                raise ValueError("Linked artifact run ID differs")
        candidate_items = candidates.get("candidates", [])
        evidence_videos = evidence.get("videos", [])
        failures = manifest.get("partial_failures", [])
        counts = manifest.get("counts")
        if (
            not isinstance(candidate_items, list)
            or not isinstance(evidence_videos, list)
            or not isinstance(failures, list)
            or not isinstance(counts, dict)
        ):
            raise TypeError("Artifact collections must be arrays")
        videos_collected = counts.get("videos_collected")
        count_values = [counts.get("candidates_scored"), counts.get("rows_written")]
        if any(
            isinstance(value, bool) or not isinstance(value, int) or value < 0
            for value in [videos_collected, *count_values]
        ):
            raise TypeError("Manifest candidate counts must be non-negative integers")
        snapshot_frame = pd.read_csv(dashboard_snapshot)
        if "video_id" not in snapshot_frame.columns:
            raise ValueError("Dashboard snapshot is missing video IDs")

        evidence_ids = []
        for video in evidence_videos:
            if not isinstance(video, dict):
                raise TypeError("Evidence video entries must be objects")
            video_id = video.get("video_id")
            if not isinstance(video_id, str) or not video_id:
                raise TypeError("Evidence video IDs must be non-empty strings")
            evidence_ids.append(video_id)

        candidate_ids = []
        for candidate in candidate_items:
            if not isinstance(candidate, dict):
                raise TypeError("Candidate entries must be objects")
            video_id = candidate.get("video_id")
            source = candidate.get("source")
            if (
                not isinstance(video_id, str)
                or not video_id
                or not isinstance(source, dict)
                or source.get("video_id") != video_id
            ):
                raise ValueError("Candidate source linkage is invalid")
            candidate_ids.append(video_id)

        snapshot_ids = snapshot_frame["video_id"].tolist()
        if not all(isinstance(video_id, str) and video_id for video_id in snapshot_ids):
            raise TypeError("Dashboard video IDs must be non-empty strings")
        if len(set(candidate_ids)) != len(candidate_ids):
            raise ValueError("Candidate video IDs must be unique")
        if not set(candidate_ids).issubset(set(evidence_ids)):
            raise ValueError("Candidate IDs are missing from evidence")
        if candidate_ids != snapshot_ids:
            raise ValueError("Candidate and dashboard video IDs differ")
        if count_values != [len(candidate_items), len(snapshot_frame)]:
            raise ValueError("Manifest counts do not match linked artifacts")
    except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError):
        return None

    source_urls = {}
    for candidate in candidate_items:
        if not isinstance(candidate, dict):
            continue
        video_id = candidate.get("video_id")
        source = candidate.get("source")
        if not isinstance(video_id, str) or not video_id or not isinstance(source, dict):
            continue
        if source.get("video_id") != video_id:
            continue
        source_url = _youtube_source_url(source.get("source_url"))
        if video_id and source_url:
            source_urls[video_id] = source_url

    return {
        "run_id": manifest.get("run_id"),
        "status": manifest.get("status"),
        "collected_at": evidence.get("collected_at"),
        "partial_failure_count": len(failures),
        "videos_collected": videos_collected,
        "candidates_scored": counts.get("candidates_scored"),
        "source_urls": source_urls,
        "dashboard_snapshot": dashboard_snapshot,
    }
