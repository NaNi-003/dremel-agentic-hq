import json
from types import SimpleNamespace

import pytest

import maya_integration


VALID_BRIEF = {
    "title": "Restore It, Don't Replace It",
    "objective": "Increase qualified interest in practical Dremel restoration projects.",
    "strategic_rationale": "The idea turns the approved restoration signal into a useful short-form story.",
    "audience": "New DIYers in the UK",
    "audience_insight": "They want proof that a worn object can be saved before buying a replacement.",
    "tone": "Bold, helpful, enthusiastic",
    "hook": "This scratched table looks finished—but wait until you see what one small tool can uncover.",
    "hook_options": [
        "What is hiding under this damaged finish?",
        "Would you replace this table—or try one last restoration?",
        "The final surface is not what this damage suggests.",
    ],
    "information_gap": {
        "known": "The table appears badly damaged.",
        "unknown": "Whether the original surface can be recovered.",
        "payoff": "The restored surface is revealed only after the process is demonstrated.",
    },
    "concept": "A fast restoration journey that delays the reveal and shows the transformation steps.",
    "key_beats": [
        "Show the damaged surface",
        "Frame the restoration question",
        "Demonstrate the key process",
        "Delay the finished view",
        "Reveal the restored table",
    ],
    "product_role": "The Dremel supports the demonstrated restoration step without unsupported performance claims.",
    "thumbnail_direction": "Show the damaged table and a curious creator expression; hide the final result.",
    "call_to_action": "What would you restore instead of replacing?",
    "success_metrics": ["Qualified comments", "Completion rate", "Saves and shares"],
    "claims_guardrails": "Use only product capabilities visible in the evidence; do not promise guaranteed results.",
}


def test_parse_maya_response_accepts_one_strict_brief_object():
    assert maya_integration.parse_maya_response(json.dumps(VALID_BRIEF)) == VALID_BRIEF


def test_parse_maya_response_rejects_markdown_wrapping():
    with pytest.raises(maya_integration.MayaIntegrationError, match="raw JSON"):
        maya_integration.parse_maya_response('```json\n{"title":"brief"}\n```')


def test_build_maya_prompt_uses_only_carls_approved_candidate():
    packet = {
        "run_id": "run-1",
        "candidates": [
            {"candidate_id": "video-1", "action_pair": "Restore Table"},
            {"candidate_id": "video-2", "action_pair": "Cut Tile"},
        ],
    }
    decision = {
        "decision": "approve",
        "selected_candidate_id": "video-1",
        "rationale": "The restoration opportunity is supported.",
        "evidence_citations": ["evidence.json#/videos/0"],
    }

    prompt = maya_integration.build_maya_prompt(packet, decision)

    assert '"candidate_id": "video-1"' in prompt
    assert '"candidate_id": "video-2"' not in prompt
    assert "YouTube Short" in prompt
    assert "professional creative brief" in prompt
    assert "self-check" in prompt
    assert "Return only the JSON object" in prompt


def test_validate_maya_brief_requires_exact_useful_fields():
    assert maya_integration.validate_maya_brief(dict(VALID_BRIEF)) == VALID_BRIEF

    malformed = dict(VALID_BRIEF)
    malformed["extra"] = "not part of the brief"
    with pytest.raises(maya_integration.MayaIntegrationError, match="fields"):
        maya_integration.validate_maya_brief(malformed)


def test_request_maya_brief_uses_approved_decision_and_writes_artifact(
    tmp_path, monkeypatch
):
    packet_path = tmp_path / "reviews" / "run-1" / "review_packet.json"
    packet_path.parent.mkdir(parents=True)
    packet_path.write_text("{}", encoding="utf-8")
    decision_path = packet_path.with_name("review_decision.json")
    decision_path.write_text("{}", encoding="utf-8")
    packet = {
        "run_id": "run-1",
        "candidates": [{"candidate_id": "video-1", "action_pair": "Restore Table"}],
    }
    decision = {
        "decision": "approve",
        "selected_candidate_id": "video-1",
        "rationale": "The restoration opportunity is supported.",
        "evidence_citations": ["evidence.json#/videos/0"],
    }
    monkeypatch.setattr(
        maya_integration.phase3_review,
        "validate_review_packet",
        lambda path, *, artifacts_root: packet,
    )
    monkeypatch.setattr(
        maya_integration.phase3_review,
        "validate_review_decision",
        lambda proposed, *, packet_path, artifacts_root: decision,
    )

    result = maya_integration.request_maya_brief(
        packet_path=packet_path,
        decision_path=decision_path,
        artifacts_root=tmp_path,
        invoke=lambda prompt: json.dumps(VALID_BRIEF),
    )

    assert result["brief_path"] == packet_path.with_name("maya_content_brief.json")
    artifact = json.loads(result["brief_path"].read_text(encoding="utf-8"))
    assert artifact["creator"] == "maya"
    assert artifact["candidate_id"] == "video-1"
    assert artifact["brief"] == VALID_BRIEF


def test_request_primary_briefs_creates_one_valid_brief_for_every_packet_candidate(
    tmp_path, monkeypatch
):
    packet_path = tmp_path / "reviews" / "run-1" / "review_packet.json"
    packet_path.parent.mkdir(parents=True)
    packet_path.write_text("{}", encoding="utf-8")
    packet = {
        "run_id": "run-1",
        "candidates": [
            {
                "candidate_id": f"video-{index}",
                "action_pair": f"Opportunity {index}",
                "evidence_refs": [f"evidence.json#/videos/{index}"],
            }
            for index in range(1, 16)
        ],
    }
    monkeypatch.setattr(
        maya_integration.phase3_review,
        "validate_review_packet",
        lambda path, *, artifacts_root: packet,
    )
    prompts = []

    def invoke(prompt):
        prompts.append(prompt)
        return json.dumps(VALID_BRIEF)

    result = maya_integration.request_primary_briefs(
        packet_path=packet_path,
        artifacts_root=tmp_path,
        invoke=invoke,
    )

    assert result["run_id"] == "run-1"
    assert result["brief_count"] == 15
    assert len(prompts) == 15
    assert all("validated top-15 primary opportunity" in prompt for prompt in prompts)
    assert all("Carl's approved opportunity" not in prompt for prompt in prompts)
    assert set(result["briefs"]) == {f"video-{index}" for index in range(1, 16)}
    for candidate_id, artifact in result["briefs"].items():
        assert artifact["candidate_id"] == candidate_id
        assert artifact["source_decision"] == "primary_candidate_batch"
        path = packet_path.parent / "maya_briefs" / f"{candidate_id}.json"
        assert json.loads(path.read_text(encoding="utf-8")) == artifact

    repeated = maya_integration.request_primary_briefs(
        packet_path=packet_path,
        artifacts_root=tmp_path,
        invoke=invoke,
    )
    assert repeated["brief_count"] == 15
    assert len(prompts) == 15


@pytest.mark.parametrize("candidate_id", ["../review_packet", "CON"])
def test_request_primary_briefs_rejects_unsafe_candidate_filename(
    tmp_path, monkeypatch, candidate_id
):
    packet_path = tmp_path / "reviews" / "run-1" / "review_packet.json"
    packet_path.parent.mkdir(parents=True)
    packet_path.write_text("original", encoding="utf-8")
    monkeypatch.setattr(
        maya_integration.phase3_review,
        "validate_review_packet",
        lambda path, *, artifacts_root: {
            "run_id": "run-1",
            "candidates": [
                {
                    "candidate_id": candidate_id,
                    "action_pair": "Unsafe",
                    "evidence_refs": [],
                }
            ],
        },
    )

    with pytest.raises(maya_integration.MayaIntegrationError, match="Candidate ID"):
        maya_integration.request_primary_briefs(
            packet_path=packet_path,
            artifacts_root=tmp_path,
            invoke=lambda prompt: (_ for _ in ()).throw(
                AssertionError("Maya must not run for an unsafe candidate ID")
            ),
        )

    assert packet_path.read_text(encoding="utf-8") == "original"


def test_request_primary_briefs_validates_entire_batch_before_invoking_maya(
    tmp_path, monkeypatch
):
    packet_path = tmp_path / "reviews" / "run-1" / "review_packet.json"
    packet_path.parent.mkdir(parents=True)
    packet_path.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(
        maya_integration.phase3_review,
        "validate_review_packet",
        lambda path, *, artifacts_root: {
            "run_id": "run-1",
            "candidates": [
                {"candidate_id": "safe-video", "evidence_refs": []},
                {"candidate_id": "../unsafe", "evidence_refs": []},
            ],
        },
    )
    calls = []

    with pytest.raises(maya_integration.MayaIntegrationError, match="Candidate ID"):
        maya_integration.request_primary_briefs(
            packet_path=packet_path,
            artifacts_root=tmp_path,
            invoke=lambda prompt: calls.append(prompt) or json.dumps(VALID_BRIEF),
        )

    assert calls == []


def test_invoke_maya_profile_uses_named_hermes_profile(monkeypatch):
    observed = {}

    def fake_run(command, **kwargs):
        observed["command"] = command
        return SimpleNamespace(returncode=0, stdout=' {"title":"brief"}\n')

    monkeypatch.setattr(maya_integration.subprocess, "run", fake_run)

    response = maya_integration.invoke_maya_profile("create brief", profile="maya")

    assert observed["command"][0:3] == ["hermes", "-p", "maya"]
    assert observed["command"][-2:] == ["--oneshot", "create brief"]
    assert response == '{"title":"brief"}'
