# Dremel Phase 0–1 Administrator Runbook

## Scope

This working copy preserves the original prototype while making the pipeline importable, fixture-testable, and able to return a structured `PipelineResult`. It does not connect Hermes agents, Slack, Kanban, cron, or external publishing.

## Safe working copy

- Working copy: `C:\\Users\\kiran\\Downloads\\Dremel_Project_Phase0_1_Work`
- Original project: unchanged at `C:\\Users\\kiran\\Downloads\\DSMM Final Project Codebase - Export\\DSMM Final Project Codebase - Export`
- Preserved artifacts are under `baseline/`.
- The development copy intentionally does not contain the original `.env` file.

## Supported environment

The implementation was exercised with the existing Conda environment:

- Environment: `dsmm_env`
- Python: 3.10.20
- spaCy model: `en_core_web_sm` 3.8.0

Python 3.10 remains the current project baseline to avoid changing analytical behavior during Phase 1. Google has announced that newer `google-api-core` releases will stop supporting Python 3.10 after its end-of-life date, so a Python upgrade should be evaluated separately after the baseline is stable.

## Install the reproducible dependency set

From Anaconda Prompt:

```bat
conda activate dsmm_env
cd /d "C:\Users\kiran\Downloads\Dremel_Project_Phase0_1_Work"
python -m pip install -r requirements-lock.txt
python -m pip install "https://github.com/explosion/spacy-models/releases/download/en_core_web_sm-3.8.0/en_core_web_sm-3.8.0-py3-none-any.whl"
python -m pip check
```

`requirements-lock.txt` pins the full core/test dependency graph resolved for Python 3.10. Use `requirements.txt` and `requirements-dev.txt` as the human-maintained direct dependency inputs when intentionally upgrading packages, then regenerate the lock with:

```bat
uv pip compile requirements-dev.txt --python-version 3.10 --output-file requirements-lock.txt
```

DeepFace is optional because the code loads it only when visual analysis needs it and falls back to a color heuristic when it is unavailable. For a fully pinned installation that includes DeepFace and TensorFlow:

```bat
python -m pip install -r requirements-optional-cv-lock.txt
python -m pip check
```

Regenerate that optional lock after deliberate dependency changes with:

```bat
uv pip compile requirements-dev.txt requirements-optional-cv.txt --python-version 3.10 --output-file requirements-optional-cv-lock.txt
```

## Configure credentials for a live run

Copy `.env.example` to `.env` and populate the two values locally:

```text
YOUTUBE_API_KEY=...
GEMINI_API_KEY=...
```

Never commit `.env`. Fixture tests do not need either credential.

## Run the tests

```bat
conda activate dsmm_env
cd /d "C:\Users\kiran\Downloads\Dremel_Project_Phase0_1_Work"
python -m pytest tests -q
```

## Exercise the deterministic fixture pipeline

```bat
python scripts\run_fixture_pipeline.py
```

The script writes only to `artifacts/fixture/dremel_final_output.csv`; it does not call YouTube, Gemini, Slack, or any Hermes profile.

## Run the live collector

Only after `.env` is configured:

```bat
python main.py
```

The default live command retains the original analytical sequence and writes `dremel_final_output.csv` in the current working directory. `run_pipeline()` now returns a `PipelineResult` with:

- `status`: `success`, `empty`, or `failed`
- output path
- channel, video, candidate, and written-row counts
- message
- error text when applicable

An empty or failed run does not overwrite a previously successful output file.

## Launch the dashboard

```bat
streamlit run app.py
```

Dashboard claim corrections, evidence provenance, and refresh-state display belong to later phases and are not part of this Phase 1 change.
