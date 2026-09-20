import argparse
import json
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import carl_integration  # noqa: E402
import here_now_publish  # noqa: E402
import maya_integration  # noqa: E402
import phase3_review  # noqa: E402
import roxy_workflow  # noqa: E402


WORKFLOW_ERRORS = (
    roxy_workflow.RoxyWorkflowError,
    carl_integration.CarlIntegrationError,
    maya_integration.MayaIntegrationError,
    phase3_review.ReviewValidationError,
    here_now_publish.HereNowPublishError,
    OSError,
    ValueError,
)


def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description=(
            "Coordinate the latest Dremel run through Carl, Maya, the static build, "
            "and optional user-approved here.now publication."
        )
    )
    parser.add_argument(
        "--publish",
        action="store_true",
        help="Publish/update here.now. Omit for a build-only readiness run.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=PROJECT_ROOT / "dist" / "dashboard",
    )
    return parser.parse_args(argv)


def main_cli(argv=None):
    args = parse_args(argv)
    try:
        result = roxy_workflow.coordinate_latest(
            project_root=PROJECT_ROOT,
            output_dir=args.output,
            publish=args.publish,
        )
    except WORKFLOW_ERRORS as exc:
        print(json.dumps({"status": "failed", "error": str(exc)}), file=sys.stderr)
        return 1
    print(json.dumps(result, sort_keys=True))
    return 0 if result["status"] != "blocked_by_carl" else 2
if __name__ == "__main__":
    raise SystemExit(main_cli())
