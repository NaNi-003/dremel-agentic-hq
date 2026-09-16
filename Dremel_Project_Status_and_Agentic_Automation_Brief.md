# Dremel Project Status and Agentic Automation Brief

Prepared on 16 September 2026

## 1. Purpose and executive overview

The Dremel project is a marketing decision-support prototype that collects DIY YouTube content, extracts relevant actions and materials, ranks videos by age-adjusted engagement, analyzes thumbnails, and generates influencer briefs through a Streamlit dashboard.

Its business objective is to reduce the effort between identifying a relevant content opportunity and preparing a creator brief. The intended audience is the “DIYer New”: people interested in crafts, furniture restoration, personalization, and upcycling. The project links those interests to Dremel demonstrations and campaign concepts.

The existing code provides a coherent processing pipeline and an accessible dashboard. A marketer can select a detected action, generate and download a brief, inspect source thumbnails, and model campaign economics. Technical help is still needed to install dependencies, configure credentials, run collection, refresh results, and launch the dashboard.

The proposed improvement is a Slack-led experience supported by scheduled automation and one focused campaign assistant. Predictable operations remain ordinary Python functions. AI judgment is introduced where it can inspect evidence, assess campaign relevance, reject weak candidates, and draft useful recommendations.

**KISS principle:** preserve the working analysis pipeline, automate its operation, and add one narrow AI assistant. Introduce further components only when they remove a demonstrated operational burden.

## 2. Review basis and current maturity

This brief is based on inspection of the project folder registered as “DREMEL Final Presentation”:

`C:\Users\kiran\Downloads\DSMM Final Project Codebase - Export\DSMM Final Project Codebase - Export`

The review covered all seven Python files, the saved CSV, configuration, a generated brief, the codebase report, dashboard screenshots, and the eight-page presentation. All seven Python files passed static syntax parsing.

The live YouTube and Gemini APIs were not executed, results were not regenerated, and the dashboard was not launched during the review. Consequently, implemented behavior can be described from the code, but current end-to-end operation, API compatibility, runtime, and output accuracy remain unverified.

No notebooks, dependency manifest, training dataset, custom model checkpoints, formal test suite, scheduler, or campaign-performance feedback loop were included in the inspected export.

## 3. What the project can currently do

| Capability | How it is implemented | Marketing value | Qualification |
|---|---|---|---|
| Discover DIY channels | Searches YouTube channels using four UK-oriented queries, English relevance, and a GB region parameter | Reduces manual channel research | Channel location and audience geography are not verified |
| Collect video evidence | Retrieves upload metadata, descriptions, publication dates, views, comment counts, and thumbnail URLs | Supplies source material for content research | The selected uploads are not restricted to Shorts |
| Retrieve spoken content | Attempts to fetch captions and flatten them into transcript text | Helps identify actions mentioned within videos | Missing transcripts fall back to metadata |
| Extract action pairs | Uses spaCy grammar analysis plus permitted verbs and material/object nouns | Translates video text into possible Dremel use cases | Broad actions and fallback matching can produce weak associations |
| Rank opportunities | Computes age-adjusted engagement and sorts videos | Prioritizes recent, engaged content | No validated future-trend forecast is implemented |
| Analyze thumbnails | Extracts dominant color and optionally facial emotion | Gives a visual reference for campaign development | Color-based mood labels do not establish audience response |
| Generate a creator brief | Sends selected action, material, and emotion label to Gemini | Produces campaign rationale and a Short concept quickly | Formatting and relevance are requested through a prompt, not validated programmatically |
| Explore campaign economics | Uses dashboard sliders for creator costs, traffic, sales, margin, and ROI | Supports scenario discussion | Conversion lift is an assumption, not a measured effect |

## 4. Current architecture and data flow

```text
main.py
  -> channel_finder.py: discover channels
  -> scraper.py: retrieve uploads, statistics, and transcripts
  -> nlp_engine.py: extract actions and score videos
  -> select up to 10 unique videos
  -> cv_layer.py: analyze selected thumbnails
  -> dremel_final_output.csv

app.py
  -> read saved CSV
  -> display dashboard and evidence
  -> request Gemini brief when a user clicks Generate Strategy
  -> calculate ROI scenarios from user inputs
```

The backend runs sequentially. The dashboard is a separate consumer of a static local CSV; it does not trigger data refresh or monitor the backend. The separation is useful and can be preserved when adding automation.

### Collection and selection

The pipeline searches for UK furniture upcycling, woodworking restoration, DIY upcycling, and furniture makeover channels. It requests up to five channels per query, deduplicates channel IDs, and retrieves up to ten uploads per channel. This gives an upper bound of approximately 200 videos before missing data, duplicate channels, and filtering reduce the pool.

For each video, transcript collection is attempted. The NLP engine uses transcript text first. If the transcript is absent or yields no permitted action, it parses the title and description. If the transcript produces actions, metadata is not used to supplement them.

### NLP interpretation

The parser loads spaCy `en_core_web_sm`, lowercases text, identifies verbs, and compares verb lemmas against a permitted vocabulary. It seeks permitted noun objects and, when necessary, a later permitted noun chunk within the same sentence.

The noun vocabulary includes substances such as wood, metal, and glass, as well as objects such as tables, chairs, drawers, and cabinets. Therefore, the column named `detected_material` sometimes represents an object rather than a raw material.

The permitted verbs include precise tool-related actions such as sand, drill, engrave, and polish, but also broad actions such as find, use, make, and do. The fallback improves coverage while reducing certainty about the relationship between the action and noun. It does not independently establish that a video is commercially relevant to Dremel.

### Engagement scoring

The implemented score is:

```text
days_live = max(whole days since publication, 1)
base_velocity = (views + 5 × comments) / days_live
velocity_score = base_velocity × exp(-0.015 × days_live)
```

Comments receive five times the weight of views. Older videos receive an exponential penalty, making recent engaged content more prominent. These coefficients are fixed assumptions; no calibration study or backtest was supplied.

The score uses lifetime metrics divided by age. It does not measure recent changes in engagement, acceleration, or future popularity. Calling it an “age-adjusted engagement score” communicates its behavior more accurately than presenting it as a validated prediction.

Each extracted action from a video initially receives the same video-level score. The pipeline sorts rows, deduplicates by video ID, and keeps up to ten videos before CV analysis. It does not explicitly choose the strongest campaign action among a video's extracted pairs or aggregate repeated action pairs across videos.

### Thumbnail analysis

ColorThief extracts a dominant RGB value, which is converted to a hexadecimal color. If DeepFace imports successfully, the code attempts facial-emotion analysis with face detection enforcement disabled and uses the first returned face result when the response is a list.

If DeepFace is unavailable, the code uses simple brightness and RGB rules:

- Mean brightness below 70: Moody.
- Otherwise, red dominance: Energetic.
- Otherwise, blue dominance: Calm.
- Otherwise, green dominance: Balanced.
- Remaining cases: Neutral.

These are visual-style heuristics. They are not measured psychological responses. The pipeline does not visually identify Dremel tools, materials, or project actions. If thumbnail analysis fails, placeholders are used; an analysis exception can also discard an otherwise extracted color.

### Brief generation

The dashboard calls Gemini `gemini-2.5-flash` with an action pair, material/object, and emotion label. The prompt requests:

1. A three-sentence strategic rationale for Dremel and the “DIYer New.”
2. A creator brief for a YouTube Short with a bold, enthusiastic, helpful tone.
3. An Information Gap hook that focuses on the starting material and withholds the finished result.
4. Thumbnail facial-expression guidance based on the supplied label.

The current prompt does not include the transcript, source evidence, numerical score, or detected hexadecimal palette. Consequently, the generated explanation is a creative interpretation of limited inputs rather than an evidence-grounded analysis of the full video.

## 5. Important files and their responsibilities

| File | Current responsibility | Important behavior |
|---|---|---|
| `channel_finder.py` | Discover channel IDs | Loads the YouTube key and performs channel searches; includes a manual discovery example |
| `scraper.py` | Collect uploads and transcripts | Resolves upload playlists, queries individual video metadata/statistics, and surfaces transcript errors |
| `nlp_engine.py` | Extract actions and rank videos | Defines vocabularies, parses transcripts/metadata, handles dates, builds action rows, and computes scores |
| `main.py` | Coordinate backend processing | Deduplicates channels, skips channel failures, handles unavailable transcripts, selects videos, enriches with CV, and writes CSV |
| `cv_layer.py` | Enrich thumbnails | Downloads images, extracts colors, attempts DeepFace or color heuristics, handles failures, and cleans analyzed temporary images |
| `app.py` | Serve the marketer dashboard | Loads cached results, displays KPIs/tabs, generates Gemini briefs, preserves the latest brief in session state, and models ROI |
| `deepface_smoke.py` | Perform a manual diagnostic | Downloads one image and prints DeepFace output shape/emotion; it has no assertions |

Supporting assets:

- `dremel_final_output.csv`: backend-to-dashboard interface with nine columns.
- `Dremel_Brief_Do_Tile (Sample AI generated brief from the dashboard).txt`: sample rationale, hook, build/reveal structure, CTA, and thumbnail guidance.
- `.env`: populated YouTube and Gemini key settings; credential values are intentionally omitted here.
- `.streamlit/config.toml`: Dremel-themed dashboard colors and font.
- `dremel_logo.png`: dashboard branding.
- `.gitignore`: excludes credentials, generated results, temporary images, and local environments. Exclusion rules do not prove that a previously shared export contains no secrets.
- `DSMM Codebase Report.docx`: architectural and operational explanation, with some differences from actual code.
- `Dashboard Snippets.docx`: screenshots of prior dashboard outputs.
- `DSMM Dremel APO 3 (Section-A).pdf`: business problem, proposed value, pipeline, examples, and role-based campaign applications.

## 6. Dashboard outputs and current evidence

The dashboard offers four tabs:

1. **Autonomous Content Ideation:** user-triggered brief generation and text download.
2. **Trend Lifecycle Matrix:** an interactive chart colored by emotion label.
3. **Raw Intelligence Feed:** thumbnail previews, action pairs, scores, labels, and palettes.
4. **Campaign ROI Estimator:** editable funnel and cost assumptions.

The saved CSV contains 10 unique videos and 9 unique action pairs because “Restore Table” appears twice. Its top entries are:

| Action pair | Saved score |
|---|---:|
| Restore Table | 7,764.62 |
| Restore Chair | 4,691.73 |
| Drill Wood | 3,103.68 |
| Find Brass | 2,146.33 |
| Make Wood | 2,101.24 |

Eight rows are labeled Moody and two Energetic. These labels are consistent with the implemented color fallback, but the CSV does not record which method generated them. They do not prove that facial-emotion detection was used.

### Financial scenario

The ROI calculation follows:

```text
campaign_cost = (creator_views / 1000 × CPM) + fixed_costs
CTR_bonus_percentage_points = (selected_score / maximum_score) × 1.5
final_CTR_percent = baseline_CTR_percent + CTR_bonus_percentage_points
site_visitors = creator_views × final_CTR_percent / 100
sales_units = site_visitors × website_CVR_percent / 100
unit_contribution = base_margin - retail_price × discount_percent / 100
optional_accessory_value = £15 per unit
net_profit = sales_units × adjusted_unit_contribution - campaign_cost
ROI_percent = net_profit / campaign_cost × 100
```

At default inputs for the highest-ranked candidate, the scenario produces £3,150 campaign cost, 3,750 visitors, 75 sales, £28 unit contribution without accessory value, £1,050 net loss, and approximately −33.3% ROI.

The variable named `projected_revenue` represents margin contribution rather than gross sales revenue. The 1.5-point CTR bonus and optional accessory value are assumptions. The model should remain clearly labeled as a scenario calculator.

### Claims that require qualification

- The dashboard's “Accelerating” indicator is fixed; no acceleration is calculated.
- The lifecycle chart uses score × 14 horizontally and score vertically. Its axes repeat the same underlying information rather than independently measuring market share and growth.
- UK-oriented channel search does not verify a UK-based creator or UK audience.
- No evidence supports zero content noise, zero manual effort, completion in under 60 seconds, or reliable interception of trends before they peak.
- The report describes `cv_engine.py`, while the implemented module is `cv_layer.py`. It also describes asynchronous architecture, although processing is sequential.
- The presentation and screenshots contain outputs from different examples; they should not be represented as the same run as the saved CSV.
- Original counts, publication dates, transcripts, collection times, extraction provenance, and CV method are not retained in the final CSV, limiting auditability.

## 7. Current end-user experience and setup burden

Once running, the dashboard requires no coding for selection, brief generation, downloads, evidence inspection, or financial scenarios. However, an administrator must currently:

1. Prepare a compatible Python environment and install the required libraries and spaCy model.
2. Configure YouTube and Gemini credentials.
3. Execute `main.py` from the project folder to collect and process data.
4. Launch the dashboard with `streamlit run app.py`.
5. Repeat collection when fresh results are needed and ensure cached dashboard data refreshes.
6. Investigate credential problems, API failures, dependency compatibility, and poor candidate quality.

The supplied report's installation example does not cover all imported backend dependencies. A tested dependency manifest and a short administrator guide would make setup more reproducible. Hosting the application would remove local installation from the marketer's workflow, although someone would still administer credentials and runtime.

## 8. Proposed experience from a marketer's perspective

The marketer opens Slack and asks for a daily or weekly Dremel brief. Alternatively, a scheduled run posts the brief at an agreed time.

The response contains up to three credible content opportunities, each with:

- A clear campaign angle and suggested Dremel demonstration.
- Supporting source links and the basis for inclusion.
- A draft curiosity hook and creator concept.
- Thumbnail style guidance with appropriate evidence qualifications.
- Access to a full draft brief and dashboard evidence.

The marketer reviews and edits the drafts, then decides what to commission. The proposal does not automatically contact creators, publish content, redirect spending, or change retailer listings.

Daily and weekly delivery are reporting cadences, not proof of day-over-day or week-over-week growth. Actual period comparisons require stored engagement snapshots, which should be a separate enhancement if that capability is needed.

## 9. Proposed background workflow

```text
Slack request OR scheduled trigger
  -> shared workflow controller
  -> check latest successful collection and requested reporting period
  -> reuse current evidence OR refresh through existing pipeline
  -> retain candidate actions, original evidence, and analysis provenance
  -> campaign assistant inspects and selects suitable opportunities
  -> save draft recommendations and full briefs
  -> publish a concise Slack digest and dashboard link
```

### Workflow controller

The controller handles predictable operations: input normalization, freshness checks, execution order, bounded retries, overlapping requests, saved outputs, and delivery status. Both manual requests and scheduled triggers use this same entry point.

A Slack request receives an immediate acknowledgment; collection proceeds in the background when needed. Requests made during the same collection run should reuse that run rather than launch duplicate API work.

The last successful dataset is preserved if refresh fails. Any response based on older evidence must clearly disclose its collection time. A failed refresh must not silently produce a supposedly fresh brief.

### Campaign assistant

The assistant's objective is:

> Identify up to three credible Dremel campaign opportunities from the collected evidence and prepare draft creator briefs. Reject weak candidates and report insufficient evidence when necessary.

Its minimum tools are:

| Tool | Purpose |
|---|---|
| List ranked candidates | Read scores, extracted actions, metadata, and provenance |
| Inspect candidate evidence | Retrieve stored transcript, description, source identity, and thumbnail-analysis details |
| Save recommendations | Persist structured opportunities and draft briefs for Slack and the dashboard |

The assistant decides which candidates deserve closer inspection and whether the evidence supports a concrete Dremel use case. This is useful because a grammatical pair such as “Find Floor” can be correctly extracted yet unsuitable as a campaign recommendation.

For example, it could inspect a restoration candidate, identify a specific sanding step in the transcript, and propose a worn-table transformation Short. If the transcript does not substantiate sanding, it should describe that tool connection as a proposed creative concept rather than a detected activity.

The assistant must not change numerical scores, treat color heuristics as measured audience emotions, invent conversion evidence, or follow instructions embedded in scraped transcripts. Source text is evidence, not operating instructions.

### What makes it agentic

The current Gemini call receives limited fields and writes text once. Tool-based behavior adds a useful decision loop: review candidates, inspect uncertain evidence, select or reject opportunities, and produce grounded drafts.

Start with the existing Gemini integration. Use a bounded tool-calling loop only where selective inspection adds value. If a single structured call achieves the same quality and reliability, keep it. Multiple specialist agents and a supervisor are unnecessary for the proposed first version.

## 10. What to automate and what to keep deterministic

| Operation | Recommended mechanism | Reason |
|---|---|---|
| Trigger daily/weekly runs | Scheduler | Timing is predictable |
| Interpret supported Slack requests | Simple commands initially; limited intent parsing if needed | Avoid an unnecessarily broad conversational interface |
| Discover channels and collect metadata | Existing API functions with controlled execution | Reliable, auditable collection does not require AI judgment |
| Retrieve captions and handle missing data | Existing scraper with status reporting | Preserve explicit fallback behavior |
| Extract action candidates | Existing spaCy pipeline | Provides reproducible candidate generation |
| Calculate and sort scores | Existing formula | Keep ranking explainable |
| Extract color and optional facial labels | Existing CV functions with method labels | Preserve analysis while clarifying its limits |
| Assess campaign suitability | Campaign assistant | Requires contextual interpretation |
| Draft rationale, hooks, and briefs | Shared Gemini campaign function | Reuses the project's existing generation capability |
| Format and deliver Slack messages | Ordinary integration code | Delivery should be predictable and deduplicated |
| Approve campaign execution | Marketer | Retain control over external commitments and brand decisions |

## 11. Modification and preservation matrix

| Existing file | Proposed modifications | Working logic to preserve |
|---|---|---|
| `main.py` | Return results and run status from callable processing; retain original evidence and timestamps; preserve the last successful output; allow candidate review before final brief selection | Sequential coordination and channel-level error isolation |
| `channel_finder.py` | Move search topics to simple configuration; reuse discovered channels; retain channel identity for source attribution | YouTube API discovery and channel-ID deduplication |
| `scraper.py` | Persist transcripts, metadata, counts, dates, channel identity, and collection status; add bounded retries and reuse available evidence | Direct API collection and transcript fallback |
| `nlp_engine.py` | Label transcript versus metadata extraction; retain multiple actions per candidate for review; document scoring assumptions | spaCy parsing, vocabularies, date handling, and deterministic scoring as a baseline |
| `cv_layer.py` | Record DeepFace, color heuristic, or failure provenance; separate palette success from emotion failure; ensure safe temporary-image cleanup | Dominant-color extraction and optional facial analysis |
| `app.py` | Move brief generation into a shared function; display stored recommendations and refresh timestamps; invalidate cached data when outputs change; correct unsupported labels | Dashboard layout, source inspection, brief downloads, and financial scenario controls |
| `deepface_smoke.py` | No agent-related changes required | Manual diagnostic purpose |

Changes to analysis accuracy should remain separate from automation. For example, refining fallback noun selection or adjusting scoring coefficients requires its own evidence and evaluation; introducing an agent does not validate those algorithms.

### New components

1. **Workflow controller:** shared orchestration for Slack and scheduled runs.
2. **Campaign assistant module:** evidence inspection, opportunity selection, and reusable brief generation.
3. **Slack adapter:** supported requests, acknowledgment, digest formatting, and delivery.

A tested dependency manifest, a small configuration file, and an administrator setup guide are supporting additions. A separate agent framework, complex database, or distributed task system should only be introduced if simpler components cannot meet measured needs.

### Minimum shared interfaces

- **Workflow request:** reporting cadence/period, trigger source, response destination, and whether refresh is required.
- **Pipeline result:** ranked candidates, supporting evidence, collection timestamp, provenance, and partial-failure status.
- **Campaign recommendation:** source IDs/links, selected action, rationale, proposed demonstration, hook, thumbnail guidance, full draft, and limitations.
- **Delivery record:** run identity, destination, completion state, and message reference where available.

Keep the existing nine-column CSV available to the dashboard during transition. Additional evidence and recommendations can initially be stored in companion structured files. This avoids forcing a database migration before it is needed.

## 12. Illustrative Slack digest

The following illustrates the proposed format; it is not a newly generated or validated campaign result.

```text
Dremel Weekly Content Brief
Evidence collected: [timestamp]

1. Worn-table restoration
Why consider it: restoration content appears among the ranked candidates.
Creative direction: demonstrate a specific precision-finishing step.
Draft hook: “Before you replace this table, look at this one detail.”
Source: [YouTube link]
Visual reference: dark warm palette; mood is a color heuristic,
not evidence of audience emotion or conversion.

[Up to two additional evidence-supported opportunities]

Review full drafts and source evidence: [dashboard link]
Status: drafts for marketer review; no campaign has been published.
```

The existing Information Gap approach can be retained: emphasize the starting problem or material and delay the finished reveal. Source attribution should remain visible even when the agent proposes an original creative treatment.

## 13. Implementation sequence

### Phase 1 — Make operation reproducible

- Document and test dependencies and model requirements.
- Centralize credentials and settings for an administrator.
- Make backend processing callable while retaining manual use.
- Persist collection times, original evidence, and provenance.
- Show the latest successful refresh in the dashboard.

**Outcome:** reliable collection and an understandable evidence trail before AI interpretation is expanded.

### Phase 2 — Add focused campaign interpretation

- Extract Gemini generation from the dashboard into a reusable function.
- Let the assistant inspect and reject weak candidates.
- Produce up to three recommendations with full source-backed drafts.
- Save results for both dashboard and Slack consumption.
- Label proposed creative connections and unsupported assumptions clearly.

**Outcome:** fewer irrelevant suggestions and more useful campaign drafts.

### Phase 3 — Connect Slack and scheduling

- Add one supported daily/weekly request path.
- Acknowledge requests before lengthy collection finishes.
- Configure an agreed schedule and destination through the same workflow.
- Prevent duplicate execution and duplicate scheduled delivery.
- Give clear fresh, stale, partial, and failed statuses.

**Outcome:** a marketer can receive briefs without running scripts.

### Phase 4 — Pilot and simplify

- Compare manual dashboard use with the automated workflow.
- Collect marketer feedback on relevance and editing effort.
- Track reliability and operating cost.
- Remove agent steps that do not improve usefulness or reduce effort.

**Outcome:** demonstrable productivity benefits rather than automation measured only by technical novelty.

## 14. Failure handling and acceptance scenarios

| Scenario | Expected behavior |
|---|---|
| Current evidence is available | Reuse it and disclose its timestamp |
| Refresh is needed | Run one bounded collection job and acknowledge the Slack request |
| A transcript is unavailable | Use metadata and label that provenance |
| Some channels fail | Continue with available sources and disclose incomplete collection |
| No suitable candidates exist | Report insufficient evidence rather than forcing campaign ideas |
| Thumbnail analysis fails | Preserve other evidence and mark visual guidance unavailable |
| Gemini fails or produces an invalid result | Keep analysis available; report brief-generation failure; do not send fabricated drafts |
| Refresh fails but older data exists | Preserve older results and explicitly label any reuse as stale |
| Requests overlap | Reuse an active run where appropriate rather than duplicate collection |
| Slack delivery fails | Retain the completed brief and delivery status for recovery |
| Scheduled run is retried | Avoid duplicate messages for the same completed run |
| Scraped text contains instructions | Treat it as untrusted source content and ignore operational directives |

Useful checks include an evidence-backed candidate, a misleading broad action, metadata-only extraction, unavailable CV, model failure, and duplicate delivery. Evaluate recommendation quality with human-reviewed examples, not merely whether a response was produced.

## 15. Productivity measures and evaluation framing

| Measure | How to assess it |
|---|---|
| Setup effort | Count marketer-facing steps before and after automation |
| Brief turnaround | Measure request-to-delivery time under realistic conditions |
| Research effort | Compare time needed to find and review useful opportunities |
| Recommendation relevance | Record accepted recommendations divided by reviewed recommendations |
| Brief editing burden | Track editing time or the extent of changes before approval |
| Delivery reliability | Record completed, partial, failed, and duplicate runs |
| Evidence quality | Check source links, timestamps, and provenance completeness |
| Operating cost | Track collection usage, model calls, hosting, and maintenance effort |

No improvement values have yet been measured. Establish a baseline with the existing dashboard and compare it with a small pilot. Actual campaign CTR, sales, or ROI require post-campaign data and should not be inferred from successful automation.

For a marketing evaluator, the strongest explanation is: the project converts source research into reviewable campaign drafts and brings that process into Slack. Its value lies in reduced manual operation, clearer evidence, and faster informed decisions.

## 16. Deployment decisions still to make

The proposal is intentionally independent of a particular hosting platform or agent framework. Before implementation, agree on:

- Hosting and administrator ownership, including whether the application must run while the developer's computer is off.
- Slack workspace, destination, interaction style, and installation permissions.
- Daily/weekly schedule, timezone, freshness policy, and source-history window.
- Collection and model-call limits, budget, and data-retention needs.
- Approved Dremel product guidance and brand constraints for generated concepts.
- Whether historical snapshots and genuine period comparisons are required.

A scheduler requires an available execution environment. A configured cron job alone does not make a locally stopped application continuously available.

## 17. Recommended first version

Preserve the existing Python pipeline and dashboard. Add evidence retention and reproducible setup, extract shared Gemini generation, and introduce one campaign assistant that can inspect evidence and reject weak opportunities. Connect it to Slack through a shared controller used by both on-demand and scheduled runs.

Keep score calculations deterministic, present thumbnail analysis accurately, and retain marketer approval for external campaign action. Correct unsupported dashboard labels independently of agent integration.

The intended user journey is simple:

**Ask for or receive a brief in Slack → review up to three opportunities → inspect evidence → edit and approve a creator draft.**

This document is a status assessment and integration proposal. Creating it does not change the project code, activate schedules, connect Slack, or publish any campaign material.
