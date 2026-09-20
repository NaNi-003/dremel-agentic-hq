import json
import sys

from scripts import request_maya_brief


def test_request_maya_brief_cli_emits_generated_brief_result(tmp_path, monkeypatch, capsys):
    packet_path = tmp_path / "reviews" / "run-1" / "review_packet.json"
    decision_path = packet_path.with_name("review_decision.json")
    brief_path = packet_path.with_name("maya_content_brief.json")
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "request_maya_brief.py",
            "--packet",
            str(packet_path),
            "--decision",
            str(decision_path),
            "--artifacts-root",
            str(tmp_path),
        ],
    )
    monkeypatch.setattr(
        request_maya_brief.maya_integration,
        "request_maya_brief",
        lambda **kwargs: {
            "brief": {"run_id": "run-1", "candidate_id": "video-1"},
            "brief_path": brief_path,
        },
    )

    assert request_maya_brief.main_cli() == 0
    assert json.loads(capsys.readouterr().out) == {
        "brief_path": str(brief_path),
        "candidate_id": "video-1",
        "run_id": "run-1",
    }
