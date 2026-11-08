---
name: notella-orchestrator
description: "The conductor of the notella-* skill family. Walks an eleven-step decision checklist (inbox check → hold duplicates → drain, pipeline catch-up with image quality and orientation gate, daily synthesis, weekly synthesis, project synthesis, themes refresh, principles refresh, monthly synthesis, stuck-page archive, ledgers aggregation, review) and proposes the next batch of work. Use whenever the user says 'run notella', 'process my inbox', 'what should notella do next', 'orchestrate', 'sync notella', 'morning notella run', 'catch me up on notella', 'what's pending', or any request asking the facility to tell itself what to do next. Approval-gated by default; `--auto` runs without prompts and is the headless entry point for scheduled runs. Reads through `notella-state` and invokes other notella-* skills. Thin by design — routes, does not perform pipeline work itself."
---

# notella-orchestrator — the conductor

Decides what to do next. Reads facility state, walks the decision checklist, proposes a batch of work, asks for approval, runs the batch.

## Purpose

Without an orchestrator, the user has to manually invoke each pipeline skill on each page. With one, they say "run notella" and the facility advances every page that's ready for the next stage, queues every overdue synthesis, refreshes longitudinal intelligence on cadence, closes the month when it closes, and hands the human the things only a human can decide.

The orchestrator is **thin**: it never writes page artifacts itself (stubs excepted), never calls a model directly, never modifies the manifest. It reads state and routes work to the right specialist.

## Inputs and outputs

**Input:** Optional flags:

| Flag | Effect |
| --- | --- |
| `--auto` | run the proposed batch without asking; review runs in `--report` mode |
| `--max-pages N` | cap how many pages advance per run (default 20) |
| `--only-step {1..11}` | run a specific step in the checklist |
| `--dry-run` | show the batch plan without executing |
| `--catch-up-weeks N` | run back-syntheses for the last N closed weeks (step 4 only) |
| `--reprocess` | pass through to specialist skills, causing existing artifacts to be overwritten |
| `--themes-now` | force a themes refresh this run regardless of cadence (step 6); principles (step 7) follow it |
| `--discover-projects` | run the project discovery pass even if the manifest is populated |
| `--skip-synthesis` | skip steps 3–8 — daily, weekly, project, themes, principles and monthly. Inbox, pipeline, stuck-page archive, ledgers and review still run |
| `--skip-weekly` | skip step 4 |
| `--skip-project` | skip step 5 |
| `--skip-themes` | skip step 6 (and therefore step 8, which needs the themes delta; step 7 runs only if already due against an existing snapshot) |
| `--skip-principles` | skip step 7 |
| `--model-override <stage>=<alias>` | run one stage on another model for this run (repeatable); see Model routing |
| `--skip-monthly` | skip step 8 |
| `--skip-review` | skip step 11 |

**Output:**
- A summary of what was done (counts per skill invoked)
- Updates to `state.json:last_orchestrator_run`
- Activity-log entries for each invocation
- Under `--auto`: `logs/review-pending.md` written by `notella-review --report`
- The facility advances by some number of phase transitions and synthesis outputs

## Facility path

The facility's default path is `~/notella`. On this machine the facility lives at `/Users/davidolsson/Documents/notella`, selected by the `NL_DIR` environment variable, which every notella-* skill and the desktop app honour. Set it in the environment of every run (interactive or scheduled); when it is unset, `~/notella` is used.

## Pipeline integrity rules (non-negotiable)

These rules are enforced before any batch is executed. Violating them is how the corpus ends up with degraded first-pass artifacts. The full check list is `references/integrity-rules.md`.

1. **first-pass cannot run until composition, diagram (if required), sketch (if required), table (if required), and metadata are all present.** The orchestrator blocks first-pass for any page missing these artifacts and queues the L1 fan-out instead.

2. **actions cannot run until first-pass is present.**

3. **daily-synthesis cannot run until the target date's pages are at phase=indexed.**

4. **project-synthesis cannot run if manifest.projects is empty.** Surface a `manifest-empty` warning and invite the user to define projects. After notella-metadata runs, the orchestrator surfaces discovered project candidates for the user to confirm.

5. **The phase transition transcribed → first-pass-done is only permitted when all L1 artifacts required by the page's route_plan are present.** If a page is at `first-pass-done` without the required L1 artifacts, flag it as `integrity-violation` and queue a reprocessing run.

6. **monthly-synthesis cannot run until the themes refresh for this run has completed** (or a snapshot newer than the month's close already exists), because it consumes the themes delta.

7. **transcribe cannot run on a page whose `quality.json` orientation is `suspected` with a concrete suggestion.** The page is fixed (`notella-images fix`) or cleared in review first. Transcribing a sideways or upside-down page is the most expensive way to get a bad transcript.

8. **intake cannot mint a file that duplicates an existing page.** Step 1 holds exact and near duplicates in `inbox/_held/` before `notella-intake` runs.

## Project discovery pass (runs after metadata fan-out completes)

After `notella-metadata` runs on a batch of pages and `manifest.projects` is empty or fewer projects than entities suggests:

```
1. Collect all project mentions from metadata.json:projects across all pages
2. Compute frequency and co-occurrence across the corpus
3. Surface candidate projects:
   - slug (auto-derived: lowercase-hyphenated entity name)
   - display_name
   - mention_count
   - representative_pages (3 examples)
   - suggested_keywords (from co-occurring entities)
4. Present to user:

   Discovered project candidates from your corpus:
   - tulevik (7 mentions across 3 pages) — keywords: data-staleness, name-matching, jp-morgan
   - aimqc (5 mentions across 4 pages) — keywords: roadmap, voice-interface, nrcan
   - dante (8 mentions across 6 pages) — keywords: pipeline, extraction, segmentor
   - atomic47 (4 mentions across 3 pages) — keywords: leadership, crm, agency
   - decima (3 mentions across 2 pages) — keywords: smiles, segmentor, scale

   Add these to manifest.yaml? [y/N/edit]

5. On approval: write the confirmed slugs to manifest.yaml:projects[]
6. Re-run notella-metadata --reprocess on all pages to backfill project_attributions
   using the new canonical slug list
```

This pass runs automatically on first run after metadata completes, and whenever the user invokes `/notella-orchestrator --discover-projects`. Under `--auto` the proposal is not applied; it is written to `logs/review-pending.md` for the next interactive session. Clustering and scoring rules: `references/project-discovery.md`.

## The eleven-step decision checklist

Walked in order on each invocation. The formal version with every condition is `references/decision-checklist.md`. The image tool used in steps 1 and 2 is `python3 "$CLAUDE_PLUGIN_ROOT/scripts/notella_images.py"` (stdlib Python + macOS `sips`; see `notella-images` and `notella-import`), always with `NL_DIR` set.

### Step 1 — Inbox check → hold duplicates → drain

```
inbox_files = images directly in $NL_DIR/inbox/          # inbox/_held/ is not part of the inbox
if inbox_files:
  notella_images.py inbox-check      # → logs/inbox-check.json: status, matched page, grade, EXIF per file
  notella_images.py hold             # exact + near duplicates of existing pages → inbox/_held/ (+ imports.ndjson)
  if files remain: invoke notella-intake
```

The check compares every inbox file with every page's `raw/` (sha256) and perceptual hash (dhash ≤ 6, including rotated and mirrored variants), so a re-uploaded page is caught whatever date it would be minted under. Held near duplicates go to review ("Held imports"); files released there are minted on the next run. After intake completes, refresh `notella-state list-pages --phase=intake` and continue.

### Step 2 — Pipeline catch-up

**Integrity check first:** For every page at `phase=first-pass-done` or later, verify required L1 artifacts are present. Flag any violations as `integrity-violation` in the plan.

**Image scan:** for pages without a fresh `quality.json` (absent, or older than `derived/page.jpg`, `classify.json`, `transcribe.json` or `meta.yaml`), run

```
notella_images.py scan          # only stale/missing pages; ~10 s for 400 pages; no model calls
```

Record `orientation_suspected` (with and without a concrete suggestion) and `poor_quality` page lists in the plan. Already-indexed pages that turn out mis-oriented are **not** reprocessed automatically — they appear in review under "Image attention", and fixing them is a person's decision because the reprocess chain costs model calls.

For each phase boundary, in strict order:

```
pages_at_intake     = list-pages --phase=intake     → notella-classify
                      (classify fixes a confidently mis-oriented page via notella-images and re-classifies once)
pages_at_classified = list-pages --phase=classified → notella-transcribe
                      ORIENTATION GATE: skip pages whose quality.json is suspected with a concrete
                      suggestion → plan.orientation_blocked (transcribe would refuse them anyway)

pages_at_transcribed → L1 fan-out (all parallel for a given page):
    notella-composition   (always — runs on every page)
    notella-metadata      (always — Layer 2, runs parallel with L1)
    notella-diagram       (if route_plan.diagram_interpretation
                           AND classify.content_mix.diagram >= 15)         ← skip when low signal
    notella-sketch        (if route_plan.sketch_interpretation
                           AND classify.content_mix.diagram + symbolic >= 10)
    notella-table         (if route_plan.table_extraction
                           AND classify.content_mix.table >= 1)

When skipped, write a stub artifact `{ <kind>_count: 0, layout_semantics: "<one-line>" }`
so downstream first-pass doesn't block on the integrity gate. The stub is cheap
(no model call) and preserves the schema.

INTEGRITY GATE: first-pass only runs when ALL of the above are present (stub OK).
pages_with_all_L1_complete → notella-first-pass

pages_at_first-pass-done with route_plan.action_decision
  AND first-pass.action_intelligence.length >= 2
  → notella-actions

(Skip standalone notella-actions when first-pass already extracted < 2 actions —
the deeper specialist run is high-cost and adds little when there are no
significant action signals to analyze.)

pages_with_all_enrichment_complete → advance to enriched
pages_at_enriched → advance to indexed
```

After metadata completes on a new batch: run project discovery pass (see above).

Cap at `--max-pages N` per run. Surface any stuck pages (in same phase > 4 hours without an error) for user attention (`references/stuck-page-rules.md`).

The orchestrator runs the per-stage skills in **parallel where safe** — composition + metadata + diagram + sketch + table for the same page can fan out concurrently because each acquires the same per-page lock. Across pages, parallelism is unlimited. Rules: `references/parallelism-rules.md`.

### Step 3 — Daily synthesis

```
indexed_dates = unique(authoritative_date for pages with phase >= indexed)
for date in sorted(indexed_dates):
  if daily/{date}.json missing (or stale: pages_analyzed < pages now indexed for date):
    previous = most recent daily/*.json with date < this date
    invoke notella-daily-synthesis(date, previous_daily=previous)
```

The previous day's brief is passed as memory so questions answered today are not re-listed as open and momentum reversals are stated. Today's date is not synthesised until it closes (midnight in `manifest.facility.timezone`).

### Step 4 — Weekly synthesis

```
closed_weeks = ISO weeks whose Sunday 23:59 (facility timezone) has passed
              AND that contain >= 1 daily/*.json
for week in closed_weeks:
  if weekly/{week}.json missing:
    invoke notella-weekly-synthesis(week)      # the skill reads the previous weekly itself
```

`--catch-up-weeks N` limits to the N most recent closed weeks. `--skip-weekly` skips the step. A weekly whose dailies have changed since it was written is flagged `weekly-stale` and re-queued with `--reprocess`.

### Step 5 — Project synthesis

```
if manifest.projects is empty: skip with manifest-empty warning
for project in manifest.projects where active:
  last_brief = state.last_synthesis_at.by_project[slug]   # null if never
  touched = list-pages --project=slug --since=last_brief --phase>=indexed
  if touched.length > 0:
    invoke notella-project-synthesis(slug)
```

Only slugs with pages touched since their last brief are synthesised; a quiet project does not pay for an Opus run. `--skip-project` skips the step.

### Step 6 — Themes refresh

```
if --themes-now
   OR state.last_longitudinal_at is null
   OR state.last_longitudinal_at > 30 days ago
   OR (a calendar month has closed since the latest snapshot's generated_at
       AND monthly/{that-month}.json is missing):        # step 8 needs a fresh snapshot
  invoke notella-themes
```

**Cadence: monthly, not weekly.** Themes that change week-to-week are mostly noise; the meaningful drift signal in a notebook corpus is monthly. Weekly refresh was spending compute to re-detect the same themes. Monthly cuts themes spend ~75% with no signal loss. `--themes-now` forces a refresh; `--skip-themes` skips (and defers step 8 with it).

Each refresh writes a dated snapshot `longitudinal/themes/{YYYY-MM-DD}.json` (plus `.md`) and copies the newest snapshot to `longitudinal/themes.json` / `themes.md`, so the pointer files always hold the latest while history accumulates. The snapshot carries a deterministic `delta` against the previous snapshot, which step 8 consumes; step 7 reads the snapshot's `conceptual_evolution`.

### Step 7 — Principles refresh

```
if notella-principles is installed
   AND (step 6 wrote a new themes snapshot this run
        OR longitudinal/principles.json is missing
        OR principles.json:generated_at is older than the newest longitudinal/themes/*.json snapshot
        OR principles.json:generated_at > 30 days ago):
  invoke notella-principles
```

Monthly, right after themes, because the principles skill reads the fresh snapshot's `conceptual_evolution`. It distils the principles David states and re-states (emphasised, boxed, starred, repeated spans in `transcribe.json:emphasis[]`) into `longitudinal/principles.json`, `principles.md` and the paste-anywhere `principles-context.md`, and emits `principles.refreshed`. A deterministic candidate pre-pass runs first, so a refresh is one reasoning step, not a per-page model run. `--skip-principles` skips the step; `--skip-synthesis` skips it with the other synthesis steps. Unconfirmed principles appear in review (step 11) once each.

### Step 8 — Monthly synthesis

```
closed_months = calendar months whose last day 23:59 (facility timezone) has passed
                AND that contain >= 1 weekly/*.json
for month in closed_months:
  if monthly/{YYYY-MM}.json missing:
    require: themes snapshot newer than month close exists (step 6 ran this run, or earlier)
    invoke notella-monthly-synthesis(month)
```

Runs **after** themes because it consumes the themes delta (theme arc: what rose, held, fell). Writes `monthly/{YYYY-MM}.{json,md}` — month-in-review with theme arc, commitment aging, forecast scorecard and next-month watchlist. When a month has closed and the latest themes snapshot predates the month close, step 6 runs regardless of the 30-day cadence (a closed month is itself the cadence trigger), so the normal outcome is a fresh snapshot before the monthly runs. Only if themes was explicitly skipped (`--skip-themes`) or failed is monthly deferred with `monthly-deferred: themes-not-fresh` in the report; `--only-step 8` runs it against the stale snapshot and the monthly records `sources.themes_current_stale: true`. `--skip-monthly` skips the step. Normally only one month is ever due; `--catch-up-weeks` does not apply — back-filling many months is an explicit `--only-step 8` decision because each month is an Opus run.

### Step 9 — Stuck-page auto-archive

```
stuck_long = list-pages --is-stuck --hours-stuck > 168    # > 7 days
for page in stuck_long:
  notella-state advance-phase {page-id, to-phase: archived, by-actor: notella-orchestrator, reason: "stuck > 7d"}
```

Pages stuck for over a week are unreachable through normal flow. Auto-archive to stop spending synthesis compute on dead pages. The page record is preserved (everything is append-only); only the phase changes so subsequent synthesis skips it. Escalation ladder before this point: `references/stuck-page-rules.md`.

### Step 10 — Ledgers aggregation (decisions, commitments, people — no model calls)

After daily synthesis completes, refresh the three ledgers:

```bash
# Preferred: the standalone CLI from the desktop repo (tries the dev server's API first,
# then runs in-process). NL_DIR must be set so it reads the right facility.
NL_DIR=/Users/davidolsson/Documents/notella node ~/WORKSONA/notella-desktop/scripts/aggregate-ledgers.mjs

# Equivalent when the Next.js dev server is already running on :3344
curl -fsS -X POST http://localhost:3344/api/aggregate
```

Both write to `$NL_DIR/longitudinal/`:
- `decisions.ndjson` — every `new_decisions` entry across all daily syntheses, one JSON per line, sorted oldest-first
- `commitments.ndjson` — every action with a state-machine annotation:
  - `proposed` — task observed, no owner identified
  - `owner_confirmed` — owner_candidates non-empty
  - `in_progress` — mentioned as started/underway in a later page
  - `done` — completion language appears in a later page, or a `done` verdict in `verdicts.ndjson`
  - `abandoned` — explicit cancel language in a later page, or a `drop` verdict
- `people.ndjson` — one row per canonical or recurring person: first seen, last seen, mentions per month, projects co-mentioned; built from `metadata.json:people` and `meta.yaml:person_attributions`

State transitions are inferred from substring + 70%-overlap matching against later page transcripts, with a 200-character window scanned for state-token phrases (`completed`, `shipped`, `started`, `cancelled`, etc.). Explicit verdicts from `notella-review` (`longitudinal/verdicts.ndjson`) take precedence over inferred transitions.

These are pure functions of existing data; cost is filesystem I/O. Re-running overwrites the ledgers atomically (tmp + rename). Implementation lives in `~/WORKSONA/notella-desktop/src/lib/notella-aggregators.ts`. The read-only desktop app (`/Applications/Notella.app`) cannot run the aggregation; use the CLI or the dev server.

### Step 11 — Review

```
if --auto:
  invoke notella-review --report        # writes logs/review-pending.md, no prompts
else:
  invoke notella-review                 # interactive: done / drop / carry / wrong per item
```

Review shows yesterday's watch items, open commitments older than 14 days, unresolved questions, pages whose first-pass drew three or more sanity warnings, stuck pages awaiting a human, image attention (pages suspected mis-oriented or graded poor), held imports (near duplicates in `inbox/_held/`), unconfirmed principles, and (under `--auto`) any project-discovery proposal that is pending confirmation. Verdicts are appended to `longitudinal/verdicts.ndjson` and feed step 10 on the next run. `--skip-review` skips the step. Review makes no model call; its cost is reading.

## How a run executes

### Phase A — Plan

Read state, walk all eleven steps, build a batch plan:

```yaml
plan:
  facility: /Users/davidolsson/Documents/notella        # from NL_DIR
  integrity_violations: []        # pages with L1 missing despite later phase
  step_1_inbox:
    files_to_check: 6
    hold_exact: [IMG_4419.HEIC]                         # → inbox/_held/, matches 2026-04-09-y534
    hold_near: []
    files_to_drain: 5
  step_2_pipeline:
    quality_scan: [page-id, ...]                        # pages lacking a fresh quality.json
    orientation_suspected: [page-id]                    # with a concrete suggestion → review / fix
    orientation_needs_look: [page-id]                   # suggested: null
    orientation_blocked: [page-id]                      # at phase=classified, transcribe gated
    poor_quality: [page-id]
    classify: [page-id, page-id]
    transcribe: [page-id]
    layer1_fanout:
      composition: [page-id, ...]
      metadata: [page-id, ...]
      diagram: [page-id, ...]
      sketch: [page-id, ...]
      table: [page-id, ...]
    project_discovery: true       # will run after metadata completes
    first_pass: [page-id]
    actions: [page-id]
    advance_enriched: [page-id]
    advance_indexed: [page-id]
  step_3_daily:
    dates_to_synthesize: [2026-11-05, 2026-11-06, 2026-11-07]
    previous_daily_for_first: 2026-11-04
  step_4_weekly:
    weeks_to_synthesize: [2026-W44]
    weeks_stale: []
  step_5_project:
    projects_to_synthesize: [tulevik, aimqc]
    manifest_empty_warning: false
  step_6_themes:
    refresh: true
    reason: "last_longitudinal_at 2026-05-09 > 30d"     # or "--themes-now" / "cadence not due"
    snapshot_path: longitudinal/themes/2026-11-08.json
  step_7_principles:
    refresh: true
    reason: "themes refreshed this run"                   # or "principles.json missing" / "not due"
  step_8_monthly:
    months_to_synthesize: [2026-10]
    deferred: null                                        # or "themes-not-fresh"
  step_9_stuck:
    auto_archive: [page-id]
  step_10_ledgers:
    run: true
    via: cli                                              # or api
  step_11_review:
    mode: report                                          # or interactive
estimated_minutes: 38
estimated_model_calls: 94
estimated_cost_usd: 4.21
budget_status:
  daily_spent_usd: 0.42
  daily_cap_usd: 10.00
  daily_remaining_usd: 9.58
  monthly_spent_usd: 4.17
  monthly_cap_usd: 200.00
  fits_in_daily_cap: true
  on_breach: warn
```

**Pre-flight cost check.** Before entering Phase B, read the live budget snapshot — `GET http://localhost:3344/api/budget` when the dev server is up, otherwise sum `logs/llm-calls.ndjson` for today and this month against `cost-controls.yaml:budgets`. Estimate the plan's cost using:

Per-stage cost follows the stage's model (see Model routing). Measured on 2026-11-08: a page-level stage in a Claude Code subagent uses about 15k tokens per page whatever the model (image, instructions and tool overhead dominate), so cost scales with the model's price: haiku ≈ $0.003, sonnet ≈ $0.05, opus ≈ $0.10 per page per stage (API-equivalent list prices; on a Claude plan this is usage-limit consumption, not billing).

| Work | Estimate |
| --- | --- |
| classify + composition + metadata (haiku) | ~$0.01 / page |
| transcribe (sonnet) | ~$0.05 / page |
| diagram / sketch / table (sonnet, when routed) | ~$0.05 / page each |
| first-pass (sonnet) | ~$0.05 / page |
| actions (sonnet) | ~$0.05 / page (when run) |
| daily synth (sonnet) | ~$0.10 / day |
| weekly synth | ~$0.55 / week |
| project synth | ~$0.40 / refresh |
| themes | ~$1.80 / refresh |
| principles | ~$0.60 / refresh (one reasoning step over the pre-pass candidates) |
| monthly synth | ~$2.00 / month |
| inbox check, hold, image scan, orientation fix | $0 (sips + Python, no model) |
| ledgers | $0 (filesystem only) |
| review | ~$0 (no model call beyond reading) |

Add the estimate to the plan and to the user-facing approval prompt. If `estimated_cost_usd > budget.daily_remaining_usd`, flag it prominently and give the user a clear choice:
  (a) approve and let the budget guard refuse mid-batch
  (b) reduce `--max-pages` to fit, or add `--skip-themes --skip-principles --skip-monthly`
  (c) raise the daily cap in `/config`

### Phase B — Approve (unless --auto)

Surface the plan to the user. Flag integrity violations prominently:

```
Notella plan ready (facility: /Users/davidolsson/Documents/notella):

⚠ Integrity violations (2 pages at first-pass-done without required L1):
  - 2026-01-02-02h0 missing: composition, diagram
  - 2026-01-02-0w4g missing: composition, sketch
  → Queued for L1 reprocessing before any synthesis runs.

Inbox:
  - 6 files checked; 1 held (IMG_4419.HEIC = 2026-04-09-y534, identical bytes); 5 to drain

Pipeline:
  - Image scan: 5 new pages → quality.json; 1 poor (2026-11-07-n2v5: blurry, dark)
  - Orientation: 1 page blocked before transcription (2026-11-07-p4q1: red stamp top-left → rotate 180) → review
  - 15 pages need L1 fan-out (composition: 15, diagram: 13, sketch: 4, table: 3, metadata: 15)
  - 15 pages need first-pass --reprocess (L1 inputs now complete)
  - 8 pages need actions
  - Project discovery: will propose manifest additions from metadata results

Synthesis (after pipeline completes):
  - Daily:   2026-11-05 → 2026-11-07 (3 dates; previous brief 2026-11-04 passed as memory)
  - Weekly:  2026-W44 (closed, no brief)
  - Project: tulevik, aimqc (touched since last brief)
  - Themes:  refresh — last 2026-05-09, cadence 30d → snapshot longitudinal/themes/2026-11-08.json
  - Principles: refresh after themes → longitudinal/principles.json
  - Monthly: 2026-10 (closed, no brief; runs after themes)

Housekeeping:
  - Stuck > 7d: 1 page to auto-archive (2026-03-02-k8x1)
  - Ledgers: decisions, commitments, people (CLI)
  - Review: interactive after the batch

~38 minutes, ~94 model calls, ~$4.21 estimated.
Daily budget: $0.42 spent / $10.00 cap → $9.58 available, batch fits.

Approve? [y/N/edit]
```

If the estimate exceeds the daily remaining cap, the prompt instead reads:

```
⚠ This batch would exceed your daily budget cap.
   Estimated cost: $12.40
   Daily cap:      $10.00 ($0.42 already spent — $9.58 remaining)
   Mode on breach: hard (routes will refuse mid-batch)

Choose:
  [a] approve — routes will refuse once cap is reached
  [b] cap     — reduce --max-pages to fit (suggest: 4 pages), or defer themes + principles + monthly (−$4.40)
  [r] raise   — open /config to raise the daily cap
  [c] cancel
```

### Phase C — Execute

Invoke each skill in plan order. For pipeline catch-up, group by stage and parallelize across pages. Stop on first hard error per stage; collect soft errors and report at the end.

#### Model routing (every stage that calls a model)

Each stage runs on the model named in `cost-controls.yaml` `model_defaults.<stage>` — a Claude Code Agent-tool alias (`haiku`, `sonnet`, `opus`, `fable`). Enforce it by **dispatching the stage to a subagent with that model**, never by running the stage inline in this session (the session's own model would be used instead):

- **Page stages** (classify, transcribe, composition, metadata, diagram, sketch, table, first-pass, actions): one `Agent` call per batch of **at most 8 pages**, `subagent_type: general-purpose`, `model: <alias>`. Prompt: the facility path (`NL_DIR`), the page ids, and "for each page, run the `notella-<stage>` skill (read `$CLAUDE_PLUGIN_ROOT/skills/notella-<stage>/SKILL.md` and follow it); write only that stage's artifact and its event; report per page: done / skipped / error, and your exact model ID". Batches of one stage run in parallel; stages stay in the dependency order below.
- **Synthesis stages** (daily, weekly, project, themes, principles, monthly): one subagent per unit of work (one date, one week, one slug, one month) with the stage's alias. Dailies stay oldest-first and sequential (each reads its predecessor).
- **No model**: inbox check, hold, image scan, orientation fix, ledgers, stuck archive, and review run here, in the session.
- `--model-override <stage>=<alias>` (repeatable) changes one stage for this run only, e.g. to re-run an eval arm; it is reported in Phase D.
- A missing or unknown alias falls back to `sonnet` with a warning in the report. `review: none` means no subagent.

**Usage logging.** After each subagent returns, append ONE line per subagent to `logs/llm-calls.ndjson` through `notella-state log-llm-call` with the measured figures from the subagent's completion report: `{actor: "notella-<stage>", task, model (the exact model ID the subagent reported), alias, pages: [...], tokens: {total: <subagent tokens>}, duration_ms, measured: true, source: "subagent-usage"}`. Never write per-page token counts that were not measured; if no usage figure is available, log `measured: false` and no tokens. The budget check reads only these lines.

**Execution sequence:**
1. inbox check → hold duplicates → drain
2. image scan for pages lacking a fresh `quality.json`
3. classify batch (parallel across pages; a confident orientation fix + one re-classify happens inside)
4. transcribe batch (parallel across pages; orientation-gated pages skipped)
5. L1 fan-out batch (parallel across skills AND pages — all 5 specialists run simultaneously)
6. [pause] project discovery if metadata is new
7. first-pass batch (parallel across pages, after 5 + 6 complete)
8. actions batch (parallel across pages)
9. advance enriched / indexed
10. daily syntheses (oldest first, each with its previous daily)
11. weekly syntheses for closed weeks
12. project syntheses for touched slugs
13. themes refresh
14. principles refresh (after themes)
15. monthly synthesis (after themes)
16. stuck-page auto-archive
17. ledgers aggregation
18. review (`--report` under `--auto`)

### Phase D — Report

```
notella-orchestrator complete (facility: /Users/davidolsson/Documents/notella):
  ✓ Inbox: 6 files checked, 1 held as duplicate → 5 pages (2 entries)
  ✓ Images: 5 scanned (4 good, 1 poor); 1 orientation-blocked page waiting for review
  ✓ Pipeline: 20 pages advanced
    - 20 transcribed → L1 fan-out (composition ✓, diagram 13/15 ✓, sketch 4/4 ✓, table 3/3 ✓, metadata 20/20 ✓)
    - 15 first-pass --reprocess (now with full L1 inputs), 5 first-pass
    - 8 actions written
    - 20 enriched → indexed
  ✓ Project discovery: proposed 2 candidates (confirmed by user: robson, stonemaps)
    - metadata --reprocess run on 16 pages to backfill project_attributions
  ✓ Daily synthesis: 3 dates (2026-11-05 → 2026-11-07), each with previous-day memory
  ✓ Weekly synthesis: 2026-W44
  ✓ Project synthesis: tulevik, aimqc
  ✓ Themes: longitudinal/themes/2026-11-08.json written (9 themes, 2 emerging, 1 fading; +37 pages since 2026-05-09) → copied to themes.json
  ✓ Principles: longitudinal/principles.json (9 principles, 7 active, 2 unconfirmed → review)
  ✓ Monthly synthesis: monthly/2026-10.json (theme arc 3 rose / 4 held / 2 fell; 11 commitments > 30d; watchlist 4)
  ✓ Stuck pages: 1 auto-archived (2026-03-02-k8x1, intake 9d)
  ✓ Ledgers: decisions 131 rows, commitments 402 rows (done 61, abandoned 9), people 48 rows
  ✓ Review: interactive — 14 items, verdicts: done 6, drop 2, carry 5, wrong 1 → verdicts.ndjson

Integrity: 0 violations remaining (2 fixed this run)
Skipped: 0
Errors: 0
Cost: $4.08 (estimate was $4.21) · daily $4.50 / $10.00 · monthly $8.67 / $200.00
```

Update `state.json:last_orchestrator_run`.

## Headless invocation (scheduled runs)

The correct non-interactive command is:

```bash
NL_DIR=/Users/davidolsson/Documents/notella \
  claude -p "/notella-orchestrator --auto" --dangerously-skip-permissions
```

`-p` runs one prompt and exits; `--dangerously-skip-permissions` is required because the run writes files and spawns `node`/`exiftool` with nobody to approve. `NL_DIR` must be in the environment — the facility default is `~/notella`, and without the override a scheduled run would create and process an empty facility there. (The desktop app's trigger route previously spawned `claude --skip-permissions -- notella-orchestrator`, which is not a valid invocation; use the form above.)

Four recipes, all idempotent, all cheap when nothing is due:

| When | Command | What it does |
| --- | --- | --- |
| Morning, daily (`30 6 * * *`) | `claude -p "/notella-orchestrator --auto --skip-weekly --skip-monthly --skip-themes --skip-principles" --dangerously-skip-permissions` | inbox check/hold/drain, image scan, pipeline, dailies for closed dates, project briefs for touched slugs, stuck archive, ledgers, `review --report` → `logs/review-pending.md` |
| Monday (`30 7 * * 1`) | `claude -p "/notella-orchestrator --auto" --dangerously-skip-permissions` | everything above plus the weekly for the week just closed; themes/principles/monthly only if due by cadence |
| First of month (`0 5 1 * *`) | `claude -p "/notella-orchestrator --auto --themes-now" --dangerously-skip-permissions` | forces the themes snapshot, then principles, then the monthly for the month just closed, then ledgers and review report |
| Inbox watcher (launchd `WatchPaths` on `$NL_DIR/inbox`, 2-minute debounce) | `claude -p "/notella-orchestrator --auto --skip-synthesis --max-pages 20" --dangerously-skip-permissions` | cheap stages only: inbox check → hold → intake → image scan → classify → transcribe → L1 → first-pass → actions → indexed. Synthesis stays on the schedule so a trickle of photos never triggers an Opus run. Moving files into `inbox/_held/` touches the watched folder; the debounce and the orchestrator lock absorb the extra trigger |

Every recipe needs `NL_DIR=/Users/davidolsson/Documents/notella` in its environment (launchd `EnvironmentVariables`, or a wrapper script). Logs go to `$NL_DIR/logs/activity.ndjson` and `pipeline.ndjson` as usual; the review report at `$NL_DIR/logs/review-pending.md` is what the human reads next morning.

## Idempotency

Every step is itself idempotent (each skill the orchestrator invokes already is). Re-running the orchestrator with no new inputs produces "nothing to do" cleanly:

```
Notella plan: nothing pending.
Last orchestrator run: 2 hours ago. Next due: weekly 2026-W45 on Mon 2026-11-16; themes 2026-12-08; monthly 2026-11 on 2026-12-01.
```

## Failure modes

| Failure | Behavior |
| --- | --- |
| A specialist fails on a page | Log to pipeline.ndjson, mark the page errored in meta.yaml:errors, continue with other pages. Surface the failure in the report. |
| Vision API rate limit | Pause pipeline catch-up, complete other steps if possible, retry next run. |
| Validation errors in a page artifact | Block the page at its current phase; surface for user inspection. |
| User declines the plan | Exit cleanly without changes. |
| `--max-pages` reached | Stop pipeline catch-up; surface "N more pages pending"; subsequent runs continue. |
| Integrity violation detected | Queue L1 reprocessing; do NOT run first-pass until L1 is complete. Surface violation in plan. |
| manifest.projects empty when project synthesis queued | Skip project synthesis; surface manifest-empty warning with project discovery candidates. |
| Project discovery produces no candidates | Skip silently; mention in report. |
| Themes refresh fails | Keep the previous snapshot and pointer; defer monthly (`themes-not-fresh`); retry next run. |
| Monthly due but themes skipped | Defer monthly with reason; the first-of-month recipe passes `--themes-now` so this does not happen on schedule. |
| Ledger CLI and API both unavailable | Report `ledgers: skipped (no node, no dev server)`; everything else proceeds. |
| `notella_images.py` cannot run (no `sips`, not macOS) | Step 1 drains without the duplicate hold (intake's id rule still catches same-date duplicates); step 2 skips the image scan and the orientation gate passes every page; both reported as `images: skipped (no sips)`. |
| A page is orientation-blocked | Not an error: the page stays at `classified`, is listed under `orientation_blocked`, and is shown in review until fixed or cleared. It does not count toward stuck-page escalation while a review item is open. |
| `notella-principles` not installed | Skip step 7 with a one-line notice. |
| `notella-review` not installed | Skip step 11 with a one-line notice. |
| Another orchestrator run is active (`locks/orchestrator.lock` live) | Exit with `another-run-active`; the watcher and the schedule can collide — this is the intended resolution. |
| `NL_DIR` unset in a headless run | Abort before Phase A with "NL_DIR not set; refusing to run against ~/notella in --auto mode" unless `~/notella/manifest.yaml` exists. |

## What this skill does NOT do

- **Does not write page artifacts.** Every actual write goes through specialist skills via `notella-state` (stubs for skipped specialists and the themes pointer copy are the only exceptions).
- **Does not call any model directly.** All model calls happen inside specialists.
- **Does not edit the manifest autonomously.** Proposes changes; user must confirm.
- **Does not delete pages, events, syntheses, or logs.** Evidence is immutable.
- **Does not skip the integrity gate.** first-pass will not run on a page that is missing required L1 artifacts, regardless of the page's current phase.
- **Does not record verdicts itself.** That is `notella-review`; the orchestrator only invokes it.

## Examples

### "Run notella"

Walks all eleven steps, presents the plan, asks for approval, executes, reports, ends in interactive review.

### "Run notella --auto"

Same but no approval prompt; review writes `logs/review-pending.md` instead of asking.

### "Run notella --only-step 2"

Pipeline catch-up only. No synthesis, no housekeeping.

### "Run notella --dry-run"

Show the full batch plan and integrity violations without executing anything.

### "Run notella --themes-now --skip-monthly"

Force a themes snapshot today without closing the month (useful mid-month to see the delta).

### "Notella status"

Read-only summary — what's pending, what's stuck, when the last run was, what is next due. No execution.

```
Notella state (2026-11-08, facility /Users/davidolsson/Documents/notella):
  Pages: 412 total
    archived: 412
  Inbox: empty
  Artifacts:
    classify:     412/412 ✓
    transcribe:   412/412 ✓
    composition:  412/412 ✓
    diagram:      301/301 ✓ (111 stubs)
    sketch:        96/96  ✓
    table:         84/84  ✓
    metadata:     412/412 ✓   (299 with date: null — normalization pending on --reprocess)
    first-pass:   412/412 ✓
    actions:      369/369 ✓
  Synthesis:
    Daily:   128 briefs (2025-12-01 → 2026-05-05); 3 dates missing (2026-05-06 → 2026-05-08, 30 pages)
    Weekly:  23 briefs (2025-W49 → 2026-W19); 2026-W19 stale (dailies missing)
    Project: 8 slugs briefed 2026-05-08; 7 manifest slugs never briefed
    Themes:  last snapshot 2026-05-09 (themes.json); 183 days — refresh due
    Monthly: none; 2026-05 … 2026-10 closed without a brief (6 months)
  Ledgers: decisions 118 rows (old schema), commitments 4 rows (old schema), people — not built
  Review:  logs/review-pending.md absent
  Integrity: 30 archived pages not in any daily (I-8); 15 duplicate raw images (all marked duplicate_of)
  Images:  quality.json 412/412; orientation suspected 104 (stamp in the wrong corner: 64 upside down, 40 sideways — all transcribed; fix + reprocess is a decision) · poor 0
  Inbox:   empty · held 0
  Stuck: 0
  Last orchestrator run: 2026-05-08T19:06Z
  Run /notella-orchestrator to fix (estimate: dailies $0.48, weekly $0.55, themes $1.80, monthly 1 × $2.00 — older months need --only-step 8).
```

## Reference files

- `references/decision-checklist.md` — formal version of the eleven steps with all the conditions.
- `references/parallelism-rules.md` — what's safe to fan out vs serialize.
- `references/stuck-page-rules.md` — when to surface a page as stuck, and the escalation ladder to auto-archive.
- `references/integrity-rules.md` — full list of pipeline integrity checks and gates.
- `references/project-discovery.md` — how candidate projects (and people aliases) are derived from metadata entities.
