# Dremel Phase 3B: Carl Connection

Phase 3B adds one thin agentic step to the existing project:

```text
Phase 2 research output -> frozen review packet -> Carl -> validated decision
```

Carl does not replace the YouTube collection or scoring scripts. He reviews their result and decides whether the proposed content opportunity is supported well enough to pass to the next content stage.

## Run

```bat
conda activate dsmm_env
cd /d "C:\Users\kiran\Downloads\Dremel_Project_Phase0_1_Work"
python scripts\request_carl_review.py ^
  --packet artifacts\reviews\<run-id>\review_packet.json ^
  --artifacts-root artifacts
```

The command:

1. Validates the packet.
2. Sends it to the existing `carl` Hermes profile in one-shot mode.
3. Parses Carl's JSON response.
4. Validates and records `review_decision.json`.

Carl may return `approve`, `reject`, or `needs_evidence`. No Roxy, Maya, Slack, scheduling, or publishing connection is added in this phase.
