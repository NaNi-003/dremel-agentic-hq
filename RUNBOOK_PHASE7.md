# Phase 7: Roxy-Coordinated here.now Launch

Roxy is the narrow workflow and launch owner for the Dremel dashboard.

```text
Pipeline -> Carl review -> Maya brief -> static build -> user-approved here.now publish -> live verification
```

## Live dashboard

- Site: https://poppy-entry-pw3g.here.now/
- Provider: here.now
- Deployment: permanent authenticated site
- Current run: `20260920T032943Z-c4888aaf`

The here.now account dashboard remains at `https://here.now/dashboard`; it is not the project URL.

## Run the publishing step

The API key is read without printing it from either:

1. `HERENOW_API_KEY`, or
2. `C:\Users\kiran\.herenow\credentials`

Build and update the existing site:

```bash
"C:/Users/kiran/anaconda3/envs/dsmm_env/python.exe" scripts/publish_here_now.py
```

The non-secret deployment receipt is stored at:

```text
artifacts/deployment/here_now_site.json
```

It contains the stable site slug and lets later runs update the same site rather than create duplicates. Runtime artifacts remain untracked.

## Ownership

- **Roxy:** coordinates the sequence, runs the approved publish step, and verifies the live URL.
- **Carl:** reviews the research opportunity and approves, rejects, or requests evidence.
- **Maya:** creates the brief only after Carl approves.
- **User:** authorizes consequential external publishing.

The launch script identifies itself to here.now as `roxy/dremel-launch`.

## Current launch note

The current live research run is usable but partial. It contains ten candidates and 119 recorded transcript-collection failures. Carl explicitly approved the selected candidate while acknowledging the partial collection. Maya's matching brief is visible in the live dashboard.
