import json
from datetime import datetime, timezone
from pathlib import Path

import carl_integration
import dashboard_content
import dashboard_evidence
import here_now_publish
import maya_integration
import phase3_review
import run_artifacts
import static_dashboard


PROJECT_ROOT = Path(__file__).resolve().parent


class RoxyWorkflowError(RuntimeError):
    pass


def _read_json(path, label):
    try:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as exc:
        raise RoxyWorkflowError(f"{label} is unreadable") from exc
    if not isinstance(payload, dict):
        raise RoxyWorkflowError(f"{label} must be a JSON object")
    return payload


def _deployment_slug(state_path):
    state_path = Path(state_path)
    if not state_path.exists():
        return None
    slug = _read_json(state_path, "Deployment state").get("slug")
    if not isinstance(slug, str) or not slug:
        raise RoxyWorkflowError("Existing deployment state has no valid slug")
    return slug


def _ensure_brief_matches_approval(brief, decision, run_id):
    if not (
        isinstance(brief, dict)
        and brief.get("run_id") == run_id
        and brief.get("candidate_id") == decision.get("selected_candidate_id")
    ):
        raise RoxyWorkflowError("Maya brief does not match Carl's approved candidate")
    return brief


def coordinate_latest(
    *,
    project_root=PROJECT_ROOT,
    output_dir=None,
    publish=False,
    deployment_state=None,
):
    """Coordinate Carl, Maya, static build, and optional user-approved publication."""
    project_root = Path(project_root).resolve()
    artifacts_root = project_root / "artifacts"
    runs_root = artifacts_root / "runs"
    reviews_root = artifacts_root / "reviews"
    output_dir = Path(output_dir or project_root / "dist" / "dashboard")
    deployment_state = Path(
        deployment_state
        or artifacts_root / "deployment" / "here_now_site.json"
    )

    context = dashboard_evidence.load_latest_evidence(runs_root)
    if not context:
        raise RoxyWorkflowError("No validated latest run is available")
    run_id = context["run_id"]
    review_dir = reviews_root / run_id
    packet_path = review_dir / "review_packet.json"
    decision_path = review_dir / "review_decision.json"
    brief_path = review_dir / "maya_content_brief.json"

    if packet_path.exists():
        phase3_review.validate_review_packet(packet_path, artifacts_root=artifacts_root)
    else:
        packet_path = phase3_review.create_review_packet(
            runs_root=runs_root,
            reviews_root=reviews_root,
            run_id=run_id,
            generated_at=datetime.now(timezone.utc),
        )

    if decision_path.exists():
        decision = phase3_review.validate_review_decision(
            _read_json(decision_path, "Carl decision"),
            packet_path=packet_path,
            artifacts_root=artifacts_root,
        )
    else:
        carl_result = carl_integration.request_carl_review(
            packet_path=packet_path,
            artifacts_root=artifacts_root,
        )
        decision = carl_result["decision"]
        decision_path = Path(carl_result["decision_path"])

    if decision.get("decision") != "approve":
        return {
            "status": "blocked_by_carl",
            "run_id": run_id,
            "carl_decision": decision.get("decision"),
            "candidate_id": None,
            "site_url": None,
        }

    if brief_path.exists():
        brief = dashboard_content.load_maya_brief(artifacts_root, run_id)
        if brief is None:
            raise RoxyWorkflowError("Existing Maya brief failed validation")
    else:
        maya_result = maya_integration.request_maya_brief(
            packet_path=packet_path,
            decision_path=decision_path,
            artifacts_root=artifacts_root,
        )
        brief = maya_result["brief"]
    _ensure_brief_matches_approval(brief, decision, run_id)

    rows, dashboard_brief, run_context = static_dashboard.load_dashboard_payload(
        runs_root=runs_root,
        artifacts_root=artifacts_root,
    )
    if run_context.get("run_id") != run_id:
        raise RoxyWorkflowError("Dashboard run changed during coordination")
    _ensure_brief_matches_approval(dashboard_brief, decision, run_id)
    static_dashboard.build_static_dashboard(
        output_dir,
        rows=rows,
        brief=dashboard_brief,
        run_context=run_context,
    )

    site_url = None
    status = "ready_for_publish"
    if publish:
        publication = here_now_publish.publish_site(
            output_dir,
            api_key=here_now_publish.load_api_key(),
            slug=_deployment_slug(deployment_state),
        )
        state = {
            "schema_version": 1,
            "provider": "here.now",
            "slug": publication["slug"],
            "site_url": publication["site_url"],
            "version_id": publication["version_id"],
            "run_id": run_id,
        }
        run_artifacts.write_json_atomically(state, deployment_state)
        site_url = state["site_url"]
        status = "published"

    return {
        "status": status,
        "run_id": run_id,
        "carl_decision": "approve",
        "candidate_id": decision["selected_candidate_id"],
        "site_url": site_url,
        "output_dir": str(output_dir.resolve()),
    }
