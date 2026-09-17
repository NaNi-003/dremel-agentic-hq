import json
from datetime import datetime, timedelta, timezone

import pandas as pd
import pytest

import run_artifacts


def test_isoformat_utc_converts_aware_values_and_rejects_naive_values():
    value = datetime(2026, 9, 16, 16, tzinfo=timezone(timedelta(hours=4)))
    assert run_artifacts.isoformat_utc(value) == "2026-09-16T12:00:00Z"

    with pytest.raises(ValueError, match="timezone-aware"):
        run_artifacts.isoformat_utc(datetime(2026, 9, 16, 12))


def test_json_writer_normalizes_all_non_finite_and_missing_values(tmp_path):
    path = tmp_path / "artifact.json"

    run_artifacts.write_json_atomically(
        {
            "nan": float("nan"),
            "positive_infinity": float("inf"),
            "negative_infinity": float("-inf"),
            "pandas_missing": pd.NA,
        },
        path,
    )

    text = path.read_text(encoding="utf-8")
    assert "Infinity" not in text
    assert "<NA>" not in text
    assert json.loads(text) == {
        "nan": None,
        "positive_infinity": None,
        "negative_infinity": None,
        "pandas_missing": None,
    }
