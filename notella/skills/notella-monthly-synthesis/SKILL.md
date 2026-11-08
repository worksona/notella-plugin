---
name: notella-monthly-synthesis
description: "Produce a month-in-review brief from a month of weekly syntheses, two themes snapshots and the longitudinal ledgers — theme arc, decisions made, commitments aging, people movement, a scorecard of last month's forecasts, and a falsifiable watchlist for next month. Use whenever the user says 'monthly synthesis', 'monthly brief', 'what happened in October', 'month in review', 'monthly themes', 'synthesize last month', or any request to consolidate a calendar month. Reads through `notella-state`; writes `monthly/{YYYY-MM}.{json,md}`. Emits `synthesis.monthly` event."
---

# notella-monthly-synthesis — the month in review

Sits between the weekly brief and the longitudinal themes. Reads the month's weeklies, the themes snapshot at the start and end of the month, and the ledgers (`decisions`, `commitments`, `people`, `verdicts`) and produces a brief whose job is to **measure** — what rose and fell, what aged, who went quiet, which of last month's predictions held — and then to **predict** in a way that next month can score.

## Purpose

Weekly briefs recap. Themes describe the whole corpus. Neither answers the month-scale questions: did the thing I said was emerging actually become a theme? How old are my open commitments? Which people dropped out of my notes? Was my focus for the month where my pages were?

The monthly brief is also where the facility learns. Every monthly ends with a `next_month_watchlist` of falsifiable predictions; the next monthly scores them in `forecast_scorecard`, alongside the previous themes snapshot's `emergent_topics`. Over a few months this produces calibration data about which signals mattered.

## Inputs and outputs

**Input:** Flags:
- `--month YYYY-MM` — the month to synthesize. **Default `--month last`**: the most recent month that has closed (in `identity.timezone`).
- `--partial` — allow a month that has not closed yet (covers the 1st through today).
- `--reprocess` — overwrite an existing brief; emits a `correction` event.

Reads, all through `notella-state`:

| Source | Operation | Used for |
| ------ | --------- | -------- |
| Every `weekly/*.json` whose ISO week overlaps the month (any day Mon–Sun inside the month) | `list-weeklies`, `get-weekly` | narrative, decisions revisit check, forecast evidence |
| The previous monthly (`monthly/{YYYY-MM minus 1}.json`) | `get-monthly` — may be null | `forecast_scorecard` rows from its `next_month_watchlist` |
| The current themes snapshot | `get-themes-snapshot latest` | `theme_arc` end weights |
| The previous themes snapshot | `get-themes-snapshot previous` | `theme_arc` start weights; `forecast_scorecard` rows from its `emergent_topics` |
| `longitudinal/decisions.ndjson` | `read-ledger decisions` | `decisions_made` |
| `longitudinal/commitments.ndjson` | `read-ledger commitments` | `commitments_aging` |
| `longitudinal/people.ndjson` | `read-ledger people` | `people_movement` |
| `longitudinal/verdicts.ndjson` | `list-verdicts --until={month_end}` | closed/dropped commitments, human verdicts on forecasts |
| Pages with authoritative date in the month | `list-pages --since --until` | `pages_total`, `pages_by_project`, `pages_by_weekday` |

The ledgers are contracts owned elsewhere and are only read here: `decisions.ndjson` and `commitments.ndjson` are built by the desktop aggregator (orchestrator Step 10, ledgers), `people.ndjson` by the same aggregator, and `verdicts.ndjson` is appended by `notella-review` (rows `{ts, target_kind, target_id, target_text, verdict, note, source_ref}`).

**Output:**
- `monthly/{YYYY-MM}.json` — monthly synthesis schema
- `monthly/{YYYY-MM}.md` — narrative rendering
- `synthesis.monthly` event
- `state.json:last_synthesis_at.monthly` updated

## How a run executes

### Step 1 — Resolve the month and gate

```
month = --month, or the most recent closed month
month_start, month_end = first and last calendar day
today = now in identity.timezone

if today <= month_end and not --partial: abort {status: "month-not-closed", month}
if monthly/{month}.json exists and not --reprocess: return {status: "exists", path}

notella-state get-manifest → cost-controls.yaml:model_defaults.monthly_synthesis (fallback: model_defaults.themes), identity.timezone
```

Where the facility keeps model defaults in `cost-controls.yaml` rather than the manifest, read `model_defaults.monthly_synthesis` there, with the same fallback to `themes`.

### Step 2 — Read inputs

```
weeks_overlapping = ISO weeks with any day in [month_start, month_end]
for w in weeks_overlapping: notella-state get-weekly {w}     # null → weeks_missing
previous_monthly   = notella-state get-monthly {month - 1}      # may be null
themes_current     = notella-state get-themes-snapshot latest   # may be null
themes_previous    = notella-state get-themes-snapshot previous # may be null
ledgers            = read-ledger decisions | commitments | people; list-verdicts --until={month_end}  # each may be absent
pages              = notella-state list-pages --since={month_start} --until={month_end}
```

If **zero** weeklies exist for the month, abort with `{status: "no-weeklies-for-month"}` — run `notella-weekly-synthesis` for the missing weeks first. Some missing is fine; they are listed in `weeks_missing`.

Record which sources were present in `sources` so the brief says what it was built from.

### Step 3 — Pre-aggregate deterministically (no model)

Everything in this step is a function of the data. The model never changes these values.

**Counts**
- `pages_total` — pages whose authoritative date is in the month.
- `pages_by_project` — `{slug: n}` from `meta.yaml:project_attributions` (a page with two attributions counts for both; unattributed pages count under `"(none)"`).
- `pages_by_weekday` — `{Mon..Sun: n}`.

**Theme arc** — for every theme name in `themes_previous.themes ∪ themes_current.themes`:
- `start_weight` = weight in `themes_previous` (null if absent), `end_weight` = weight in `themes_current` (null if absent).
- `direction` by rank `primary=3 > secondary=2 > emerging=1 > fading=0`: `new` when start is null, `gone` when end is null, `rising` when end rank > start rank, `fell` when lower, `held` when equal.
- `evidence_candidates` = the theme's `evidence_pages` from both snapshots whose authoritative date falls in the month, plus pages in the month whose `metadata.json:themes` names the theme. The model picks ≤ 5 of these for `evidence_pages`; it may not add others.
- If `themes_current.generated_at` is earlier than `month_end`, the arc is measured against a stale snapshot: set `sources.themes_current_stale: true` and say so in the rendered table caption.

**Decisions** — `decisions.ndjson` rows with `date` in the month and a non-empty `description` → candidate rows `{decision, date, page_id}`. Blank rows are skipped and counted in `notes`.

**Commitments aging** — a row's text is `task` (older rows: `description`) and its id is `task_id` (older rows: none; compute `hash(task)` as `notella-review` defines it). A row is open when `state ∈ {proposed, owner_confirmed, in_progress}`, `date ≤ month_end`, and no verdict row with `target_kind: commitment`, that `target_id`, and `verdict ∈ {done, drop}` exists with `ts ≤ month_end` (human verdicts close items the aggregator has not seen close). Age = `month_end − date` in days.
- `buckets`: `{"<7d", "7-30d", "30-90d", ">90d"}` → counts.
- `oldest`: the 5 oldest open rows as `{task, source_date: date, state}`.
- `closed_this_month`: verdict rows with `target_kind: commitment`, `verdict: done`, `ts` in the month; `dropped_this_month`: same with `verdict: drop`. When `verdicts.ndjson` is absent, fall back to ledger rows with `state ∈ {done}` / `{abandoned}` and `date` in the month, and add a note that the counts are approximate (the ledger does not record when a state changed).

**People movement** — from `people.ndjson` `mentions_by_month`:
- `new`: `first_seen` in the month.
- `steady`: mentions in this month > 0 and in at least one earlier month.
- `gone_quiet`: zero mentions this month, mentions > 0 in ≥ 2 earlier months.
Each list holds `canonical` names, sorted by `mentions_total` descending.

**Forecast scorecard rows** — one row per:
- item `i` in `previous_monthly.next_month_watchlist` → `{prediction: item.prediction, source: "monthly/{YYYY-MM}.json#next_month_watchlist[{i}]"}`
- entry `i` in `themes_previous.emergent_topics` → `{prediction: "'{name}' becomes a theme", source: "longitudinal/themes/{date}.json#emergent_topics[{i}]"}`, with a deterministic hint: `held` if the name is in `themes_current.themes`, `partial` if still in `themes_current.emergent_topics`, `missed` if in neither.
- Human verdicts win: a verdict row with `target_kind: forecast` matches a watchlist row when its `source_ref` equals the row's `source`, or its `target_id` equals the row's `id` (`YYYY-MM-w{n}`, what `notella-review` writes for forecasts), or its `target_id` equals `hash(prediction)` (FNV-1a 32-bit over the normalised text, exactly as `notella-review` computes it). Latest row per `target_id` wins and fixes the outcome — `done → held`, `wrong → missed`, `carry → unknown` (still open), `drop → unknown` with evidence "dropped at review".

### Step 4 — Build the prompt

System prompt:

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

## decisions_made
For each candidate row: set `revisited` true if a later weekly or daily in the
month reopens, reverses or re-decides it; `revisit_note` says where. Otherwise
false and an empty note.

## forecast_scorecard
For each row without a human verdict: set `outcome` to held | partial | missed
| unknown and `evidence` to the weekly or page that shows it. Rows with a hint
default to the hint; override only with evidence. Rows with a human verdict
are fixed — copy them through.

## next_month_watchlist
3 to 5 predictions about next month. Each must be falsifiable:
- prediction: a statement about next month that can turn out false
- signal_to_watch: the observable that decides it (pages, a ledger state, a
  theme weight)
- falsified_if: what next month's data looks like if you are wrong
Reject your own prediction if `falsified_if` cannot be checked from the facility.

## narrative
3 to 6 paragraphs. Open with the month's shape (pages, cadence, where the
pages went). Then what the arc says, what was decided and what aged, who
appeared and disappeared, and how last month's forecasts fared. Close with
what the watchlist is betting on. Name page-ids or weeks when you make a
claim.

## suggested_focus_next_month
3 to 5 items, each tied to an open commitment, an unresolved question, a
rising theme, or a missed forecast. Each item names its source.

Return ONLY valid JSON matching MonthlySynthesisSchema. Leave every
pre-computed field exactly as given.
```

User prompt: the measurements block (Step 3) as JSON, the weeklies as `{iso_week, weekly_json}` (full), the previous monthly's `narrative` and `next_month_watchlist`, the two snapshots' `themes` / `emergent_topics` (names, weights, trajectories, first/last seen), and the verdict rows that touched this month.

### Step 5 — Call the model

Runs on `model_defaults.monthly_synthesis` (currently `opus`), falling back to `model_defaults.themes`; the orchestrator dispatches a subagent with that model. Use prompt caching on the system block. Cost ≈ one themes refresh (~$1.80 at current estimates); the monthly scheduled task runs this once, after the themes refresh.

### Step 6 — Validate

```yaml
schema_version: "0.1.0"
month: "YYYY-MM"
generated_at: ISO-8601
partial: bool                                  # true only with --partial
weeks_covered: ["YYYY-Www"]                    # weeklies read
weeks_missing: ["YYYY-Www"]                    # overlapping weeks with no weekly
sources:
  previous_monthly: "monthly/YYYY-MM.json" | null
  themes_current: "longitudinal/themes/YYYY-MM-DD.json" | null
  themes_previous: "longitudinal/themes/YYYY-MM-DD.json" | null
  themes_current_stale: bool
  ledgers: { decisions: bool, commitments: bool, people: bool, verdicts: bool }
pages_total: int
pages_by_project: { slug: int }
pages_by_weekday: { Mon: int, Tue: int, Wed: int, Thu: int, Fri: int, Sat: int, Sun: int }
theme_arc:
  - theme: string
    start_weight: primary | secondary | emerging | fading | null
    end_weight: primary | secondary | emerging | fading | null
    direction: rising | held | fell | new | gone
    evidence_pages: [page-id]                  # ≤ 5, subset of candidates
    note: string
decisions_made:
  - decision: string
    date: "YYYY-MM-DD"
    page_id: string
    revisited: bool
    revisit_note: string
commitments_aging:
  buckets: { "<7d": int, "7-30d": int, "30-90d": int, ">90d": int }
  oldest:                                       # ≤ 5
    - { task: string, source_date: "YYYY-MM-DD", state: proposed | owner_confirmed | in_progress }
  closed_this_month: int
  dropped_this_month: int
people_movement:
  new: [string]
  steady: [string]
  gone_quiet: [string]
forecast_scorecard:
  - prediction: string
    source: "monthly/YYYY-MM.json#next_month_watchlist[i]" | "longitudinal/themes/YYYY-MM-DD.json#emergent_topics[i]"
    outcome: held | partial | missed | unknown
    evidence: string
next_month_watchlist:                           # 3–5
  - id: "YYYY-MM-w1"                            # this month + ordinal, for rendering; verdicts key on hash(prediction) + source_ref
    prediction: string
    signal_to_watch: string
    falsified_if: string
narrative: string                               # 3–6 paragraphs
suggested_focus_next_month: [string]            # 3–5
notes: [string]                                 # skipped sections, blank rows, approximations
```

Checks; any failure refuses the write and allows one retry:

1. Every pre-computed field equals the Step 3 value (the skill overwrites them regardless, then compares what the model returned to catch a model that reasoned from altered numbers).
2. Every `theme_arc[].evidence_pages` id is in that row's candidates; every `decisions_made[].page_id` exists.
3. `next_month_watchlist` has 3–5 items, each with non-empty `falsified_if`.
4. `forecast_scorecard` rows with a human verdict carry the verdict's outcome.

### Step 7 — Render the markdown

```
# Month in review — {Month YYYY}
_{pages_total} pages · {weeks_covered.length} weeks · generated {generated_at}{ · partial}_

## Narrative
## Theme arc                      ← table: Theme | Start | End | Direction | Evidence | Note   (caption notes a stale snapshot)
## Forecast scorecard             ← table: Prediction | Source | Outcome | Evidence
## Decisions                      ← one line each: date — decision (page-id); "revisited: note" when true
## Commitments aging              ← bucket line; oldest table: Task | Since | State; closed / dropped line
## People movement                ← New / Steady / Gone quiet
## Watchlist for next month       ← numbered, each with id, signal to watch, falsified if
## Suggested focus
```

Each decision and evidence page-id links to `pages/{page-id}/`; each week in the narrative links to `weekly/{iso-week}.md`. Sections whose source ledger was absent render "Not available — {ledger} missing." from `notes`.

### Step 8 — Write the synthesis

```
notella-state log-synthesis {kind: synthesis.monthly, month: {YYYY-MM}, json, md}
```

Writes `monthly/{YYYY-MM}.{json,md}`, updates `state.json:last_synthesis_at.monthly`, emits `synthesis.monthly` with evidence `{month, weeks_covered, weeks_missing, pages_total, theme_arc_count, decisions_count, open_commitments, scorecard: {held, partial, missed, unknown}, watchlist_count, partial, model}`.

## Idempotency

- Re-running for a month whose `monthly/{YYYY-MM}.json` exists: no-op, `{status: "exists"}`.
- `--reprocess`: overwrite both files and emit a `correction` event with `evidence.correction_type: "reprocess"`, `evidence.target: "monthly/{YYYY-MM}"`.
- A `--partial` brief is a real file; when the month closes, the orchestrator's next monthly run sees it exists and does nothing — rerun with `--reprocess` to replace the partial with the full month. The `partial` flag in the json and the md subtitle make the difference visible.

## Cadence

Orchestrator step after the weekly step, on the first run after a month closes; the scheduled monthly task runs `/notella-themes --themes-now` and then `/notella-monthly-synthesis --month last` on the 1st, so both snapshots the arc needs exist. Any time on demand with `--month`.

## Failure modes

| Failure | Behavior |
| --- | --- |
| Month has zero weeklies | Abort `{status: "no-weeklies-for-month"}`; name the overlapping weeks so `notella-weekly-synthesis` can be run first. |
| Some overlapping weeks have no weekly | Proceed; list them in `weeks_missing`; narrative says so. |
| Previous monthly absent | Proceed; `forecast_scorecard` rows come only from the previous themes snapshot's `emergent_topics`; `sources.previous_monthly: null`. |
| No themes snapshots at all | Proceed; `theme_arc` is empty with a note; scorecard has no themes rows. |
| Only one themes snapshot | Every arc row is `direction: new`; note that the arc has no start. |
| Current snapshot older than month end | Proceed; `sources.themes_current_stale: true`; caption in the md. Suggest `notella-themes --themes-now` then `--reprocess`. |
| A ledger file missing | Skip that section (empty structure), add a note, render "Not available"; do not fail the run. |
| Ledger rows blank or unparseable | Skip the row, count in `notes`. |
| Month not yet closed | Refuse `{status: "month-not-closed"}` unless `--partial`. |
| Model alters a pre-computed field | Overwrite with the Step 3 value; if the narrative contradicts the measurements, one retry. |
| Watchlist not falsifiable (empty `falsified_if`) | Refuse; one retry asking for checkable predictions. |

## What this skill does NOT do

- Does not read individual pages' content — only weeklies, snapshots, ledgers, and page counts. The granularity below the week is already in the weeklies.
- Does not modify weeklies, snapshots or ledgers. It reads `verdicts.ndjson`; it never appends to it (that is `notella-review`).
- Does not refresh themes. If the snapshot is stale, it says so and leaves the refresh to `notella-themes`.
- Does not score its own watchlist. That happens next month, in the next brief, with the human verdicts from `notella-review` taking precedence. `notella-review` shows the watchlist once the forecast month has closed, so the verdicts usually exist before the next monthly runs.
- Does not run on an unclosed month without `--partial`.

## Examples

### "Synthesize last month" (run 2026-06-01)

```
Month: 2026-05 (closed)
Weeklies: 2026-W18, W19, W20, W21, W22 (5 of 5 overlapping)
Previous monthly: monthly/2026-04.json (4 watchlist items)
Themes: current 2026-06-01, previous 2026-05-09
Ledgers: decisions ✓ commitments ✓ people ✓ verdicts ✓
Pages: 47 (aimqc 18, project-state 11, tulevik 7, ...) — Mon 12, Tue 9, Wed 8, Thu 7, Fri 6, Sat 3, Sun 2
Theme arc: 12 rows — 2 rising, 7 held, 1 fell, 2 new, 0 gone
Decisions: 9 candidates
Commitments: 31 open — <7d 3, 7-30d 9, 30-90d 14, >90d 5 — closed 6, dropped 2
People: new 2, steady 9, gone quiet 3
Scorecard rows: 4 from monthly/2026-04.json, 4 from longitudinal/themes/2026-05-09.json (2 with human verdicts)
Synthesizing with claude-opus-5-5...
Validated ✓
Wrote monthly/2026-05.json, monthly/2026-05.md
synthesis.monthly event emitted.
```

### "What happened in October?"

`--month 2026-10`. If October has not closed, refuses with `month-not-closed`; add `--partial` to get a brief through today.

### "Monthly brief for 2026-03 --reprocess"

Overwrites `monthly/2026-03.{json,md}`, emits `correction`. Use after a late weekly or a themes refresh changes the inputs.

## Reference files

- `references/monthly-prompt.md` — full prompt.
- `references/monthly-aggregation.md` — the deterministic rules: week overlap, authoritative date, arc direction ranks, aging buckets, people movement, scorecard sources and verdict precedence.
- `references/monthly-md-template.md` — markdown rendering.
