import json
import subprocess
from pathlib import Path

import phase3_review
import run_artifacts


class MayaIntegrationError(ValueError):
    pass


def _reject_nonstandard_constant(value):
    raise ValueError(f"Non-standard JSON constant: {value}")


def parse_maya_response(response_text):
    """Parse Maya's one-shot response as exactly one JSON object."""
    if not isinstance(response_text, str):
        raise MayaIntegrationError("Maya must return raw JSON text")
    try:
        payload = json.loads(
            response_text,
            parse_constant=_reject_nonstandard_constant,
        )
    except (json.JSONDecodeError, ValueError) as exc:
        raise MayaIntegrationError("Maya must return one raw JSON object") from exc
    if not isinstance(payload, dict):
        raise MayaIntegrationError("Maya must return one raw JSON object")
    return payload


def validate_maya_brief(brief):
    required_fields = {
        "title",
        "strategic_rationale",
        "audience",
        "tone",
        "hook",
        "concept",
        "key_beats",
        "thumbnail_direction",
        "call_to_action",
    }
    if not isinstance(brief, dict) or set(brief) != required_fields:
        raise MayaIntegrationError("Maya brief fields differ from the contract")
    text_fields = required_fields - {"key_beats"}
    if not all(
        isinstance(brief[field], str) and brief[field].strip()
        for field in text_fields
    ):
        raise MayaIntegrationError("Maya brief text fields must be non-empty")
    beats = brief["key_beats"]
    if (
        not isinstance(beats, list)
        or len(beats) < 3
        or not all(isinstance(beat, str) and beat.strip() for beat in beats)
    ):
        raise MayaIntegrationError("Maya brief requires at least three key beats")
    return brief


def build_maya_prompt(packet, decision):
    """Build a focused content-brief assignment from Carl's approval."""
    if decision.get("decision") != "approve":
        raise MayaIntegrationError("Maya requires an approved Carl decision")
    selected_id = decision.get("selected_candidate_id")
    selected = next(
        (
            candidate
            for candidate in packet.get("candidates", [])
            if candidate.get("candidate_id") == selected_id
        ),
        None,
    )
    if selected is None:
        raise MayaIntegrationError("Carl's selected candidate is missing")

    output_shape = {
        "title": "brief title",
        "strategic_rationale": "concise rationale",
        "audience": "intended audience",
        "tone": "creative tone",
        "hook": "Information Gap hook without revealing the result",
        "concept": "YouTube Short concept",
        "key_beats": ["beat 1", "beat 2", "beat 3"],
        "thumbnail_direction": "visual and creator-expression direction",
        "call_to_action": "viewer call to action",
    }
    assignment = {
        "run_id": packet["run_id"],
        "approved_candidate": selected,
        "carl_rationale": decision.get("rationale"),
        "evidence_citations": decision.get("evidence_citations"),
    }
    return (
        "Create a concise Dremel UK YouTube Short content brief from Carl's approved "
        "opportunity. Preserve the evidence and do not invent product claims. Use "
        "Loewenstein's Information Gap approach for the hook: build curiosity without "
        "revealing the finished result. Keep the tone bold, brave, enthusiastic, and "
        "helpful.\n\nReturn only the JSON object—no markdown or commentary—using "
        "exactly this shape:\n"
        f"{json.dumps(output_shape, indent=2, sort_keys=True)}\n\n"
        "Approved assignment:\n"
        f"{json.dumps(assignment, indent=2, sort_keys=True)}"
    )


def invoke_maya_profile(prompt, *, profile="maya", timeout=600):
    """Run one isolated Hermes one-shot turn using Maya's profile."""
    project_root = Path(__file__).resolve().parent
    try:
        completed = subprocess.run(
            [
                "hermes",
                "-p",
                profile,
                "--in",
                str(project_root),
                "--oneshot",
                prompt,
            ],
            cwd=project_root,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=timeout,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise MayaIntegrationError("Maya profile invocation failed") from exc
    if completed.returncode != 0:
        raise MayaIntegrationError("Maya profile invocation failed")
    return completed.stdout.strip()


def request_maya_brief(
    *, packet_path, decision_path, artifacts_root, invoke=None
):
    """Ask Maya for one brief based on Carl's validated approval."""
    packet_path = Path(packet_path).resolve()
    decision_path = Path(decision_path).resolve()
    packet = phase3_review.validate_review_packet(
        packet_path,
        artifacts_root=artifacts_root,
    )
    try:
        decision = json.loads(
            decision_path.read_bytes(),
            parse_constant=_reject_nonstandard_constant,
        )
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as exc:
        raise MayaIntegrationError("Carl decision is unreadable") from exc
    decision = phase3_review.validate_review_decision(
        decision,
        packet_path=packet_path,
        artifacts_root=artifacts_root,
    )
    prompt = build_maya_prompt(packet, decision)
    response_text = (invoke or invoke_maya_profile)(prompt)
    brief = validate_maya_brief(parse_maya_response(response_text))
    artifact = {
        "schema_version": 1,
        "run_id": packet["run_id"],
        "candidate_id": decision["selected_candidate_id"],
        "creator": "maya",
        "source_decision": decision_path.name,
        "brief": brief,
    }
    brief_path = packet_path.with_name("maya_content_brief.json")
    run_artifacts.write_json_atomically(artifact, brief_path)
    return {"brief": artifact, "brief_path": brief_path}
