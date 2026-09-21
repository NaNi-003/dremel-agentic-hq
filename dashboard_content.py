import json
from pathlib import Path


_BRIEF_FIELDS = {
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
_PROFESSIONAL_BRIEF_FIELDS = _BRIEF_FIELDS | {
    "objective",
    "audience_insight",
    "hook_options",
    "information_gap",
    "product_role",
    "success_metrics",
    "claims_guardrails",
}


def _load_brief_path(path, run_id, allowed_sources, expected_candidate_id=None):
    try:
        artifact = json.loads(Path(path).read_text(encoding="utf-8"))
        brief = artifact["brief"]
        if (
            artifact.get("schema_version") != 1
            or artifact.get("run_id") != run_id
            or artifact.get("creator") != "maya"
            or not isinstance(artifact.get("candidate_id"), str)
            or not artifact["candidate_id"]
            or (
                expected_candidate_id is not None
                and artifact["candidate_id"] != expected_candidate_id
            )
            or artifact.get("source_decision") not in allowed_sources
            or not isinstance(brief, dict)
            or (
                set(brief) != _BRIEF_FIELDS
                and set(brief) != _PROFESSIONAL_BRIEF_FIELDS
            )
        ):
            return None
        text_fields = set(brief) - {
            "key_beats",
            "hook_options",
            "information_gap",
            "success_metrics",
        }
        if not all(
            isinstance(brief[field], str) and brief[field].strip()
            for field in text_fields
        ):
            return None
        beats = brief["key_beats"]
        if not isinstance(beats, list) or not all(
            isinstance(beat, str) and beat.strip() for beat in beats
        ):
            return None
        if set(brief) == _PROFESSIONAL_BRIEF_FIELDS:
            gap = brief["information_gap"]
            if (
                len(beats) < 5
                or
                not isinstance(gap, dict)
                or set(gap) != {"known", "unknown", "payoff"}
                or not all(isinstance(value, str) and value.strip() for value in gap.values())
                or not all(
                    isinstance(brief[field], list)
                    and len(brief[field]) >= 3
                    and all(isinstance(value, str) and value.strip() for value in brief[field])
                    for field in ("hook_options", "success_metrics")
                )
            ):
                return None
    except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError):
        return None
    return artifact


def load_maya_brief(artifacts_root, run_id):
    """Load the legacy selected-candidate brief for one run."""
    if not isinstance(run_id, str) or not run_id:
        return None
    path = Path(artifacts_root).resolve() / "reviews" / run_id / "maya_content_brief.json"
    return _load_brief_path(path, run_id, {"review_decision.json"})


def load_maya_briefs(artifacts_root, run_id):
    """Load all valid saved Maya briefs for the run, keyed by candidate ID."""
    if not isinstance(run_id, str) or not run_id:
        return {}
    root = Path(artifacts_root).resolve() / "reviews" / run_id
    artifacts = {}
    legacy = load_maya_brief(artifacts_root, run_id)
    if legacy is not None:
        artifacts[legacy["candidate_id"]] = legacy
    for path in sorted((root / "maya_briefs").glob("*.json")):
        artifact = _load_brief_path(
            path,
            run_id,
            {"primary_candidate_batch"},
            expected_candidate_id=path.stem,
        )
        if artifact is not None:
            artifacts[artifact["candidate_id"]] = artifact
    return artifacts


def format_maya_brief(artifact):
    brief = artifact["brief"]
    beats = "\n".join(
        f"{index}. {beat}" for index, beat in enumerate(brief["key_beats"], start=1)
    )
    return f"""# {brief['title']}

## Strategic Rationale
{brief['strategic_rationale']}

**Audience:** {brief['audience']}

**Tone:** {brief['tone']}

## Hook
{brief['hook']}

## YouTube Short Concept
{brief['concept']}

## Key Beats
{beats}

## Thumbnail Direction
{brief['thumbnail_direction']}

## Call to Action
{brief['call_to_action']}
"""
