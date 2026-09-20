import json
from pathlib import Path

import pytest

from static_dashboard import build_static_dashboard


ROWS = [
    {
        "video_id": "video-1",
        "video_title": "Restore a Table",
        "thumbnail_url": "https://example.com/thumb.jpg",
        "action_pair": "Restore Table",
        "velocity_score": 13292.3,
        "cv_color_hex": "#846f5b",
        "cv_emotion": "Energetic",
        "source_url": "https://youtube.com/watch?v=video-1",
    }
]

BRIEF = {
    "schema_version": 1,
    "run_id": "run-1",
    "candidate_id": "video-1",
    "creator": "maya",
    "source_decision": "review_decision.json",
    "brief": {
        "title": "Can This Tired Table Be Restored?",
        "strategic_rationale": "The evidence supports a restoration story.",
        "audience": "New DIYers",
        "tone": "Bold and helpful",
        "hook": "What is hidden under this damaged surface?",
        "concept": "Restore the table before the final reveal.",
        "key_beats": ["Show damage", "Show process", "Reveal result"],
        "thumbnail_direction": "Show damage, not the result.",
        "call_to_action": "What would you restore?",
    },
}


def test_build_static_dashboard_preserves_original_sections(tmp_path):
    source = Path(__file__).parents[1] / "web_dashboard"
    output = tmp_path / "site"

    build_static_dashboard(
        output,
        rows=ROWS,
        brief=BRIEF,
        run_context={
            "run_id": "run-1",
            "collected_at": "2026-09-20T00:00:00Z",
            "status": "complete",
            "partial_failure_count": 0,
        },
        source_dir=source,
    )

    html = (output / "index.html").read_text(encoding="utf-8")
    assert "Predictive Trend Engine" in html
    assert "Autonomous Content Ideation" in html
    assert "Trend Lifecycle Matrix" in html
    assert "Raw Intelligence Feed" in html
    assert "Campaign ROI Estimator" in html
    assert "streamlit" not in html.lower()
    assert (output / "assets" / "dremel_logo.png").is_file()


def test_build_static_dashboard_embeds_validated_run_data(tmp_path):
    source = Path(__file__).parents[1] / "web_dashboard"
    output = tmp_path / "site"

    build_static_dashboard(
        output,
        rows=ROWS,
        brief=BRIEF,
        run_context={
            "run_id": "run-1",
            "collected_at": "2026-09-20T00:00:00Z",
            "status": "complete",
            "partial_failure_count": 0,
        },
        source_dir=source,
    )

    payload = json.loads((output / "data" / "dashboard.json").read_text(encoding="utf-8"))
    assert payload["run"]["run_id"] == "run-1"
    assert payload["rows"] == ROWS
    assert payload["maya_brief"] == BRIEF


def test_build_static_dashboard_omits_mismatched_brief(tmp_path):
    source = Path(__file__).parents[1] / "web_dashboard"
    output = tmp_path / "site"

    build_static_dashboard(
        output,
        rows=ROWS,
        brief=dict(BRIEF, candidate_id="other-video"),
        run_context={"run_id": "run-1"},
        source_dir=source,
    )

    payload = json.loads((output / "data" / "dashboard.json").read_text(encoding="utf-8"))
    assert payload["maya_brief"] is None


def test_build_static_dashboard_removes_unsafe_browser_values(tmp_path):
    source = Path(__file__).parents[1] / "web_dashboard"
    output = tmp_path / "site"
    unsafe_rows = [
        dict(
            ROWS[0],
            thumbnail_url='data:image/svg+xml,<svg onload="alert(1)"/>',
            source_url="javascript:alert(1)",
            cv_color_hex="red; background:url(javascript:alert(1))",
        )
    ]

    build_static_dashboard(
        output,
        rows=unsafe_rows,
        brief=None,
        run_context={"run_id": "run-1"},
        source_dir=source,
    )

    payload = json.loads((output / "data" / "dashboard.json").read_text(encoding="utf-8"))
    row = payload["rows"][0]
    assert row["thumbnail_url"] is None
    assert row["source_url"] is None
    assert row["cv_color_hex"] == "#cccccc"


def test_build_static_dashboard_rejects_empty_data_without_destroying_last_build(tmp_path):
    source = Path(__file__).parents[1] / "web_dashboard"
    output = tmp_path / "site"
    output.mkdir()
    marker = output / "last-good.txt"
    marker.write_text("keep", encoding="utf-8")

    with pytest.raises(ValueError, match="no validated rows"):
        build_static_dashboard(
            output,
            rows=[],
            brief=None,
            run_context={"run_id": "run-1"},
            source_dir=source,
        )

    assert marker.read_text(encoding="utf-8") == "keep"
