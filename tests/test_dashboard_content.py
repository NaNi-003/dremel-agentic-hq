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


def test_load_maya_brief_accepts_professional_information_gap_contract(tmp_path):
    professional = json.loads(json.dumps(BRIEF))
    professional["brief"].update(
        {
            "objective": "Increase qualified interest.",
            "audience_insight": "DIYers want proof before replacing furniture.",
            "hook_options": ["Hook one", "Hook two", "Hook three"],
            "information_gap": {
                "known": "The surface is damaged.",
                "unknown": "Whether it can be restored.",
                "payoff": "Reveal the restored surface at the end.",
            },
            "product_role": "Support the demonstrated restoration step.",
            "success_metrics": ["Completion", "Saves", "Qualified comments"],
            "claims_guardrails": "Do not promise guaranteed results.",
            "key_beats": ["One", "Two", "Three", "Four", "Five"],
        }
    )
    path = tmp_path / "reviews" / "run-1" / "maya_content_brief.json"
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps(professional), encoding="utf-8")

    assert dashboard_content.load_maya_brief(tmp_path, "run-1") == professional


def test_load_maya_briefs_includes_legacy_and_primary_batch_artifacts(tmp_path):
    legacy_path = tmp_path / "reviews" / "run-1" / "maya_content_brief.json"
    legacy_path.parent.mkdir(parents=True)
    legacy_path.write_text(json.dumps(BRIEF), encoding="utf-8")
    batch_brief = json.loads(json.dumps(BRIEF))
    batch_brief["candidate_id"] = "video-2"
    batch_brief["source_decision"] = "primary_candidate_batch"
    batch_path = legacy_path.parent / "maya_briefs" / "video-2.json"
    batch_path.parent.mkdir()
    batch_path.write_text(json.dumps(batch_brief), encoding="utf-8")

    loaded = dashboard_content.load_maya_briefs(tmp_path, "run-1")

    assert set(loaded) == {"video-1", "video-2"}
    assert loaded["video-2"]["source_decision"] == "primary_candidate_batch"


def test_load_maya_briefs_rejects_batch_brief_with_too_few_key_beats(tmp_path):
    artifact = json.loads(json.dumps(BRIEF))
    artifact["source_decision"] = "primary_candidate_batch"
    artifact["brief"].update(
        {
            "objective": "Increase qualified interest.",
            "audience_insight": "DIYers want evidence before acting.",
            "hook_options": ["One", "Two", "Three"],
            "information_gap": {
                "known": "The object is damaged.",
                "unknown": "Whether it can be restored.",
                "payoff": "Reveal the result at the end.",
            },
            "product_role": "Support the visible restoration step.",
            "success_metrics": ["Completion", "Saves", "Comments"],
            "claims_guardrails": "Avoid unsupported claims.",
            "key_beats": ["One", "Two", "Three"],
        }
    )
    path = tmp_path / "reviews" / "run-1" / "maya_briefs" / "video-1.json"
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps(artifact), encoding="utf-8")

    assert dashboard_content.load_maya_briefs(tmp_path, "run-1") == {}


def test_format_maya_brief_produces_dashboard_ready_markdown():
    rendered = dashboard_content.format_maya_brief(BRIEF)

    assert "# Restore It" in rendered
    assert "## Hook" in rendered
    assert "1. Show damage" in rendered
    assert "## Thumbnail Direction" in rendered
