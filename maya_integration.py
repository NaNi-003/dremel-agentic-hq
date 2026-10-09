import json
import re
import subprocess
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import dashboard_content
import phase3_review
import run_artifacts


class MayaIntegrationError(ValueError):
    pass


_WINDOWS_RESERVED_NAMES = {
    "CON", "PRN", "AUX", "NUL",
    *(f"COM{index}" for index in range(1, 10)),
    *(f"LPT{index}" for index in range(1, 10)),
}


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
        "objective",
        "strategic_rationale",
        "audience",
        "audience_insight",
        "tone",
        "hook",
        "hook_options",
        "information_gap",
        "concept",
        "key_beats",
        "product_role",
        "thumbnail_direction",
        "call_to_action",
        "success_metrics",
        "claims_guardrails",
    }
    if not isinstance(brief, dict) or set(brief) != required_fields:
        raise MayaIntegrationError("Maya brief fields differ from the contract")
    text_fields = required_fields - {
        "key_beats",
        "hook_options",
        "information_gap",
        "success_metrics",
    }
    if not all(
        isinstance(brief[field], str) and brief[field].strip()
        for field in text_fields
    ):
        raise MayaIntegrationError("Maya brief text fields must be non-empty")
    beats = brief["key_beats"]
    if (
        not isinstance(beats, list)
        or len(beats) < 5
        or not all(isinstance(beat, str) and beat.strip() for beat in beats)
    ):
        raise MayaIntegrationError("Maya brief requires at least five key beats")
    for field, minimum in (("hook_options", 3), ("success_metrics", 3)):
        values = brief[field]
        if (
            not isinstance(values, list)
            or len(values) < minimum
            or not all(isinstance(value, str) and value.strip() for value in values)
        ):
            raise MayaIntegrationError(f"Maya brief {field} is incomplete")
    gap = brief["information_gap"]
    if (
        not isinstance(gap, dict)
        or set(gap) != {"known", "unknown", "payoff"}
        or not all(isinstance(value, str) and value.strip() for value in gap.values())
    ):
        raise MayaIntegrationError("Maya brief information gap is invalid")
    return brief


def build_maya_prompt(
    packet,
    decision,
    *,
    assignment_source="Carl's approved opportunity",
):
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
        "objective": "specific communication or business objective",
        "strategic_rationale": "concise rationale",
        "audience": "intended audience",
        "audience_insight": "evidence-grounded audience tension or motivation",
        "tone": "creative tone",
        "hook": "Information Gap hook without revealing the result",
        "hook_options": ["alternative hook 1", "alternative hook 2", "alternative hook 3"],
        "information_gap": {
            "known": "what the opening establishes",
            "unknown": "the specific unanswered question",
            "payoff": "how and when the answer is delivered",
        },
        "concept": "YouTube Short concept",
        "key_beats": ["beat 1", "beat 2", "beat 3", "beat 4", "beat 5"],
        "product_role": "natural, evidence-supported Dremel role",
        "thumbnail_direction": "visual and creator-expression direction",
        "call_to_action": "viewer call to action",
        "success_metrics": ["metric 1", "metric 2", "metric 3"],
        "claims_guardrails": "unsupported claims the creator must avoid",
    }
    assignment = {
        "run_id": packet["run_id"],
        "approved_candidate": selected,
        "carl_rationale": decision.get("rationale"),
        "evidence_citations": decision.get("evidence_citations"),
    }
    return (
        "Create a concise, professional creative brief for a Dremel UK YouTube Short "
        f"from {assignment_source}. Preserve the evidence and do not invent "
        "product claims. Apply Loewenstein's Information Gap Theory explicitly: define "
        "what viewers know, the precise missing information that creates curiosity, and "
        "a satisfying delayed payoff. Before returning, perform one silent self-check "
        "for evidence fidelity, specificity, executable production, honest payoff, brand "
        "fit, and non-generic language; revise weak sections once. "
        "Keep the tone bold, brave, enthusiastic, and "
        "helpful.\n\nReturn only the JSON object—no markdown or commentary—using "
        "exactly this shape:\n"
        f"{json.dumps(output_shape, indent=2, sort_keys=True)}\n\n"
        "Approved assignment:\n"
        f"{json.dumps(assignment, indent=2, sort_keys=True)}"
    )


def invoke_maya_profile(prompt, *, profile="maya", timeout=600):
    """Run one isolated turn using Gemini for Maya's profile."""
    import os
    from dotenv import load_dotenv
    from google import genai

    load_dotenv()
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise MayaIntegrationError("GEMINI_API_KEY environment variable is not set")
    
    try:
        client = genai.Client(api_key=api_key)
        response = client.models.generate_content(
            model=os.getenv("GEMINI_TEXT_MODEL", "gemini-2.5-flash"),
            contents=prompt,
            config={
                "temperature": 0.0,
                "response_mime_type": "application/json",
            }
        )
        return response.text
    except Exception as exc:
        print(f"MAYA API ERROR: {exc}")
        raise MayaIntegrationError("Maya profile invocation failed via Gemini") from exc


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


def request_primary_briefs(*, packet_path, artifacts_root, invoke=None, max_workers=3):
    """Create one contract-validated Maya brief for every primary candidate."""
    packet_path = Path(packet_path).resolve()
    packet = phase3_review.validate_review_packet(
        packet_path,
        artifacts_root=artifacts_root,
    )
    candidates = packet.get("candidates", [])
    if not candidates or len(candidates) > 15:
        raise MayaIntegrationError("Primary candidate packet must contain 1 to 15 candidates")

    saved = dashboard_content.load_maya_briefs(artifacts_root, packet["run_id"])
    briefs = {}
    briefs_dir = (packet_path.parent / "maya_briefs").resolve()
    validated = []
    for candidate in candidates:
        candidate_id = candidate["candidate_id"]
        if (
            not isinstance(candidate_id, str)
            or not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", candidate_id)
            or candidate_id.upper() in _WINDOWS_RESERVED_NAMES
        ):
            raise MayaIntegrationError("Candidate ID is unsafe for an artifact filename")
        brief_path = (briefs_dir / f"{candidate_id}.json").resolve()
        if brief_path.parent != briefs_dir:
            raise MayaIntegrationError("Candidate ID escapes the brief artifact directory")
        validated.append((candidate, candidate_id, brief_path))

    pending = []
    for candidate, candidate_id, brief_path in validated:
        existing = saved.get(candidate_id)
        if (
            isinstance(existing, dict)
            and existing.get("source_decision") == "primary_candidate_batch"
        ):
            briefs[candidate_id] = existing
            continue
        pending.append((candidate, candidate_id, brief_path))

    def generate_brief(item):
        candidate, candidate_id, brief_path = item
        decision = {
            "decision": "approve",
            "selected_candidate_id": candidate_id,
            "rationale": (
                "Create a demonstration-ready brief for this validated top-15 "
                "primary marketing opportunity."
            ),
            "evidence_citations": candidate.get("evidence_refs", []),
        }
        prompt = build_maya_prompt(
            packet,
            decision,
            assignment_source="a validated top-15 primary opportunity",
        )
        brief = validate_maya_brief(
            parse_maya_response((invoke or invoke_maya_profile)(prompt))
        )
        artifact = {
            "schema_version": 1,
            "run_id": packet["run_id"],
            "candidate_id": candidate_id,
            "creator": "maya",
            "source_decision": "primary_candidate_batch",
            "brief": brief,
        }
        run_artifacts.write_json_atomically(artifact, brief_path)
        return candidate_id, artifact

    if pending:
        workers = min(max(int(max_workers), 1), 3, len(pending))
        with ThreadPoolExecutor(max_workers=workers) as executor:
            for candidate_id, artifact in executor.map(generate_brief, pending):
                briefs[candidate_id] = artifact

    return {
        "run_id": packet["run_id"],
        "brief_count": len(briefs),
        "briefs": briefs,
    }
