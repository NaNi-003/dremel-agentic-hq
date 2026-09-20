import json

import dashboard_content


BRIEF = {
    "schema_version": 1,
    "run_id": "run-1",
    "candidate_id": "video-1",
    "creator": "maya",
    "source_decision": "review_decision.json",
    "brief": {
        "title": "Restore It",
        "strategic_rationale": "A supported restoration story.",
        "audience": "New DIYers",
        "tone": "Bold and helpful",
        "hook": "What is hidden under this damaged surface?",
        "concept": "Restore the table before the final reveal.",
        "key_beats": ["Show damage", "Show process", "Reveal result"],
        "thumbnail_direction": "Show damage, not the result.",
        "call_to_action": "What would you restore?",
    },
}


def test_load_maya_brief_for_run_returns_valid_matching_artifact(tmp_path):
    path = tmp_path / "reviews" / "run-1" / "maya_content_brief.json"
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps(BRIEF), encoding="utf-8")

    assert dashboard_content.load_maya_brief(tmp_path, "run-1") == BRIEF


def test_load_maya_brief_for_run_rejects_wrong_run(tmp_path):
    path = tmp_path / "reviews" / "run-1" / "maya_content_brief.json"
    path.parent.mkdir(parents=True)
    wrong = dict(BRIEF, run_id="other-run")
    path.write_text(json.dumps(wrong), encoding="utf-8")

    assert dashboard_content.load_maya_brief(tmp_path, "run-1") is None


def test_format_maya_brief_produces_dashboard_ready_markdown():
    rendered = dashboard_content.format_maya_brief(BRIEF)

    assert "# Restore It" in rendered
    assert "## Hook" in rendered
    assert "1. Show damage" in rendered
    assert "## Thumbnail Direction" in rendered
