"""Agent-facing command line. JSON on stdout, non-zero exit on errors."""

import argparse
import json
import sys
from pathlib import Path

import hq.tools as tools
from hq.tools import (
    DEFAULT_DASHBOARD,
    DEFAULT_OUTPUT,
    DEFAULT_RUNS,
    HqError,
)


def _emit(payload):
    json.dump(payload, sys.stdout, indent=2, sort_keys=True, ensure_ascii=False)
    sys.stdout.write("\n")


def _add_run_selection(parser, *, with_age=False):
    parser.add_argument("--run-id", default=None, help="Run id. Defaults to the latest usable run.")
    parser.add_argument("--runs-root", type=Path, default=DEFAULT_RUNS)
    if with_age:
        parser.add_argument(
            "--max-age-hours",
            type=int,
            default=24,
            help="A run older than this is stale when it is reused.",
        )


def _build_parser():
    parser = argparse.ArgumentParser(
        prog="python -m hq",
        description="Deterministic tools for the Dremel marketing-intelligence workflow.",
    )
    commands = parser.add_subparsers(dest="command", required=True)

    collect = commands.add_parser("collect", help="Collect a run or reuse the latest one.")
    mode = collect.add_mutually_exclusive_group()
    mode.add_argument("--refresh", action="store_true", help="Always run collection.")
    mode.add_argument("--reuse", action="store_true", help="Never collect; report the latest run.")
    collect.add_argument(
        "--fixture",
        action="store_true",
        help="Collect from the local fixture instead of YouTube.",
    )
    collect.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    _add_run_selection(collect, with_age=True)
    collect.set_defaults(func=_collect)

    candidates = commands.add_parser("candidates", help="List ranked candidates.")
    _add_run_selection(candidates, with_age=True)
    candidates.set_defaults(func=_candidates)

    evidence = commands.add_parser("evidence", help="Show evidence for one candidate.")
    evidence.add_argument("candidate_id")
    _add_run_selection(evidence, with_age=True)
    evidence.set_defaults(func=_evidence)

    review = commands.add_parser("review", help="Record a review decision.")
    review.add_argument("--input", type=Path, help="Decision JSON. Reads stdin when omitted.")
    _add_run_selection(review)
    review.set_defaults(func=_review)

    brief = commands.add_parser("brief", help="Save a creator brief for an approved candidate.")
    brief.add_argument("--input", type=Path, help="Brief JSON. Reads stdin when omitted.")
    _add_run_selection(brief)
    brief.set_defaults(func=_brief)

    dashboard = commands.add_parser("dashboard", help="Build the static dashboard.")
    dashboard.add_argument("--output", type=Path, default=DEFAULT_DASHBOARD)
    _add_run_selection(dashboard, with_age=True)
    dashboard.set_defaults(func=_dashboard)

    publish = commands.add_parser("publish", help="Publish the dashboard to here.now.")
    publish.add_argument(
        "--confirm",
        action="store_true",
        help="Required. Records that a human approved this publish.",
    )
    publish.add_argument("--site-dir", type=Path, default=DEFAULT_DASHBOARD)
    publish.add_argument("--slug", default=None)
    _add_run_selection(publish)
    publish.set_defaults(func=_publish)

    status = commands.add_parser("status", help="Summarise where a run is in the flow.")
    status.add_argument("--dashboard-dir", type=Path, default=DEFAULT_DASHBOARD)
    _add_run_selection(status, with_age=True)
    status.set_defaults(func=_status)

    return parser


def _collect(args):
    return tools.collect(
        runs_root=args.runs_root,
        output_path=args.output,
        refresh=args.refresh,
        reuse=args.reuse,
        fixture=args.fixture,
        max_age_hours=args.max_age_hours,
    )


def _candidates(args):
    return tools.list_candidates(
        runs_root=args.runs_root,
        run_id=args.run_id,
        max_age_hours=args.max_age_hours,
    )


def _evidence(args):
    return tools.show_evidence(
        args.candidate_id,
        runs_root=args.runs_root,
        run_id=args.run_id,
        max_age_hours=args.max_age_hours,
    )


def _review(args):
    return tools.record_review(
        tools.read_input(args.input),
        runs_root=args.runs_root,
        run_id=args.run_id,
    )


def _brief(args):
    return tools.save_brief(
        tools.read_input(args.input),
        runs_root=args.runs_root,
        run_id=args.run_id,
    )


def _dashboard(args):
    return tools.build_dashboard(
        output_dir=args.output,
        runs_root=args.runs_root,
        run_id=args.run_id,
        max_age_hours=args.max_age_hours,
    )


def _publish(args):
    return tools.publish_dashboard(
        site_dir=args.site_dir,
        runs_root=args.runs_root,
        confirm=args.confirm,
        slug=args.slug,
        run_id=args.run_id,
    )


def _status(args):
    return tools.status(
        runs_root=args.runs_root,
        run_id=args.run_id,
        dashboard_dir=args.dashboard_dir,
        max_age_hours=args.max_age_hours,
    )


def main(argv=None):
    parser = _build_parser()
    args = parser.parse_args(argv)
    try:
        payload = args.func(args)
    except HqError as exc:
        _emit({"ok": False, "error": str(exc)})
        return exc.code
    _emit(payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
