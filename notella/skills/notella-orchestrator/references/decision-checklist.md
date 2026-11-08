# Decision checklist — formal version

The ten steps `notella-orchestrator` walks, each as **condition → action → skip reason**, with the flags that affect it. Phase A evaluates every condition read-only and records the result in the plan; Phase C executes the actions in order. Times are in `manifest.facility.timezone`. `$NL_DIR` is the facility (default `~/notella`; this machine: `/Users/davidolsson/Documents/notella`).

## Preconditions (before step 1)

| Check | On failure |
| --- | --- |
| `$NL_DIR/manifest.yaml` exists | interactive: offer `notella-state init`; `--auto`: abort `facility-missing` |
| `NL_DIR` set, or `~/notella/manifest.yaml` exists | `--auto`: abort `nl-dir-unset` |
| no live `locks/orchestrator.lock` | abort `another-run-active` (unless `--force`) |
| integrity checks I-1 … I-12 (`integrity-rules.md`) | record violations; queue fixes into step 2 |
| budget snapshot readable | fall back to summing `logs/llm-calls.ndjson`; never block on this |

## Step 1 — Inbox drain

| | |
| --- | --- |
| Condition | `ls $NL_DIR/inbox/*.{jpg,jpeg,heic,heif,png,pdf}` non-empty |
| Action | `notella-intake` |
| Skip when | inbox empty → `nothing to drain` |
| Flags | none (always runs when files exist; `--only-step 1` isolates it) |
| Plan fields | `step_1_inbox.files_to_drain` |

## Step 2 — Pipeline catch-up

Evaluated per page, bounded by `--max-pages` (default 20) counted as pages that will change phase this run.

| Sub-stage | Condition | Action |
| --- | --- | --- |
| classify | `phase == intake` | `notella-classify` |
| transcribe | `phase == classified` | `notella-transcribe` |
| L1: composition | `phase == transcribed` and `composition.json` absent | `notella-composition` |
| L1: metadata | `phase == transcribed` and `metadata.json` absent | `notella-metadata` |
| L1: diagram | `phase == transcribed`, `route_plan ∋ diagram_interpretation`, `diagram.json` absent | `content_mix.diagram ≥ 15` → `notella-diagram`; else write stub |
| L1: sketch | same with `sketch_interpretation` | `content_mix.diagram + symbolic ≥ 10` → `notella-sketch`; else stub |
| L1: table | same with `table_extraction` | `content_mix.table ≥ 1` → `notella-table`; else stub |
| discovery | metadata ran on ≥ 1 page this run and (`manifest.projects` empty or unmatched project mentions ≥ 3), or `--discover-projects` | project discovery (`project-discovery.md`); `--auto` → write proposal to `logs/review-pending.md` |
| first-pass | `phase == transcribed` and required set present (stub OK) — **the integrity gate** | `notella-first-pass` |
| actions | `first-pass.json` present, `actions.json` absent, `route_plan ∋ action_decision`, `first-pass.action_intelligence.length ≥ 2` | `notella-actions` |
| advance enriched | `phase == first-pass-done` and (actions present or not required) | `notella-state advance-phase enriched` |
| advance indexed | `phase == enriched` and `meta.yaml` mirrors populated | `notella-state advance-phase indexed` |

Skip reasons recorded per page: `wrong-phase`, `blocked-on-L1 [list]`, `below-threshold (stub)`, `max-pages`, `lock-held`, `errored`, `disabled-in-cost-controls (stub)`.

Flags: `--max-pages`, `--reprocess` (passes through; also re-runs stages whose artifact exists), `--discover-projects`, `--only-step 2`.

Plan fields: `step_2_pipeline.{classify, transcribe, layer1_fanout.*, project_discovery, first_pass, actions, advance_enriched, advance_indexed}`, `integrity_violations`.

## Step 3 — Daily synthesis

| | |
| --- | --- |
| Condition | for each date `d` < today with ≥ 1 page at `phase ≥ indexed` whose authoritative date is `d`: `daily/{d}.json` absent, **or** present with `pages_analyzed` < current indexed count for `d` (`daily-stale`) |
| Action | `notella-daily-synthesis(d, previous_daily = newest daily/*.json with date < d)`; stale → with `--reprocess` |
| Skip when | all dates briefed → `dailies current`; `--skip-synthesis` |
| Order | oldest date first, so each brief's "previous" exists |
| Flags | `--skip-synthesis`, `--reprocess`, `--only-step 3` |
| Plan fields | `step_3_daily.dates_to_synthesize`, `step_3_daily.previous_daily_for_first` |

Authoritative date chain: `metadata.date` → `transcribe.extractedDate` → `meta.source_capture_time` → `meta.ingested_at`, ISO values only.

## Step 4 — Weekly synthesis

| | |
| --- | --- |
| Condition | ISO week `w` has closed (its Sunday 23:59 has passed) and ≥ 1 `daily/*.json` falls in `w`, and `weekly/{w}.json` absent — **or** present but older than the newest daily inside `w` (`weekly-stale`) |
| Action | `notella-weekly-synthesis(w)`; stale → with `--reprocess` |
| Skip when | no closed week lacks a brief → `weeklies current`; `--skip-weekly`; `--skip-synthesis` |
| Limit | `--catch-up-weeks N` → the N most recent qualifying weeks only (default: all qualifying) |
| Flags | `--skip-weekly`, `--skip-synthesis`, `--catch-up-weeks`, `--reprocess`, `--only-step 4` |
| Plan fields | `step_4_weekly.weeks_to_synthesize`, `step_4_weekly.weeks_stale` |

The current (open) week is never synthesised here; `notella-weekly-synthesis --partial` is a manual call.

## Step 5 — Project synthesis

| | |
| --- | --- |
| Condition | `manifest.projects` non-empty; for each `active` slug: ≥ 1 page at `phase ≥ indexed` with `project_attributions ∋ slug` and `ingested_at` or phase-change after `state.last_synthesis_at.by_project[slug]` (or that value is null) |
| Action | `notella-project-synthesis(slug)` |
| Skip when | manifest empty → `manifest-empty` warning (+ discovery candidates if any); slug untouched since last brief → `project quiet`; `--skip-project`; `--skip-synthesis` |
| Flags | `--skip-project`, `--skip-synthesis`, `--only-step 5` |
| Plan fields | `step_5_project.projects_to_synthesize`, `step_5_project.manifest_empty_warning` |

## Step 6 — Themes refresh

| | |
| --- | --- |
| Condition | `--themes-now`, **or** `state.last_longitudinal_at` null, **or** `now − state.last_longitudinal_at > 30 days`; and ≥ 10 pages at `phase ≥ indexed` |
| Action | `notella-themes` → writes `longitudinal/themes/{today}.json|.md`, copies to `longitudinal/themes.json|.md`, updates `state.last_longitudinal_at` |
| Skip when | cadence not due → `themes: next due {date}`; `< 10 pages` → `corpus too small`; `--skip-themes`; `--skip-synthesis` |
| Flags | `--themes-now`, `--skip-themes`, `--skip-synthesis`, `--only-step 6` |
| Plan fields | `step_6_themes.{refresh, reason, snapshot_path}` |

## Step 7 — Monthly synthesis

| | |
| --- | --- |
| Condition | calendar month `m` has closed (its last day 23:59 has passed); ≥ 1 `weekly/*.json` whose week overlaps `m`; `monthly/{m}.json` absent; **and** a themes snapshot with `generated_at` ≥ close of `m` exists (written this run in step 6, or earlier) |
| Action | `notella-monthly-synthesis(m)` → `monthly/{m}.json|.md` |
| Skip when | no closed month lacks a brief → `monthlies current`; themes not fresh → `monthly-deferred: themes-not-fresh`; `--skip-monthly`; `--skip-themes` (implies deferral unless a fresh snapshot already exists); `--skip-synthesis` |
| Limit | in a normal run, only the most recently closed qualifying month; older months are listed as `monthly backlog: [...]` and require `--only-step 7` (each is an Opus run) |
| Flags | `--skip-monthly`, `--skip-themes`, `--skip-synthesis`, `--only-step 7` |
| Plan fields | `step_7_monthly.{months_to_synthesize, deferred}` |

Order dependency: runs after step 6 and after step 4 (weeklies of the month must exist).

## Step 8 — Stuck-page auto-archive

| | |
| --- | --- |
| Condition | `notella-state list-pages --is-stuck --hours-stuck 168` non-empty (`stuck-page-rules.md`) |
| Action | `notella-state advance-phase {page, archived, by-actor: notella-orchestrator, reason: "stuck > 7d at {phase}"}` |
| Skip when | none → `no stuck pages > 7d` |
| Flags | `--only-step 8` (no skip flag — housekeeping always runs; `--dry-run` lists without archiving) |
| Plan fields | `step_8_stuck.auto_archive`; shorter-stuck pages appear under `stuck_pages` for information |

Runs after pipeline catch-up so pages unstuck this run are not archived.

## Step 9 — Ledgers aggregation

| | |
| --- | --- |
| Condition | any daily, actions.json, metadata.json or verdicts.ndjson changed since `state.last_ledgers_at` (or that is null) |
| Action | `NL_DIR=$NL_DIR node ~/WORKSONA/notella-desktop/scripts/aggregate-ledgers.mjs` (CLI tries `POST http://localhost:3344/api/aggregate` first, then in-process) → `longitudinal/{decisions,commitments,people}.ndjson`; set `state.last_ledgers_at` |
| Skip when | nothing changed → `ledgers current`; neither `node` nor dev server available → `ledgers: skipped (no runtime)` |
| Flags | `--only-step 9` (no skip flag) |
| Plan fields | `step_9_ledgers.{run, via}` |

## Step 10 — Review

| | |
| --- | --- |
| Condition | `notella-review` installed; and at least one of: open commitments > 14 days, yesterday's `watch_tomorrow` items, unresolved questions carried ≥ 3 days, pages with ≥ 3 first-pass sanity warnings this run, stuck pages 3× threshold – 7 d, pending project-discovery proposal |
| Action | `--auto` → `notella-review --report` (writes `logs/review-pending.md`); interactive → `notella-review` (done / drop / carry / wrong → `longitudinal/verdicts.ndjson`, `correction` events) |
| Skip when | nothing to review → `review: nothing pending` (under `--auto`, still write an empty-state `review-pending.md` so the morning reader sees the run happened); not installed → notice; `--skip-review` |
| Flags | `--skip-review`, `--auto`, `--only-step 10` |
| Plan fields | `step_10_review.mode` |

## Flag interaction summary

| Flag | Steps affected |
| --- | --- |
| `--skip-synthesis` | 3, 4, 5, 6, 7 skipped |
| `--skip-weekly` | 4 |
| `--skip-project` | 5 |
| `--skip-themes` | 6, and 7 deferred unless a fresh snapshot exists |
| `--skip-monthly` | 7 |
| `--skip-review` | 10 |
| `--themes-now` | 6 forced (overrides cadence, not `--skip-themes`) |
| `--catch-up-weeks N` | 4 limited |
| `--max-pages N` | 2 limited |
| `--discover-projects` | 2 (discovery forced) |
| `--reprocess` | 2 (pass-through), 3/4 (stale re-runs) |
| `--only-step k` | only step k, preconditions still evaluated |
| `--dry-run` | Phase A only |
| `--auto` | Phase B skipped; step 10 in report mode; discovery proposals written, not applied |

## Phase D — what gets recorded

- `state.json:last_orchestrator_run = {at, flags, steps_run, counts, cost_usd, errors}`
- `state.json:last_ledgers_at` (step 9), `state.json:last_longitudinal_at` (by themes), `state.json:last_synthesis_at.*` (by the synthesis skills)
- one `activity.ndjson` line per invocation and one `orchestrator.run` summary line
- under `--auto`: `logs/review-pending.md`
