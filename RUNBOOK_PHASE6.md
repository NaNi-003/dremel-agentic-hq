# Phase 6: Static here.now Dashboard

The public dashboard is now built as a static site rather than served by Streamlit.

## What stays the same

The browser UI retains the original dashboard structure and controls:

- Dremel-branded strategy sidebar
- executive KPI cards
- Autonomous Content Ideation tab
- Trend Lifecycle Matrix tab
- Raw Intelligence Feed tab
- Campaign ROI Estimator tab
- Maya brief display and download

The former Streamlit file remains only as a local visual/behavior reference. It is not the publish target.

## Build

Use the project environment:

```bash
"C:/Users/kiran/anaconda3/envs/dsmm_env/python.exe" static_dashboard.py --output dist/dashboard
```

The build validates and snapshots the latest pipeline output into `dist/dashboard/data/dashboard.json`. The complete here.now upload directory is `dist/dashboard`.

## Hosting decision

`https://here.now/dashboard` is here.now's account/login dashboard. A project cannot replace that route.

here.now publishes a project at one of these addresses:

- `https://<site-slug>.here.now/`
- `https://<handle>.here.now/dashboard` when a paid handle and link are configured
- a linked custom domain/location

The static conversion belongs in this phase because here.now hosts static files, not a Streamlit Python process. The permanent production publish belongs in the next launch phase because it requires an owned here.now account/API key and a final public location.

## Publishing owner

Roxy should own the narrow launch step once her coordinator profile is connected. She should:

1. run the existing pipeline/Carl/Maya sequence;
2. build `dist/dashboard`;
3. request the user's approval for the external publish;
4. publish or update the owned here.now site;
5. return the verified live URL.

Carl remains the opportunity reviewer and Maya remains the content specialist. Neither should own infrastructure publishing. Ian remains outside the operational architecture.
