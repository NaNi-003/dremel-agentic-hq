import hashlib
import json
import os
import re
import tempfile
from datetime import datetime
from io import BytesIO
from pathlib import Path

from filelock import FileLock, Timeout
import pandas as pd

import run_artifacts


SCHEMA_VERSION = 1
_RUN_ID_PATTERN = re.compile(r"^[A-Za-z0-9._-]+$")


class ReviewValidationError(ValueError):
    pass


def _has_schema_version(document):
    value = document.get("schema_version")
    return type(value) is int and value == SCHEMA_VERSION


def _is_non_negative_int(value):
    return type(value) is int and value >= 0


def _read_file_bytes(path):
    try:
        return Path(path).read_bytes()
    except OSError as exc:
        raise ReviewValidationError(f"Unreadable artifact: {Path(path).name}") from exc


def _parse_json_object(raw_bytes, artifact_name):
    def reject_nonstandard_constant(value):
        raise ValueError(f"Non-standard JSON constant: {value}")

    try:
        payload = json.loads(raw_bytes, parse_constant=reject_nonstandard_constant)
    except (UnicodeError, json.JSONDecodeError, ValueError) as exc:
        raise ReviewValidationError(f"Invalid JSON artifact: {artifact_name}") from exc
    if not isinstance(payload, dict):
        raise ReviewValidationError(f"Artifact must be a JSON object: {artifact_name}")
    return payload


def _parse_aware_timestamp(value, field_name):
    if not isinstance(value, str) or not value:
        raise ReviewValidationError(f"{field_name} timestamp is invalid")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ReviewValidationError(f"{field_name} timestamp is invalid") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ReviewValidationError(f"{field_name} timestamp must be timezone-aware")
    return parsed


def _contained_file(base, reference):
    if not isinstance(reference, str) or not reference:
        raise ReviewValidationError("Artifact reference must be a non-empty string")
    base = Path(base).resolve()
    path = (base / reference).resolve()
    if not path.is_relative_to(base) or not path.is_file():
        raise ReviewValidationError("Artifact reference is missing or escapes its run")
    return path


def _build_candidate_summaries(
    evidence,
    candidates_document,
    *,
    evidence_name,
    candidates_name,
):
    evidence_videos = evidence.get("videos")
    candidate_items = candidates_document.get("candidates")
    if not isinstance(evidence_videos, list) or not isinstance(candidate_items, list):
        raise ReviewValidationError("Evidence and candidate collections must be arrays")
    evidence_indexes = {}
    for index, video in enumerate(evidence_videos):
        if not isinstance(video, dict):
            raise ReviewValidationError("Evidence entries must be objects")
        video_id = video.get("video_id")
        if not isinstance(video_id, str) or not video_id or video_id in evidence_indexes:
            raise ReviewValidationError("Evidence video IDs must be unique strings")
        evidence_indexes[video_id] = index

    summaries = []
    seen_candidate_ids = set()
    for index, candidate in enumerate(candidate_items):
        if not isinstance(candidate, dict):
            raise ReviewValidationError("Candidate entries must be objects")
        candidate_id = candidate.get("video_id")
        source = candidate.get("source")
        if (
            not isinstance(candidate_id, str)
            or not candidate_id
            or candidate_id in seen_candidate_ids
            or candidate_id not in evidence_indexes
            or not isinstance(source, dict)
            or source.get("video_id") != candidate_id
        ):
            raise ReviewValidationError("Candidate evidence linkage is invalid")
        if source != evidence_videos[evidence_indexes[candidate_id]]:
            raise ReviewValidationError("Candidate embedded source differs from evidence")
        seen_candidate_ids.add(candidate_id)
        summaries.append(
            {
                "candidate_id": candidate_id,
                "candidate_ref": f"{candidates_name}#/candidates/{index}",
                "evidence_refs": [
                    f"{evidence_name}#/videos/{evidence_indexes[candidate_id]}"
                ],
                "action_pair": candidate.get("action_pair"),
                "velocity_score": candidate.get("velocity_score"),
                "provenance": candidate.get("provenance"),
            }
        )
    if not summaries:
        raise ReviewValidationError("A review packet requires at least one candidate")
    return summaries


def _validate_manifest_status(manifest):
    status = manifest.get("status")
    failures = manifest.get("partial_failures")
    if not isinstance(failures, list):
        raise ReviewValidationError("Manifest partial failures must be an array")
    if status not in {"success", "partial"}:
        raise ReviewValidationError("Manifest does not represent a usable run")
    if (status == "success" and failures) or (status == "partial" and not failures):
        raise ReviewValidationError("Manifest status and failures are inconsistent")


def _sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def review_packet_sha256(packet_path):
    return _sha256(Path(packet_path).resolve())


def _write_json_exclusively(payload, path):
    path = Path(path).resolve()
    serialized = (
        json.dumps(payload, indent=2, sort_keys=True, allow_nan=False) + "\n"
    ).encode("utf-8")
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    temporary_path = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as destination:
            descriptor = None
            destination.write(serialized)
            destination.flush()
            os.fsync(destination.fileno())
        os.link(temporary_path, path)
    except FileExistsError as exc:
        raise ReviewValidationError("Review decision already exists") from exc
    finally:
        if descriptor is not None:
            os.close(descriptor)
        temporary_path.unlink(missing_ok=True)
    return path


def _validate_packet_location(packet_path, artifacts_root):
    packet_path = Path(packet_path).resolve()
    artifacts_root = Path(artifacts_root).resolve()
    if not packet_path.is_relative_to(artifacts_root) or not packet_path.is_file():
        raise ReviewValidationError("Review packet is outside the artifact root")
    if (
        packet_path.name != "review_packet.json"
        or packet_path.parent.parent != artifacts_root / "reviews"
        or not _RUN_ID_PATTERN.fullmatch(packet_path.parent.name)
    ):
        raise ReviewValidationError("Review packet location is not canonical")
    return packet_path, artifacts_root


def _validate_review_packet_snapshot(packet_path, *, artifacts_root):
    """Validate packet structure and prove every frozen source is unchanged."""
    packet_path, artifacts_root = _validate_packet_location(
        packet_path,
        artifacts_root,
    )
    packet_bytes = _read_file_bytes(packet_path)
    packet = _parse_json_object(packet_bytes, packet_path.name)
    packet_fields = {
        "schema_version",
        "run_id",
        "run_status",
        "generated_at",
        "review_state",
        "evidence_is_untrusted",
        "partial_failures",
        "source_artifacts",
        "candidates",
    }
    if set(packet) != packet_fields:
        raise ReviewValidationError("Review packet fields differ from the contract")
    if not _has_schema_version(packet):
        raise ReviewValidationError("Unsupported review packet schema")
    _parse_aware_timestamp(packet.get("generated_at"), "generated_at")
    run_id = packet.get("run_id")
    if not isinstance(run_id, str) or not _RUN_ID_PATTERN.fullmatch(run_id):
        raise ReviewValidationError("Invalid packet run ID")
    if packet_path.parent.name != run_id:
        raise ReviewValidationError("Review packet directory and run ID differ")
    if packet.get("review_state") != "pending":
        raise ReviewValidationError("Review packet is not pending")
    if packet.get("evidence_is_untrusted") is not True:
        raise ReviewValidationError("Review packet must label source evidence untrusted")

    source_artifacts = packet.get("source_artifacts")
    if not isinstance(source_artifacts, dict):
        raise ReviewValidationError("Review packet source artifacts must be an object")
    required_sources = {"manifest", "evidence", "candidates", "dashboard_snapshot"}
    if set(source_artifacts) != required_sources:
        raise ReviewValidationError("Review packet source inventory is incomplete")
    resolved_sources = {}
    source_snapshots = {}
    for source_name, source in source_artifacts.items():
        if not isinstance(source, dict):
            raise ReviewValidationError("Review packet source entry must be an object")
        if set(source) != {"path", "sha256", "bytes"}:
            raise ReviewValidationError("Review packet source fields differ from contract")
        reference = source.get("path")
        if not isinstance(reference, str) or not reference:
            raise ReviewValidationError("Review packet source path is invalid")
        source_path = (packet_path.parent / reference).resolve()
        if not source_path.is_relative_to(artifacts_root) or not source_path.is_file():
            raise ReviewValidationError("Review packet source path escapes or is missing")
        source_bytes = _read_file_bytes(source_path)
        expected_bytes = source.get("bytes")
        if (
            isinstance(expected_bytes, bool)
            or not isinstance(expected_bytes, int)
            or expected_bytes < 0
            or len(source_bytes) != expected_bytes
        ):
            raise ReviewValidationError(f"Source size mismatch: {source_name}")
        expected_digest = source.get("sha256")
        if (
            not isinstance(expected_digest, str)
            or not re.fullmatch(r"[0-9a-f]{64}", expected_digest)
            or hashlib.sha256(source_bytes).hexdigest() != expected_digest
        ):
            raise ReviewValidationError(f"Source digest mismatch: {source_name}")
        resolved_sources[source_name] = source_path
        source_snapshots[source_name] = source_bytes

    canonical_run_dir = artifacts_root / "runs" / run_id
    if resolved_sources["manifest"] != canonical_run_dir / "manifest.json":
        raise ReviewValidationError("Frozen sources are outside the canonical run directory")

    packet_candidates = packet.get("candidates")
    if not isinstance(packet_candidates, list) or not packet_candidates:
        raise ReviewValidationError("Review packet requires candidates")
    candidate_ids = []
    for candidate in packet_candidates:
        if not isinstance(candidate, dict):
            raise ReviewValidationError("Packet candidate entries must be objects")
        candidate_id = candidate.get("candidate_id")
        evidence_refs = candidate.get("evidence_refs")
        if (
            not isinstance(candidate_id, str)
            or not candidate_id
            or not isinstance(evidence_refs, list)
            or not evidence_refs
            or not all(isinstance(ref, str) and ref for ref in evidence_refs)
        ):
            raise ReviewValidationError("Packet candidate references are invalid")
        candidate_ids.append(candidate_id)
    if len(set(candidate_ids)) != len(candidate_ids):
        raise ReviewValidationError("Packet candidate IDs must be unique")
    manifest = _parse_json_object(
        source_snapshots["manifest"], resolved_sources["manifest"].name
    )
    evidence = _parse_json_object(
        source_snapshots["evidence"], resolved_sources["evidence"].name
    )
    candidates_document = _parse_json_object(
        source_snapshots["candidates"], resolved_sources["candidates"].name
    )
    for source_document in (manifest, evidence, candidates_document):
        if not _has_schema_version(source_document):
            raise ReviewValidationError("Unsupported frozen source schema")
        if source_document.get("run_id") != run_id:
            raise ReviewValidationError("Frozen source run ID differs")
    if packet.get("run_status") != manifest.get("status"):
        raise ReviewValidationError("Packet run status differs from its manifest")
    _validate_manifest_status(manifest)
    if packet.get("partial_failures") != manifest.get("partial_failures", []):
        raise ReviewValidationError("Packet failures differ from its manifest")
    manifest_artifacts = manifest.get("artifacts")
    if not isinstance(manifest_artifacts, dict):
        raise ReviewValidationError("Frozen manifest artifacts must be an object")
    artifact_reference_keys = {
        "evidence": "evidence",
        "candidates": "candidates",
        "dashboard_snapshot": "dashboard_snapshot",
    }
    manifest_dir = resolved_sources["manifest"].parent.resolve()
    for source_name, manifest_key in artifact_reference_keys.items():
        reference = manifest_artifacts.get(manifest_key)
        if not isinstance(reference, str) or not reference:
            raise ReviewValidationError("Frozen manifest artifact reference is invalid")
        expected_path = (manifest_dir / reference).resolve()
        if (
            not expected_path.is_relative_to(manifest_dir)
            or expected_path != resolved_sources[source_name]
        ):
            raise ReviewValidationError("Packet source differs from manifest reference")
    expected_candidates = _build_candidate_summaries(
        evidence,
        candidates_document,
        evidence_name=resolved_sources["evidence"].name,
        candidates_name=resolved_sources["candidates"].name,
    )
    if packet_candidates != expected_candidates:
        raise ReviewValidationError("Packet candidate summary differs from frozen sources")
    counts = manifest.get("counts")
    expected_count = len(expected_candidates)
    count_values = (
        counts.get("candidates_scored") if isinstance(counts, dict) else None,
        counts.get("rows_written") if isinstance(counts, dict) else None,
    )
    if (
        not all(_is_non_negative_int(value) for value in count_values)
        or list(count_values) != [expected_count, expected_count]
    ):
        raise ReviewValidationError("Frozen manifest counts differ from artifacts")
    try:
        dashboard_frame = pd.read_csv(BytesIO(source_snapshots["dashboard_snapshot"]))
    except (OSError, UnicodeError, ValueError) as exc:
        raise ReviewValidationError("Frozen dashboard snapshot is unreadable") from exc
    if "video_id" not in dashboard_frame.columns or dashboard_frame[
        "video_id"
    ].tolist() != [candidate["candidate_id"] for candidate in expected_candidates]:
        raise ReviewValidationError("Frozen dashboard candidate IDs differ")
    return packet, hashlib.sha256(packet_bytes).hexdigest()


def validate_review_packet(packet_path, *, artifacts_root):
    packet, _ = _validate_review_packet_snapshot(
        packet_path,
        artifacts_root=artifacts_root,
    )
    return packet


def validate_review_decision(decision, *, packet_path, artifacts_root):
    """Validate Carl's structured decision against one frozen packet."""
    if not isinstance(decision, dict):
        raise ReviewValidationError("Review decision must be an object")
    allowed_fields = {
        "schema_version",
        "run_id",
        "packet_sha256",
        "reviewer",
        "decision",
        "selected_candidate_id",
        "rationale",
        "evidence_citations",
        "risk_acknowledgements",
        "reviewed_at",
        "external_actions_authorized",
    }
    if set(decision) != allowed_fields:
        raise ReviewValidationError("Review decision fields differ from the contract")
    packet, validated_packet_digest = _validate_review_packet_snapshot(
        packet_path,
        artifacts_root=artifacts_root,
    )
    if not _has_schema_version(decision):
        raise ReviewValidationError("Unsupported review decision schema")
    if decision.get("run_id") != packet.get("run_id"):
        raise ReviewValidationError("Decision run ID differs from its packet")
    if decision.get("packet_sha256") != validated_packet_digest:
        raise ReviewValidationError("Decision packet digest differs")
    if decision.get("reviewer") != "carl":
        raise ReviewValidationError("Decision reviewer must be carl")
    outcome = decision.get("decision")
    if outcome not in {"approve", "reject", "needs_evidence"}:
        raise ReviewValidationError("Unsupported review decision")
    rationale = decision.get("rationale")
    if not isinstance(rationale, str) or not rationale.strip() or len(rationale) > 4000:
        raise ReviewValidationError("Decision rationale must be non-empty and bounded")
    citations = decision.get("evidence_citations")
    if (
        not isinstance(citations, list)
        or not citations
        or not all(isinstance(citation, str) and citation for citation in citations)
    ):
        raise ReviewValidationError("Decision requires evidence citations")
    _parse_aware_timestamp(decision.get("reviewed_at"), "Decision")
    if decision.get("external_actions_authorized") is not False:
        raise ReviewValidationError("Carl cannot authorize external actions")
    risk_acknowledgements = decision.get("risk_acknowledgements")
    if (
        not isinstance(risk_acknowledgements, list)
        or not all(item == "partial_collection" for item in risk_acknowledgements)
        or len(set(risk_acknowledgements)) != len(risk_acknowledgements)
    ):
        raise ReviewValidationError("Decision risk acknowledgements are invalid")
    if (
        outcome == "approve"
        and packet.get("partial_failures")
        and "partial_collection" not in risk_acknowledgements
    ):
        raise ReviewValidationError("Partial approval requires partial_collection acknowledgement")

    candidates_by_id = {
        candidate["candidate_id"]: candidate for candidate in packet["candidates"]
    }
    selected_candidate_id = decision.get("selected_candidate_id")
    if outcome == "approve":
        selected = candidates_by_id.get(selected_candidate_id)
        if selected is None:
            raise ReviewValidationError("Approved candidate is not in the packet")
        if not set(citations).issubset(set(selected["evidence_refs"])):
            raise ReviewValidationError("Approval cites evidence outside its candidate")
    elif selected_candidate_id is not None:
        raise ReviewValidationError("Only approvals may select a candidate")
    else:
        all_evidence_refs = {
            reference
            for candidate in packet["candidates"]
            for reference in candidate["evidence_refs"]
        }
        if not set(citations).issubset(all_evidence_refs):
            raise ReviewValidationError("Decision cites evidence outside its packet")
    return dict(decision)


def record_review_decision(
    decision,
    *,
    packet_path,
    artifacts_root,
    lock_timeout=10,
):
    """Persist one validated Carl decision without permitting replacement."""
    packet_path, _ = _validate_packet_location(packet_path, artifacts_root)
    decision_path = packet_path.parent / "review_decision.json"
    lock_path = packet_path.parent / ".review_decision.lock"
    try:
        with FileLock(str(lock_path), timeout=lock_timeout):
            if decision_path.exists():
                raise ReviewValidationError("Review decision already exists")
            validated = validate_review_decision(
                decision,
                packet_path=packet_path,
                artifacts_root=artifacts_root,
            )
            return _write_json_exclusively(validated, decision_path)
    except Timeout as exc:
        raise ReviewValidationError("Review decision lock is unavailable") from exc


def create_review_packet(*, runs_root, reviews_root, run_id, generated_at):
    """Create one immutable, source-bound review packet for a usable run."""
    if not isinstance(run_id, str) or not _RUN_ID_PATTERN.fullmatch(run_id):
        raise ReviewValidationError("Invalid run ID")

    runs_root = Path(runs_root).resolve()
    reviews_root = Path(reviews_root).resolve()
    if (
        runs_root.name != "runs"
        or reviews_root.name != "reviews"
        or runs_root.parent != reviews_root.parent
    ):
        raise ReviewValidationError("Configured artifact roots are not canonical")
    run_dir = (runs_root / run_id).resolve()
    if not run_dir.is_relative_to(runs_root) or not run_dir.is_dir():
        raise ReviewValidationError("Run directory does not exist")

    manifest_path = run_dir / "manifest.json"
    manifest_bytes = _read_file_bytes(manifest_path)
    manifest = _parse_json_object(manifest_bytes, manifest_path.name)
    if not _has_schema_version(manifest):
        raise ReviewValidationError("Unsupported manifest schema")
    if manifest.get("run_id") != run_id:
        raise ReviewValidationError("Manifest run ID differs")
    if manifest.get("status") not in {"success", "partial"}:
        raise ReviewValidationError("Only usable runs can be reviewed")
    _validate_manifest_status(manifest)

    artifact_refs = manifest.get("artifacts")
    if not isinstance(artifact_refs, dict):
        raise ReviewValidationError("Manifest artifacts must be an object")
    evidence_path = _contained_file(run_dir, artifact_refs.get("evidence"))
    candidates_path = _contained_file(run_dir, artifact_refs.get("candidates"))
    dashboard_path = _contained_file(run_dir, artifact_refs.get("dashboard_snapshot"))
    source_snapshots = {
        "manifest": manifest_bytes,
        "evidence": _read_file_bytes(evidence_path),
        "candidates": _read_file_bytes(candidates_path),
        "dashboard_snapshot": _read_file_bytes(dashboard_path),
    }
    evidence = _parse_json_object(source_snapshots["evidence"], evidence_path.name)
    candidates_document = _parse_json_object(
        source_snapshots["candidates"], candidates_path.name
    )
    for document in (evidence, candidates_document):
        if not _has_schema_version(document):
            raise ReviewValidationError("Unsupported linked artifact schema")
        if document.get("run_id") != run_id:
            raise ReviewValidationError("Linked artifact run ID differs")

    packet_candidates = _build_candidate_summaries(
        evidence,
        candidates_document,
        evidence_name=evidence_path.name,
        candidates_name=candidates_path.name,
    )
    counts = manifest.get("counts")
    if not isinstance(counts, dict):
        raise ReviewValidationError("Manifest counts must be an object")
    expected_counts = [len(packet_candidates), len(packet_candidates)]
    actual_counts = [counts.get("candidates_scored"), counts.get("rows_written")]
    if (
        not all(_is_non_negative_int(value) for value in actual_counts)
        or actual_counts != expected_counts
    ):
        raise ReviewValidationError("Manifest candidate counts do not match artifacts")
    try:
        dashboard_frame = pd.read_csv(BytesIO(source_snapshots["dashboard_snapshot"]))
    except (OSError, UnicodeError, ValueError) as exc:
        raise ReviewValidationError("Dashboard snapshot is unreadable") from exc
    if "video_id" not in dashboard_frame.columns:
        raise ReviewValidationError("Dashboard snapshot is missing video IDs")
    if dashboard_frame["video_id"].tolist() != [
        candidate["candidate_id"] for candidate in packet_candidates
    ]:
        raise ReviewValidationError("Dashboard candidate IDs do not match the packet")

    reviews_root.mkdir(parents=True, exist_ok=True)
    review_dir = reviews_root / run_id
    try:
        review_dir.mkdir()
    except FileExistsError as exc:
        raise ReviewValidationError("A review packet already exists for this run") from exc

    source_paths = {
        "manifest": manifest_path,
        "evidence": evidence_path,
        "candidates": candidates_path,
        "dashboard_snapshot": dashboard_path,
    }
    try:
        packet = {
            "schema_version": SCHEMA_VERSION,
            "run_id": run_id,
            "run_status": manifest["status"],
            "generated_at": run_artifacts.isoformat_utc(generated_at),
            "review_state": "pending",
            "evidence_is_untrusted": True,
            "partial_failures": manifest.get("partial_failures", []),
            "source_artifacts": {
                name: {
                    "path": Path(os.path.relpath(path, start=review_dir)).as_posix(),
                    "sha256": hashlib.sha256(source_snapshots[name]).hexdigest(),
                    "bytes": len(source_snapshots[name]),
                }
                for name, path in source_paths.items()
            },
            "candidates": packet_candidates,
        }
        return run_artifacts.write_json_atomically(
            packet,
            review_dir / "review_packet.json",
        )
    except Exception:
        for child in review_dir.iterdir():
            child.unlink(missing_ok=True)
        review_dir.rmdir()
        raise
