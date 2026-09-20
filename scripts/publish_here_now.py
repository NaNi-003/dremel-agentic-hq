import argparse
import json
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import here_now_publish  # noqa: E402
import run_artifacts  # noqa: E402
import static_dashboard  # noqa: E402


def parse_args():
    parser = argparse.ArgumentParser(
        description="Build and permanently publish the Dremel dashboard to here.now."
    )
    parser.add_argument("--output", type=Path, default=PROJECT_ROOT / "dist" / "dashboard")
    parser.add_argument(
        "--state",
        type=Path,
        default=PROJECT_ROOT / "artifacts" / "deployment" / "here_now_site.json",
    )
    return parser.parse_args()


def _existing_slug(state_path):
    try:
        state = json.loads(Path(state_path).read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None
    except (OSError, json.JSONDecodeError, TypeError, ValueError) as exc:
        raise here_now_publish.HereNowPublishError(
            "The existing here.now deployment state is unreadable"
        ) from exc
    slug = state.get("slug") if isinstance(state, dict) else None
    if not isinstance(slug, str) or not slug:
        raise here_now_publish.HereNowPublishError(
            "The existing here.now deployment state has no valid slug"
        )
    return slug


def main_cli():
    args = parse_args()
    try:
        api_key = here_now_publish.load_api_key()
        rows, brief, run = static_dashboard.load_dashboard_payload()
        output = static_dashboard.build_static_dashboard(
            args.output,
            rows=rows,
            brief=brief,
            run_context=run,
        )
        publication = here_now_publish.publish_site(
            output,
            api_key=api_key,
            slug=_existing_slug(args.state),
        )
        state = {
            "schema_version": 1,
            "provider": "here.now",
            "slug": publication["slug"],
            "site_url": publication["site_url"],
            "version_id": publication["version_id"],
            "run_id": run.get("run_id"),
        }
        run_artifacts.write_json_atomically(state, args.state)
    except (
        here_now_publish.HereNowPublishError,
        RuntimeError,
        OSError,
        ValueError,
    ) as exc:
        print(json.dumps({"status": "failed", "error": str(exc)}), file=sys.stderr)
        return 1

    print(json.dumps({"status": "published", **state}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main_cli())
