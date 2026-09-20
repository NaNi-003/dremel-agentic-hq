import json
from pathlib import Path

import pytest
import roxy_workflow


def _context(tmp_path):
    return {
        "run_id": "run-1",
        "status": "success",
        "collected_at": "2026-09-20T00:00:00Z",
        "partial_failure_count": 0,
        "dashboard_snapshot": tmp_path / "snapshot.csv",
        "source_urls": {"video-1": "https://youtube.com/watch?v=video-1"},
    }


def test_coordinate_latest_builds_approved_carl_and_maya_flow_without_publishing(tmp_path, monkeypatch):
    calls = []
    context = _context(tmp_path)
    packet_path = tmp_path / "artifacts" / "reviews" / "run-1" / "review_packet.json"
    decision_path = packet_path.with_name("review_decision.json")
    brief_path = packet_path.with_name("maya_content_brief.json")

    monkeypatch.setattr(roxy_workflow.dashboard_evidence, "load_latest_evidence", lambda root: context)
    monkeypatch.setattr(
        roxy_workflow.phase3_review,
        "create_review_packet",
        lambda **kwargs: (packet_path.parent.mkdir(parents=True), packet_path.write_text("{}", encoding="utf-8"), packet_path)[-1],
    )
    monkeypatch.setattr(
        roxy_workflow.carl_integration,
        "request_carl_review",
        lambda **kwargs: {
            "decision": {
                "run_id": "run-1",
                "decision": "approve",
                "selected_candidate_id": "video-1",
            },
            "decision_path": decision_path,
        },
    )
    monkeypatch.setattr(
        roxy_workflow.maya_integration,
        "request_maya_brief",
        lambda **kwargs: {
            "brief": {"run_id": "run-1", "candidate_id": "video-1"},
            "brief_path": brief_path,
        },
    )
    monkeypatch.setattr(
        roxy_workflow.static_dashboard,
        "load_dashboard_payload",
        lambda **kwargs: ([{"video_id": "video-1"}], {"run_id": "run-1", "candidate_id": "video-1"}, {"run_id": "run-1"}),
    )
    monkeypatch.setattr(
        roxy_workflow.static_dashboard,
        "build_static_dashboard",
        lambda output, **kwargs: calls.append(("build", Path(output))) or Path(output),
    )

    result = roxy_workflow.coordinate_latest(
        project_root=tmp_path,
        output_dir=tmp_path / "dist",
        publish=False,
    )

    assert result["status"] == "ready_for_publish"
    assert result["run_id"] == "run-1"
    assert result["candidate_id"] == "video-1"
    assert calls == [("build", tmp_path / "dist")]
    assert result["site_url"] is None


def test_coordinate_latest_stops_when_carl_does_not_approve(tmp_path, monkeypatch):
    context = _context(tmp_path)
    packet_path = tmp_path / "artifacts" / "reviews" / "run-1" / "review_packet.json"
    decision_path = packet_path.with_name("review_decision.json")

    monkeypatch.setattr(roxy_workflow.dashboard_evidence, "load_latest_evidence", lambda root: context)
    monkeypatch.setattr(
        roxy_workflow.phase3_review,
        "create_review_packet",
        lambda **kwargs: (packet_path.parent.mkdir(parents=True), packet_path.write_text("{}", encoding="utf-8"), packet_path)[-1],
    )
    monkeypatch.setattr(
        roxy_workflow.carl_integration,
        "request_carl_review",
        lambda **kwargs: {
            "decision": {
                "run_id": "run-1",
                "decision": "needs_evidence",
                "selected_candidate_id": None,
            },
            "decision_path": decision_path,
        },
    )
    monkeypatch.setattr(
        roxy_workflow.maya_integration,
        "request_maya_brief",
        lambda **kwargs: (_ for _ in ()).throw(AssertionError("Maya must not run")),
    )

    result = roxy_workflow.coordinate_latest(project_root=tmp_path, output_dir=tmp_path / "dist")

    assert result["status"] == "blocked_by_carl"
    assert result["carl_decision"] == "needs_evidence"
    assert not (tmp_path / "dist").exists()


def test_maya_brief_must_match_carls_approved_candidate():
    decision = {"selected_candidate_id": "approved-video"}
    wrong_brief = {"run_id": "run-1", "candidate_id": "different-video"}

    with pytest.raises(roxy_workflow.RoxyWorkflowError, match="approved candidate"):
        roxy_workflow._ensure_brief_matches_approval(wrong_brief, decision, "run-1")


def test_existing_deployment_state_without_slug_fails_closed(tmp_path):
    state_path = tmp_path / "here_now_site.json"
    state_path.write_text(json.dumps({"provider": "here.now"}), encoding="utf-8")

    with pytest.raises(roxy_workflow.RoxyWorkflowError, match="valid slug"):
        roxy_workflow._deployment_slug(state_path)
