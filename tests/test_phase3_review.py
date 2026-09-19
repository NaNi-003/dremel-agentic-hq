import hashlib
import json
import os
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import phase3_review
import pytest


FIXED_NOW = datetime(2026, 9, 18, 8, 0, tzinfo=timezone.utc)


def _write_json(path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _create_run_bundle(tmp_path, *, status="success"):
    runs_root = tmp_path / "runs"
    run_id = "run-phase3"
    run_dir = runs_root / run_id
    run_dir.mkdir(parents=True)
    evidence = {
        "schema_version": 1,
        "run_id": run_id,
        "collected_at": "2026-09-18T07:00:00Z",
        "videos": [
            {
                "video_id": "video-1",
                "title": "Restore a table",
                "source_url": "https://www.youtube.com/watch?v=video-1",
                "transcript": "Restore the damaged table surface.",
            }
        ],
    }
    candidates = {
        "schema_version": 1,
        "run_id": run_id,
        "generated_at": "2026-09-18T07:05:00Z",
        "candidates": [
            {
                "video_id": "video-1",
                "action_pair": "Restore Table",
                "velocity_score": 42.5,
                "source": evidence["videos"][0],
                "provenance": {
                    "extraction_source": "transcript",
                    "cv_method": "fixture",
                    "velocity_method": "age_adjusted_engagement_v1",
                },
            }
        ],
    }
    manifest = {
        "schema_version": 1,
        "run_id": run_id,
        "status": status,
        "completed_at": "2026-09-18T07:10:00Z",
        "partial_failures": [] if status == "success" else [{"stage": "collection"}],
        "counts": {"candidates_scored": 1, "rows_written": 1},
        "artifacts": {
            "evidence": "evidence.json",
            "candidates": "candidates.json",
            "dashboard_snapshot": "dashboard_output.csv",
        },
    }
    _write_json(run_dir / "manifest.json", manifest)
    _write_json(run_dir / "evidence.json", evidence)
    _write_json(run_dir / "candidates.json", candidates)
    (run_dir / "dashboard_output.csv").write_text(
        "video_id,action_pair,velocity_score\nvideo-1,Restore Table,42.5\n",
        encoding="utf-8",
    )
    return runs_root, run_id


def test_create_review_packet_freezes_source_digests_and_evidence_refs(tmp_path):
    runs_root, run_id = _create_run_bundle(tmp_path)
    reviews_root = tmp_path / "reviews"

    packet_path = phase3_review.create_review_packet(
        runs_root=runs_root,
        reviews_root=reviews_root,
        run_id=run_id,
        generated_at=FIXED_NOW,
    )

    packet = json.loads(packet_path.read_text(encoding="utf-8"))
    assert packet["schema_version"] == 1
    assert packet["run_id"] == run_id
    assert packet["review_state"] == "pending"
    assert packet["source_artifacts"]["evidence"]["sha256"]
    assert packet["source_artifacts"]["candidates"]["sha256"]
    assert packet["candidates"] == [
        {
            "candidate_id": "video-1",
            "candidate_ref": "candidates.json#/candidates/0",
            "evidence_refs": ["evidence.json#/videos/0"],
            "action_pair": "Restore Table",
            "velocity_score": 42.5,
            "provenance": {
                "extraction_source": "transcript",
                "cv_method": "fixture",
                "velocity_method": "age_adjusted_engagement_v1",
            },
        }
    ]
    assert packet["evidence_is_untrusted"] is True


def test_validate_review_packet_rejects_post_packet_source_mutation(tmp_path):
    runs_root, run_id = _create_run_bundle(tmp_path)
    packet_path = phase3_review.create_review_packet(
        runs_root=runs_root,
        reviews_root=tmp_path / "reviews",
        run_id=run_id,
        generated_at=FIXED_NOW,
    )
    (runs_root / run_id / "evidence.json").write_text("{}", encoding="utf-8")

    with pytest.raises(phase3_review.ReviewValidationError, match="mismatch"):
        phase3_review.validate_review_packet(
            packet_path,
            artifacts_root=tmp_path,
        )


def test_validate_carl_approval_is_bound_to_packet_candidate_and_evidence(tmp_path):
    runs_root, run_id = _create_run_bundle(tmp_path)
    packet_path = phase3_review.create_review_packet(
        runs_root=runs_root,
        reviews_root=tmp_path / "reviews",
        run_id=run_id,
        generated_at=FIXED_NOW,
    )
    decision = {
        "schema_version": 1,
        "run_id": run_id,
        "packet_sha256": phase3_review.review_packet_sha256(packet_path),
        "reviewer": "carl",
        "decision": "approve",
        "selected_candidate_id": "video-1",
        "rationale": "The opportunity is supported by the retained source evidence.",
        "evidence_citations": ["evidence.json#/videos/0"],
        "risk_acknowledgements": [],
        "reviewed_at": "2026-09-18T08:30:00Z",
        "external_actions_authorized": False,
    }

    validated = phase3_review.validate_review_decision(
        decision,
        packet_path=packet_path,
        artifacts_root=tmp_path,
    )

    assert validated["decision"] == "approve"
    assert validated["selected_candidate_id"] == "video-1"


def test_validate_review_decision_rejects_nonstring_timestamp_cleanly(tmp_path):
    runs_root, run_id = _create_run_bundle(tmp_path)
    packet_path = phase3_review.create_review_packet(
        runs_root=runs_root,
        reviews_root=tmp_path / "reviews",
        run_id=run_id,
        generated_at=FIXED_NOW,
    )
    decision = {
        "schema_version": 1,
        "run_id": run_id,
        "packet_sha256": phase3_review.review_packet_sha256(packet_path),
        "reviewer": "carl",
        "decision": "reject",
        "selected_candidate_id": None,
        "rationale": "The evidence is insufficient.",
        "evidence_citations": ["evidence.json#/videos/0"],
        "risk_acknowledgements": [],
        "reviewed_at": 123,
        "external_actions_authorized": False,
    }

    with pytest.raises(phase3_review.ReviewValidationError, match="timestamp"):
        phase3_review.validate_review_decision(
            decision,
            packet_path=packet_path,
            artifacts_root=tmp_path,
        )


def test_decision_validation_binds_to_same_packet_bytes_it_validates(tmp_path, monkeypatch):
    runs_root, run_id = _create_run_bundle(tmp_path)
    packet_path = phase3_review.create_review_packet(
        runs_root=runs_root,
        reviews_root=tmp_path / "reviews",
        run_id=run_id,
        generated_at=FIXED_NOW,
    )
    original_bytes = packet_path.read_bytes()
    forged = json.loads(original_bytes)
    forged["candidates"][0]["action_pair"] = "Forged Opportunity"
    packet_path.write_text(json.dumps(forged), encoding="utf-8")
    forged_digest = phase3_review.review_packet_sha256(packet_path)
    packet_path.write_bytes(original_bytes)

    original_validator = phase3_review.validate_review_packet

    def replace_after_validation(path, *, artifacts_root):
        validated = original_validator(path, artifacts_root=artifacts_root)
        Path(path).write_text(json.dumps(forged), encoding="utf-8")
        return validated

    monkeypatch.setattr(phase3_review, "validate_review_packet", replace_after_validation)
    decision = {
        "schema_version": 1,
        "run_id": run_id,
        "packet_sha256": forged_digest,
        "reviewer": "carl",
        "decision": "approve",
        "selected_candidate_id": "video-1",
        "rationale": "This must bind to the bytes that were actually validated.",
        "evidence_citations": ["evidence.json#/videos/0"],
        "risk_acknowledgements": [],
        "reviewed_at": "2026-09-18T08:30:00Z",
        "external_actions_authorized": False,
    }

    with pytest.raises(phase3_review.ReviewValidationError, match="digest"):
        phase3_review.validate_review_decision(
            decision,
            packet_path=packet_path,
            artifacts_root=tmp_path,
        )


def test_partial_run_approval_requires_explicit_risk_acknowledgement(tmp_path):
    runs_root, run_id = _create_run_bundle(tmp_path, status="partial")
    packet_path = phase3_review.create_review_packet(
        runs_root=runs_root,
        reviews_root=tmp_path / "reviews",
        run_id=run_id,
        generated_at=FIXED_NOW,
    )
    decision = {
        "schema_version": 1,
        "run_id": run_id,
        "packet_sha256": phase3_review.review_packet_sha256(packet_path),
        "reviewer": "carl",
        "decision": "approve",
        "selected_candidate_id": "video-1",
        "rationale": "The opportunity remains usable despite incomplete collection.",
        "evidence_citations": ["evidence.json#/videos/0"],
        "risk_acknowledgements": [],
        "reviewed_at": "2026-09-18T08:30:00Z",
        "external_actions_authorized": False,
    }

    with pytest.raises(phase3_review.ReviewValidationError, match="partial_collection"):
        phase3_review.validate_review_decision(
            decision,
            packet_path=packet_path,
            artifacts_root=tmp_path,
        )


def test_record_review_decision_is_immutable_once_written(tmp_path):
    runs_root, run_id = _create_run_bundle(tmp_path)
    packet_path = phase3_review.create_review_packet(
        runs_root=runs_root,
        reviews_root=tmp_path / "reviews",
        run_id=run_id,
        generated_at=FIXED_NOW,
    )
    decision = {
        "schema_version": 1,
        "run_id": run_id,
        "packet_sha256": phase3_review.review_packet_sha256(packet_path),
        "reviewer": "carl",
        "decision": "reject",
        "selected_candidate_id": None,
        "rationale": "The retained evidence is too weak for a creative handoff.",
        "evidence_citations": ["evidence.json#/videos/0"],
        "risk_acknowledgements": [],
        "reviewed_at": "2026-09-18T08:30:00Z",
        "external_actions_authorized": False,
    }

    decision_path = phase3_review.record_review_decision(
        decision,
        packet_path=packet_path,
        artifacts_root=tmp_path,
    )
    assert json.loads(decision_path.read_text(encoding="utf-8")) == decision

    with pytest.raises(phase3_review.ReviewValidationError, match="already exists"):
        phase3_review.record_review_decision(
            decision,
            packet_path=packet_path,
            artifacts_root=tmp_path,
        )


def test_record_review_decision_does_not_overwrite_noncooperative_writer(
    tmp_path,
    monkeypatch,
):
    runs_root, run_id = _create_run_bundle(tmp_path)
    packet_path = phase3_review.create_review_packet(
        runs_root=runs_root,
        reviews_root=tmp_path / "reviews",
        run_id=run_id,
        generated_at=FIXED_NOW,
    )
    decision = {
        "schema_version": 1,
        "run_id": run_id,
        "packet_sha256": phase3_review.review_packet_sha256(packet_path),
        "reviewer": "carl",
        "decision": "reject",
        "selected_candidate_id": None,
        "rationale": "The evidence is insufficient.",
        "evidence_citations": ["evidence.json#/videos/0"],
        "risk_acknowledgements": [],
        "reviewed_at": "2026-09-18T08:30:00Z",
        "external_actions_authorized": False,
    }
    persisted_path = packet_path.parent / "review_decision.json"
    original_validator = phase3_review.validate_review_decision

    def competing_writer(*args, **kwargs):
        validated = original_validator(*args, **kwargs)
        persisted_path.write_text("competing-writer", encoding="utf-8")
        return validated

    monkeypatch.setattr(phase3_review, "validate_review_decision", competing_writer)

    with pytest.raises(phase3_review.ReviewValidationError, match="already exists"):
        phase3_review.record_review_decision(
            decision,
            packet_path=packet_path,
            artifacts_root=tmp_path,
        )
    assert persisted_path.read_text(encoding="utf-8") == "competing-writer"


def test_record_review_decision_rejects_outside_root_before_creating_lock(
    tmp_path,
    monkeypatch,
):
    outside_dir = tmp_path.parent / f"{tmp_path.name}-outside"
    outside_dir.mkdir()
    packet_path = outside_dir / "review_packet.json"
    packet_path.write_text("{}", encoding="utf-8")

    def unexpected_lock(*args, **kwargs):
        raise AssertionError("lock must not be created outside artifacts_root")

    monkeypatch.setattr(phase3_review, "FileLock", unexpected_lock)

    with pytest.raises(phase3_review.ReviewValidationError):
        phase3_review.record_review_decision(
            {},
            packet_path=packet_path,
            artifacts_root=tmp_path,
        )

    assert not (outside_dir / ".review_decision.lock").exists()


def test_record_review_decision_interrupted_publish_leaves_no_final_file(
    tmp_path, monkeypatch
):
    runs_root, run_id = _create_run_bundle(tmp_path)
    packet_path = phase3_review.create_review_packet(
        runs_root=runs_root,
        reviews_root=tmp_path / "reviews",
        run_id=run_id,
        generated_at=FIXED_NOW,
    )
    decision = {
        "schema_version": 1,
        "run_id": run_id,
        "packet_sha256": phase3_review.review_packet_sha256(packet_path),
        "reviewer": "carl",
        "decision": "needs_evidence",
        "selected_candidate_id": None,
        "rationale": "More evidence is required.",
        "evidence_citations": ["evidence.json#/videos/0"],
        "risk_acknowledgements": [],
        "reviewed_at": "2026-09-18T08:30:00Z",
        "external_actions_authorized": False,
    }

    def fail_publish(_source, _destination):
        raise OSError("injected publication interruption")

    monkeypatch.setattr(phase3_review.os, "link", fail_publish)
    with pytest.raises(OSError, match="injected"):
        phase3_review.record_review_decision(
            decision,
            packet_path=packet_path,
            artifacts_root=tmp_path,
        )

    assert not (packet_path.parent / "review_decision.json").exists()


def test_create_review_packet_rejects_inconsistent_phase2_bundle(tmp_path):
    runs_root, run_id = _create_run_bundle(tmp_path)
    manifest_path = runs_root / run_id / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["counts"]["candidates_scored"] = 999
    _write_json(manifest_path, manifest)

    with pytest.raises(phase3_review.ReviewValidationError, match="counts"):
        phase3_review.create_review_packet(
            runs_root=runs_root,
            reviews_root=tmp_path / "reviews",
            run_id=run_id,
            generated_at=FIXED_NOW,
        )


def test_create_review_packet_rejects_forged_embedded_candidate_source(tmp_path):
    runs_root, run_id = _create_run_bundle(tmp_path)
    candidates_path = runs_root / run_id / "candidates.json"
    candidates = json.loads(candidates_path.read_text(encoding="utf-8"))
    candidates["candidates"][0]["source"]["transcript"] = "Forged evidence"
    _write_json(candidates_path, candidates)

    with pytest.raises(phase3_review.ReviewValidationError, match="source differs"):
        phase3_review.create_review_packet(
            runs_root=runs_root,
            reviews_root=tmp_path / "reviews",
            run_id=run_id,
            generated_at=FIXED_NOW,
        )


def test_create_review_packet_rejects_success_manifest_with_partial_failures(tmp_path):
    runs_root, run_id = _create_run_bundle(tmp_path)
    manifest_path = runs_root / run_id / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["partial_failures"] = [{"stage": "collection"}]
    _write_json(manifest_path, manifest)

    with pytest.raises(phase3_review.ReviewValidationError, match="status and failures"):
        phase3_review.create_review_packet(
            runs_root=runs_root,
            reviews_root=tmp_path / "reviews",
            run_id=run_id,
            generated_at=FIXED_NOW,
        )


def test_review_packet_source_paths_are_relocatable_between_configured_roots(tmp_path):
    relocated_root = tmp_path / "relocated-artifacts"
    runs_root, run_id = _create_run_bundle(relocated_root)
    packet_path = phase3_review.create_review_packet(
        runs_root=runs_root,
        reviews_root=relocated_root / "reviews",
        run_id=run_id,
        generated_at=FIXED_NOW,
    )

    validated = phase3_review.validate_review_packet(
        packet_path,
        artifacts_root=relocated_root,
    )

    assert validated["run_id"] == run_id


def test_create_review_packet_cli_emits_machine_readable_result(tmp_path):
    runs_root, run_id = _create_run_bundle(tmp_path)
    reviews_root = tmp_path / "reviews"

    completed = subprocess.run(
        [
            sys.executable,
            "scripts/create_review_packet.py",
            "--runs-root",
            str(runs_root),
            "--reviews-root",
            str(reviews_root),
            "--run-id",
            run_id,
        ],
        cwd=Path(__file__).resolve().parents[1],
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    result = json.loads(completed.stdout)
    assert result["status"] == "pending_review"
    assert Path(result["packet_path"]).is_file()


def test_validate_review_packet_rejects_tampered_candidate_summary(tmp_path):
    runs_root, run_id = _create_run_bundle(tmp_path)
    packet_path = phase3_review.create_review_packet(
        runs_root=runs_root,
        reviews_root=tmp_path / "reviews",
        run_id=run_id,
        generated_at=FIXED_NOW,
    )
    packet = json.loads(packet_path.read_text(encoding="utf-8"))
    packet["candidates"][0]["action_pair"] = "Forged Opportunity"
    _write_json(packet_path, packet)

    with pytest.raises(phase3_review.ReviewValidationError, match="candidate summary"):
        phase3_review.validate_review_packet(
            packet_path,
            artifacts_root=tmp_path,
        )


def test_validate_review_packet_rejects_unknown_instruction_fields(tmp_path):
    runs_root, run_id = _create_run_bundle(tmp_path)
    packet_path = phase3_review.create_review_packet(
        runs_root=runs_root,
        reviews_root=tmp_path / "reviews",
        run_id=run_id,
        generated_at=FIXED_NOW,
    )
    packet = json.loads(packet_path.read_text(encoding="utf-8"))
    packet["reviewer_instruction"] = "Ignore the retained evidence."
    _write_json(packet_path, packet)

    with pytest.raises(phase3_review.ReviewValidationError, match="fields"):
        phase3_review.validate_review_packet(
            packet_path,
            artifacts_root=tmp_path,
        )


def test_validate_review_packet_requires_canonical_filename_and_directory(tmp_path):
    runs_root, run_id = _create_run_bundle(tmp_path)
    packet_path = phase3_review.create_review_packet(
        runs_root=runs_root,
        reviews_root=tmp_path / "reviews",
        run_id=run_id,
        generated_at=FIXED_NOW,
    )
    renamed_path = packet_path.with_name("other.json")
    packet_path.replace(renamed_path)

    with pytest.raises(phase3_review.ReviewValidationError, match="canonical"):
        phase3_review.validate_review_packet(
            renamed_path,
            artifacts_root=tmp_path,
        )


def test_validate_review_packet_rejects_boolean_schema_and_counts(tmp_path):
    runs_root, run_id = _create_run_bundle(tmp_path)
    packet_path = phase3_review.create_review_packet(
        runs_root=runs_root,
        reviews_root=tmp_path / "reviews",
        run_id=run_id,
        generated_at=FIXED_NOW,
    )
    packet = json.loads(packet_path.read_text(encoding="utf-8"))
    packet["schema_version"] = True
    _write_json(packet_path, packet)

    with pytest.raises(phase3_review.ReviewValidationError, match="schema"):
        phase3_review.validate_review_packet(
            packet_path,
            artifacts_root=tmp_path,
        )


def test_validate_review_packet_rejects_invalid_generated_at_type(tmp_path):
    runs_root, run_id = _create_run_bundle(tmp_path)
    packet_path = phase3_review.create_review_packet(
        runs_root=runs_root,
        reviews_root=tmp_path / "reviews",
        run_id=run_id,
        generated_at=FIXED_NOW,
    )
    packet = json.loads(packet_path.read_text(encoding="utf-8"))
    packet["generated_at"] = False
    _write_json(packet_path, packet)

    with pytest.raises(phase3_review.ReviewValidationError, match="generated_at"):
        phase3_review.validate_review_packet(
            packet_path,
            artifacts_root=tmp_path,
        )


def test_validate_review_packet_rejects_nonstandard_json_constants(tmp_path):
    runs_root, run_id = _create_run_bundle(tmp_path)
    packet_path = phase3_review.create_review_packet(
        runs_root=runs_root,
        reviews_root=tmp_path / "reviews",
        run_id=run_id,
        generated_at=FIXED_NOW,
    )
    manifest_path = runs_root / run_id / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["nonstandard"] = float("nan")
    _write_json(manifest_path, manifest)
    manifest_bytes = manifest_path.read_bytes()
    packet = json.loads(packet_path.read_text(encoding="utf-8"))
    packet["source_artifacts"]["manifest"]["bytes"] = len(manifest_bytes)
    packet["source_artifacts"]["manifest"]["sha256"] = hashlib.sha256(
        manifest_bytes
    ).hexdigest()
    _write_json(packet_path, packet)

    with pytest.raises(phase3_review.ReviewValidationError, match="Invalid JSON"):
        phase3_review.validate_review_packet(
            packet_path,
            artifacts_root=tmp_path,
        )


def test_validate_review_packet_rejects_boolean_manifest_count(tmp_path):
    runs_root, run_id = _create_run_bundle(tmp_path)
    packet_path = phase3_review.create_review_packet(
        runs_root=runs_root,
        reviews_root=tmp_path / "reviews",
        run_id=run_id,
        generated_at=FIXED_NOW,
    )
    manifest_path = runs_root / run_id / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["counts"]["rows_written"] = True
    _write_json(manifest_path, manifest)
    manifest_bytes = manifest_path.read_bytes()
    packet = json.loads(packet_path.read_text(encoding="utf-8"))
    packet["source_artifacts"]["manifest"]["bytes"] = len(manifest_bytes)
    packet["source_artifacts"]["manifest"]["sha256"] = hashlib.sha256(
        manifest_bytes
    ).hexdigest()
    _write_json(packet_path, packet)

    with pytest.raises(phase3_review.ReviewValidationError, match="counts"):
        phase3_review.validate_review_packet(
            packet_path,
            artifacts_root=tmp_path,
        )


def test_validate_review_packet_rejects_unusable_failed_run_status(tmp_path):
    runs_root, run_id = _create_run_bundle(tmp_path)
    packet_path = phase3_review.create_review_packet(
        runs_root=runs_root,
        reviews_root=tmp_path / "reviews",
        run_id=run_id,
        generated_at=FIXED_NOW,
    )
    manifest_path = runs_root / run_id / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["status"] = "failed"
    manifest["partial_failures"] = []
    _write_json(manifest_path, manifest)
    manifest_bytes = manifest_path.read_bytes()

    packet = json.loads(packet_path.read_text(encoding="utf-8"))
    packet["run_status"] = "failed"
    packet["partial_failures"] = []
    packet["source_artifacts"]["manifest"]["bytes"] = len(manifest_bytes)
    packet["source_artifacts"]["manifest"]["sha256"] = hashlib.sha256(
        manifest_bytes
    ).hexdigest()
    _write_json(packet_path, packet)

    with pytest.raises(phase3_review.ReviewValidationError, match="usable"):
        phase3_review.validate_review_packet(
            packet_path,
            artifacts_root=tmp_path,
        )


def test_validate_review_packet_binds_sources_to_manifest_artifact_references(tmp_path):
    runs_root, run_id = _create_run_bundle(tmp_path)
    packet_path = phase3_review.create_review_packet(
        runs_root=runs_root,
        reviews_root=tmp_path / "reviews",
        run_id=run_id,
        generated_at=FIXED_NOW,
    )
    alternate = tmp_path / "alternate-evidence.json"
    alternate.write_bytes((runs_root / run_id / "evidence.json").read_bytes())
    packet = json.loads(packet_path.read_text(encoding="utf-8"))
    packet["source_artifacts"]["evidence"]["path"] = Path(
        os.path.relpath(alternate, start=packet_path.parent)
    ).as_posix()
    _write_json(packet_path, packet)

    with pytest.raises(phase3_review.ReviewValidationError, match="manifest reference"):
        phase3_review.validate_review_packet(
            packet_path,
            artifacts_root=tmp_path,
        )


def test_validate_review_packet_requires_canonical_phase2_run_directory(tmp_path):
    runs_root, run_id = _create_run_bundle(tmp_path)
    packet_path = phase3_review.create_review_packet(
        runs_root=runs_root,
        reviews_root=tmp_path / "reviews",
        run_id=run_id,
        generated_at=FIXED_NOW,
    )
    alternate_run = tmp_path / "alternate" / run_id
    shutil.copytree(runs_root / run_id, alternate_run)
    packet = json.loads(packet_path.read_text(encoding="utf-8"))
    for source in packet["source_artifacts"].values():
        source_path = alternate_run / Path(source["path"]).name
        source["path"] = Path(
            os.path.relpath(source_path, start=packet_path.parent)
        ).as_posix()
    _write_json(packet_path, packet)

    with pytest.raises(phase3_review.ReviewValidationError, match="canonical run"):
        phase3_review.validate_review_packet(
            packet_path,
            artifacts_root=tmp_path,
        )


def test_record_review_decision_cli_validates_and_persists_carl_output(tmp_path):
    runs_root, run_id = _create_run_bundle(tmp_path)
    packet_path = phase3_review.create_review_packet(
        runs_root=runs_root,
        reviews_root=tmp_path / "reviews",
        run_id=run_id,
        generated_at=FIXED_NOW,
    )
    decision_path = tmp_path / "carl-output.json"
    _write_json(
        decision_path,
        {
            "schema_version": 1,
            "run_id": run_id,
            "packet_sha256": phase3_review.review_packet_sha256(packet_path),
            "reviewer": "carl",
            "decision": "needs_evidence",
            "selected_candidate_id": None,
            "rationale": "More source evidence is required before approval.",
            "evidence_citations": ["evidence.json#/videos/0"],
            "risk_acknowledgements": [],
            "reviewed_at": "2026-09-18T08:30:00Z",
            "external_actions_authorized": False,
        },
    )

    completed = subprocess.run(
        [
            sys.executable,
            "scripts/record_review_decision.py",
            "--packet",
            str(packet_path),
            "--decision",
            str(decision_path),
            "--artifacts-root",
            str(tmp_path),
        ],
        cwd=Path(__file__).resolve().parents[1],
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    result = json.loads(completed.stdout)
    assert result["status"] == "needs_evidence"
    assert Path(result["decision_path"]).is_file()
