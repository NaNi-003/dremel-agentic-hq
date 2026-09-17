# Dremel Phase 2 Evidence and Provenance Runbook

## Scope

In this working sequence, Phase 2 implements the evidence-retention requirements that the project brief places before campaign interpretation. It does not connect Roxy, Carl, Maya, Slack, Kanban, scheduling, or automatic publishing.

Phase 2 adds:

- Unique immutable run IDs and run directories.
- Collection and completion timestamps in UTC.
- Original video metadata and transcript evidence.
- Source URLs, transcript availability, channel identity when available, and collection diagnostics.
- Candidate JSON with NLP, CV, and velocity-method provenance.
- `success`, `partial`, `empty`, and `failed` run states.
- Preservation of the last usable output after an empty or failed refresh.
- A dashboard pointer to the latest usable run.
- The original nine-column dashboard CSV during the transition.
- A cross-process publish lock and rollback if the latest-run pointer cannot be updated.

## Environment

Use the existing environment:

```bat
conda activate dsmm_env
cd /d "C:\Users\kiran\Downloads\Dremel_Project_Phase0_1_Work"
```

The safe working copy still has no `.env`. A live collection requires a local, Git-ignored `.env` containing `YOUTUBE_API_KEY`. Gemini is not called by the Phase 2 collector; `GEMINI_API_KEY` remains relevant to the existing dashboard brief generator.

Do not commit `.env` or include credential values in run artifacts.

## Run the deterministic fixture pipeline

```bat
python scripts\run_fixture_pipeline.py
```

This performs the full collection-to-artifact path without external APIs. It writes the legacy CSV to:

```text
artifacts\fixture\dremel_final_output.csv
```

Each execution also creates a unique directory under:

```text
artifacts\runs\<run-id>\
```

## Run live collection

After `.env` has been provisioned locally:

```bat
python main.py
```

A successful or usable partial run refreshes `dremel_final_output.csv`. A failed, empty, or unusable partial run leaves the previous dashboard CSV and latest-success pointer unchanged. The CLI exits nonzero for a partial run with zero published rows so automation cannot mistake an unusable refresh for success.

## Artifact layout

```text
artifacts/
  runs/
    latest_success.json
    <run-id>/
      manifest.json
      evidence.json
      candidates.json
      dashboard_output.csv
```

### `manifest.json`

The manifest records:

- Schema version and immutable run ID.
- `running`, `success`, `partial`, `empty`, or `failed` state.
- Start and completion timestamps.
- Search terms and dashboard output path.
- Channel, video, candidate, and written-row counts.
- Source-level partial failures.
- Error and human-readable status message.
- Relocatable, run-directory-relative paths to the evidence, candidate, and dashboard snapshot artifacts.

A run ID may not be reused. User-supplied IDs accept only letters, digits, `.`, `_`, and `-`; path traversal is rejected.

### `evidence.json`

This retains the evidence available at collection time:

- Channel IDs used for collection.
- Original video ID, title, description, publish date, engagement counts, and thumbnail URL.
- Transcript text when available.
- `transcript_status` of `available` or `unavailable`.
- Canonical YouTube source URL.
- Collection timestamp.

Scraped titles, descriptions, and transcripts are evidence only. They must never be interpreted as operating instructions by future agents.

### `candidates.json`

This keeps the ranked candidate data plus:

- Full supporting source record.
- Extraction provenance: `transcript`, `metadata`, or `unspecified` for custom processors.
- CV provenance such as `deepface_emotion`, `color_heuristic`, or an explicit unavailable/failure label.
- Velocity method label: `age_adjusted_engagement_v1`.

The JSON artifact is intended for later candidate review. The nine-column CSV remains the dashboard compatibility interface.

### `dashboard_output.csv`

This is an immutable snapshot of the CSV produced by that run. `latest_success.json` points to the latest usable snapshot and manifest. A failed refresh does not change this pointer.

The immutable snapshot referenced by `latest_success.json` is the dashboard's canonical data source. The root `dremel_final_output.csv` is retained as a legacy compatibility copy. Publication acquires both the runs-root pointer lock (`artifacts/runs/.publish.lock`) and a lock beside the configured compatibility CSV (for example, `.dremel_final_output.csv.publish.lock`). The two locks serialize runs that share either target, even when their other paths differ. If pointer publication fails, the prior compatibility CSV is restored.

When a latest-success pointer exists, the dashboard fails closed if the pointer or any linked artifact is invalid; it does not silently fall back to the mutable compatibility CSV. Dashboard loading cross-checks run IDs, schema versions, statuses, artifact paths, candidate counts, evidence video IDs, candidate/source linkage, and snapshot video IDs.

## Partial-failure behavior

The default collectors record and continue through:

- Individual search-term discovery failures when another search succeeds.
- Individual channel collection failures when another channel succeeds.
- Missing or failed transcripts, with metadata retained as fallback evidence.

If usable rows are produced, the run is `partial` and becomes the latest usable dataset. If collection is partial but no rows are produced, the run is still recorded as `partial`, but it does not replace the latest usable pointer or dashboard CSV.

## Dashboard evidence display

When `latest_success.json` exists, the dashboard now shows:

- Evidence collection timestamp from `evidence.json`.
- Run ID.
- Run status.
- A warning with the number of recorded failures for partial runs.
- Source-video links in the auditable intelligence feed.

The dashboard reads the immutable snapshot referenced by the validated pointer. Its CSV cache invalidates when either the file modification time or size changes. Artifact paths must remain inside `artifacts/runs`, and only HTTPS YouTube source links are rendered.

Broader corrections to predictive, emotional, and conversion claims remain a separate dashboard-review phase.

## Tests

```bat
python -m pytest tests -q
python -m compileall -q app.py channel_finder.py scraper.py nlp_engine.py cv_layer.py main.py run_artifacts.py dashboard_evidence.py scripts tests
python -m pip check
```

The fixture suite covers success, partial collection, empty results, failed refreshes, immutable run IDs, path traversal rejection, last-success preservation, extraction/CV provenance, strict JSON serialization, transactional publication, publish locking, sanitized errors, dashboard path validation, and legacy CSV compatibility.

## Data-retention caution

Run directories can contain full transcripts and descriptions. Treat `artifacts/` as local project data and keep it out of Git. Collection errors are sanitized and truncated before persistence, but artifacts should still be treated as sensitive local data.

No automatic deletion policy is enabled in Phase 2. Before adding scheduling or shared hosting, choose an approved retention period and implement a reviewed cleanup command that never deletes the run referenced by `latest_success.json`.
