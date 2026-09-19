import argparse
import json
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import phase3_review  # noqa: E402


def _reject_nonstandard_constant(value):
    raise json.JSONDecodeError(f"Non-standard JSON constant: {value}", value, 0)


def parse_args():
    parser = argparse.ArgumentParser(
        description="Validate and immutably record one Carl review decision."
    )
    parser.add_argument("--packet", type=Path, required=True)
    parser.add_argument("--decision", type=Path, required=True)
    parser.add_argument(
        "--artifacts-root",
        type=Path,
        default=PROJECT_ROOT / "artifacts",
    )
    return parser.parse_args()


def main_cli():
    args = parse_args()
    try:
        decision = json.loads(
            args.decision.read_text(encoding="utf-8"),
            parse_constant=_reject_nonstandard_constant,
        )
        decision_path = phase3_review.record_review_decision(
            decision,
            packet_path=args.packet,
            artifacts_root=args.artifacts_root,
        )
    except (OSError, UnicodeError, json.JSONDecodeError):
        print(
            json.dumps({"status": "failed", "error": "Decision input is unreadable"}),
            file=sys.stderr,
        )
        return 1
    except phase3_review.ReviewValidationError as exc:
        print(json.dumps({"status": "failed", "error": str(exc)}), file=sys.stderr)
        return 1

    print(
        json.dumps(
            {
                "status": decision["decision"],
                "run_id": decision["run_id"],
                "decision_path": str(decision_path),
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main_cli())
