import json
import sys
from pathlib import Path

from scripts import request_carl_review


def test_request_carl_review_cli_emits_recorded_decision_result(tmp_path, monkeypatch, capsys):
    packet_path = tmp_path / "reviews" / "run-1" / "review_packet.json"
    decision_path = packet_path.parent / "review_decision.json"
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "request_carl_review.py",
            "--packet",
            str(packet_path),
            "--artifacts-root",
            str(tmp_path),
        ],
    )
    monkeypatch.setattr(
        request_carl_review.carl_integration,
        "request_carl_review",
        lambda **kwargs: {
            "decision": {"run_id": "run-1", "decision": "reject"},
            "decision_path": decision_path,
        },
    )

    assert request_carl_review.main_cli() == 0
    output = json.loads(capsys.readouterr().out)
    assert output == {
        "decision": "reject",
        "decision_path": str(decision_path),
        "run_id": "run-1",
    }
