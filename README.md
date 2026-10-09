# Dremel marketing intelligence

A small research pipeline ranks DIY YouTube videos for Dremel campaign planning. Real agents on an agent platform (Grok Bot) decide what to do with that evidence. This repository is their tool belt: deterministic commands with JSON in and JSON out.

The operating manual is [`AGENTS.md`](AGENTS.md).

## Architecture

```text
Human
  approves anything external
        |
        v
Roxy (orchestrator)
  hq collect / status / dashboard / publish --confirm
        |                         |
        | one-line handoff        | one-line handoff
        v                         v
Carl (analyst)              Maya (briefs)
  hq candidates             hq evidence
  hq evidence               hq brief
  hq review
        |
        v
Python tools
  channel_finder -> scraper -> nlp_engine -> cv_layer
  artifacts/runs/<run_id>/{manifest,evidence,candidates}.json
  artifacts/reviews/<run_id>/{decisions,briefs}/
  dist/dashboard
```

Collection, spaCy action extraction, the age-adjusted engagement score, and thumbnail analysis stay in Python. Carl, Maya, and Roxy are not Python modules and this repo does not call a model on their behalf.

| Path | What it holds |
|---|---|
| `artifacts/runs/<run_id>/` | Evidence, ranked candidates, manifest, dashboard snapshot |
| `artifacts/runs/latest_success.json` | Pointer to the latest usable run |
| `artifacts/reviews/<run_id>/decisions/` | Carl's decisions, one JSON file per candidate |
| `artifacts/reviews/<run_id>/briefs/` | Maya's briefs for approved candidates |
| `dist/dashboard/` | Static dashboard |
| `artifacts/deployment/here_now_site.json` | Last confirmed here.now publish |

`Dremel_Project_Status_and_Agentic_Automation_Brief.md` is the June/September assessment that led here. It is background, not the operating manual.

## Setup

Use Python 3.11 or newer.

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python -m spacy download en_core_web_sm
```

On Windows, activate the environment with `.venv\Scripts\activate`. Install the same requirements file. Do not point scripts at a machine-specific Anaconda path.

Copy `.env.example` to `.env` and fill in only the keys you need. `.env` is gitignored. Never commit it.

| Variable | Used by |
|---|---|
| `YOUTUBE_API_KEY` | Live collection (`hq collect` without `--fixture`) |
| `GEMINI_API_KEY` | Optional thumbnail vision inside `cv_layer.py`. Leave it unset to skip that call. |
| `GEMINI_VISION_MODEL` | Optional override for that vision call. Defaults to `gemini-2.5-flash`. |
| `HERENOW_API_KEY` | `hq publish --confirm` only. A key in `~/.herenow/credentials` is also accepted. |

Carl and Maya do not use `GEMINI_API_KEY`. Their judgment runs in the agent platform.

`requirements-lock.txt` and `requirements-optional-cv-lock.txt` are older resolver snapshots and still mention Streamlit. Install from `requirements.txt`. Optional DeepFace weights are not required; thumbnail analysis falls back when they are absent.

## Commands

Every command prints one JSON object to stdout and exits non-zero on error. `hq publish` without `--confirm` exits `2`.

```bash
python -m hq collect [--refresh | --reuse] [--fixture] [--max-age-hours 24]
python -m hq candidates [--run-id ID]
python -m hq evidence CANDIDATE_ID [--run-id ID]
python -m hq review --input decision.json [--run-id ID]
python -m hq brief --input brief.json [--run-id ID]
python -m hq dashboard [--output dist/dashboard] [--run-id ID]
python -m hq publish --confirm [--site-dir dist/dashboard] [--slug SLUG]
python -m hq status [--run-id ID]
```

`collect` reuses the latest usable run when it is still inside `--max-age-hours` (default 24). Otherwise it collects. `--reuse` never collects and reports `fresh` or `stale`. `--refresh` always collects; if that fails and an older usable run exists, the command returns that run with `freshness: stale` and a `refresh_error`. A partial collection is `collection_status: partial` and includes `collected_at`. `--fixture` runs the checked-in videos file and does not call YouTube.

Review JSON, brief JSON, and the order of work are in [`AGENTS.md`](AGENTS.md).

Check the flow offline:

```bash
python -m hq collect --fixture --refresh --output artifacts/fixture/dremel_final_output.csv
python -m hq status
```

## Tests

```bash
python -m pytest
```

The suite does not call YouTube, Gemini, or here.now. Pipeline and scoring tests cover the deterministic core. CLI tests drive a fixture run and the validation edges (unknown candidate, empty rationale, missing evidence, brief before approval, publish without `--confirm`).

## Dashboard

`hq dashboard` builds the static site in `web_dashboard/`: ideation, trend matrix, intelligence feed, creator briefs for approved candidates, and the campaign ROI estimator (unconstrained and availability-constrained). The velocity KPI is labelled age-adjusted. Colour and expression labels are visual heuristics.

Open `dist/dashboard/index.html` locally, or publish only after a human approval:

```bash
python -m hq publish --confirm
```
