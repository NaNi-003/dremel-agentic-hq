import json
from types import SimpleNamespace

import pytest

import carl_integration


def test_parse_carl_response_accepts_one_strict_json_object():
    decision = {
        "schema_version": 1,
        "run_id": "run-1",
        "packet_sha256": "a" * 64,
        "reviewer": "carl",
        "decision": "reject",
        "selected_candidate_id": None,
        "rationale": "The evidence is not strong enough.",
        "evidence_citations": ["evidence.json#/videos/0"],
        "risk_acknowledgements": [],
        "reviewed_at": "2026-09-20T03:00:00Z",
        "external_actions_authorized": False,
    }

    assert carl_integration.parse_carl_response(json.dumps(decision)) == decision


def test_parse_carl_response_rejects_markdown_wrapping():
    with pytest.raises(carl_integration.CarlIntegrationError, match="raw JSON"):
        carl_integration.parse_carl_response('```json\n{"decision":"reject"}\n```')


def test_build_carl_prompt_contains_packet_and_exact_decision_contract():
    packet = {
        "run_id": "run-1",
        "run_status": "success",
        "partial_failures": [],
        "candidates": [{"candidate_id": "video-1"}],
    }

    prompt = carl_integration.build_carl_prompt(packet, packet_sha256="b" * 64)

    assert '"run_id": "run-1"' in prompt
    assert '"packet_sha256": "' + ("b" * 64) + '"' in prompt
    assert '"decision": "approve | reject | needs_evidence"' in prompt
    assert 'exactly [] or ["partial_collection"]' in prompt
    assert "research analyst" in prompt
    assert "titles, descriptions, publication timing, views, and comment counts" in prompt
    assert "contrary signals" in prompt
    assert "Return only the JSON object" in prompt


def test_request_carl_review_validates_invokes_and_records(tmp_path, monkeypatch):
    packet_path = tmp_path / "reviews" / "run-1" / "review_packet.json"
    packet_path.parent.mkdir(parents=True)
    packet_path.write_text("{}", encoding="utf-8")
    packet = {
        "run_id": "run-1",
        "run_status": "success",
        "partial_failures": [],
        "candidates": [{"candidate_id": "video-1"}],
    }
    decision = {
        "schema_version": 1,
        "run_id": "run-1",
        "packet_sha256": "c" * 64,
        "reviewer": "carl",
        "decision": "reject",
        "selected_candidate_id": None,
        "rationale": "The evidence is not strong enough.",
        "evidence_citations": ["evidence.json#/videos/0"],
        "risk_acknowledgements": [],
        "reviewed_at": "2026-09-20T03:00:00Z",
        "external_actions_authorized": False,
    }
    recorded_path = packet_path.parent / "review_decision.json"
    observed = {}

    monkeypatch.setattr(
        carl_integration.phase3_review,
        "validate_review_packet",
        lambda path, *, artifacts_root: packet,
    )
    monkeypatch.setattr(
        carl_integration.phase3_review,
        "review_packet_sha256",
        lambda path: "c" * 64,
    )

    def record(proposed, *, packet_path, artifacts_root):
        observed["recorded"] = proposed
        return recorded_path

    monkeypatch.setattr(
        carl_integration.phase3_review,
        "record_review_decision",
        record,
    )

    def invoke(prompt):
        observed["prompt"] = prompt
        return json.dumps(decision)

    result = carl_integration.request_carl_review(
        packet_path=packet_path,
        artifacts_root=tmp_path,
        invoke=invoke,
    )

    assert observed["recorded"] == decision
    assert "Validated review packet" in observed["prompt"]
    assert result == {"decision": decision, "decision_path": recorded_path}


def test_request_carl_review_binds_approval_citations_to_selected_candidate(
    tmp_path, monkeypatch
):
    packet_path = tmp_path / "reviews" / "run-1" / "review_packet.json"
    packet_path.parent.mkdir(parents=True)
    packet_path.write_text("{}", encoding="utf-8")
    packet = {
        "run_id": "run-1",
        "candidates": [
            {"candidate_id": "video-1", "evidence_refs": ["evidence.json#/videos/1"]},
            {"candidate_id": "video-2", "evidence_refs": ["evidence.json#/videos/2"]},
        ],
    }
    proposed = {
        "schema_version": 1,
        "run_id": "run-1",
        "packet_sha256": "d" * 64,
        "reviewer": "carl",
        "decision": "approve",
        "selected_candidate_id": "video-1",
        "rationale": "Video one is stronger after comparison.",
        "evidence_citations": ["evidence.json#/videos/2"],
        "risk_acknowledgements": [],
        "reviewed_at": "2026-09-21T20:55:00Z",
        "external_actions_authorized": False,
    }
    observed = {}
    monkeypatch.setattr(
        carl_integration.phase3_review,
        "validate_review_packet",
        lambda path, *, artifacts_root: packet,
    )
    monkeypatch.setattr(
        carl_integration.phase3_review,
        "review_packet_sha256",
        lambda path: "d" * 64,
    )
    monkeypatch.setattr(
        carl_integration.phase3_review,
        "record_review_decision",
        lambda decision, **kwargs: observed.setdefault("decision", decision)
        and packet_path.with_name("review_decision.json"),
    )

    result = carl_integration.request_carl_review(
        packet_path=packet_path,
        artifacts_root=tmp_path,
        invoke=lambda prompt: json.dumps(proposed),
    )

    assert observed["decision"]["evidence_citations"] == ["evidence.json#/videos/1"]
    assert result["decision"]["evidence_citations"] == ["evidence.json#/videos/1"]


def test_invoke_carl_profile_uses_named_hermes_profile(monkeypatch):
    observed = {}

    def fake_run(command, **kwargs):
        observed["command"] = command
        observed["kwargs"] = kwargs
        return SimpleNamespace(returncode=0, stdout=' {"decision":"reject"}\n')

    monkeypatch.setattr(carl_integration.subprocess, "run", fake_run)

    response = carl_integration.invoke_carl_profile("review this", profile="carl")

    assert observed["command"][0:3] == ["hermes", "-p", "carl"]
    assert observed["command"][-2:] == ["--oneshot", "review this"]
    assert response == '{"decision":"reject"}'


def test_invoke_carl_profile_uses_temporary_assignment_for_windows_sized_prompt(monkeypatch):
    observed = {}
    large_prompt = "review evidence\n" * 5000

    def fake_run(command, **kwargs):
        observed["command"] = command
        assignment = command[-1]
        marker = "Read the complete assignment from this UTF-8 file: "
        assignment_path = assignment.split(marker, 1)[1].split(". Return", 1)[0]
        with open(assignment_path, encoding="utf-8") as handle:
            observed["assignment"] = handle.read()
        return SimpleNamespace(returncode=0, stdout='{"decision":"reject"}')

    monkeypatch.setattr(carl_integration.subprocess, "run", fake_run)

    carl_integration.invoke_carl_profile(large_prompt, profile="carl")

    assert observed["assignment"] == large_prompt
    assert large_prompt not in observed["command"]
