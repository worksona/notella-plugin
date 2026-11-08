---
name: notella-weekly-synthesis
description: "Produce a weekly synthesis report from a week of daily intelligence briefs — executive summary, key themes with their prior weight, themes dropped, projects progressed, people and relationships, ideas and insights, action items with how long they have been open, a scorecard of last week's suggested focus, a silence report, suggested focus for next week. Use whenever the user says 'weekly report for this week', 'synthesize last week', 'weekly intelligence', 'week-on-week summary', 'what happened this past week', 'did I do what I said I would last week', or any request to consolidate seven days of daily briefs. Reads the previous weekly, the current themes and any review verdicts through `notella-state`; writes `weekly/{iso-week}.{json,md}`. Emits `synthesis.weekly` event."
---

# notella-weekly-synthesis — the weekly intelligence brief

Reads a week's worth of daily syntheses (already produced) and the weekly brief that came before, and integrates them into a weekly brief. Higher-altitude than daily — themes evolved, projects progressed, people who showed up most, ideas worth highlighting, focus for next week — and, because it remembers last week, it can say what persisted, what vanished, and whether last week's suggestions happened.

## Purpose

The week is the natural granularity for review and planning: long enough that themes emerge, short enough that recall is good. Daily briefs are operational; weekly briefs are reflective.

A weekly without memory re-detects the same themes every Monday and never learns whether its own advice was taken. With memory, each theme carries its prior weight and age, each open action carries the week it first appeared, and last week's `suggested_focus` is scored against this week's evidence. That scorecard is the facility's only measure of whether its forecasts mean anything.

## Inputs and outputs

**Input:** An ISO week (e.g. `2026-W18`) or a date that resolves to one. Reads every `daily/YYYY-MM-DD.json` whose date falls in that week.

**Context inputs** (all optional):

| Input | Source | Role |
| --- | --- | --- |
| Previous weekly | `weekly/{iso-week − 1}.json` (may be null; if that week has no file, the most recent earlier weekly is used and the gap is noted) | `prior_weight`, `weeks_active`, `themes_dropped`, `focus_scorecard`, `first_seen_week` |
| Current themes | latest `longitudinal/themes.json` | Vocabulary: the model prefers an existing theme name over coining a near-duplicate |
| Latest monthly | latest `monthly/{YYYY-MM}.json`, if present | Read-only context: `next_month_watchlist` items the week speaks to |
| Review verdicts | `longitudinal/verdicts.ndjson` rows with `ts` inside the week (Mon 00:00 → Sun 23:59:59) | `focus` verdicts settle scorecard rows; `commitment`/`question` verdicts close open actions |
| Day coverage | `notella-state list-dailies` restricted to the previous 4 ISO weeks | Baseline for the silence report |

**Output:**
- `weekly/{iso-week}.json` — weekly synthesis schema (every pre-existing field kept; additions below)
- `weekly/{iso-week}.md` — narrative rendering
- `synthesis.weekly` event with `evidence: {days_with_briefs, themes_count, themes_dropped_count, focus_happened, focus_partial, focus_no_evidence, carried_actions_count}`
- `state.json:last_synthesis_at.weekly` updated

## How a run executes

### Step 1 — Resolve the week & read daily briefs

```
iso_week = isoformat(date)              # e.g. "2026-W18"
dates_in_week = [Mon..Sun for that week]

notella-state get-manifest → manifest.model_defaults.weekly_synthesis
for d in dates_in_week:
  notella-state get-daily {d}            # may return null
```

If the week has zero daily briefs, abort with `{status: "no-dailies-for-week"}`. If the week has fewer than expected (e.g. 4 of 7), proceed with what's available; surface in the brief.

### Step 2 — Read the predecessor and context

```
prev_week = iso_week − 1
previous  = notella-state get-weekly {prev_week}
           # null → fall back to the latest week in list-weeklies before iso_week; record which
themes    = notella-state get-longitudinal themes
monthly   = notella-state get-monthly {last of list-monthlies}         # null if none
verdicts  = notella-state read-ledger {file: verdicts, since: {Mon}T00:00:00, until: {Sun}T23:59:59}
            # {status: "absent"} → []
coverage  = notella-state list-dailies filtered to the 28 days before Mon
```

Compute deterministically, before the model is called:

- **Scorecard skeleton** — one row per `previous.suggested_focus[]`, outcome unset. Apply `focus` verdicts: `done` → `happened`, `drop` or `wrong` → `no_evidence` with the note, `carry` → `no_evidence` and flag the item for re-suggestion. Rows without a verdict are left for the model.
- **Action pool** — `previous.action_items_open[]` minus items with a `commitment` or `question` verdict of `done`/`drop`/`wrong` in the week (those appear one final time with status `resolved`/`dropped`). Each pool item keeps its `first_seen_week` (the previous weekly's value, or `prev_week` for legacy shapes).
- **Silence report** — `days_without_pages` = dates in the week with no `daily/{d}.json`. For each weekday, count how many of the previous 4 weeks had a brief on that weekday; a silent weekday with ≥ 3/4 prior coverage is *unusual*, one with ≤ 1/4 is *normal*. Draft `weekday_pattern_note` from these counts; the model may reword it but not change the numbers.
- **Theme vocabulary** — names and weights of `previous.key_themes[]` plus names of `themes.themes[]` with weight primary or secondary.

### Step 3 — Build the prompt

Adapted from notella-the-app's `buildWeeklyReportPrompt()` from `src/lib/prompts/report.ts`, passing each daily as `{date, daily_intelligence_json}` rather than a free-text summary. The model gets structured input it can integrate. The previous weekly, the scorecard skeleton, the action pool, the theme vocabulary and the silence numbers follow as a **memory block**.

System prompt (paraphrased):

```
You are a weekly synthesis analyst for a personal knowledge management system.
You receive structured daily intelligence reports for one week, the previous
week's brief, and the current longitudinal themes, and produce a coherent
weekly brief that continues the previous one.

Your output covers:

## executive_summary
3-5 sentences capturing the shape of the week. Say explicitly what changed
relative to last week.

## key_themes
Themes that recurred or evolved. For each:
- theme: short label. If the theme is the same as one in last week's brief or
  in the longitudinal themes, REUSE THAT LABEL VERBATIM. Do not coin a
  near-synonym.
- evolution: how it shifted across the week
- weight: primary | secondary | minor
- prior_weight: the weight this theme had in last week's brief, or null if it
  did not appear there
- weeks_active: consecutive weeks this theme has appeared, counting this one
  (last week's weeks_active + 1, or 1 if new)

## themes_dropped
Every theme that was in last week's key_themes and is absent from this week's.
For each: theme (verbatim label), last_weight, reason_guess — one line on why
it may have gone quiet (resolved, superseded, no pages on the relevant days,
project paused). A guess is fine; silence is not.

## projects_progressed
Per project that saw meaningful activity:
- project: slug or name
- progress: what changed
- pages_count: how many pages touched it

## people_and_relationships
People who appeared multiple times; new entrants; relationships discussed.

## ideas_and_insights
Highlight 3-7 ideas worth marking (high value_hypotheses confidence, recurring
across days, or explicitly starred in source pages).

## action_items_open
The open action items still standing at week-end. For each: item, urgency,
source_date, status (new | carried | resolved | dropped), first_seen_week.
An item from the action pool that is still open is carried, with the pool's
wording and first_seen_week. An item is resolved only when a daily brief's
resolved_today names it or a verdict says done; it then appears one final time
with status=resolved. New items get first_seen_week = this week.

## focus_scorecard
One row per item of last week's suggested_focus. outcome: happened | partial |
no_evidence. evidence_date is the date of the daily brief that shows it;
evidence is a short quote from that brief. no_evidence means exactly that —
the notebook does not show it — not that it did not happen. Rows the memory
block has already settled from a verdict are copied as given.

## silence_report
days_without_pages (given) and weekday_pattern_note: whether this week's
silent days fit the previous four weeks' pattern. Use the counts given.

## suggested_focus
3-5 suggestions for the upcoming week, grounded in unresolved questions,
blocked work, carried actions, or emerging themes. Phrase each so that next
week's brief can score it from the notebook alone: name the thing that should
appear on a page ("Write the Sprint 3 scope for AIMQC with dates"), not an
attitude ("Stay focused on AIMQC"). Re-suggest any focus item the verdicts
marked carry.

## momentum_summary
Overall: accelerating, stable, or decelerating? What's the strongest signal?
Compare to last week's momentum_summary in one clause.

Return ONLY valid JSON matching WeeklySynthesisSchema.
```

### Step 4 — Call the model

Default: `claude-opus-4-6`. **Use prompt caching** on the system prompt block (`cache_control: { type: "ephemeral" }`) — when running weekly back-syntheses for multiple weeks in one orchestrator pass, the system prompt is reused. ~80-90% discount on cached input tokens after the first call. The memory block is in the user turn and changes every week.

### Step 5 — Validate

```yaml
iso_week: "YYYY-Www"
dates_covered: [date]
generated_at: ISO-8601
days_with_briefs: int
days_missing_briefs: int
previous_week: "YYYY-Www" | null                    # NEW — the predecessor actually used
executive_summary: string
key_themes:
  - theme, evolution, weight
    prior_weight: primary | secondary | minor | null  # NEW
    weeks_active: int >= 1                            # NEW
themes_dropped:                                       # NEW
  - theme, last_weight, reason_guess
projects_progressed:
  - project, progress, pages_count
people_and_relationships:
  - person, mentions_count, summary
ideas_and_insights: [string]
action_items_open:
  - item, urgency, source_date
    status: new | carried | resolved | dropped        # NEW
    first_seen_week: "YYYY-Www"                       # NEW
carried_actions:                                      # NEW — derived, not model-authored
  - item, urgency, first_seen_week, weeks_open
focus_scorecard:                                      # NEW
  - focus: string                       # previous.suggested_focus[i], verbatim
    outcome: happened | partial | no_evidence
    evidence_date: "YYYY-MM-DD" | null  # null only when no_evidence
    evidence: string
silence_report:                                       # NEW
  days_without_pages: [date]
  weekday_pattern_note: string
suggested_focus: [string]                             # 3..5
momentum_summary: string
```

Derivations applied after the model returns:
- `carried_actions` = every `action_items_open[]` with status `carried` and `weeks_open = weeknum(iso_week) − weeknum(first_seen_week) + 1 >= 2`, sorted oldest first. Computed here, never asked of the model.

Sanity:
- Every `key_themes[].theme` with non-null `prior_weight` matches (verbatim, case-insensitive) a theme in `previous.key_themes`, and `prior_weight` equals that theme's weight; `weeks_active` equals its `weeks_active + 1` (or 2 if the previous lacks the field).
- Every `key_themes[].theme` with `prior_weight: null` has `weeks_active: 1` and is absent from `previous.key_themes`.
- `themes_dropped` contains exactly the themes in `previous.key_themes` whose labels are absent from `key_themes` — no more, no fewer.
- `focus_scorecard` has exactly `len(previous.suggested_focus)` rows, in order, `focus` verbatim; `evidence_date` is in `dates_covered` when outcome is not `no_evidence`.
- Every `action_items_open[]` with status `carried` matches an action-pool item and keeps its `first_seen_week`; `new` items have `first_seen_week == iso_week`.
- `suggested_focus` has 3 to 5 entries.
- `silence_report.days_without_pages` equals the computed list.
- When `previous` is null: `prior_weight` all null, `weeks_active` all 1, `themes_dropped` and `focus_scorecard` empty, every action `new`.

On a sanity failure, retry once with the violations named; refuse the write on a second failure.

### Step 6 — Render the markdown

Standard week brief format. Title `# Week of {iso-week} ({first-date} → {last-date})`, then coverage line, then sections in this order:

```markdown
## Executive Summary

## Focus scorecard                                   ← NEW (omitted when no predecessor)
| Last week's focus | Outcome | Evidence |
| --- | --- | --- |
| {focus} | happened / partial / no evidence | {evidence_date}: {evidence} |
{N of M happened}

## Key Themes
### {theme} `{weight}, was {prior_weight}` · {weeks_active} weeks     ← "new" when prior_weight is null
{evolution}
**Dropped since last week:** {theme} (was {last_weight}) — {reason_guess}   ← one line per themes_dropped

## Projects Progressed
## People & Relationships
## Ideas & Insights

## Action Items Open
{grouped by urgency; carried items end with "(since {first_seen_week})"; resolved/dropped items in a short closing list}

## Carried actions                                   ← NEW (omitted when empty)
{oldest first: "{item} — open {weeks_open} weeks (since {first_seen_week})"}

## Silence report                                    ← NEW
{days_without_pages as weekday + date, or "No silent days"}
{weekday_pattern_note}

## Suggested Focus
## Momentum
```

Each item in `action_items_open` links to its source daily (`daily/{date}.md`). Each scorecard row with an `evidence_date` links to that daily.

### Step 7 — Write the synthesis

```
notella-state log-synthesis {
  kind: synthesis.weekly, week: {iso-week}, json, md,
  evidence: {days_with_briefs, themes_count, themes_dropped_count,
             focus_happened, focus_partial, focus_no_evidence, carried_actions_count}
}
```

Updates `state.json:last_synthesis_at.weekly`.

## Idempotency

- Re-running for an existing week: no-op unless `--reprocess`.
- `--reprocess`: pass `reprocess: true` to `log-synthesis`, which overwrites and emits `correction`. Recomputes against the same predecessor (`iso_week − 1`); verdicts are re-read. Does not cascade: the following week keeps the `prior_weight`, `weeks_active` and `first_seen_week` it computed from the old version. Reprocess later weeks in order if the change matters.
- Back-syntheses (`--catch-up-weeks N`) must run oldest week first so each week finds its predecessor already written.

## Failure modes

| Failure                                                | Behavior |
| ------------------------------------------------------ | -------- |
| No dailies in the week                                 | Skip cleanly. Probably a week with no notebook activity. |
| Some days missing briefs                               | Proceed with what's available; surface the gaps in `days_missing_briefs` and `silence_report`. |
| Briefs exist but are sparse                            | Run anyway; the weekly may be terse; that's correct. |
| No previous weekly                                     | First weekly: `previous_week: null`, no scorecard, no dropped themes, every theme `weeks_active: 1`. |
| `iso_week − 1` has no file but an earlier week does    | Use the most recent earlier weekly as predecessor; set `previous_week` to it; note the gap in the executive summary. `weeks_active` still increments by 1 (consecutive *briefs*, not calendar weeks). |
| Previous weekly predates the new fields (legacy shape) | Treat its themes as `weeks_active: 1` and its actions as `first_seen_week: prev_week`. Legacy files are never rewritten. |
| Model coins a new label for a theme that is in the previous weekly | `themes_dropped` and `prior_weight` disagree; validation fails. Retry once, naming the suspected pair; then refuse. |
| Fewer than 3 or more than 5 `suggested_focus`          | Validation failure; retry once; then refuse. |
| Fewer than 4 prior weeks of coverage for the silence baseline | Use what exists; say "baseline: N weeks" in `weekday_pattern_note`. |
| `themes.json` or `verdicts.ndjson` absent              | Proceed without; not an error. |

## What this skill does NOT do

- Does not re-read individual pages — only consumes daily briefs. (The granularity below the day is already captured in the dailies.)
- Does not modify daily briefs or earlier weeklies.
- Does not write verdicts. A `no_evidence` scorecard row is a fact about the notebook, not a judgement; the person settles it in `notella-review`.
- Does not update `longitudinal/themes.json`. It reads the theme vocabulary; `notella-themes` owns the file.
- Does not run on partial weeks except when explicitly invoked mid-week (in which case the brief covers up to today and the scorecard is marked provisional).

## Examples

### "Weekly synthesis for 2026-W18"

```
Daily briefs found: 5 of 7 (no notes on Sat/Sun)
Predecessor: weekly/2026-W17.json (4 themes, 6 open actions, 4 focus items)
Verdicts in week: 2 (1 focus done, 1 commitment drop)
Synthesizing with claude-opus-4-6...
Generated weekly/2026-W18.json
  themes: 4 (2 continuing, 2 new) · dropped: 1
  focus scorecard: 2 happened, 1 partial, 1 no evidence
  actions open: 7 (3 carried ≥ 2 weeks)
  silence: Sat, Sun — normal (0/4 prior weeks had weekend pages)
Generated weekly/2026-W18.md
synthesis.weekly event emitted.
```

### "Mid-week synthesis"

If invoked on Wednesday with `--partial`, integrates Mon-Wed briefs and notes the partial coverage in the executive summary. The focus scorecard is rendered with a "provisional" marker; `silence_report` covers only the elapsed days.

### "Weekly synthesis for 2025-W49" (first weekly in the facility)

```
Daily briefs found: 6 of 7
Predecessor: none (first weekly)
Generated weekly/2025-W49.json — 5 themes, all new; no scorecard
```

## Reference files

- `references/weekly-prompt.md` — full prompt including the memory block.
- `references/weekly-md-template.md` — markdown rendering.
