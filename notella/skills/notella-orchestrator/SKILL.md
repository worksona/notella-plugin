---
name: notella-orchestrator
description: "The conductor of the notella-* skill family. Walks a ten-step decision checklist (inbox drain, pipeline catch-up, daily synthesis, weekly synthesis, project synthesis, themes refresh, monthly synthesis, stuck-page archive, ledgers aggregation, review) and proposes the next batch of work. Use whenever the user says 'run notella', 'process my inbox', 'what should notella do next', 'orchestrate', 'sync notella', 'morning notella run', 'catch me up on notella', 'what's pending', or any request asking the facility to tell itself what to do next. Approval-gated by default; `--auto` runs without prompts and is the headless entry point for scheduled runs. Reads through `notella-state` and invokes other notella-* skills. Thin by design — routes, does not perform pipeline work itself."
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
| `--only-step {1..10}` | run a specific step in the checklist |
| `--dry-run` | show the batch plan without executing |
| `--catch-up-weeks N` | run back-syntheses for the last N closed weeks (step 4 only) |
| `--reprocess` | pass through to specialist skills, causing existing artifacts to be overwritten |
| `--themes-now` | force a themes refresh this run regardless of cadence (step 6) |
| `--discover-projects` | run the project discovery pass even if the manifest is populated |
| `--skip-synthesis` | skip steps 3, 4, 5, 6 and 7 — daily, weekly, project, themes and monthly. Pipeline, stuck-page archive, ledgers and review still run |
| `--skip-weekly` | skip step 4 |
| `--skip-project` | skip step 5 |
| `--skip-themes` | skip step 6 (and therefore step 7, which needs the themes delta) |
| `--skip-monthly` | skip step 7 |
| `--skip-review` | skip step 10 |

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

## The ten-step decision checklist

Walked in order on each invocation. The formal version with every condition is `references/decision-checklist.md`.

### Step 1 — Inbox drain

```
inbox_files = ls $NL_DIR/inbox/
if inbox_files: invoke notella-intake
```

After intake completes, refresh `notella-state list-pages --phase=intake` and continue.

### Step 2 — Pipeline catch-up

**Integrity check first:** For every page at `phase=first-pass-done` or later, verify required L1 artifacts are present. Flag any violations as `integrity-violation` in the plan.

For each phase boundary, in strict order:

```
pages_at_intake     = list-pages --phase=intake     → notella-classify
pages_at_classified = list-pages --phase=classified → notella-transcribe

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
       AND monthly/{that-month}.json is missing):        # step 7 needs a fresh snapshot
  invoke notella-themes
```

**Cadence: monthly, not weekly.** Themes that change week-to-week are mostly noise; the meaningful drift signal in a notebook corpus is monthly. Weekly refresh was spending compute to re-detect the same themes. Monthly cuts themes spend ~75% with no signal loss. `--themes-now` forces a refresh; `--skip-themes` skips (and skips step 7 with it).

Each refresh writes a dated snapshot `longitudinal/themes/{YYYY-MM-DD}.json` (plus `.md`) and copies the newest snapshot to `longitudinal/themes.json` / `themes.md`, so the pointer files always hold the latest while history accumulates. The snapshot carries a deterministic `delta` against the previous snapshot, which step 7 consumes.

### Step 7 — Monthly synthesis

```
closed_months = calendar months whose last day 23:59 (facility timezone) has passed
                AND that contain >= 1 weekly/*.json
for month in closed_months:
  if monthly/{YYYY-MM}.json missing:
    require: themes snapshot newer than month close exists (step 6 ran this run, or earlier)
    invoke notella-monthly-synthesis(month)
```

Runs **after** themes because it consumes the themes delta (theme arc: what rose, held, fell). Writes `monthly/{YYYY-MM}.{json,md}` — month-in-review with theme arc, commitment aging, forecast scorecard and next-month watchlist. When a month has closed and the latest themes snapshot predates the month close, step 6 runs regardless of the 30-day cadence (a closed month is itself the cadence trigger), so the normal outcome is a fresh snapshot before the monthly runs. Only if themes was explicitly skipped (`--skip-themes`) or failed is monthly deferred with `monthly-deferred: themes-not-fresh` in the report; `--only-step 7` runs it against the stale snapshot and the monthly records `sources.themes_current_stale: true`. `--skip-monthly` skips the step. Normally only one month is ever due; `--catch-up-weeks` does not apply — back-filling many months is an explicit `--only-step 7` decision because each month is an Opus run.

### Step 8 — Stuck-page auto-archive

```
stuck_long = list-pages --is-stuck --hours-stuck > 168    # > 7 days
for page in stuck_long:
  notella-state advance-phase {page-id, to-phase: archived, by-actor: notella-orchestrator, reason: "stuck > 7d"}
```

Pages stuck for over a week are unreachable through normal flow. Auto-archive to stop spending synthesis compute on dead pages. The page record is preserved (everything is append-only); only the phase changes so subsequent synthesis skips it. Escalation ladder before this point: `references/stuck-page-rules.md`.

### Step 9 — Ledgers aggregation (decisions, commitments, people — no model calls)

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

### Step 10 — Review

```
if --auto:
  invoke notella-review --report        # writes logs/review-pending.md, no prompts
else:
  invoke notella-review                 # interactive: done / drop / carry / wrong per item
```

Review shows yesterday's watch items, open commitments older than 14 days, unresolved questions, pages whose first-pass drew three or more sanity warnings, stuck pages awaiting a human, and (under `--auto`) any project-discovery proposal that is pending confirmation. Verdicts are appended to `longitudinal/verdicts.ndjson` and feed step 9 on the next run. `--skip-review` skips the step. Review makes no model call; its cost is reading.

## How a run executes

### Phase A — Plan

Read state, walk all ten steps, build a batch plan:

```yaml
plan:
  facility: /Users/davidolsson/Documents/notella        # from NL_DIR
  integrity_violations: []        # pages with L1 missing despite later phase
  step_1_inbox:
    files_to_drain: 5
  step_2_pipeline:
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
  step_7_monthly:
    months_to_synthesize: [2026-10]
    deferred: null                                        # or "themes-not-fresh"
  step_8_stuck:
    auto_archive: [page-id]
  step_9_ledgers:
    run: true
    via: cli                                              # or api
  step_10_review:
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

| Work | Estimate |
| --- | --- |
| L1 vision specialists | ~$0.07 / page (when all run; less when conditional skips fire) |
| first-pass | ~$0.020 / page (post-cache) |
| actions | ~$0.030 / page (when run) |
| daily synth | ~$0.16 / day (post-cache) |
| weekly synth | ~$0.55 / week |
| project synth | ~$0.40 / refresh |
| themes | ~$1.80 / refresh |
| monthly synth | ~$2.00 / month |
| ledgers | $0 (filesystem only) |
| review | ~$0 (no model call beyond reading) |

Add the estimate to the plan and to the user-facing approval prompt. If `estimated_cost_usd > budget.daily_remaining_usd`, flag it prominently and give the user a clear choice:
  (a) approve and let the budget guard refuse mid-batch
  (b) reduce `--max-pages` to fit, or add `--skip-themes --skip-monthly`
  (c) raise the daily cap in `/config`

### Phase B — Approve (unless --auto)

Surface the plan to the user. Flag integrity violations prominently:

```
Notella plan ready (facility: /Users/davidolsson/Documents/notella):

⚠ Integrity violations (2 pages at first-pass-done without required L1):
  - 2026-01-02-02h0 missing: composition, diagram
  - 2026-01-02-0w4g missing: composition, sketch
  → Queued for L1 reprocessing before any synthesis runs.

Pipeline:
  - 5 inbox files
  - 15 pages need L1 fan-out (composition: 15, diagram: 13, sketch: 4, table: 3, metadata: 15)
  - 15 pages need first-pass --reprocess (L1 inputs now complete)
  - 8 pages need actions
  - Project discovery: will propose manifest additions from metadata results

Synthesis (after pipeline completes):
  - Daily:   2026-11-05 → 2026-11-07 (3 dates; previous brief 2026-11-04 passed as memory)
  - Weekly:  2026-W44 (closed, no brief)
  - Project: tulevik, aimqc (touched since last brief)
  - Themes:  refresh — last 2026-05-09, cadence 30d → snapshot longitudinal/themes/2026-11-08.json
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
  [b] cap     — reduce --max-pages to fit (suggest: 4 pages), or defer themes + monthly (−$3.80)
  [r] raise   — open /config to raise the daily cap
  [c] cancel
```

### Phase C — Execute

Invoke each skill in plan order. For pipeline catch-up, group by stage and parallelize across pages. Stop on first hard error per stage; collect soft errors and report at the end.

**Execution sequence:**
1. inbox drain
2. classify batch (parallel across pages)
3. transcribe batch (parallel across pages)
4. L1 fan-out batch (parallel across skills AND pages — all 5 specialists run simultaneously)
5. [pause] project discovery if metadata is new
6. first-pass batch (parallel across pages, after 4 + 5 complete)
7. actions batch (parallel across pages)
8. advance enriched / indexed
9. daily syntheses (oldest first, each with its previous daily)
10. weekly syntheses for closed weeks
11. project syntheses for touched slugs
12. themes refresh
13. monthly synthesis (after themes)
14. stuck-page auto-archive
15. ledgers aggregation
16. review (`--report` under `--auto`)

### Phase D — Report

```
notella-orchestrator complete (facility: /Users/davidolsson/Documents/notella):
  ✓ Inbox: 5 files → 5 pages (2 entries)
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
| Morning, daily (`30 6 * * *`) | `claude -p "/notella-orchestrator --auto --skip-weekly --skip-monthly --skip-themes" --dangerously-skip-permissions` | inbox, pipeline, dailies for closed dates, project briefs for touched slugs, stuck archive, ledgers, `review --report` → `logs/review-pending.md` |
| Monday (`30 7 * * 1`) | `claude -p "/notella-orchestrator --auto" --dangerously-skip-permissions` | everything above plus the weekly for the week just closed; themes/monthly only if due by cadence |
| First of month (`0 5 1 * *`) | `claude -p "/notella-orchestrator --auto --themes-now" --dangerously-skip-permissions` | forces the themes snapshot, then the monthly for the month just closed, then ledgers and review report |
| Inbox watcher (launchd `WatchPaths` on `$NL_DIR/inbox`, 2-minute debounce) | `claude -p "/notella-orchestrator --auto --skip-synthesis --max-pages 20" --dangerously-skip-permissions` | cheap stages only: intake → classify → transcribe → L1 → first-pass → actions → indexed. Synthesis stays on the schedule so a trickle of photos never triggers an Opus run |

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
| `notella-review` not installed | Skip step 10 with a one-line notice. |
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

Walks all ten steps, presents the plan, asks for approval, executes, reports, ends in interactive review.

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
  Integrity: 30 archived pages not in any daily (I-8); 15 duplicate raw images (review)
  Stuck: 0
  Last orchestrator run: 2026-05-08T19:06Z
  Run /notella-orchestrator to fix (estimate: dailies $0.48, weekly $0.55, themes $1.80, monthly 1 × $2.00 — older months need --only-step 7).
```

## Reference files

- `references/decision-checklist.md` — formal version of the ten steps with all the conditions.
- `references/parallelism-rules.md` — what's safe to fan out vs serialize.
- `references/stuck-page-rules.md` — when to surface a page as stuck, and the escalation ladder to auto-archive.
- `references/integrity-rules.md` — full list of pipeline integrity checks and gates.
- `references/project-discovery.md` — how candidate projects (and people aliases) are derived from metadata entities.
