# notella-weekly-synthesis — prompt

The complete weekly-synthesis prompt, self-contained in the plugin. It is adapted from the app's `buildWeeklyReportPrompt()` (`src/lib/prompts/report.ts`) as the SKILL.md describes: the app passed free-text daily summaries and asked for prose; the skill passes each day's structured `daily/{date}.json` and asks for `WeeklySynthesisSchema` JSON. It is extended with the **memory block** of Step 2 — the previous weekly, the focus-scorecard skeleton, the action pool, the theme vocabulary and the silence numbers — so the brief it produces continues the one before: themes carry their prior weight and age, open actions carry the week they first appeared, last week's suggested focus is scored, and the week's silent days are judged against the previous four weeks.

**Placeholders:** `{{double-curly}}`. Blocks marked *(conditional)* are omitted, heading included, when their input is absent.

| Placeholder | Source |
| --- | --- |
| `{{iso_week}}` | `YYYY-Www` |
| `{{first_date}}`, `{{last_date}}` | Monday and Sunday of that week |
| `{{days_with_briefs}}`, `{{days_missing}}` | counts; `{{missing_dates}}` the list |
| `{{dailies_json}}` | array of `{date, weekday, daily}` where `daily` is the full `daily/{date}.json` minus `generated_at` (including `theme_of_day`, per-item `status`, `resolved_today`, `watch_tomorrow` when present) |
| `{{page_counts_by_project}}` | `{slug: n}` computed from `meta.yaml:project_attributions` for pages dated in the week |
| `{{partial}}` | `true` when invoked mid-week with `--partial`; else `false` |
| `{{previous_week}}` | ISO week of the predecessor actually used: `iso_week − 1`, or the most recent earlier weekly when that file is absent; null when none |
| `{{previous_gap}}` | `true` when `previous_week` is not `iso_week − 1` |
| `{{previous_weekly_json}}` | `weekly/{previous_week}.json` reduced to `executive_summary`, `key_themes` (with `prior_weight`, `weeks_active` where present), `themes_dropped`, `suggested_focus`, `momentum_summary` |
| `{{scorecard_skeleton_json}}` | one row per `previous.suggested_focus[i]`, in order (shape below) |
| `{{action_pool_json}}` | `previous.action_items_open[]` minus items closed by a verdict in the week (shape below) |
| `{{closed_actions_json}}` | the items a `commitment` / `question` verdict closed: `[{item, urgency, first_seen_week, status: resolved \| dropped, note}]` |
| `{{theme_vocabulary_json}}` | `[{theme, prior_weight, weeks_active}]` from `previous.key_themes`, then `[{theme, prior_weight: null, source: "themes.json", weight}]` for every `themes.themes[]` with weight primary or secondary not already listed |
| `{{silence_json}}` | the silence numbers (shape below) |
| `{{monthly_month}}`, `{{monthly_watchlist_json}}` | `[w.prediction for w in latest monthly.next_month_watchlist]` |

**Call shape:** system block with `cache_control: {type: "ephemeral"}` (reused across a `--catch-up-weeks` batch), one user turn. Model from `manifest.model_defaults.weekly_synthesis` (default `claude-opus-4-6`). If the user turn exceeds ~60k tokens, drop `key_entities_active` from each daily first, then `momentum_signals`; the memory block is never trimmed. JSON only.

---

## Memory block shapes

### Scorecard skeleton (`{{scorecard_skeleton_json}}`)

```json
[
  { "focus": "Write the Sprint 3 scope for AIMQC with dates", "outcome": null, "evidence_date": null, "evidence": null },
  { "focus": "Get a dated answer on JP Morgan data access or escalate", "outcome": "happened", "evidence_date": null, "evidence": "verdict:5b2d90e1 — answer came by phone Tuesday", "settled_by_verdict": true },
  { "focus": "Decide on the Toronto office question", "outcome": "no_evidence", "evidence_date": null, "evidence": "verdict:a81c3f07 — carry", "settled_by_verdict": true, "resuggest": true }
]
```

`focus` is `previous.suggested_focus[i]` verbatim. Rows with `settled_by_verdict` are fixed (`done` → `happened`; `drop` / `wrong` → `no_evidence` with the note; `carry` → `no_evidence` and `resuggest: true`). Rows with `outcome: null` are the model's to fill. `settled_by_verdict` and `resuggest` are not output fields.

### Action pool (`{{action_pool_json}}`)

```json
[
  { "item": "Follow up with JP Morgan contact on data access", "urgency": "high", "source_date": "2026-04-28", "first_seen_week": "2026-W17" },
  { "item": "Document workstream-3", "urgency": "medium", "source_date": "2026-04-27", "first_seen_week": "2026-W18" }
]
```

`first_seen_week` is the previous weekly's value, or `{{previous_week}}` for a legacy predecessor without the field. Items a verdict closed in the week are not in the pool; they are in `{{closed_actions_json}}` and come back one final time with `status: resolved` (verdict `done`) or `status: dropped` (verdict `drop` or `wrong`).

### Silence numbers (`{{silence_json}}`)

```json
{
  "days_without_pages": ["2026-05-02", "2026-05-03"],
  "baseline_weeks": 4,
  "weekday_coverage": { "Mon": 4, "Tue": 4, "Wed": 3, "Thu": 4, "Fri": 3, "Sat": 0, "Sun": 1 },
  "classification": { "2026-05-02": "normal", "2026-05-03": "normal" },
  "draft_note": "Sat and Sun silent; 0/4 and 1/4 prior weeks had pages on those days — normal."
}
```

`weekday_coverage[d]` is how many of the previous `baseline_weeks` ISO weeks had a `daily/` brief on weekday `d`. A silent weekday with coverage ≥ 3 of 4 is `unusual`, ≤ 1 of 4 is `normal`, otherwise `mixed`. With fewer than 4 prior weeks, thresholds scale (`unusual` when coverage ≥ ¾ of `baseline_weeks`, rounded up) and the draft note ends with `(baseline: N weeks)`. The model may reword `draft_note` into `weekday_pattern_note` but may not change the numbers; `days_without_pages` is copied through.

## System prompt

```
You are a weekly synthesis analyst for a personal knowledge management system.
You receive structured daily intelligence reports for one ISO week, the previous
week's brief, and the current longitudinal themes, and produce a coherent weekly
brief that continues the previous one. Daily briefs are operational; the weekly
brief is reflective — it says how the week moved, not what each day contained.

Your analysis must be grounded in the daily briefs provided. Do not invent projects,
people, decisions or questions that no daily brief supports. When the week has days
without a brief, say so where it matters (a silent Thursday is a fact about the week).

## Output sections

### executive_summary (string)
3–5 sentences capturing the shape of the week: what dominated, the most significant
development, the biggest open risk, and what next week hinges on. Say explicitly what
changed relative to last week. If the predecessor is not the immediately preceding
week, say which week it is.

### key_themes (array)
Themes that recurred or evolved across the week. For each:
- theme        : short label. If the theme is the same as one in last week's brief or
                 in the theme vocabulary, REUSE THAT LABEL VERBATIM. Do not coin a
                 near-synonym.
- evolution    : how it shifted across the week, with the days it appeared
- weight       : primary | secondary | minor
- prior_weight : the weight this theme had in last week's brief, or null if it did
                 not appear there (the vocabulary gives it)
- weeks_active : consecutive briefs this theme has appeared in, counting this one —
                 last week's weeks_active + 1, or 1 if new
Prefer 3–7 themes. A theme mentioned on one day only is minor unless it was a major
decision.

### themes_dropped (array)
Every theme that was in last week's key_themes and is absent from this week's — no
more, no fewer. For each: theme (verbatim label), last_weight, reason_guess — one line
on why it may have gone quiet (resolved, superseded, no pages on the relevant days,
project paused). A guess is fine; silence is not.

### projects_progressed (array)
Per project that saw meaningful activity:
- project     : slug or name as it appears in the briefs
- progress    : what changed this week (decisions, actions closed, blockers hit)
- pages_count : how many pages touched it (use the page counts supplied)

### people_and_relationships (array)
People who appeared on multiple days, new entrants, and relationships discussed:
- person         : name as it appears
- mentions_count : number of daily briefs naming them
- summary        : their role in the week in one sentence

### ideas_and_insights (array of strings)
3–7 ideas worth marking: recurring across days, explicitly emphasised in source pages,
or reframing something the author had treated differently before.

### action_items_open (array)
The open action items still standing at week-end. For each:
- item            : imperative statement
- urgency         : high | medium | low
- source_date     : the date of the daily brief it comes from
- status          : new | carried | resolved | dropped
- first_seen_week : the ISO week the item first appeared
An item from the action pool that is still open is carried, with the pool's wording,
source_date and first_seen_week — even when no daily this week mentions it. An item is
resolved only when a daily brief's resolved_today names it or a verdict says done; it
then appears one final time with status=resolved. The closed-actions list is copied in
as given. New items get first_seen_week = this week.

### focus_scorecard (array)
One row per item of last week's suggested_focus, in order, focus verbatim:
- outcome       : happened | partial | no_evidence
- evidence_date : the date of the daily brief that shows it; null when no_evidence
- evidence      : a short quote from that brief
no_evidence means exactly that — the notebook does not show it — not that it did not
happen. Rows the memory block has already settled from a verdict are copied as given.

### silence_report (object)
- days_without_pages  : copied from the memory block
- weekday_pattern_note: whether this week's silent days fit the previous four weeks'
                        pattern, using the counts given. Keep the numbers.

### suggested_focus (array of strings)
3–5 suggestions for the upcoming week, grounded in unresolved questions, blocked work,
carried actions, or emerging themes. Phrase each so that next week's brief can score it
from the notebook alone: name the thing that should appear on a page ("Write the Sprint
3 scope for AIMQC with dates"), not an attitude ("Stay focused on AIMQC"). Re-suggest
any focus item the memory block flags for re-suggestion.

### momentum_summary (string)
Overall: accelerating, stable, or decelerating? What is the strongest signal? Compare
to last week's momentum_summary in one clause. One paragraph.

## Grounding
- Every source_date and evidence_date is a date that has a brief this week.
- Every prior_weight and weeks_active comes from the theme vocabulary; a theme not in
  the vocabulary has prior_weight null and weeks_active 1.
- Every carried action matches a pool entry verbatim.
- The month watchlist, when supplied, is context: mention in executive_summary or
  projects_progressed when the week speaks to an item; never list its items as actions.
- When no previous brief is supplied: every prior_weight is null, every weeks_active is
  1, themes_dropped and focus_scorecard are empty, every action is new.

Return ONLY valid JSON matching WeeklySynthesisSchema.
```

## User prompt (adapted from `buildWeeklyReportPrompt()`)

```
Generate a weekly synthesis for ISO week {{iso_week}} ({{first_date}} → {{last_date}}) from the
following daily intelligence briefs.

Coverage: {{days_with_briefs}} of 7 days have briefs{{#if days_missing}}; no brief for {{missing_dates}}{{/if}}.
{{#if partial}}This is a mid-week partial run; the brief covers only the days listed and the focus scorecard is provisional.{{/if}}

## Pages per project this week
{{page_counts_by_project}}

## Daily briefs, Monday first
{{dailies_json}}

## Memory — continuing the brief of {{previous_week}}                 (conditional)
{{#if previous_gap}}Note: {{previous_week}} is not the immediately preceding week; the weeks between have no brief.{{/if}}
Last week's brief, reduced:
{{previous_weekly_json}}

### Theme vocabulary
Reuse these labels verbatim. prior_weight and weeks_active for a continuing theme come from here.
{{theme_vocabulary_json}}

### Focus scorecard skeleton
One row per last week's suggested_focus. Fill outcome, evidence_date and evidence where null; copy settled rows as given; re-suggest rows marked resuggest.
{{scorecard_skeleton_json}}

### Action pool
Open at the end of last week. Each comes back carried (verbatim, same first_seen_week) or resolved with the daily that shows it.
{{action_pool_json}}

### Closed by review verdict this week                                (conditional)
Copy each into action_items_open once, with the status given.
{{closed_actions_json}}

## Silence numbers
{{silence_json}}

## Month watchlist ({{monthly_month}})                                (conditional)
Context only.
{{monthly_watchlist_json}}

Produce the complete WeeklySynthesisSchema output. Set iso_week to "{{iso_week}}",
dates_covered to the dates that have briefs, days_with_briefs to {{days_with_briefs}},
days_missing_briefs to {{days_missing}} and previous_week to {{previous_week_literal}}.
Every source_date and evidence_date must be one of the dates above. themes_dropped must be
exactly the vocabulary themes with a non-null prior_weight that are absent from key_themes.
focus_scorecard must have exactly {{count scorecard_skeleton}} rows, in order. suggested_focus
has 3 to 5 entries. Be specific and grounded — use exact language from the briefs where it
adds precision.
```

`{{previous_week_literal}}` is `"2026-W17"` (quoted) or `null`. When there is no predecessor the Memory heading and its subsections are omitted, `{{count scorecard_skeleton}}` is 0, and the silence block still appears (it depends on day coverage, not on a previous brief).

## Expected response shape (`WeeklySynthesisSchema`)

```json
{
  "iso_week": "2026-W18",
  "dates_covered": ["2026-04-27", "2026-04-28", "2026-04-29", "2026-04-30", "2026-05-01"],
  "days_with_briefs": 5,
  "days_missing_briefs": 2,
  "previous_week": "2026-W17",
  "executive_summary": "…",
  "key_themes": [
    { "theme": "q2-prioritisation", "evolution": "…", "weight": "primary", "prior_weight": "secondary", "weeks_active": 3 },
    { "theme": "edge-inference", "evolution": "…", "weight": "minor", "prior_weight": null, "weeks_active": 1 }
  ],
  "themes_dropped": [
    { "theme": "toronto-office", "last_weight": "minor", "reason_guess": "No pages touched the office question; the decision was deferred on 2026-04-24." }
  ],
  "projects_progressed": [ { "project": "tulevik", "progress": "…", "pages_count": 6 } ],
  "people_and_relationships": [ { "person": "Alice", "mentions_count": 3, "summary": "…" } ],
  "ideas_and_insights": ["…"],
  "action_items_open": [
    { "item": "Follow up with JP Morgan contact on data access", "urgency": "high", "source_date": "2026-04-28", "status": "carried", "first_seen_week": "2026-W17" },
    { "item": "Send Alice the Sprint 3 scope", "urgency": "medium", "source_date": "2026-04-30", "status": "new", "first_seen_week": "2026-W18" },
    { "item": "Document workstream-3", "urgency": "medium", "source_date": "2026-04-27", "status": "resolved", "first_seen_week": "2026-W18" }
  ],
  "focus_scorecard": [
    { "focus": "Write the Sprint 3 scope for AIMQC with dates", "outcome": "happened", "evidence_date": "2026-04-29", "evidence": "Sprint 3 scope fixed: three workstreams, ship 2026-05-15" },
    { "focus": "Get a dated answer on JP Morgan data access or escalate", "outcome": "happened", "evidence_date": null, "evidence": "verdict:5b2d90e1 — answer came by phone Tuesday" },
    { "focus": "Decide on the Toronto office question", "outcome": "no_evidence", "evidence_date": null, "evidence": "verdict:a81c3f07 — carry" }
  ],
  "silence_report": {
    "days_without_pages": ["2026-05-02", "2026-05-03"],
    "weekday_pattern_note": "Saturday and Sunday silent, as in the previous four weeks (0/4 and 1/4 had pages) — normal."
  },
  "suggested_focus": ["…", "…", "…"],
  "momentum_summary": "…"
}
```

Set by the skill, not the model: `generated_at`, and `carried_actions` — every `action_items_open[]` item with `status: carried` and `weeks_open = weeknum(iso_week) − weeknum(first_seen_week) + 1 ≥ 2`, as `{item, urgency, first_seen_week, weeks_open}`, oldest first. A verdict-settled scorecard row may carry `evidence_date: null` with `outcome: happened`; the Step 5 check `evidence_date in dates_covered when outcome is not no_evidence` is waived for rows whose `evidence` begins `verdict:`.

## Validation the prompt is written to pass

Mirrors Step 5 of the SKILL.md.

- Every `key_themes[].theme` with non-null `prior_weight` matches (verbatim, case-insensitive) a theme in `previous.key_themes`; `prior_weight` equals that theme's weight; `weeks_active` equals its `weeks_active + 1` (or 2 when the previous lacks the field).
- Every `key_themes[].theme` with `prior_weight: null` has `weeks_active: 1` and is absent from `previous.key_themes`.
- `themes_dropped` is exactly `previous.key_themes` minus `key_themes`, by label.
- `focus_scorecard` has exactly `len(previous.suggested_focus)` rows, in order, `focus` verbatim; settled rows carry the skeleton's `outcome` and `evidence`.
- Every `carried` action matches a pool item and keeps its `first_seen_week`; `new` items have `first_seen_week == iso_week`; every closed-actions item appears once with its given status.
- `suggested_focus` has 3–5 entries; `silence_report.days_without_pages` equals the computed list.
- `previous_week` equals the predecessor the skill used.

A failure refuses the write and allows one retry with the violations appended under `## Violations in your previous answer`.

## Differences from the app prompt

- Structured daily JSON in, structured JSON out (the app did prose → prose).
- Explicit coverage statement (days with / without briefs) and partial-week flag.
- Per-project page counts supplied so `pages_count` is measured, not guessed.
- Memory block: previous weekly, theme vocabulary with prior weights and ages, focus-scorecard skeleton with verdict-settled rows, action pool with `first_seen_week`, verdict-closed actions, silence numbers, month watchlist.
- New fields: `previous_week`, `prior_weight` / `weeks_active`, `themes_dropped`, per-action `status` / `first_seen_week`, `focus_scorecard`, `silence_report`; `suggested_focus` widened to 3–5 and required to be scoreable.
