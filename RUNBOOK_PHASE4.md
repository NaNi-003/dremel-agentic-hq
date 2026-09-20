# Dremel Phase 4: Maya Content Brief

Phase 4 adds the content step from the original dashboard as a Maya agent task:

```text
YouTube pipeline -> Carl-approved opportunity -> Maya content brief
```

Maya receives only Carl's approved candidate and creates a concise Dremel UK YouTube Short brief containing the rationale, audience, tone, Information Gap hook, concept, key beats, thumbnail direction, and call to action.

## Run

```bat
conda activate dsmm_env
cd /d "C:\Users\kiran\Downloads\Dremel_Project_Phase0_1_Work"
python scripts\request_maya_brief.py ^
  --packet artifacts\reviews\<run-id>\review_packet.json ^
  --decision artifacts\reviews\<run-id>\review_decision.json ^
  --artifacts-root artifacts
```

The generated brief is saved as:

```text
artifacts\reviews\<run-id>\maya_content_brief.json
```

This phase connects Maya only. It does not add Roxy, Slack, scheduling, or publishing.
