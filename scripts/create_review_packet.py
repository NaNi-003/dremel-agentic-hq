import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import phase3_review  # noqa: E402


def parse_args():
    parser = argparse.ArgumentParser(
        description="Create one immutable Phase 3 Carl review packet."
    )
    parser.add_argument("--runs-root", type=Path, default=PROJECT_ROOT / "artifacts" / "runs")
    parser.add_argument(
        "--reviews-root",
        type=Path,
        default=PROJECT_ROOT / "artifacts" / "reviews",
    )
    parser.add_argument("--run-id", required=True)
    return parser.parse_args()


def main_cli():
    args = parse_args()
    try:
        packet_path = phase3_review.create_review_packet(
            runs_root=args.runs_root,
            reviews_root=args.reviews_root,
            run_id=args.run_id,
            generated_at=datetime.now(timezone.utc),
        )
    except phase3_review.ReviewValidationError as exc:
        print(json.dumps({"status": "failed", "error": str(exc)}), file=sys.stderr)
        return 1

    print(
        json.dumps(
            {
                "status": "pending_review",
                "run_id": args.run_id,
                "packet_path": str(packet_path),
                "packet_sha256": phase3_review.review_packet_sha256(packet_path),
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main_cli())
