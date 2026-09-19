# Dremel Phase 3A Carl Review Interface Runbook

## Scope

Phase 3A introduces a deterministic boundary between the Phase 2 evidence pipeline and a future Carl reviewer profile. It does **not** invoke Carl, modify Carl's Hermes profile, create a Maya handoff, connect Roxy or Slack, create Kanban tasks, add scheduling, or authorize publishing, outreach, spending, or any other external action.

The interface has two application-level write-once artifacts:

```text
artifacts/
  runs/<run-id>/                  # Phase 2 source bundle
  reviews/<run-id>/
    review_packet.json            # generated once
    review_decision.json          # recorded once after validation
```

The review directory can also contain `.review_decision.lock`, used to serialize cooperating decision writers. A decision is fsynced to a same-directory temporary file and then published with a no-replace hard-link operation, so readers see either no final decision or the complete bytes and a competing writer is not overwritten. The artifact filesystem must support hard links.

## Mental model

```text
Phase 2 run bundle
      |
      | validate IDs, counts, provenance, snapshot, and source files
      v
review_packet.json  -- SHA-256 bound -->  Carl decision contract
                                              |
                                              | validate reviewer, outcome,
                                              | candidate, citations, risks
                                              v
                                      review_decision.json
```

The packet does not declare that a candidate is good. It freezes what Carl is allowed to review. The decision does not authorize external activity; it only records `approve`, `reject`, or `needs_evidence`.

## Create a review packet

Use the required project interpreter/environment:

```bat
conda activate dsmm_env
cd /d "C:\Users\kiran\Downloads\Dremel_Project_Phase0_1_Work"
python scripts\create_review_packet.py --run-id <run-id>
```

Optional path overrides:

```bat
python scripts\create_review_packet.py ^
  --runs-root artifacts\runs ^
  --reviews-root artifacts\reviews ^
  --run-id <run-id>
```

The command emits one JSON object containing:

- `status: "pending_review"`
- `run_id`
- absolute `packet_path`
- `packet_sha256`

A packet can only be generated for a usable `success` or `partial` Phase 2 run. A second packet for the same run is rejected rather than overwritten.

## Packet guarantees

`review_packet.json` includes:

- Schema version, run ID, run status, generation timestamp, and `pending` state.
- `evidence_is_untrusted: true` so scraped text is never treated as operating instructions.
- Any Phase 2 partial-failure records.
- Candidate IDs, score summaries, provenance, and JSON-pointer-style evidence references.
- Relative paths, byte sizes, and SHA-256 digests for the Phase 2 manifest, evidence, candidates, and dashboard snapshot.

Packet creation fails closed if:

- The run or artifact paths are missing or escape their managed directory.
- Schema versions or run IDs disagree.
- Candidate/source/evidence IDs do not link correctly.
- Manifest counts disagree with candidates or dashboard rows.
- Dashboard candidate IDs disagree with candidate JSON.
- No candidate is available for review.

Packet validation requires the canonical `<artifact-root>/reviews/<run-id>/review_packet.json` shape, with the directory name equal to the packet run ID, and binds its manifest to `<artifact-root>/runs/<run-id>/manifest.json`. It recomputes every source size and digest from the same byte snapshots used for parsing, revalidates the manifest's artifact references, counts, lifecycle status, and dashboard IDs, and reconstructs each candidate summary from the frozen source files. Post-generation mutation of either the source artifacts or the packet summary is rejected. JSON is parsed strictly: `NaN` and infinity are rejected, timestamps must be timezone-aware strings, and booleans are not accepted as schema versions, byte sizes, or counts.

## Carl decision contract

Carl's output must be a JSON object with exactly these fields:

```json
{
  "schema_version": 1,
  "run_id": "<run-id>",
  "packet_sha256": "<64 lowercase hex characters>",
  "reviewer": "carl",
  "decision": "approve",
  "selected_candidate_id": "<candidate video ID>",
  "rationale": "A source-grounded explanation.",
  "evidence_citations": ["evidence.json#/videos/0"],
  "risk_acknowledgements": [],
  "reviewed_at": "2026-09-18T08:30:00Z",
  "external_actions_authorized": false
}
```

Allowed outcomes:

| Outcome | Candidate rule | Citation rule |
|---|---|---|
| `approve` | Must select exactly one candidate from the packet | Citations must belong to that candidate |
| `reject` | `selected_candidate_id` must be `null` | Citations must belong to the packet |
| `needs_evidence` | `selected_candidate_id` must be `null` | Citations must belong to the packet |

Additional controls:

- `reviewer` must be exactly `carl`.
- Rationale must be non-empty and no longer than 4,000 characters.
- `reviewed_at` must be timezone-aware.
- An approval of a `partial` run must include `"partial_collection"` in `risk_acknowledgements`.
- `external_actions_authorized` must remain `false`.
- Unknown or missing fields are rejected.
- The packet and all bound Phase 2 source artifacts are revalidated before recording.

## Record a decision

Save Carl's raw JSON response to a temporary local file outside the write-once review directory, then run:

```bat
python scripts\record_review_decision.py ^
  --packet artifacts\reviews\<run-id>\review_packet.json ^
  --decision path\to\carl-output.json ^
  --artifacts-root artifacts
```

A valid decision is atomically published without replacement to:

```text
artifacts\reviews\<run-id>\review_decision.json
```

A second decision for the same packet is rejected rather than replacing the first. Corrections therefore require an explicit future supersession design; Phase 3A does not silently rewrite review history.

This is an application-level guarantee, not operating-system write-once storage. A user or process with direct write permission to `artifacts/` can still modify or delete files. Keep that directory least-privileged and auditable; later consumers must revalidate the packet, decision digest binding, and frozen source digests before acting. Hardware-backed or append-only storage is outside Phase 3A.

## Human and downstream boundaries

An `approve` decision means only that Carl found one candidate adequately supported for the next internal preparation stage. It does not authorize:

- Publishing content.
- Contacting creators or customers.
- Spending campaign funds.
- Sending Slack messages.
- Creating or assigning Maya work automatically.

A future Phase 3B may connect the reviewed contract to the separate Carl profile. A later Maya handoff must validate `review_decision.json` again and may only be created for an approved candidate. Roxy remains the sole planned Slack-facing profile, and the user remains the final authority for consequential external actions.

## Verification

```bat
python -m pytest tests\test_phase3_review.py -q
python -m pytest tests -q
python -m compileall -q phase3_review.py scripts tests
python -m pip check
```

`artifacts/` remains Git-ignored. Review packets and decisions may contain sensitive campaign evidence or rationale and should follow the same future retention policy as Phase 2 run bundles.
