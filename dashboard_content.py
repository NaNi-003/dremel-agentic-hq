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


def load_maya_brief(artifacts_root, run_id):
    """Load the Maya brief for one run, returning None when unavailable or invalid."""
    if not isinstance(run_id, str) or not run_id:
        return None
    path = Path(artifacts_root).resolve() / "reviews" / run_id / "maya_content_brief.json"
    try:
        artifact = json.loads(path.read_text(encoding="utf-8"))
        brief = artifact["brief"]
        if (
            artifact.get("schema_version") != 1
            or artifact.get("run_id") != run_id
            or artifact.get("creator") != "maya"
            or not isinstance(artifact.get("candidate_id"), str)
            or not artifact["candidate_id"]
            or artifact.get("source_decision") != "review_decision.json"
            or not isinstance(brief, dict)
            or set(brief) != _BRIEF_FIELDS
        ):
            return None
        text_fields = _BRIEF_FIELDS - {"key_beats"}
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
    except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError):
        return None
    return artifact


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
