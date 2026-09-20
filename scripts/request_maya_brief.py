import argparse
import json
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import maya_integration  # noqa: E402
import phase3_review  # noqa: E402


def parse_args():
    parser = argparse.ArgumentParser(
        description="Send Carl's approved Dremel opportunity to the Maya profile."
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
        result = maya_integration.request_maya_brief(
            packet_path=args.packet,
            decision_path=args.decision,
            artifacts_root=args.artifacts_root,
        )
    except (maya_integration.MayaIntegrationError, phase3_review.ReviewValidationError) as exc:
        print(json.dumps({"status": "failed", "error": str(exc)}), file=sys.stderr)
        return 1

    artifact = result["brief"]
    print(
        json.dumps(
            {
                "run_id": artifact["run_id"],
                "candidate_id": artifact["candidate_id"],
                "brief_path": str(result["brief_path"]),
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main_cli())
