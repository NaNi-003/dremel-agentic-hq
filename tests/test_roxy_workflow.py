import json
from datetime import datetime
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


def test_coordinate_latest_generates_all_primary_maya_briefs_before_build(
    tmp_path, monkeypatch
):
    calls = []
    generated_at_values = []
    context = _context(tmp_path)
    packet_path = tmp_path / "artifacts" / "reviews" / "run-1" / "review_packet.json"
    decision_path = packet_path.with_name("review_decision.json")

    monkeypatch.setattr(roxy_workflow.dashboard_evidence, "load_latest_evidence", lambda root: context)

    def create_packet(**kwargs):
        generated_at_values.append(kwargs["generated_at"])
        packet_path.parent.mkdir(parents=True)
        packet_path.write_text("{}", encoding="utf-8")
        return packet_path

    monkeypatch.setattr(roxy_workflow.phase3_review, "create_review_packet", create_packet)
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
    generated_briefs = {
        f"video-{index}": {"candidate_id": f"video-{index}"}
        for index in range(1, 16)
    }
    monkeypatch.setattr(
        roxy_workflow.maya_integration,
        "request_primary_briefs",
        lambda **kwargs: calls.append(("maya", kwargs))
        or {
            "run_id": "run-1",
            "brief_count": 15,
            "briefs": generated_briefs,
        },
    )
    monkeypatch.setattr(
        roxy_workflow.static_dashboard,
        "load_dashboard_payload",
        lambda **kwargs: ([{"video_id": "video-1"}], None, {"run_id": "run-1"}),
    )
    monkeypatch.setattr(
        roxy_workflow.dashboard_content,
        "load_maya_briefs",
        lambda root, run_id: generated_briefs,
    )
    monkeypatch.setattr(
        roxy_workflow.static_dashboard,
        "build_static_dashboard",
        lambda output, **kwargs: calls.append(("build", Path(output), kwargs)) or Path(output),
    )

    result = roxy_workflow.coordinate_latest(
        project_root=tmp_path,
        output_dir=tmp_path / "dist",
        publish=False,
    )

    assert result["status"] == "ready_for_publish"
    assert result["run_id"] == "run-1"
    assert result["candidate_id"] == "video-1"
    assert result["brief_count"] == 15
    assert calls[0][0] == "maya"
    assert calls[1][0:2] == ("build", tmp_path / "dist")
    assert calls[1][2]["briefs"] == generated_briefs
    assert len(generated_at_values) == 1
    assert isinstance(generated_at_values[0], datetime)
    assert generated_at_values[0].tzinfo is not None
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
