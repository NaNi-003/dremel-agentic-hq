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
