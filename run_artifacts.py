import json
import math
from datetime import timezone
from pathlib import Path
from tempfile import NamedTemporaryFile

import pandas as pd


SCHEMA_VERSION = 1
VELOCITY_METHOD = "age_adjusted_engagement_v1"


def isoformat_utc(value):
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("Timestamp must be timezone-aware")
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _json_safe(value):
    if value is None or value is pd.NA or value is pd.NaT:
        return None
    if isinstance(value, (str, int, bool)):
        return value
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    if hasattr(value, "item"):
        return _json_safe(value.item())
    return str(value)


def write_json_atomically(payload, path):
    path = Path(path).resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    with NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        dir=path.parent,
        prefix=f".{path.name}.",
        suffix=".tmp",
        delete=False,
    ) as temporary_file:
        temporary_path = Path(temporary_file.name)
        json.dump(
            _json_safe(payload),
            temporary_file,
            indent=2,
            sort_keys=True,
            allow_nan=False,
        )
        temporary_file.write("\n")

    try:
        temporary_path.replace(path)
    finally:
        temporary_path.unlink(missing_ok=True)
    return path


def create_run_directory(runs_root, run_id):
    runs_root = Path(runs_root).resolve()
    runs_root.mkdir(parents=True, exist_ok=True)
    run_dir = runs_root / run_id
    run_dir.mkdir()
    return run_dir


def build_evidence_document(run_id, channels, videos, collected_at):
    evidence_videos = []
    for video in videos:
        record = dict(video)
        video_id = record.get("video_id")
        record["source_url"] = (
            f"https://www.youtube.com/watch?v={video_id}" if video_id else None
        )
        record["transcript_status"] = (
            "available" if (record.get("transcript") or "").strip() else "unavailable"
        )
        record["collected_at"] = collected_at
        evidence_videos.append(record)

    return {
        "schema_version": SCHEMA_VERSION,
        "run_id": run_id,
        "collected_at": collected_at,
        "channels": list(channels),
        "videos": evidence_videos,
    }


def build_candidates_document(
    run_id,
    candidate_frame,
    evidence_videos,
    generated_at,
    extraction_sources=None,
):
    extraction_sources = extraction_sources or {}
    sources = {
        video.get("video_id"): dict(video)
        for video in evidence_videos
        if video.get("video_id")
    }
    candidates = []
    for row in candidate_frame.to_dict("records"):
        record = dict(row)
        video_id = record.get("video_id")
        extraction_source = record.pop(
            "extraction_source",
            extraction_sources.get(video_id, "unspecified"),
        )
        cv_method = record.pop("cv_method", "unspecified")
        record["source"] = sources.get(video_id, {"video_id": video_id})
        record["provenance"] = {
            "extraction_source": extraction_source,
            "cv_method": cv_method,
            "velocity_method": VELOCITY_METHOD,
        }
        candidates.append(record)

    return {
        "schema_version": SCHEMA_VERSION,
        "run_id": run_id,
        "generated_at": generated_at,
        "candidates": candidates,
    }
