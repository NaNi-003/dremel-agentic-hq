import json
from datetime import datetime, timezone
from pathlib import Path

import nlp_engine


FIXTURES = Path(__file__).parent / "fixtures"


def test_fixture_scoring_accepts_a_fixed_clock_without_changing_the_formula():
    videos = json.loads((FIXTURES / "videos.json").read_text(encoding="utf-8"))
    fixed_now = datetime(2026, 9, 16, tzinfo=timezone.utc)

    result = nlp_engine.process_and_score_data(videos, now=fixed_now)

    assert result.to_dict("records") == [
        {
            "video_id": "fixture-restore-table",
            "video_title": "Restoring a table",
            "thumbnail_url": "https://example.invalid/table.jpg",
            "detected_verb": "Restore",
            "detected_material": "Table",
            "action_pair": "Restore Table",
            "velocity_score": 90.37,
        }
    ]


def test_fractional_and_offset_publish_timestamps_keep_the_same_score():
    videos = json.loads((FIXTURES / "videos.json").read_text(encoding="utf-8"))
    fixed_now = datetime(2026, 9, 16, tzinfo=timezone.utc)
    baseline = nlp_engine.process_and_score_data(videos, now=fixed_now).iloc[0]["velocity_score"]

    for publish_date in (
        "2026-09-06T00:00:00.000Z",
        "2026-09-06T00:00:00+00:00",
        "2026-09-06T01:00:00+01:00",
    ):
        stamped = json.loads(json.dumps(videos))
        stamped[0]["publish_date"] = publish_date
        observed = nlp_engine.process_and_score_data(stamped, now=fixed_now)
        assert observed.iloc[0]["velocity_score"] == baseline == 90.37


def test_naive_or_unparseable_publish_dates_are_skipped():
    videos = json.loads((FIXTURES / "videos.json").read_text(encoding="utf-8"))
    fixed_now = datetime(2026, 9, 16, tzinfo=timezone.utc)
    for publish_date in ("2026-09-06T00:00:00", "not-a-date"):
        stamped = json.loads(json.dumps(videos))
        stamped[0]["publish_date"] = publish_date
        assert nlp_engine.process_and_score_data(stamped, now=fixed_now).empty
