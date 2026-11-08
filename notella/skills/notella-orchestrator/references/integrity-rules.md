# Pipeline integrity rules

The full list of checks `notella-orchestrator` runs before and during a batch. They exist because the corpus once ended up with 15 pages at `first-pass-done` whose first-pass had run on a bare transcript — composition, diagram, sketch, table and metadata were all missing — and every daily, weekly and themes output built on them was degraded. The checks are cheap (filesystem reads) and are never skipped, not even under `--auto`.

## Vocabulary

- **L1 artifacts**: `classify.json`, `transcribe.json`, `composition.json`, `diagram.json`, `sketch.json`, `table.json`.
- **L2 artifacts**: `metadata.json`, `first-pass.json`, `actions.json`.
- **Required set for a page**: `transcribe`, `composition`, `metadata` always; `diagram` if `route_plan ∋ diagram_interpretation`; `sketch` if `∋ sketch_interpretation`; `table` if `∋ table_extraction`. A **stub** (`{ "<kind>_count": 0, "layout_semantics": "<one line>" }` written by the orchestrator when the content_mix signal was below threshold) satisfies the requirement.
- **Phase order**: `intake → classified → transcribed → first-pass-done → enriched → indexed → archived`.

## Pre-batch checks (Phase A)

| # | Check | Scope | On failure |
| --- | --- | --- | --- |
| I-1 | Every page at `phase ≥ first-pass-done` has the full required set present. | all pages | Flag `integrity-violation`; queue the missing L1 specialists and then `first-pass --reprocess`; exclude the page from synthesis until fixed. |
| I-2 | Every page at `phase ≥ first-pass-done` has `first-pass.json`. | all pages | Flag; queue `first-pass`. |
| I-3 | Every page at `phase ≥ enriched` with `route_plan ∋ action_decision` and `first-pass.action_intelligence.length ≥ 2` has `actions.json`. | all pages | Flag `enrichment-incomplete`; queue `actions`; the page may stay at its phase. |
| I-4 | `classify.json:route_plan` ⊆ `manifest.route_plan_vocab` and contains the minimum set (`transcription`, `composition`, `tagging`). | pages ≥ classified | Flag `route-plan-invalid`; queue `classify --reprocess`. |
| I-5 | `metadata.json:date` is ISO or null; `transcribe.json:extractedDate` is ISO or null. | pages with those artifacts | Flag `date-not-iso`; queue `metadata --reprocess` (which normalizes); until then the page's authoritative date falls through to capture time. |
| I-6 | `meta.yaml:project_attributions` ⊆ `manifest.projects[].slug`. | all pages | Flag `unknown-project-attribution`; surface the slugs; do not auto-fix (the manifest may have been edited). |
| I-7 | Every `daily/{date}.json` has `pages_analyzed == count(pages with authoritative date == date and phase ≥ indexed)`. | all dailies | Flag `daily-stale`; queue `daily-synthesis --reprocess` for that date (pages were added after the brief). |
| I-8 | Every page at `phase == archived` is listed in exactly one `daily/*.json`. | archived pages | Flag `archived-not-in-daily`; queue daily synthesis for that page's date. |
| I-9 | `weekly/{week}.json:dates_covered` ⊆ existing dailies. | all weeklies | Flag `weekly-stale` when a daily inside the week is newer than the weekly; queue `weekly --reprocess`. |
| I-10 | `monthly/{YYYY-MM}.json` exists for every closed month that has at least one weekly, when monthly synthesis is enabled. | months | Not a violation — a plan item for step 7. |
| I-11 | `longitudinal/themes.json` equals the newest `longitudinal/themes/*.json` when the snapshot folder exists. | once | Flag `themes-pointer-stale`; copy the newest snapshot over `themes.json` (no model call). |
| I-12 | `locks/` contains no lock older than 2 hours whose actor process is gone. | once | Release with a `lock-reaped` activity entry; the page it guarded is re-checked. |

Violations are listed at the top of the plan and the approval prompt, with page ids, before any pipeline counts.

## Gate checks (Phase C, per page, before each invocation)

| Gate | Rule |
| --- | --- |
| G-classify | `phase == intake` and `derived/page.jpg` exists and is non-empty. |
| G-transcribe | `phase == classified` and `classify.json` valid. |
| G-L1-fanout | `phase == transcribed`; each specialist additionally requires its route_plan entry and content_mix threshold (`decision-checklist.md` step 2). |
| **G-first-pass** | `phase == transcribed` **and the full required set is present (stub OK)**. This is the integrity gate. No flag, no `--auto`, and no `--reprocess` bypasses it. If a specialist failed, first-pass waits for the next run. |
| G-actions | `first-pass.json` present, `route_plan ∋ action_decision`, `first-pass.action_intelligence.length ≥ 2`. |
| G-enriched | first-pass present and every conditional L2 that should run has run (or was skipped by the ≥ 2 rule). |
| G-indexed | `phase == enriched`; `meta.yaml` mirrors (`tags`, `project_attributions`, `person_attributions`, `content_mix`) are populated. |
| G-daily | every page for the date is at `phase ≥ indexed`; none is flagged by I-1/I-2. |
| G-weekly | the ISO week has closed (Sunday 23:59 in the facility timezone has passed) and ≥ 1 daily exists in it; `--partial` relaxes the closed-week condition. |
| G-project | `manifest.projects` non-empty; slug exists; ≥ 1 attributed page at `phase ≥ indexed`. |
| G-themes | `state.last_longitudinal_at` null or > 30 days ago, or `--themes-now`; ≥ 10 pages at `phase ≥ indexed`. |
| G-monthly | the calendar month has closed; `monthly/{YYYY-MM}.json` missing; themes step for this run has completed (monthly consumes the themes delta); ≥ 1 weekly inside the month. |
| G-review | `notella-review` is installed; there is something to review (open commitments > 14 days, yesterday's watch items, pages with ≥ 3 first-pass warnings, or verdict-pending ledger rows). |

## Post-invocation checks (Phase C, after each skill returns)

- The artifact the skill was asked to write exists and parses.
- The phase advanced to exactly the expected value (or stayed, for L1/L2 specialists that do not advance).
- `pipeline.ndjson` has a line for the invocation with `status: complete | error | skipped`.
- No lock remains for the page.

A failed post-check marks the page `errored` in `meta.yaml:errors`, excludes it from the rest of the batch, and lists it in the report. Three consecutive runs with the same error make the page **stuck** (`stuck-page-rules.md`).

## Invariants the orchestrator itself must honour

- It never writes an artifact except stubs (and `themes.json` pointer copies under I-11), and stubs only when the content_mix threshold says the specialist would find nothing.
- It never advances a phase except `enriched`, `indexed`, and the stuck-page `archived` — all through `notella-state advance-phase`.
- It never deletes. Reprocessing overwrites through the specialist, which emits a `correction` event.
- It never edits `manifest.yaml`; project discovery proposes and the user confirms.

## Reporting

The Phase D report ends with an integrity line:

```
Integrity: 0 violations (checked 412 pages, 128 dailies, 23 weeklies, 1 themes pointer)
```

or, when violations were found and fixed in the run, the before/after counts per check id.
