---
name: notella-weekly-synthesis
description: "Produce a weekly synthesis report from a week of daily intelligence briefs — executive summary, key themes evolved, projects progressed, people and relationships, ideas and insights, action items, suggested focus for next week. Use whenever the user says 'weekly report for this week', 'synthesize last week', 'weekly intelligence', 'week-on-week summary', 'what happened this past week', or any request to consolidate seven days of daily briefs. Reads through `notella-state`; writes `weekly/{iso-week}.{json,md}`. Emits `synthesis.weekly` event."
---

# notella-weekly-synthesis — the weekly intelligence brief

Reads a week's worth of daily syntheses (already produced) and integrates them into a weekly brief. Higher-altitude than daily — themes evolved, projects progressed, people who showed up most, ideas worth highlighting, focus for next week.

## Purpose

The week is the natural granularity for review and planning: long enough that themes emerge, short enough that recall is good. Daily briefs are operational; weekly briefs are reflective.

## Inputs and outputs

**Input:** An ISO week (e.g. `2026-W18`) or a date that resolves to one. Reads every `daily/YYYY-MM-DD.json` whose date falls in that week.

**Output:**
- `weekly/{iso-week}.json` — weekly synthesis schema
- `weekly/{iso-week}.md` — narrative rendering
- `synthesis.weekly` event
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

### Step 2 — Build the prompt

Adapted from notella-the-app's `buildWeeklyReportPrompt()` from `src/lib/prompts/report.ts`, passing each daily as `{date, daily_intelligence_json}` rather than a free-text summary. The model gets structured input it can integrate.

System prompt (paraphrased):

```
You are a weekly synthesis analyst for a personal knowledge management system.
You receive structured daily intelligence reports for one week and produce a
coherent weekly brief.

Your output covers:

## executive_summary
3-5 sentences capturing the shape of the week.

## key_themes
Themes that recurred or evolved. For each:
- theme: short label
- evolution: how it shifted across the week
- weight: primary | secondary | minor

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
The open action items still standing at week-end. Group by urgency.

## suggested_focus
2-4 specific suggestions for the upcoming week, grounded in unresolved
questions, blocked work, or emerging themes.

## momentum_summary
Overall: accelerating, stable, or decelerating? What's the strongest signal?

Return ONLY valid JSON matching WeeklySynthesisSchema.
```

### Step 3 — Call the model

Default: `claude-opus-4-6`. **Use prompt caching** on the system prompt block (`cache_control: { type: "ephemeral" }`) — when running weekly back-syntheses for multiple weeks in one orchestrator pass, the system prompt is reused. ~80-90% discount on cached input tokens after the first call.

### Step 4 — Validate

```yaml
iso_week: "YYYY-Www"
dates_covered: [date]
generated_at: ISO-8601
days_with_briefs: int
days_missing_briefs: int
executive_summary: string
key_themes:
  - theme, evolution, weight
projects_progressed:
  - project, progress, pages_count
people_and_relationships:
  - person, mentions_count, summary
ideas_and_insights: [string]
action_items_open:
  - item, urgency, source_date
suggested_focus: [string]
momentum_summary: string
```

### Step 5 — Render the markdown

Standard week brief format. Title `# Week of {iso-week} ({first-date} → {last-date})`, sections in the order above. Each item in `action_items_open` links to its source daily (`daily/{date}.md`).

### Step 6 — Write the synthesis

```
notella-state log-synthesis {kind: synthesis.weekly, week: {iso-week}, json, md}
```

Updates `state.json:last_synthesis_at.weekly`.

## Idempotency

- Re-running for an existing week: no-op unless `--reprocess`.
- `--reprocess`: overwrite, emit `correction`.

## Failure modes

| Failure                                                | Behavior |
| ------------------------------------------------------ | -------- |
| No dailies in the week                                 | Skip cleanly. Probably a week with no notebook activity. |
| Some days missing briefs                               | Proceed with what's available; surface the gaps in `days_missing_briefs`. |
| Briefs exist but are sparse                            | Run anyway; the weekly may be terse; that's correct. |

## What this skill does NOT do

- Does not re-read individual pages — only consumes daily briefs. (The granularity below the day is already captured in the dailies.)
- Does not modify daily briefs.
- Does not run on partial weeks except when explicitly invoked mid-week (in which case the brief covers up to today).

## Examples

### "Weekly synthesis for 2026-W18"

```
Daily briefs found: 5 of 7 (no notes on Sat/Sun)
Synthesizing with claude-opus-4-6...
Generated weekly/2026-W18.json (8 sections, 4 themes, 3 projects)
Generated weekly/2026-W18.md
synthesis.weekly event emitted.
```

### "Mid-week synthesis"

If invoked on Wednesday with `--partial`, integrates Mon-Wed briefs and notes the partial coverage in the executive summary.

## Reference files

- `references/weekly-prompt.md` — full prompt.
- `references/weekly-md-template.md` — markdown rendering.
