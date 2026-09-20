import argparse
import json
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import carl_integration  # noqa: E402
import phase3_review  # noqa: E402


def parse_args():
    parser = argparse.ArgumentParser(
        description="Send one frozen Dremel review packet to the Carl profile."
    )
    parser.add_argument("--packet", type=Path, required=True)
    parser.add_argument(
        "--artifacts-root",
        type=Path,
        default=PROJECT_ROOT / "artifacts",
    )
    return parser.parse_args()


def main_cli():
    args = parse_args()
    try:
        result = carl_integration.request_carl_review(
            packet_path=args.packet,
            artifacts_root=args.artifacts_root,
        )
    except (carl_integration.CarlIntegrationError, phase3_review.ReviewValidationError) as exc:
        print(json.dumps({"status": "failed", "error": str(exc)}), file=sys.stderr)
        return 1

    decision = result["decision"]
    print(
        json.dumps(
            {
                "run_id": decision["run_id"],
                "decision": decision["decision"],
                "decision_path": str(result["decision_path"]),
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main_cli())
