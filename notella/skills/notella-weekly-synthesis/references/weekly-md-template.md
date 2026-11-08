# weekly/{iso-week}.md — rendering template

How `notella-weekly-synthesis` renders `weekly/{iso-week}.json` into the matching `.md`. Deterministic; the JSON is the record. No model call. The brief scores last week's focus before it says anything about this week's themes, shows each theme with the weight it had last week and how many weeks it has run, lists what was dropped, marks each open action with the week it first appeared, and reports the week's silent days against the previous four weeks.

**Placeholders:** `{{double-curly}}`; `{{#each}}` loops; `{{#if}}` conditionals. Empty arrays render `_None._` under their heading. Sections marked *omitted* below are left out entirely, heading included, under the stated condition.

## Sort orders

- `focus_scorecard`: as in the JSON (the order of last week's `suggested_focus`).
- `key_themes`: weight primary → secondary → minor, then `weeks_active` descending, then label.
- `themes_dropped`: `last_weight` primary → secondary → minor, then label.
- `projects_progressed`: `pages_count` descending, then project.
- `people_and_relationships`: `mentions_count` descending, then name.
- `action_items_open` (open part): urgency high → medium → low, then `first_seen_week` ascending (oldest first, so age is visible), then `source_date` ascending.
- `action_items_open` (closed part): resolved before dropped, then `first_seen_week` ascending.
- `carried_actions`: `weeks_open` descending (oldest first), then item — the order the skill derives it in.
- `ideas_and_insights`, `suggested_focus`: as returned.

## Markers

| urgency | marker |
| --- | --- |
| high | `[!!]` |
| medium | `[!]` |
| low | `[ ]` |

| outcome | cell |
| --- | --- |
| happened | `**happened**` |
| partial | `partial` |
| no_evidence | `_no evidence_` |

| weight | text |
| --- | --- |
| primary / secondary / minor | the word as is |

## Links

- `{{daily_link date}}` → `[{{date}}](../daily/{{date}}.md)`
- `{{weekly_link w}}` → `[{{w}}](./{{w}}.md)`
- Missing-brief dates are rendered plain (no link) in the coverage line and the silence report.
- Evidence strings beginning `verdict:` render as `review verdict — {note}` with no date link.

## Template

```markdown
# Week of {{iso_week}} ({{first_date}} → {{last_date}})

**{{days_with_briefs}} of 7 days with briefs**{{#if days_missing_briefs}} · no notes on {{#each missing_dates}}{{weekday_short this}}{{#unless @last}}, {{/unless}}{{/each}}{{/if}} · generated {{generated_at}}
{{#if partial}}
> Partial week — covers {{first_covered}} → {{last_covered}} only. Focus scorecard is provisional.
{{/if}}
{{#if previous_week}}
_Continues {{weekly_link previous_week}}{{#if previous_gap}} (no brief for the weeks between){{/if}}._
{{else}}
_First weekly brief — no predecessor._
{{/if}}

## Executive Summary

{{executive_summary}}

## Focus scorecard                                                    ← omitted when previous_week is null

| Last week's focus | Outcome | Evidence |
| --- | --- | --- |
{{#each focus_scorecard}}
| {{focus}} | {{outcome_cell outcome}} | {{#if evidence_date}}{{daily_link evidence_date}}: {{/if}}{{evidence_cell evidence}} |
{{/each}}

**{{happened_count}} of {{count focus_scorecard}} happened**{{#if partial_count}} · {{partial_count}} partial{{/if}}{{#if no_evidence_count}} · {{no_evidence_count}} no evidence{{/if}}

## Key Themes

{{#each key_themes}}
### {{theme}} `{{weight}}{{#if prior_weight}}, was {{prior_weight}}{{else}}, new{{/if}}` · {{weeks_active}} {{plural weeks_active "week" "weeks"}}

{{evolution}}

{{/each}}
{{#each themes_dropped}}
**Dropped since last week:** {{theme}} (was {{last_weight}}) — {{reason_guess}}
{{/each}}

## Projects Progressed

| Project | Pages | Progress |
| --- | --- | --- |
{{#each projects_progressed}}
| {{project}} | {{pages_count}} | {{progress}} |
{{/each}}

## People & Relationships

{{#each people_and_relationships}}
- **{{person}}** ({{mentions_count}}) — {{summary}}
{{/each}}

## Ideas & Insights

{{#each ideas_and_insights}}
- {{this}}
{{/each}}

## Action Items Open

{{#each urgency_groups}}
**{{label}}**

{{#each items}}
- {{marker urgency}} {{item}} — {{daily_link source_date}}{{#if (eq status "carried")}} (since {{first_seen_week}}){{/if}}
{{/each}}

{{/each}}
{{#if closed_items}}
**Closed this week:** {{#each closed_items}}{{item}} ({{status}}{{#if (ne first_seen_week ../iso_week)}}, since {{first_seen_week}}{{/if}}){{#unless @last}}; {{/unless}}{{/each}}
{{/if}}

## Carried actions                                                    ← omitted when carried_actions is empty

{{#each carried_actions}}
- {{marker urgency}} {{item}} — open {{weeks_open}} weeks (since {{weekly_link first_seen_week}})
{{/each}}

## Silence report

{{#if silence_report.days_without_pages}}
{{#each silence_report.days_without_pages}}
- {{weekday_long this}} {{this}}
{{/each}}
{{else}}
No silent days.
{{/if}}

{{silence_report.weekday_pattern_note}}

## Suggested Focus for {{next_iso_week}}

{{#each suggested_focus}}
{{@index1}}. {{this}}
{{/each}}

## Momentum

{{momentum_summary}}

---
*Generated {{generated_at}} by notella-weekly-synthesis from daily briefs {{#each dates_covered}}{{daily_link this}}{{#unless @last}}, {{/unless}}{{/each}}{{#if previous_week}}; previous brief {{weekly_link previous_week}}{{/if}}.*
```

## Helpers

- `weekday_short` renders `Sat`, `Sun`; `weekday_long` renders `Saturday`.
- `@index1` is a 1-based counter; `next_iso_week` is computed by the renderer.
- `happened_count`, `partial_count`, `no_evidence_count` — counts over `focus_scorecard[].outcome`; they are also the event's `focus_happened` / `focus_partial` / `focus_no_evidence`.
- `urgency_groups` — `action_items_open` items with status `new` or `carried`, split into `High`, `Medium`, `Low` groups in that order; a group with no items is skipped. When all three are empty the section reads `_None._`.
- `closed_items` — `action_items_open` items with status `resolved` or `dropped`.
- `outcome_cell`, `evidence_cell` — per the marker tables; `evidence_cell` strips the `verdict:{id} — ` prefix and renders `review verdict — {note}`.
- `plural n a b` — `a` when `n == 1`, else `b`.
- `previous_gap` — true when `previous_week` is not the ISO week immediately before `iso_week`.
- Pipes inside table cells are escaped as `\|`.

The theme heading's inline code carries both weights so a `grep` across `weekly/*.md` for `` `primary, was secondary` `` finds every promotion.

## Example (abbreviated)

```markdown
# Week of 2026-W18 (2026-04-27 → 2026-05-03)

**5 of 7 days with briefs** · no notes on Sat, Sun · generated 2026-05-04T07:31:10Z
_Continues [2026-W17](./2026-W17.md)._

## Executive Summary

The week moved from Q2 planning to execution on Tulevik; relative to W17 the data-access blocker is unchanged and the Toronto question has gone quiet …

## Focus scorecard

| Last week's focus | Outcome | Evidence |
| --- | --- | --- |
| Write the Sprint 3 scope for AIMQC with dates | **happened** | [2026-04-29](../daily/2026-04-29.md): Sprint 3 scope fixed: three workstreams, ship 2026-05-15 |
| Get a dated answer on JP Morgan data access or escalate | **happened** | review verdict — answer came by phone Tuesday |
| Decide on the Toronto office question | _no evidence_ | review verdict — carry |

**2 of 3 happened** · 1 no evidence

## Key Themes

### q2-prioritisation `primary, was secondary` · 3 weeks

Opened Monday with the 2x2, resolved Wednesday into three quick wins, absent Friday.

### data-access `secondary, was secondary` · 4 weeks

JP Morgan access blocked Tuesday and again Thursday; the phone answer is not yet on a page.

### edge-inference `minor, new` · 1 week

One page Thursday sketching an on-device inference path.

**Dropped since last week:** toronto-office (was minor) — No pages touched the office question; the decision was deferred on 2026-04-24.

## Projects Progressed

| Project | Pages | Progress |
| --- | --- | --- |
| tulevik | 6 | name-matching report shipped; dashboard still blocked on data access |

## People & Relationships

- **Alice** (3) — capacity for Q2 is the week's open question

## Ideas & Insights

- Treating the staleness dashboard as the name-matching report's consumer collapses two roadmaps into one.

## Action Items Open

**High**

- [!!] Follow up with JP Morgan contact on data access — [2026-04-28](../daily/2026-04-28.md) (since 2026-W17)

**Medium**

- [!] Send Alice the Sprint 3 scope — [2026-04-30](../daily/2026-04-30.md)

**Closed this week:** Document workstream-3 (resolved)

## Carried actions

- [!!] Follow up with JP Morgan contact on data access — open 2 weeks (since [2026-W17](./2026-W17.md))

## Silence report

- Saturday 2026-05-02
- Sunday 2026-05-03

Saturday and Sunday silent, as in the previous four weeks (0/4 and 1/4 had pages) — normal.

## Suggested Focus for 2026-W19

1. Decide on the Toronto office question and write the decision on a page — it has been open two weeks.
2. Get the JP Morgan answer onto a page with the date access is expected.
3. Put dates on the three Sprint 3 workstreams.

## Momentum

Stable to accelerating, up from last week's stable: four of five days touched Tulevik …

---
*Generated 2026-05-04T07:31:10Z by notella-weekly-synthesis from daily briefs [2026-04-27](../daily/2026-04-27.md), …; previous brief [2026-W17](./2026-W17.md).*
```
