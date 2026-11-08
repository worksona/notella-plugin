# daily/{date}.md — rendering template

How `notella-daily-synthesis` renders `daily/{date}.json` into `daily/{date}.md`. The markdown is derived; the JSON is the record. Re-rendering from the JSON must reproduce the file byte-for-byte, so the template is deterministic: fixed section order, fixed sort orders, no model call. The brief opens with the theme of the day and the resolved / carried / new counts, shows what closed before what is open, marks every carried item with the date it first appeared, and ends with what tomorrow should show.

**Placeholders:** `{{double-curly}}`; `{{#each}}…{{/each}}` loops; `{{#if}}…{{/if}}` conditionals. Sections whose array is empty render the heading followed by `_None._` so the file shape is stable for the desktop app's parser.

## Sort orders

- `resolved_today`: `origin_date` ascending (oldest open item first), then item text.
- `top_priorities`: urgency high → medium → low, then status carried → new → resolved (dropped are not listed here), then `carried_since` ascending, then source page id.
- `new_decisions`: status carried → new → resolved, then confidence descending.
- `unresolved_questions`: status carried → new → resolved, then `carried_since` ascending, then source page id.
- Dropped items (any list): `carried_since` ascending, then text.
- `key_entities_active`: grouped by `entity_type` in the order project, person, organization, concept, decision, task, place; alphabetical inside a group.
- `momentum_signals`, `watch_tomorrow`: as returned (the model orders by salience).

## Markers

| urgency | marker |
| --- | --- |
| high | `[!!]` |
| medium | `[!]` |
| low | `[ ]` |

| status | suffix |
| --- | --- |
| new | nothing |
| carried | `(carried since {{carried_since}})` |
| resolved | `_(resolved today)_` |
| dropped | not rendered in its section — see Resolved today |

Markers are plain ASCII so the file renders the same in a terminal, the desktop app and GitHub. The `✓` on resolved rows is the single exception, taken from the SKILL.md.

## Page links

`{{page_link id}}` renders `[{{id}}](../pages/{{id}}/)` — relative, so the facility can move. The desktop app rewrites these to its own routes. `{{page_link_or_dash id}}` renders `—` when `id` is null (a carried weekly action no page mentioned). `{{daily_link d}}` renders `[{{d}}](./{{d}}.md)`.

## Counts

```
resolved_count = len(resolved_today)
carried_count  = count of items with status == carried across new_decisions, unresolved_questions, top_priorities
new_count      = count of items with status == new across the same three lists
```

The same three numbers go into the `synthesis.daily` event, so the subtitle and the event always agree.

## Template

```markdown
# Daily Intelligence — {{date}} ({{weekday}})

**Theme of the day:** {{theme_of_day}}

**{{pages_analyzed}} pages analyzed** · {{resolved_count}} resolved · {{carried_count}} carried · {{new_count}} new

## Synthesis Notes

{{synthesis_notes}}

## Resolved today

{{#each resolved_today}}
- ✓ {{item}} — open since {{origin_date}}; {{evidence_text evidence}} ({{#if evidence_page_id}}{{page_link evidence_page_id}}{{else}}review verdict{{/if}})
{{/each}}
{{#if dropped_items}}

{{#each dropped_items}}
Dropped: {{text}} (since {{carried_since}})
{{/each}}
{{/if}}

## Top Priorities

{{#each top_priorities_shown}}
- {{marker urgency}} {{priority}} — {{page_link_or_dash source_page_id}}{{status_suffix status carried_since}}
{{/each}}

## New Decisions

{{#each new_decisions_shown}}
- {{decision}} _(confidence {{percent confidence}})_ — {{page_link source_page_id}}{{status_suffix status carried_since}}
{{/each}}

## Unresolved Questions

{{#each unresolved_questions_shown}}
- **{{question}}**{{status_suffix status carried_since}}
  {{context}} — {{page_link source_page_id}}
{{/each}}

## Momentum Signals

{{#each momentum_signals}}
- {{this}}
{{/each}}

## Key Entities Active

{{#each entity_groups}}
### {{type_label}}

{{#each entities}}
- **{{name}}** — {{activity_summary}}
{{/each}}

{{/each}}
## Watch tomorrow

{{#each watch_tomorrow}}
- [ ] {{this}}
{{/each}}

---
*Generated {{generated_at}} by notella-daily-synthesis from pages {{#each page_ids}}{{page_link this}}{{#unless @last}}, {{/unless}}{{/each}}; predecessor {{#if previous_date}}{{daily_link previous_date}}{{else}}none{{/if}}.*
```

## Helpers

- `*_shown` — the list with `status: dropped` items removed. Dropped items from all three lists are collected into `dropped_items` (`{text, carried_since}`, text being the `decision` / `question` / `priority` field) and rendered only on the `Dropped:` lines of the Resolved today section. When `resolved_today` is empty and `dropped_items` is empty the section reads `_None._`; when only dropped items exist, the section holds just the `Dropped:` lines.
- `{{status_suffix}}` — a leading space plus the suffix from the status table; nothing for `new`.
- `{{evidence_text}}` — for strings beginning `verdict:`, the text after the first ` — ` (the whole remainder when there is none); other strings as is.
- `type_label` maps `entity_type` to a plural heading: Projects, People, Organizations, Concepts, Decisions, Tasks, Places.
- `percent` renders `0.85` as `85%`.
- `previous_date` is the predecessor the run actually used; `none` on a first brief or when the predecessor was a legacy brief with no usable statuses is still that brief's date — legacy is a shape, not an absence.

## Example (abbreviated)

```markdown
# Daily Intelligence — 2026-05-02 (Saturday)

**Theme of the day:** Locking the AIMQC Sprint 3 scope before the NRCAN call.

**4 pages analyzed** · 2 resolved · 2 carried · 3 new

## Synthesis Notes

The day centred on the Sprint 3 cut for AIMQC; yesterday's watch item — a date for the NRCAN demo — did not appear …

## Resolved today

- ✓ Does workstream-3 overlap with Project Sunshine's data layer? — open since 2026-05-01; "WS3 reads Sunshine's staging tables only — no overlap" (margin note) ([2026-05-02-w9m3](../pages/2026-05-02-w9m3/))
- ✓ Send the NRCAN pre-read — open since 2026-04-27; sent Thursday by email (review verdict)

Dropped: Draft the Toronto office memo (since 2026-04-29)

## Top Priorities

- [!!] Follow up with JP Morgan contact on data access — — (carried since 2026-04-28)
- [!!] Confirm Alice's Q2 bandwidth before the Sunshine kickoff — [2026-05-02-x7k2](../pages/2026-05-02-x7k2/)
- [!] Document workstream-3 — [2026-05-02-w9m3](../pages/2026-05-02-w9m3/)

## New Decisions

- Treat workstreams 1, 2 and 5 as quick wins _(confidence 90%)_ — [2026-04-30-p2m8](../pages/2026-04-30-p2m8/) (carried since 2026-04-30)
- Sprint 3 ships without the export path _(confidence 85%)_ — [2026-05-02-x7k2](../pages/2026-05-02-x7k2/)

## Unresolved Questions

- **Does workstream-3 overlap with Project Sunshine's data layer?** _(resolved today)_
  Raised beside the 2x2; answered in the margin — [2026-05-02-w9m3](../pages/2026-05-02-w9m3/)

## Momentum Signals

- Project Sunshine gaining: three of four pages reference it.

## Key Entities Active

### Projects

- **project-sunshine** — resource-overlap concern and kickoff planning

### People

- **Alice** — capacity for Q2 is the day's open question

## Watch tomorrow

- [ ] A date is set for the NRCAN demo.
- [ ] Alice answers the Q2 bandwidth question in writing.

---
*Generated 2026-05-02T19:00:47Z by notella-daily-synthesis from pages [2026-05-02-x7k2](../pages/2026-05-02-x7k2/), [2026-05-02-w9m3](../pages/2026-05-02-w9m3/); predecessor [2026-05-01](./2026-05-01.md).*
```
