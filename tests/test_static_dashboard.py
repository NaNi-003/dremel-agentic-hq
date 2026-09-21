import json
from pathlib import Path

import pytest

import static_dashboard
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
    app_js = (output / "app.js").read_text(encoding="utf-8")
    assert "Predictive Trend Engine" in html
    assert "Autonomous Content Ideation" in html
    assert "Trend Lifecycle Matrix" in html
    assert "Auditable Intelligence Feed" in html
    assert "Thumbnail Signals" in html
    assert "Emotional Trigger" not in html
    assert "Campaign ROI Estimator" in html
    assert 'id="load-more"' in html
    assert 'id="inventory" type="number"' in html
    assert 'id="inventory-warning"' in html
    assert "state.data.maya_briefs" in app_js
    assert "Open Maya brief" in app_js
    assert "Maya brief unavailable" in app_js
    assert "Request brief through Roxy" not in app_js
    assert "Slack" not in app_js
    assert "Generate Content Brief" not in app_js
    assert "navigator.clipboard.writeText" not in app_js
    assert "Evidence collected:" not in app_js
    assert "This dataset is usable but collection was partial" not in app_js
    assert "const availableUnits = Math.max(values.inventory, 0);" in app_js
    assert "const fulfillableUnits = Math.min(projectedDemand, availableUnits);" in app_js
    assert "const unconstrainedRoi" in app_js
    assert "const constrainedRoi" in app_js
    assert "Unconstrained Campaign ROI" in app_js
    assert "Availability-Constrained ROI" in app_js
    assert "const fulfillableLabel" in app_js
    assert "Projected demand exceeds available inventory" in app_js
    assert "streamlit" not in html.lower()
    assert (output / "assets" / "dremel_logo.png").is_file()


def test_build_static_dashboard_embeds_validated_run_data(tmp_path):
    source = Path(__file__).parents[1] / "web_dashboard"
    output = tmp_path / "site"

    build_static_dashboard(
        output,
        rows=ROWS,
        brief=BRIEF,
        briefs={"video-1": BRIEF},
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
    assert payload["maya_briefs"] == {"video-1": BRIEF}


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


def test_dashboard_payload_exposes_collection_and_candidate_counts(tmp_path, monkeypatch):
    snapshot = tmp_path / "dashboard.csv"
    snapshot.write_text(
        "video_id,action_pair,velocity_score,cv_emotion,detected_material,thumbnail_url,cv_color_hex\n"
        "video-1,Restore Table,12.5,Energetic,Table,https://example.com/thumb.jpg,#123456\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(
        static_dashboard.dashboard_evidence,
        "load_latest_evidence",
        lambda root: {
            "run_id": "run-1",
            "collected_at": "2026-09-20T00:00:00Z",
            "status": "partial",
            "partial_failure_count": 4,
            "videos_collected": 170,
            "candidates_scored": 42,
            "dashboard_snapshot": snapshot,
            "source_urls": {"video-1": "https://youtube.com/watch?v=video-1"},
        },
    )

    _, _, run = static_dashboard.load_dashboard_payload(
        runs_root=tmp_path / "runs",
        artifacts_root=tmp_path / "artifacts",
    )

    assert run["videos_collected"] == 170
    assert run["candidates_scored"] == 42
