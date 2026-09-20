import argparse
import json
import sys
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import main  # noqa: E402
import nlp_engine  # noqa: E402


FIXTURE_PATH = PROJECT_ROOT / "tests" / "fixtures" / "videos.json"
DEFAULT_OUTPUT = PROJECT_ROOT / "artifacts" / "fixture" / "dremel_final_output.csv"
DEFAULT_RUNS_ROOT = PROJECT_ROOT / "artifacts" / "runs"
FIXED_NOW = datetime(2026, 9, 16, tzinfo=timezone.utc)


def fixture_visual_analysis(frame, top_n=10):
    analyzed = frame.head(top_n).copy()
    analyzed["cv_color_hex"] = "#123456"
    analyzed["cv_emotion"] = "Fixture"
    analyzed["cv_method"] = "fixture"
    return analyzed


def parse_args():
    parser = argparse.ArgumentParser(description="Exercise the Dremel pipeline with local fixtures.")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--runs-root", type=Path, default=DEFAULT_RUNS_ROOT)
    return parser.parse_args()


def main_cli():
    args = parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    videos = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))

    result = main.run_pipeline(
        search_terms=["fixture search"],
        output_path=args.output,
        runs_root=args.runs_root,
        discover_channels_fn=lambda terms, max_results: ["fixture-channel"],
        scrape_videos_fn=lambda channels, max_results: videos,
        process_data_fn=lambda collected: nlp_engine.process_and_score_data(
            collected,
            now=FIXED_NOW,
        ),
        visual_analysis_fn=fixture_visual_analysis,
    )

    print(json.dumps(asdict(result), sort_keys=True))
    return 0 if result.status == "success" else 1


if __name__ == "__main__":
    raise SystemExit(main_cli())
