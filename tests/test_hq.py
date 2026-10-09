import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

import hq.cli
import hq.tools
import main
import nlp_engine


FIXTURES = hq.tools.FIXTURE_VIDEOS


def invoke(argv, capsys):
    code = hq.cli.main(argv)
    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    return code, payload


def collect_fixture(tmp_path, capsys):
    runs = tmp_path / "runs"
    code, payload = invoke(
        [
            "collect",
            "--fixture",
            "--refresh",
            "--runs-root",
            str(runs),
            "--output",
            str(tmp_path / "out.csv"),
        ],
        capsys,
    )
    assert code == 0, payload
    assert payload["ok"] is True
    return runs, payload


def _decision(candidate_id="fixture-restore-table", **overrides):
    payload = {
        "candidate_id": candidate_id,
        "decision": "approve",
        "rationale": "The transcript shows a table being restored.",
        "evidence_refs": ["transcript", "score"],
    }
    payload.update(overrides)
    return payload


def _brief(candidate_id="fixture-restore-table", **overrides):
    payload = {
        "candidate_id": candidate_id,
        "title": "Restore the worn table",
        "strategic_rationale": "The transcript shows a restoration, which can demonstrate a Dremel step.",
        "audience": "DIYer New",
        "tone": "Helpful and specific",
        "hook": "The top looks finished. The edge does not.",
        "concept": "Open on the worn edge, then show one precise sanding pass.",
        "key_beats": ["Show the worn edge", "Sand one pass", "Hold the reveal"],
        "thumbnail_direction": "Use the dark palette as a style reference, not as audience emotion.",
        "call_to_action": "Ask which edge they would restore first.",
    }
    payload.update(overrides)
    return payload


def _write(path, payload):
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_collect_reuses_a_fresh_run_and_marks_an_old_one_stale(tmp_path, capsys, monkeypatch):
    runs, first = collect_fixture(tmp_path, capsys)
    assert first["status"] == "fresh"
    assert first["freshness"] == "fresh"
    assert first["reused"] is False
    assert first["collected_at"]

    def fail_live(**kwargs):
        raise AssertionError("fresh reuse must not collect again")

    monkeypatch.setattr(hq.tools, "_run_live", fail_live)
    code, reused = invoke(
        ["collect", "--runs-root", str(runs), "--output", str(tmp_path / "again.csv")],
        capsys,
    )
    assert code == 0
    assert reused["reused"] is True
    assert reused["status"] == "fresh"
    assert reused["run_id"] == first["run_id"]

    code, stale = invoke(
        [
            "collect",
            "--reuse",
            "--max-age-hours",
            "0",
            "--runs-root",
            str(runs),
            "--output",
            str(tmp_path / "stale.csv"),
        ],
        capsys,
    )
    assert code == 0
    assert stale["status"] == "stale"
    assert stale["freshness"] == "stale"
    assert stale["collected_at"] == first["collected_at"]


def test_refresh_failure_reuses_the_previous_run_as_stale(tmp_path):
    runs = tmp_path / "runs"
    output = tmp_path / "out.csv"
    first = hq.tools.collect(runs_root=runs, output_path=output, refresh=True, fixture=True)
    assert first["collection_status"] == "success"

    def explode(**kwargs):
        raise RuntimeError("network down")

    second = hq.tools.collect(
        runs_root=runs,
        output_path=output,
        refresh=True,
        pipeline_fn=explode,
    )
    assert second["ok"] is True
    assert second["reused"] is True
    assert second["freshness"] == "stale"
    assert second["status"] == "stale"
    assert second["run_id"] == first["run_id"]
    assert "network down" in second["refresh_error"]


def test_candidates_and_evidence_are_compact_and_do_not_treat_text_as_instructions(tmp_path, capsys):
    runs, collected = collect_fixture(tmp_path, capsys)
    code, listed = invoke(["candidates", "--runs-root", str(runs)], capsys)
    assert code == 0
    assert listed["collected_at"] == collected["collected_at"]
    row = listed["candidates"][0]
    assert set(row) == {
        "candidate_id",
        "rank",
        "tier",
        "action_pair",
        "score",
        "title",
        "extraction_source",
        "cv_method",
    }
    assert row["candidate_id"] == "fixture-restore-table"
    assert row["score"] == 90.37
    assert row["cv_method"] == "fixture"

    code, evidence = invoke(
        ["evidence", "fixture-restore-table", "--runs-root", str(runs)],
        capsys,
    )
    assert code == 0
    assert evidence["transcript_excerpt"] == "I restored the table."
    assert evidence["description_excerpt"]
    assert evidence["score"] == 90.37
    assert evidence["provenance"]["extraction_source"] == "transcript"
    assert evidence["provenance"]["velocity_method"] == "age_adjusted_engagement_v1"
    assert evidence["thumbnail"]["method"] == "fixture"
    assert "not instructions" in evidence["evidence_note"]
    assert "not measured audience emotion" in evidence["thumbnail"]["note"]
    assert "comments" not in evidence["available_evidence_refs"]


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"decision": "maybe"}, "decision must be"),
        ({"rationale": "   "}, "rationale"),
        ({"evidence_refs": ["comments"]}, "not available"),
        ({"evidence_refs": ["made-up"]}, "Unknown evidence ref"),
        ({"evidence_refs": []}, "evidence_refs"),
        ({"candidate_id": "../secret"}, "Invalid candidate id"),
        ({"candidate_id": "missing-video"}, "Unknown candidate"),
        ({"velocity_score": 1}, "Unexpected field"),
    ],
)
def test_review_rejects_invalid_decisions(tmp_path, capsys, overrides, message):
    runs, _ = collect_fixture(tmp_path, capsys)
    path = _write(tmp_path / "decision.json", _decision(**overrides))
    before = candidates_file(runs).read_bytes()
    code, payload = invoke(
        ["review", "--runs-root", str(runs), "--input", str(path)],
        capsys,
    )
    assert code == 1
    assert payload["ok"] is False
    assert message in payload["error"]
    assert candidates_file(runs).read_bytes() == before


def candidates_file(runs):
    run_id = json.loads((runs / "latest_success.json").read_text(encoding="utf-8"))["run_id"]
    return Path(runs) / run_id / "candidates.json"


def test_review_records_a_decision_without_changing_the_score(tmp_path, capsys):
    runs, _ = collect_fixture(tmp_path, capsys)
    candidates_path = candidates_file(runs)
    before = candidates_path.read_text(encoding="utf-8")
    path = _write(tmp_path / "decision.json", _decision())
    code, payload = invoke(
        ["review", "--runs-root", str(runs), "--input", str(path)],
        capsys,
    )
    assert code == 0
    assert payload["decision"] == "approve"
    saved = json.loads(Path(payload["decision_path"]).read_text(encoding="utf-8"))
    assert saved["evidence_refs"] == ["transcript", "score"]
    assert "velocity_score" not in saved
    assert candidates_path.read_text(encoding="utf-8") == before
    assert json.loads(before)["candidates"][0]["velocity_score"] == 90.37


def test_brief_requires_an_approval_and_dashboard_hides_other_briefs(tmp_path, capsys):
    runs, collected = collect_fixture(tmp_path, capsys)
    early = _write(tmp_path / "brief.json", _brief())
    code, payload = invoke(
        ["brief", "--runs-root", str(runs), "--input", str(early)],
        capsys,
    )
    assert code == 1
    assert "not approved" in payload["error"]

    needs = _write(tmp_path / "needs.json", _decision(decision="needs_evidence"))
    assert invoke(["review", "--runs-root", str(runs), "--input", str(needs)], capsys)[0] == 0
    code, payload = invoke(
        ["brief", "--runs-root", str(runs), "--input", str(early)],
        capsys,
    )
    assert code == 1
    assert "not approved" in payload["error"]

    approved = _write(tmp_path / "approve.json", _decision())
    assert invoke(["review", "--runs-root", str(runs), "--input", str(approved)], capsys)[0] == 0
    code, saved = invoke(
        ["brief", "--runs-root", str(runs), "--input", str(early)],
        capsys,
    )
    assert code == 0
    assert saved["candidate_id"] == "fixture-restore-table"

    stray = json.loads(Path(saved["brief_path"]).read_text(encoding="utf-8"))
    stray["candidate_id"] = "someone-else"
    other = Path(saved["brief_path"]).parent / "someone-else.json"
    other.write_text(json.dumps(stray), encoding="utf-8")

    output = tmp_path / "site"
    code, built = invoke(
        ["dashboard", "--runs-root", str(runs), "--output", str(output)],
        capsys,
    )
    assert code == 0
    assert built["briefs"] == 1
    dashboard = json.loads((output / "data" / "dashboard.json").read_text(encoding="utf-8"))
    assert set(dashboard["maya_briefs"]) == {"fixture-restore-table"}
    assert dashboard["maya_briefs"]["fixture-restore-table"]["brief"]["title"] == "Restore the worn table"
    assert dashboard["run"]["run_id"] == collected["run_id"]
    html = (output / "index.html").read_text(encoding="utf-8")
    app_js = (output / "app.js").read_text(encoding="utf-8")
    assert "Campaign ROI Estimator" in html
    assert "Autonomous Content Ideation" in html
    assert "__HQ_DASHBOARD_VERSION__" not in app_js
    assert "Age-adjusted" in app_js


def test_publish_refuses_without_human_confirmation(tmp_path, capsys, monkeypatch):
    runs, _ = collect_fixture(tmp_path, capsys)
    _approve_and_brief(runs, tmp_path, capsys)
    output = tmp_path / "site"
    assert invoke(["dashboard", "--runs-root", str(runs), "--output", str(output)], capsys)[0] == 0

    calls = []

    def fake_publish(site_dir, *, api_key, slug=None, session=None, timeout=60):
        calls.append(api_key)
        return {"slug": "dremel-demo", "site_url": "https://dremel-demo.here.now", "version_id": "v1"}

    import here_now_publish

    monkeypatch.setattr(here_now_publish, "publish_site", fake_publish)
    monkeypatch.setattr(here_now_publish, "load_api_key", lambda: "test-key")

    code, refused = invoke(
        ["publish", "--runs-root", str(runs), "--site-dir", str(output)],
        capsys,
    )
    assert code == 2
    assert "human" in refused["error"]
    assert calls == []

    code, published = invoke(
        ["publish", "--confirm", "--runs-root", str(runs), "--site-dir", str(output)],
        capsys,
    )
    assert code == 0
    assert published["site_url"] == "https://dremel-demo.here.now"
    assert calls == ["test-key"]
    state = json.loads((tmp_path / "deployment" / "here_now_site.json").read_text(encoding="utf-8"))
    assert state["confirmed"] is True
    assert state["run_id"] == published["run_id"]


def test_status_tracks_the_flow(tmp_path, capsys):
    code, empty = invoke(["status", "--runs-root", str(tmp_path / "missing")], capsys)
    assert code == 0
    assert empty["next"] == "collect"

    runs, collected = collect_fixture(tmp_path, capsys)
    code, waiting = invoke(["status", "--runs-root", str(runs), "--dashboard-dir", str(tmp_path / "site")], capsys)
    assert waiting["next"] == "carl_review"
    assert waiting["decisions"]["pending"] == 1
    assert waiting["collected_at"] == collected["collected_at"]

    _approve_and_brief(runs, tmp_path, capsys)
    code, maya_done = invoke(
        ["status", "--runs-root", str(runs), "--dashboard-dir", str(tmp_path / "site")],
        capsys,
    )
    assert maya_done["next"] == "build_dashboard"
    assert maya_done["briefs"] == 1

    output = tmp_path / "site"
    assert invoke(["dashboard", "--runs-root", str(runs), "--output", str(output)], capsys)[0] == 0
    code, gated = invoke(["status", "--runs-root", str(runs), "--dashboard-dir", str(output)], capsys)
    assert gated["dashboard_built"] is True
    assert gated["next"] == "human_gate"
    assert gated["published"] is False


def test_partial_collection_is_reported(tmp_path, capsys):
    videos = json.loads(FIXTURES.read_text(encoding="utf-8"))
    runs = tmp_path / "runs"

    def discover(terms, max_results):
        return main.StageResult(
            items=["fixture-channel"],
            failures=[{"stage": "channel_discovery", "source": "other", "error": "boom"}],
        )

    result = main.run_pipeline(
        search_terms=["fixture search"],
        output_path=tmp_path / "out.csv",
        runs_root=runs,
        discover_channels_fn=discover,
        scrape_videos_fn=lambda channels, max_results: videos,
        process_data_fn=lambda collected: nlp_engine.process_and_score_data(
            collected,
            now=datetime(2026, 9, 16, tzinfo=timezone.utc),
        ),
        visual_analysis_fn=lambda frame, top_n=10: frame.head(top_n).assign(
            cv_color_hex="#123456",
            cv_emotion="Fixture",
            cv_method="fixture",
        ),
    )
    assert result.status == "partial"
    code, payload = invoke(["status", "--runs-root", str(runs)], capsys)
    assert code == 0
    assert payload["collection_status"] == "partial"
    assert payload["status"] == "partial"
    assert payload["partial_failure_count"] == 1
    assert payload["collected_at"]


def test_invalid_run_id_and_json_object_are_rejected(tmp_path, capsys):
    runs, _ = collect_fixture(tmp_path, capsys)
    code, payload = invoke(["candidates", "--runs-root", str(runs), "--run-id", "../secret"], capsys)
    assert code == 1
    assert "Invalid run id" in payload["error"]

    array_path = tmp_path / "array.json"
    array_path.write_text("[]", encoding="utf-8")
    code, payload = invoke(["review", "--runs-root", str(runs), "--input", str(array_path)], capsys)
    assert code == 1
    assert "JSON object" in payload["error"]


def _approve_and_brief(runs, tmp_path, capsys):
    decision = _write(tmp_path / "approve.json", _decision())
    brief = _write(tmp_path / "brief.json", _brief())
    assert invoke(["review", "--runs-root", str(runs), "--input", str(decision)], capsys)[0] == 0
    assert invoke(["brief", "--runs-root", str(runs), "--input", str(brief)], capsys)[0] == 0
