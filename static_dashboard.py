import json
import re
import shutil
from pathlib import Path
from urllib.parse import urlparse

import pandas as pd

import dashboard_evidence


PROJECT_ROOT = Path(__file__).resolve().parent
DEFAULT_SOURCE_DIR = PROJECT_ROOT / "web_dashboard"
DEFAULT_RUNS_ROOT = PROJECT_ROOT / "artifacts" / "runs"
DEFAULT_ARTIFACTS_ROOT = PROJECT_ROOT / "artifacts"
DEFAULT_LEGACY_OUTPUT = PROJECT_ROOT / "dremel_final_output.csv"


def _safe_https_url(value):
    if not isinstance(value, str):
        return None
    try:
        parsed = urlparse(value)
    except ValueError:
        return None
    return value if parsed.scheme == "https" and parsed.hostname else None


def _browser_safe_rows(rows):
    safe_rows = []
    for source in rows:
        row = dict(source)
        row["thumbnail_url"] = _safe_https_url(row.get("thumbnail_url"))
        row["source_url"] = _safe_https_url(row.get("source_url"))
        color = row.get("cv_color_hex")
        if not isinstance(color, str) or not re.fullmatch(r"#[0-9a-fA-F]{6}", color):
            row["cv_color_hex"] = "#cccccc"
        safe_rows.append(row)
    return safe_rows


def _json_safe_rows(dataframe):
    import numpy as np
    dataframe = dataframe.replace([np.inf, -np.inf], np.nan)
    dataframe = dataframe.fillna(np.nan).replace({np.nan: None})
    records = dataframe.to_dict(orient="records")
    return json.loads(json.dumps(records, allow_nan=False))


def build_static_dashboard(
    output_dir, *, rows, brief, run_context, briefs=None, source_dir=DEFAULT_SOURCE_DIR
):
    """Build a dependency-free static copy of the original dashboard UI."""
    output_dir = Path(output_dir)
    source_dir = Path(source_dir)
    if not isinstance(rows, list) or not rows:
        raise ValueError("Cannot build dashboard: no validated rows")
    rows = _browser_safe_rows(rows)
    if output_dir.exists():
        shutil.rmtree(output_dir)
    shutil.copytree(source_dir, output_dir)

    logo_source = PROJECT_ROOT / "dremel_logo.png"
    assets_dir = output_dir / "assets"
    assets_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(logo_source, assets_dir / "dremel_logo.png")

    candidate_ids = {row.get("video_id") for row in rows}
    if not (
        isinstance(brief, dict)
        and brief.get("run_id") == run_context.get("run_id")
        and brief.get("candidate_id") in candidate_ids
    ):
        brief = None
    primary_ids = {row.get("video_id") for row in rows[:15]}
    briefs = briefs if isinstance(briefs, dict) else {}
    briefs = {
        candidate_id: artifact
        for candidate_id, artifact in briefs.items()
        if candidate_id in primary_ids
        and isinstance(artifact, dict)
        and artifact.get("run_id") == run_context.get("run_id")
        and artifact.get("candidate_id") == candidate_id
    }

    data_dir = output_dir / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "run": run_context,
        "rows": rows,
        "maya_brief": brief,
        "maya_briefs": briefs,
    }
    (data_dir / "dashboard.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    _stamp_dashboard_version(output_dir, run_context)
    return output_dir


def _stamp_dashboard_version(output_dir, run_context):
    """Replace the template cache token so a rebuild is not pinned to one run."""
    app_js = Path(output_dir) / "app.js"
    if not app_js.is_file():
        return
    token = str(
        (run_context or {}).get("collected_at")
        or (run_context or {}).get("run_id")
        or "build"
    )
    safe = re.sub(r"[^A-Za-z0-9_-]", "", token) or "build"
    text = app_js.read_text(encoding="utf-8")
    placeholder = "data/dashboard.json?v=__HQ_DASHBOARD_VERSION__"
    if placeholder in text:
        app_js.write_text(
            text.replace(placeholder, f"data/dashboard.json?v={safe}", 1),
            encoding="utf-8",
        )


def load_dashboard_payload(runs_root=DEFAULT_RUNS_ROOT, artifacts_root=DEFAULT_ARTIFACTS_ROOT):
    context = dashboard_evidence.load_latest_evidence(Path(runs_root))
    if context:
        dataframe = pd.read_csv(context["dashboard_snapshot"])
        dataframe = dashboard_evidence.validate_dashboard_dataframe(dataframe)
        if "video_id" in dataframe.columns:
            dataframe["source_url"] = dataframe["video_id"].map(context["source_urls"])
        run = {
            key: context[key]
            for key in (
                "run_id",
                "collected_at",
                "status",
                "partial_failure_count",
                "videos_collected",
                "candidates_scored",
            )
        }
        return _json_safe_rows(dataframe), None, run

    if dashboard_evidence.latest_pointer_exists(Path(runs_root)):
        raise RuntimeError("The latest evidence bundle failed validation")

    dataframe = dashboard_evidence.validate_dashboard_dataframe(
        pd.read_csv(DEFAULT_LEGACY_OUTPUT)
    )
    return _json_safe_rows(dataframe), None, {
        "run_id": None,
        "collected_at": None,
        "status": "legacy",
        "partial_failure_count": 0,
        "videos_collected": len(dataframe),
        "candidates_scored": len(dataframe),
    }


def main(argv=None):
    """Delegate to the hq dashboard command so there is one build path."""
    from hq.cli import main as hq_main

    return hq_main(["dashboard", *list(argv or [])])


if __name__ == "__main__":
    raise SystemExit(main())
