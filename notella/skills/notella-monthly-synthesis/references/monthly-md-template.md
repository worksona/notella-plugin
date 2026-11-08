# monthly/{YYYY-MM}.md — rendering template

How `notella-monthly-synthesis` renders `monthly/{YYYY-MM}.json` into the matching `.md`. Deterministic: same JSON → same markdown, no model call. The JSON is the record; the markdown is derived and can be regenerated from it at any time.

**Placeholders:** `{{double-curly}}`; `{{#each}}…{{/each}}` loops; `{{#if}}…{{/if}}` conditionals. Tables whose array is empty render the heading, the table header row, and one row reading `_None._` so the desktop app's parser sees a stable shape. Sections whose source ledger was absent (`sources.ledgers.{name}: false`) render the heading followed by `Not available — {name} missing.` and nothing else.

## Sort orders

Every array is rendered in the order the JSON holds it — the pre-aggregation already fixed those orders (`theme_arc` alphabetical, `decisions_made` by date, `commitments_aging.oldest` oldest first, people by `mentions_total` descending, `forecast_scorecard` monthly rows before emergent-topic rows) and the model-authored lists (`next_month_watchlist`, `suggested_focus_next_month`) are ordered by the model. The renderer never re-sorts.

## Labels and markers

| direction | cell |
| --- | --- |
| rising | `↑ rising` |
| held | `→ held` |
| fell | `↓ fell` |
| new | `+ new` |
| gone | `− gone` |

| outcome | cell |
| --- | --- |
| held | `**held**` |
| partial | `partial` |
| missed | `_missed_` |
| unknown | `unknown` |

| weight | cell |
| --- | --- |
| primary / secondary / emerging / fading | the word as is |
| null | `—` |

`{{month_label}}` renders `2026-05` as `May 2026` (English month name, full). `{{short_source}}` renders `monthly/2026-04.json#next_month_watchlist[2]` as `monthly 2026-04 · w3` and `longitudinal/themes/2026-05-09.json#emergent_topics[1]` as `themes 2026-05-09 · emergent 2`.

## Links

- `{{page_link id}}` → `[{{id}}](../pages/{{id}}/)` — relative, so the facility can move; the desktop app rewrites these to its own routes.
- `{{week_link w}}` → `[{{w}}](../weekly/{{w}}.md)`.
- `{{narrative_linked}}`: the narrative with every token matching a page id (`\d{4}-\d{2}-\d{2}-[a-z0-9]{4}`) that exists in the facility replaced by `{{page_link}}`, and every token matching an ISO week (`\d{4}-W\d{2}`) that is in `weeks_covered` replaced by `{{week_link}}`. Tokens already inside a markdown link are left alone.
- `{{source_link source}}`: `monthly/…` sources link to `../monthly/{{YYYY-MM}}.md#watchlist-for-next-month`; `longitudinal/themes/…` sources link to `../longitudinal/themes.md#emergent-topics`.
- Evidence strings that begin with `verdict:` render as `review verdict — {note}` with no link.

## Template

```markdown
# Month in review — {{month_label}}

_{{pages_total}} pages · {{count weeks_covered}} weeks · generated {{generated_at}}{{#if partial}} · **partial — data through {{month_end}}**{{/if}}_

{{#if weeks_missing}}
> No weekly brief for {{#each weeks_missing}}{{this}}{{#unless @last}}, {{/unless}}{{/each}}. Those weeks are silence, not absence of activity.
{{/if}}

## Narrative

{{narrative_linked}}

## Theme arc

{{#if sources.themes_current_stale}}
_Measured against a snapshot from {{date sources.themes_current}}, before the month closed. Run `notella-themes --themes-now` and `--reprocess` for a current arc._
{{/if}}
{{#if (and (null sources.themes_previous) sources.themes_current)}}
_Single snapshot — every row is new; the arc has no start._
{{/if}}

| Theme | Start | End | Direction | Evidence | Note |
| --- | --- | --- | --- | --- | --- |
{{#each theme_arc}}
| {{theme}} | {{weight_cell start_weight}} | {{weight_cell end_weight}} | {{direction_cell direction}} | {{#each evidence_pages}}{{page_link this}}{{#unless @last}} {{/unless}}{{/each}} | {{note}} |
{{/each}}

## Forecast scorecard

| Prediction | Source | Outcome | Evidence |
| --- | --- | --- | --- |
{{#each forecast_scorecard}}
| {{prediction}} | [{{short_source source}}]({{source_link source}}) | {{outcome_cell outcome}} | {{evidence_cell evidence}} |
{{/each}}

{{scorecard_tally}}

## Decisions

{{#if sources.ledgers.decisions}}
{{#each decisions_made}}
- {{date}} — {{decision}} ({{page_link page_id}}){{#if revisited}} — **revisited:** {{revisit_note}}{{/if}}
{{/each}}
{{else}}
Not available — decisions missing.
{{/if}}

## Commitments aging

{{#if sources.ledgers.commitments}}
**{{open_total}} open** — &lt;7d {{buckets.[<7d]}} · 7–30d {{buckets.[7-30d]}} · 30–90d {{buckets.[30-90d]}} · &gt;90d {{buckets.[>90d]}}

| Task | Since | State |
| --- | --- | --- |
{{#each commitments_aging.oldest}}
| {{task}} | {{source_date}} ({{age_days source_date}} days) | {{state}} |
{{/each}}

Closed this month: {{commitments_aging.closed_this_month}} · dropped: {{commitments_aging.dropped_this_month}}{{#if approx_note}} — _{{approx_note}}_{{/if}}
{{else}}
Not available — commitments missing.
{{/if}}

## People movement

{{#if sources.ledgers.people}}
- **New:** {{#if people_movement.new}}{{join people_movement.new ", "}}{{else}}none{{/if}}
- **Steady:** {{#if people_movement.steady}}{{join people_movement.steady ", "}}{{else}}none{{/if}}
- **Gone quiet:** {{#if people_movement.gone_quiet}}{{join people_movement.gone_quiet ", "}}{{else}}none{{/if}}
{{else}}
Not available — people missing.
{{/if}}

## Watchlist for next month

{{#each next_month_watchlist}}
{{@index1}}. **{{prediction}}** `{{id}}`
   - Signal to watch: {{signal_to_watch}}
   - Falsified if: {{falsified_if}}
{{/each}}

## Suggested focus

{{#each suggested_focus_next_month}}
- {{this}}
{{/each}}

{{#if notes}}
## Notes

{{#each notes}}
- {{this}}
{{/each}}
{{/if}}

---
*Generated {{generated_at}} by notella-monthly-synthesis from {{#each weeks_covered}}{{week_link this}}{{#unless @last}}, {{/unless}}{{/each}}{{#if sources.previous_monthly}}; previous brief [{{previous_month}}](../monthly/{{previous_month}}.md){{else}}; no previous brief{{/if}}; themes {{#if sources.themes_previous}}{{date sources.themes_previous}} → {{/if}}{{#if sources.themes_current}}{{date sources.themes_current}}{{else}}none{{/if}}.*
```

## Helpers

- `{{count}}` — array length.
- `{{date path}}` — the `YYYY-MM-DD` embedded in a snapshot path.
- `{{open_total}}` — sum of the four bucket counts.
- `{{age_days d}}` — `month_end − d` in whole days, the same age the buckets were computed from.
- `{{approx_note}}` — the `notes[]` entry beginning `commitments: closed/dropped counts approximate`, when present; otherwise empty.
- `{{scorecard_tally}}` — `**{held} held · {partial} partial · {missed} missed · {unknown} unknown** of {total} forecasts.`; when `forecast_scorecard` is empty, `_No forecasts to score — first month with a brief._`
- `{{evidence_cell}}` — `review verdict — {note}` for strings beginning `verdict:` (the part after ` — `; the whole string after `verdict:` when there is no note); `dropped at review` as is; any other string with page ids and weeks linkified as in `{{narrative_linked}}`.
- `{{@index1}}` — 1-based counter.
- `{{join list sep}}` — items separated by `sep`.
- Pipes inside table cells are escaped as `\|`; newlines inside cells are replaced by a space.

The Notes section is rendered only when `notes` is non-empty, so a clean month has exactly the eight sections the SKILL.md names.

## Example (abbreviated)

```markdown
# Month in review — May 2026

_47 pages · 5 weeks · generated 2026-06-01T06:12:40Z_

## Narrative

May put 47 pages on the notebook, a third of them on Mondays, and 18 of them on aimqc — the first month it has outweighed project-state. [2026-W20](../weekly/2026-W20.md) was the hinge: the NRCAN demo scope was fixed on [2026-05-12-a3c8](../pages/2026-05-12-a3c8/) and every later week refers back to it …

## Theme arc

| Theme | Start | End | Direction | Evidence | Note |
| --- | --- | --- | --- | --- | --- |
| data-access | secondary | secondary | → held | [2026-05-05-q1w8](../pages/2026-05-05-q1w8/) | Blocked on JP Morgan in W18 and still blocked in W22; held, not healthy. |
| edge-inference | — | emerging | + new | [2026-05-20-b5t6](../pages/2026-05-20-b5t6/) | Four pages, three of them in W21. |
| sovereign-infrastructure | secondary | primary | ↑ rising | [2026-05-04-k2p9](../pages/2026-05-04-k2p9/) [2026-05-12-a3c8](../pages/2026-05-12-a3c8/) [2026-05-27-d1v4](../pages/2026-05-27-d1v4/) | Three of five weeklies name it primary; W20 ties it to the NRCAN demo scope. |

## Forecast scorecard

| Prediction | Source | Outcome | Evidence |
| --- | --- | --- | --- |
| Pharmaliga onboarding starts before month end | [monthly 2026-04 · w1](../monthly/2026-04.md#watchlist-for-next-month) | **held** | review verdict — kickoff call 2026-05-21 |
| 'edge-inference' becomes a theme | [themes 2026-05-09 · emergent 3](../longitudinal/themes.md#emergent-topics) | partial | Still listed under emergent_topics in the 2026-06-01 snapshot; 4 pages, needs 5. |

**1 held · 1 partial · 0 missed · 0 unknown** of 2 forecasts.

## Decisions

- 2026-05-02 — Treat workstreams 1, 2 and 5 as quick wins ([2026-05-02-x7k2](../pages/2026-05-02-x7k2/)) — **revisited:** 2026-W20 reopens workstream 5 as blocked on data access.

## Commitments aging

**31 open** — &lt;7d 3 · 7–30d 9 · 30–90d 14 · &gt;90d 5

| Task | Since | State |
| --- | --- | --- |
| Draft AIMQC Q1 feature roadmap for NRCAN review | 2026-01-14 (137 days) | owner_confirmed |

Closed this month: 6 · dropped: 2

## People movement

- **New:** Priya Natarajan, Tom Ekholm
- **Steady:** Alice Chen, …
- **Gone quiet:** Marcus Lind, …

## Watchlist for next month

1. **The NRCAN demo gets a dated slot in June** `2026-05-w1`
   - Signal to watch: A page in June naming a demo date, or the commitment "Schedule NRCAN demo" reaching done
   - Falsified if: No June page names a date and the commitment is still open on 2026-06-30

## Suggested focus

- Close or drop "Draft AIMQC Q1 feature roadmap for NRCAN review" — 137 days open (commitments_aging.oldest[0])

---
*Generated 2026-06-01T06:12:40Z by notella-monthly-synthesis from [2026-W18](../weekly/2026-W18.md), [2026-W19](../weekly/2026-W19.md), [2026-W20](../weekly/2026-W20.md), [2026-W21](../weekly/2026-W21.md), [2026-W22](../weekly/2026-W22.md); previous brief [2026-04](../monthly/2026-04.md); themes 2026-05-09 → 2026-06-01.*
```
