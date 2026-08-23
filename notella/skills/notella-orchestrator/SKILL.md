---
name: notella-orchestrator
description: "The conductor of the notella-* skill family. Walks a six-step decision checklist (inbox drain, pipeline catch-up, daily synthesis, project synthesis, weekly synthesis, longitudinal refresh) and proposes the next batch of work. Use whenever the user says 'run notella', 'process my inbox', 'what should notella do next', 'orchestrate', 'sync notella', 'morning notella run', 'catch me up on notella', 'what's pending', or any request asking the facility to tell itself what to do next. Approval-gated by default; `--auto` runs without prompts. Reads through `notella-state` and invokes other notella-* skills. Thin by design — routes, does not perform pipeline work itself."
---

# notella-orchestrator — the conductor

Decides what to do next. Reads facility state, walks the decision checklist, proposes a batch of work, asks for approval, runs the batch.

## Purpose

Without an orchestrator, the user has to manually invoke each pipeline skill on each page. With one, they say "run notella" and the facility advances every page that's ready for the next stage, queues every overdue synthesis, and refreshes longitudinal intelligence on cadence.

The orchestrator is **thin**: it never writes page artifacts itself, never calls a model directly, never modifies the manifest. It reads state and routes work to the right specialist.

## Inputs and outputs

**Input:** Optional flags:
- `--auto` — run the proposed batch without asking
- `--max-pages N` — cap how many pages advance per run (default 20)
- `--skip-synthesis` — only do pipeline work, don't run daily/weekly/project/themes
- `--only-step {1..6}` — run a specific step in the checklist
- `--dry-run` — show the batch plan without executing
- `--catch-up-weeks N` — run back-syntheses for the last N weeks (Step 5 only)
- `--reprocess` — pass through to specialist skills, causing existing artifacts to be overwritten

**Output:**
- A summary of what was done (counts per skill invoked)
- Updates to `state.json:last_orchestrator_run`
- Activity-log entries for each invocation
- The facility advances by some number of phase transitions and synthesis outputs

## Pipeline integrity rules (non-negotiable)

These rules are enforced before any batch is executed. Violating them is how the corpus ends up with degraded first-pass artifacts.

1. **first-pass cannot run until composition, diagram (if required), sketch (if required), table (if required), and metadata are all present.** The orchestrator blocks first-pass for any page missing these artifacts and queues the L1 fan-out instead.

2. **actions cannot run until first-pass is present.**

3. **daily-synthesis cannot run until the target date's pages are at phase=indexed.**

4. **project-synthesis cannot run if manifest.projects is empty.** Surface a `manifest-empty` warning and invite the user to define projects. After notella-metadata runs, the orchestrator surfaces discovered project candidates for the user to confirm.

5. **The phase transition transcribed → first-pass-done is only permitted when all L1 artifacts required by the page's route_plan are present.** If a page is at `first-pass-done` without the required L1 artifacts, flag it as `integrity-violation` and queue a reprocessing run.

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

This pass runs automatically on first run after metadata completes, and whenever the user invokes `/notella-orchestrator --discover-projects`.

## The six-step decision checklist

Walked in order on each invocation:

### Step 1 — Inbox drain

```
inbox_files = ls ~/notella/inbox/
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

Cap at `--max-pages N` per run. Surface any stuck pages (in same phase > 4 hours without an error) for user attention.

The orchestrator runs the per-stage skills in **parallel where safe** — composition + metadata + diagram + sketch + table for the same page can fan out concurrently because each acquires the same per-page lock. Across pages, parallelism is unlimited.

### Step 3 — Daily synthesis

```
indexed_dates = unique(authoritative_date for pages with phase >= indexed)
for date in indexed_dates:
  if state.last_synthesis_at.daily is null OR daily/{date}.json missing:
    invoke notella-daily-synthesis(date)
```

### Step 4 — Project synthesis

```
if manifest.projects is empty: skip with manifest-empty warning
for project in manifest.projects:
  pages_touched = list-pages --project=project.slug
  if pages_touched.length > 0 AND projects/{slug}/ missing or stale:
    invoke notella-project-synthesis(project.slug)
```

### Step 5 — Weekly synthesis

```
completed_weeks = ISO weeks represented in daily/ syntheses
for week in completed_weeks:
  if weekly/{week}.json missing:
    invoke notella-weekly-synthesis(week)
```

`--catch-up-weeks N` limits to the N most recent weeks.

### Step 6 — Longitudinal refresh

```
if state.last_longitudinal_at is null OR > 30 days ago:
  invoke notella-themes
```

**Cadence: monthly, not weekly.** Themes that change week-to-week are mostly noise;
the meaningful drift signal in a notebook corpus is monthly. Weekly refresh was
spending compute to re-detect the same themes. Monthly cuts themes spend ~75%
with no signal loss. Override with `--themes-now` to force a fresh refresh.

### Step 7 — Stuck-page auto-archive (NEW)

```
stuck_long = list-pages --is-stuck --hours-stuck > 168    # > 7 days
for page in stuck_long:
  notella-state advance-phase {page-id, to-phase: archived, by-actor: notella-orchestrator, reason: "stuck > 7d"}
```

Pages stuck for over a week are unreachable through normal flow. Auto-archive
to stop spending synthesis compute on dead pages. The page record is preserved
(everything is append-only); only the phase changes so subsequent synthesis
skips it.

### Step 8 — Decisions ledger + commitment tracker (aggregation only, no model calls)

After daily synthesis completes, run the aggregator to refresh both ledgers:

```bash
# Preferred: hit the kanban API endpoint (idempotent, persists atomically)
curl -fsS -X POST http://localhost:3344/api/aggregate

# Or invoke the standalone CLI from the kanban repo
node ~/WORKSONA/notella-desktop/scripts/aggregate-ledgers.mjs
```

Both write to:
- `~/notella/longitudinal/decisions.ndjson` — every `new_decisions` entry across
  all daily syntheses, one JSON per line, sorted oldest-first
- `~/notella/longitudinal/commitments.ndjson` — every action with a state-machine
  annotation:
  - `proposed` — task observed, no owner identified
  - `owner_confirmed` — owner_candidates non-empty
  - `in_progress` — mentioned as started/underway in a later page
  - `done` — completion language appears in a later page
  - `abandoned` — explicit cancel language in a later page

State transitions are inferred from substring + 70%-overlap matching against
later page transcripts, with a 200-character window scanned for state-token
phrases (`completed`, `shipped`, `started`, `cancelled`, etc.).

These are pure functions of existing data; cost is filesystem I/O. Re-running
overwrites the ledgers atomically (tmp + rename). Implementation lives in
`~/WORKSONA/notella-desktop/src/lib/notella-aggregators.ts`.

## How a run executes

### Phase A — Plan

Read state, walk all six steps, build a batch plan:

```yaml
plan:
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
    dates_to_synthesize: [2025-12-01, 2025-12-02]
  step_4_project:
    projects_to_synthesize: [tulevik, aimqc]
    manifest_empty_warning: false
  step_5_weekly:
    weeks_to_synthesize: [2025-W49, 2025-W50]
  step_6_longitudinal:
    refresh_themes: true
estimated_minutes: 32
estimated_model_calls: 89
estimated_cost_usd: 1.85
budget_status:
  daily_spent_usd: 0.42
  daily_cap_usd: 10.00
  daily_remaining_usd: 9.58
  monthly_spent_usd: 4.17
  monthly_cap_usd: 200.00
  fits_in_daily_cap: true
  on_breach: warn
```

**Pre-flight cost check.** Before entering Phase B, hit
`GET http://localhost:3344/api/budget` and read the live snapshot.
Estimate the plan's cost using:

- L1 vision specialists: ~$0.07 / page (when all run; less when conditional skips fire)
- first-pass:    ~$0.020 / page (post-cache)
- actions:       ~$0.030 / page (when run)
- daily synth:   ~$0.16 / day (post-cache)
- weekly synth:  ~$0.55 / week
- project synth: ~$0.40 / refresh
- themes:        ~$1.80 / refresh

Add the estimate to the plan and to the user-facing approval prompt.
If `estimated_cost_usd > budget.daily_remaining_usd`, flag it
prominently and give the user a clear choice:
  (a) approve and let the budget guard refuse mid-batch
  (b) reduce `--max-pages` to fit
  (c) raise the daily cap in `/config`

### Phase B — Approve (unless --auto)

Surface the plan to the user. Flag integrity violations prominently:

```
Notella plan ready:

⚠ Integrity violations (2 pages at first-pass-done without required L1):
  - 2026-01-02-02h0 missing: composition, diagram
  - 2026-01-02-0w4g missing: composition, sketch
  → Queued for L1 reprocessing before any synthesis runs.

Pipeline:
  - 0 inbox files
  - 15 pages need L1 fan-out (composition: 15, diagram: 13, sketch: 4, table: 3, metadata: 15)
  - 15 pages need first-pass --reprocess (L1 inputs now complete)
  - 8 pages need actions
  - Project discovery: will propose manifest from metadata results

Synthesis (after pipeline completes):
  - Daily: 2025-12-01 → 2025-12-10 (10 dates)
  - Weekly: 2025-W49, 2025-W50 (2 weeks)
  - Project: requires manifest confirmation first
  - Themes: never run

~32 minutes, ~89 model calls, ~$1.85 estimated.
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
  [b] cap     — reduce --max-pages to fit (suggest: 4 pages)
  [r] raise   — open /config to raise the daily cap
  [c] cancel
```

### Phase C — Execute

Invoke each skill in plan order. For pipeline catch-up, group by stage and parallelize across pages. Stop on first hard error per stage; collect soft errors and report at the end.

**Execution sequence for pipeline catch-up:**
1. classify batch (parallel across pages)
2. transcribe batch (parallel across pages)
3. L1 fan-out batch (parallel across skills AND pages — all 5 specialists run simultaneously)
4. [pause] project discovery if metadata is new
5. first-pass batch (parallel across pages, after step 3 + 4 complete)
6. actions batch (parallel across pages)
7. advance enriched / indexed

### Phase D — Report

```
notella-orchestrator complete:
  ✓ Pipeline: 15 pages advanced
    - 15 transcribed → L1 fan-out (composition ✓, diagram 13/15 ✓, sketch 4/4 ✓, table 3/3 ✓, metadata 15/15 ✓)
    - 15 first-pass --reprocess (now with full L1 inputs)
    - 8 actions written
    - 15 enriched → indexed
  ✓ Project discovery: proposed 5 candidates (confirmed by user: tulevik, aimqc, dante, atomic47, decima)
    - metadata --reprocess run to backfill project_attributions
  ✓ Daily synthesis: 10 dates (2025-12-01 → 2025-12-10)
  ✓ Weekly synthesis: 2025-W49, 2025-W50
  ✓ Project synthesis: tulevik, aimqc, dante, atomic47, decima
  ✓ Themes: longitudinal/themes.json written (8 themes detected)

Skipped: 0
Errors: 0
```

Update `state.json:last_orchestrator_run`.

## Idempotency

Every step is itself idempotent (each skill the orchestrator invokes already is). Re-running the orchestrator with no new inputs produces "nothing to do" cleanly:

```
Notella plan: nothing pending.
Last orchestrator run: 2 hours ago.
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

## What this skill does NOT do

- **Does not write page artifacts.** Every actual write goes through specialist skills via `notella-state`.
- **Does not call any model directly.** All model calls happen inside specialists.
- **Does not edit the manifest autonomously.** Proposes changes; user must confirm.
- **Does not delete pages, events, syntheses, or logs.** Evidence is immutable.
- **Does not skip the integrity gate.** first-pass will not run on a page that is missing required L1 artifacts, regardless of the page's current phase.

## Examples

### "Run notella"

Walks all six steps, presents the plan, asks for approval, executes, reports.

### "Run notella --auto"

Same but no approval prompt.

### "Run notella --only-step 2"

Pipeline catch-up only. No synthesis.

### "Run notella --dry-run"

Show the full batch plan and integrity violations without executing anything.

### "Notella status"

Read-only summary — what's pending, what's stuck, when the last run was. No execution.

```
Notella state (2026-05-02):
  Pages: 15 total
    archived: 15 (all — but L1 artifacts missing on all)
  Inbox: empty
  Artifacts:
    classify:     15/15 ✓
    transcribe:   15/15 ✓
    composition:   0/15 ✗ MISSING
    diagram:       0/13 ✗ MISSING
    sketch:        0/4  ✗ MISSING
    table:         0/3  ✗ MISSING
    metadata:      0/15 ✗ MISSING
    first-pass:   15/15 (but degraded — ran without L1 inputs)
    actions:       0/8  ✗ MISSING
  Synthesis:
    Daily: 2025-12-01 (1 of 10 needed dates)
    Weekly: none
    Project: none (manifest.projects empty)
    Themes: never run
  Integrity violations: 15 pages (first-pass ran without L1)
  Run /notella-orchestrator to fix.
```

## Reference files

- `references/decision-checklist.md` — formal version of the six steps with all the conditions.
- `references/parallelism-rules.md` — what's safe to fan out vs serialize.
- `references/stuck-page-rules.md` — when to surface a page as stuck.
- `references/integrity-rules.md` — full list of pipeline integrity checks.
- `references/project-discovery.md` — how candidate projects are derived from metadata entities.
