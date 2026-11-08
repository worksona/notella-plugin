# notella-monthly-synthesis — prompt

The complete month-in-review prompt, self-contained in the plugin. Unlike the daily and weekly prompts it has no app ancestor: the monthly brief is new to the facility and its prompt is built around a block of pre-computed measurements that the model annotates but never changes. Every number, bucket, weight, direction, people list and scorecard row is produced by `references/monthly-aggregation.md` before the model is called; the model writes the judgement around them.

**Placeholders:** `{{double-curly}}`. Blocks marked *(conditional)* are omitted, heading included, when their input is absent.

| Placeholder | Source |
| --- | --- |
| `{{month}}` | `YYYY-MM` |
| `{{month_label}}` | `{Month YYYY}`, e.g. `May 2026` |
| `{{month_start}}`, `{{month_end}}` | first and last calendar day, `YYYY-MM-DD` (with `--partial`, `month_end` is today) |
| `{{partial}}` | `true` when invoked with `--partial`; else `false` |
| `{{measurements_json}}` | the Step 3 pre-aggregation block (shape below) serialised as JSON |
| `{{weeklies_json}}` | array of `{iso_week, weekly_json}` — the full `weekly/{iso_week}.json` for every week in `weeks_covered`, oldest first |
| `{{weeks_missing}}` | the overlapping ISO weeks with no weekly, as a list; `[]` when none |
| `{{previous_month}}` | `YYYY-MM` of the previous monthly |
| `{{previous_monthly_json}}` | `monthly/{previous_month}.json` reduced to `narrative` and `next_month_watchlist` |
| `{{themes_previous_path}}`, `{{themes_current_path}}` | `longitudinal/themes/YYYY-MM-DD.json` for each snapshot |
| `{{themes_previous_json}}`, `{{themes_current_json}}` | each snapshot reduced to `generated_at`, `themes[]` as `{name, weight, trajectory, first_seen, last_seen}`, and `emergent_topics[]` as `{name, first_seen, pages_count}` — no descriptions |
| `{{verdicts_json}}` | `verdicts.ndjson` rows that touched the month: `target_kind: forecast` rows matched to a scorecard row, and `target_kind: commitment` rows with `ts` in the month — `{ts, target_kind, target_id, target_text, verdict, note, source_ref}` |

**Call shape:** system block with `cache_control: {type: "ephemeral"}` (identical across months, so a back-fill of several months pays it once), one user turn. Model from `manifest.model_defaults.monthly_synthesis`, falling back to `model_defaults.themes` (default `claude-opus-4-6`); where the facility keeps model defaults in `cost-controls.yaml`, read them there with the same fallback. If the user turn exceeds ~80k tokens, reduce each weekly in `{{weeklies_json}}` to `executive_summary`, `key_themes`, `themes_dropped`, `action_items_open`, `focus_scorecard`, `suggested_focus`, `momentum_summary` first; then drop `people_and_relationships` and `ideas_and_insights`. Never trim `{{measurements_json}}`. JSON only.

---

## What is deterministic and what the model decides

The split is the contract of this prompt. The skill overwrites every field in the left column with its own Step 3 value after the model returns, then compares what the model sent back — a model that reasoned from altered numbers fails validation and gets one retry.

| Given to the model (deterministic, from `monthly-aggregation.md`) | Decided by the model |
| --- | --- |
| `pages_total`, `pages_by_project`, `pages_by_weekday` | — |
| `theme_arc[]`: `theme`, `start_weight`, `end_weight`, `direction`, `evidence_candidates` | `theme_arc[].note`, `theme_arc[].evidence_pages` (≤ 5, subset of `evidence_candidates`) |
| `decisions_made[]`: `decision`, `date`, `page_id` | `decisions_made[].revisited`, `decisions_made[].revisit_note` |
| `commitments_aging` (all of it: `buckets`, `oldest`, `closed_this_month`, `dropped_this_month`) | — |
| `people_movement` (all three lists) | — |
| `forecast_scorecard[]`: `prediction`, `source`, and for rows with a human verdict `outcome` + `evidence`; for emergent-topic rows a `hint` | `forecast_scorecard[].outcome` and `evidence` on rows without a verdict (hint is the default; override only with evidence) |
| `next_month_watchlist[].id` (minted `{{month}}-w{n}` by the skill after the model returns, in list order) | `next_month_watchlist[]`: `prediction`, `signal_to_watch`, `falsified_if` (3–5 items) |
| `sources`, `weeks_covered`, `weeks_missing`, `partial`, `generated_at`, `schema_version`, `month` | `narrative` (3–6 paragraphs), `suggested_focus_next_month` (3–5) |
| `notes[]` entries about skipped sections, blank rows and approximations (the skill appends these; the model may add its own) | additional `notes[]` entries the model wants to record |

The model returns the full `MonthlySynthesisSchema` object, pre-computed fields copied through verbatim, so a single JSON parse yields the brief. Fields that the skill sets (`generated_at`, `id` on watchlist items) may be returned as `null` or omitted; the skill fills them.

## Measurements block shape (`{{measurements_json}}`)

```json
{
  "month": "2026-05",
  "month_start": "2026-05-01",
  "month_end": "2026-05-31",
  "partial": false,
  "weeks_covered": ["2026-W18", "2026-W19", "2026-W20", "2026-W21", "2026-W22"],
  "weeks_missing": [],
  "sources": {
    "previous_monthly": "monthly/2026-04.json",
    "themes_current": "longitudinal/themes/2026-06-01.json",
    "themes_previous": "longitudinal/themes/2026-05-09.json",
    "themes_current_stale": false,
    "ledgers": { "decisions": true, "commitments": true, "people": true, "verdicts": true }
  },
  "pages_total": 47,
  "pages_by_project": { "aimqc": 18, "project-state": 11, "tulevik": 7, "(none)": 4 },
  "pages_by_weekday": { "Mon": 12, "Tue": 9, "Wed": 8, "Thu": 7, "Fri": 6, "Sat": 3, "Sun": 2 },
  "theme_arc": [
    {
      "theme": "sovereign-infrastructure",
      "start_weight": "secondary",
      "end_weight": "primary",
      "direction": "rising",
      "evidence_candidates": ["2026-05-04-k2p9", "2026-05-11-m7q1", "2026-05-12-a3c8", "2026-05-19-x9r2", "2026-05-20-b5t6", "2026-05-27-d1v4"]
    }
  ],
  "decisions_made": [
    { "decision": "Treat workstreams 1, 2 and 5 as quick wins", "date": "2026-05-02", "page_id": "2026-05-02-x7k2" }
  ],
  "commitments_aging": {
    "buckets": { "<7d": 3, "7-30d": 9, "30-90d": 14, ">90d": 5 },
    "oldest": [
      { "task": "Draft AIMQC Q1 feature roadmap for NRCAN review", "source_date": "2026-01-14", "state": "owner_confirmed" }
    ],
    "closed_this_month": 6,
    "dropped_this_month": 2
  },
  "people_movement": {
    "new": ["Priya Natarajan", "Tom Ekholm"],
    "steady": ["Alice Chen", "…"],
    "gone_quiet": ["Marcus Lind", "…"]
  },
  "forecast_scorecard": [
    {
      "prediction": "Pharmaliga onboarding starts before month end",
      "source": "monthly/2026-04.json#next_month_watchlist[0]",
      "id": "2026-04-w1",
      "verdict": { "outcome": "held", "evidence": "verdict:2026-04-w1 — kickoff call 2026-05-21" }
    },
    {
      "prediction": "'edge-inference' becomes a theme",
      "source": "longitudinal/themes/2026-05-09.json#emergent_topics[2]",
      "hint": "partial"
    }
  ],
  "notes": ["decisions.ndjson: 2 blank rows skipped"]
}
```

`forecast_scorecard[].verdict` is present only when a human verdict fixed the row; `hint` is present only on rows built from `emergent_topics`. Neither key appears in the output schema — the model folds them into `outcome` / `evidence`.

## System prompt

```
You are a monthly review analyst for a personal notes corpus. You receive
one month of weekly briefs, the themes snapshot at the start and end of the
month, ledgers of decisions, commitments, people and human verdicts, and a
block of PRE-COMPUTED MEASUREMENTS. The measurements are ground truth: you do
not change counts, buckets, weights, directions, people lists or scorecard
rows. You write the judgement around them.

## theme_arc
For each row (theme, start_weight, end_weight, direction already set): write
`note` — one or two sentences on why it moved or held, grounded in the
weeklies — and choose up to 5 `evidence_pages` from the candidates given.
You may not add a page id that is not in that row's evidence_candidates. If
the candidates are empty, evidence_pages is empty and the note says what the
weeklies show instead.

## decisions_made
For each candidate row: set `revisited` true if a later weekly or daily in the
month reopens, reverses or re-decides it; `revisit_note` says where (the ISO
week or page id). Otherwise false and an empty note. Do not add, remove or
reword decisions.

## forecast_scorecard
For each row without a human verdict: set `outcome` to held | partial | missed
| unknown and `evidence` to the weekly or page that shows it. Rows with a hint
default to the hint; override only with evidence. Rows with a human verdict
are fixed — copy them through. `unknown` means the notebook cannot decide it;
it is not a polite `missed`.

## next_month_watchlist
3 to 5 predictions about next month. Each must be falsifiable:
- prediction: a statement about next month that can turn out false
- signal_to_watch: the observable that decides it (pages, a ledger state, a
  theme weight)
- falsified_if: what next month's data looks like if you are wrong
Reject your own prediction if `falsified_if` cannot be checked from the facility
(pages, dailies, weeklies, the ledgers, the next themes snapshot). "The team
stays motivated" is not checkable; "at least three pages attribute to aimqc
in each of the first two weeks" is. Leave `id` null; the skill mints it.

## narrative
3 to 6 paragraphs. Open with the month's shape (pages, cadence, where the
pages went). Then what the arc says, what was decided and what aged, who
appeared and disappeared, and how last month's forecasts fared. Close with
what the watchlist is betting on. Name page-ids or weeks when you make a
claim. If weeks are missing, say which, and do not fill them from memory.

## suggested_focus_next_month
3 to 5 items, each tied to an open commitment, an unresolved question, a
rising theme, or a missed forecast. Each item names its source in
parentheses — a task from commitments_aging.oldest, a theme from theme_arc,
a scorecard row, or an ISO week.

## Grounding
- Every page id you write (theme_arc evidence, revisit notes, narrative,
  focus items) must be one you were given: an evidence candidate, a
  decisions_made page_id, or a page id that appears in a weekly. Never
  construct one.
- Every ISO week you cite must be in weeks_covered.
- Every person you name must appear in people_movement or in a weekly.
- When a ledger is marked absent in sources.ledgers, its section is empty;
  do not infer its contents from the weeklies.

Return ONLY valid JSON matching MonthlySynthesisSchema. Leave every
pre-computed field exactly as given.
```

## User turn

```
Write the month in review for {{month_label}} ({{month_start}} → {{month_end}}).
{{#if partial}}This is a PARTIAL month: the data runs only through {{month_end}}. Say so in the narrative's first sentence.{{/if}}
{{#if weeks_missing}}Overlapping weeks with no weekly brief: {{weeks_missing}}. Treat them as silence, not as empty weeks.{{/if}}

## Pre-computed measurements (ground truth — copy through unchanged)
{{measurements_json}}

## Weekly briefs for the month, oldest first
{{weeklies_json}}

## Previous month's brief ({{previous_month}})                   (conditional)
Its narrative is context; its next_month_watchlist is what the scorecard rows
with a monthly/ source were built from.
{{previous_monthly_json}}

## Themes snapshot at the start of the month ({{themes_previous_path}})   (conditional)
{{themes_previous_json}}

## Themes snapshot at the end of the month ({{themes_current_path}})      (conditional)
{{themes_current_json}}

## Human verdicts that touched this month                        (conditional)
Forecast verdicts are already folded into the scorecard rows above; they are
repeated here so you can cite the note. Commitment verdicts explain the
closed / dropped counts.
{{verdicts_json}}

Produce the complete MonthlySynthesisSchema object. Set month to "{{month}}" and
partial to {{partial}}. Copy weeks_covered, weeks_missing, sources, pages_total,
pages_by_project, pages_by_weekday, commitments_aging and people_movement exactly
as given. For theme_arc keep theme, start_weight, end_weight and direction as
given and add note and evidence_pages. For decisions_made keep decision, date
and page_id and add revisited and revisit_note. For forecast_scorecard keep
prediction and source, set outcome and evidence (fixed rows copied through).
Then write next_month_watchlist, narrative, suggested_focus_next_month and
notes.
```

Conditional blocks whose input is null are omitted entirely; the measurements block's `sources` already records their absence, and the narrative is expected to mention it (the only-one-snapshot and no-previous-monthly cases in the SKILL.md failure table).

## Expected response shape (`MonthlySynthesisSchema`)

```json
{
  "schema_version": "0.1.0",
  "month": "2026-05",
  "generated_at": null,
  "partial": false,
  "weeks_covered": ["2026-W18", "2026-W19", "2026-W20", "2026-W21", "2026-W22"],
  "weeks_missing": [],
  "sources": {
    "previous_monthly": "monthly/2026-04.json",
    "themes_current": "longitudinal/themes/2026-06-01.json",
    "themes_previous": "longitudinal/themes/2026-05-09.json",
    "themes_current_stale": false,
    "ledgers": { "decisions": true, "commitments": true, "people": true, "verdicts": true }
  },
  "pages_total": 47,
  "pages_by_project": { "aimqc": 18, "project-state": 11, "tulevik": 7, "(none)": 4 },
  "pages_by_weekday": { "Mon": 12, "Tue": 9, "Wed": 8, "Thu": 7, "Fri": 6, "Sat": 3, "Sun": 2 },
  "theme_arc": [
    {
      "theme": "sovereign-infrastructure",
      "start_weight": "secondary",
      "end_weight": "primary",
      "direction": "rising",
      "evidence_pages": ["2026-05-04-k2p9", "2026-05-12-a3c8", "2026-05-27-d1v4"],
      "note": "Three of five weeklies name it primary; W20 ties it to the NRCAN demo scope."
    }
  ],
  "decisions_made": [
    {
      "decision": "Treat workstreams 1, 2 and 5 as quick wins",
      "date": "2026-05-02",
      "page_id": "2026-05-02-x7k2",
      "revisited": true,
      "revisit_note": "2026-W20 reopens workstream 5 as blocked on data access."
    }
  ],
  "commitments_aging": {
    "buckets": { "<7d": 3, "7-30d": 9, "30-90d": 14, ">90d": 5 },
    "oldest": [
      { "task": "Draft AIMQC Q1 feature roadmap for NRCAN review", "source_date": "2026-01-14", "state": "owner_confirmed" }
    ],
    "closed_this_month": 6,
    "dropped_this_month": 2
  },
  "people_movement": {
    "new": ["Priya Natarajan", "Tom Ekholm"],
    "steady": ["Alice Chen"],
    "gone_quiet": ["Marcus Lind"]
  },
  "forecast_scorecard": [
    {
      "prediction": "Pharmaliga onboarding starts before month end",
      "source": "monthly/2026-04.json#next_month_watchlist[0]",
      "outcome": "held",
      "evidence": "verdict:2026-04-w1 — kickoff call 2026-05-21"
    },
    {
      "prediction": "'edge-inference' becomes a theme",
      "source": "longitudinal/themes/2026-05-09.json#emergent_topics[2]",
      "outcome": "partial",
      "evidence": "Still listed under emergent_topics in the 2026-06-01 snapshot; 4 pages, needs 5."
    }
  ],
  "next_month_watchlist": [
    {
      "id": null,
      "prediction": "The NRCAN demo gets a dated slot in June",
      "signal_to_watch": "A page in June naming a demo date, or the commitment 'Schedule NRCAN demo' reaching done",
      "falsified_if": "No June page names a date and the commitment is still open on 2026-06-30"
    }
  ],
  "narrative": "May put 47 pages on the notebook …",
  "suggested_focus_next_month": [
    "Close or drop 'Draft AIMQC Q1 feature roadmap for NRCAN review' — 137 days open (commitments_aging.oldest[0])"
  ],
  "notes": ["decisions.ndjson: 2 blank rows skipped"]
}
```

`generated_at` and each watchlist `id` are set by the skill after validation. `id` is `{{month}}-w{n}`, `n` the 1-based position in `next_month_watchlist` — the id `notella-review` later uses as `target_id` for forecast verdicts.

## Validation the prompt is written to pass

Mirrors Step 6 of the SKILL.md; listed here so a prompt edit can be checked against it.

1. Every pre-computed field equals the Step 3 value (the skill overwrites, then compares).
2. Every `theme_arc[].evidence_pages` id is in that row's `evidence_candidates`; every `decisions_made[].page_id` exists (`notella-state get-page` returns a record).
3. `next_month_watchlist` has 3–5 items, each with non-empty `prediction`, `signal_to_watch` and `falsified_if`.
4. `forecast_scorecard` rows that carried a `verdict` in the measurements block come back with exactly that `outcome` and `evidence`.
5. `narrative` has 3–6 paragraphs (split on blank lines); `suggested_focus_next_month` has 3–5 entries.

A failure refuses the write and allows one retry with the violations appended to the user turn under a `## Violations in your previous answer` heading.
