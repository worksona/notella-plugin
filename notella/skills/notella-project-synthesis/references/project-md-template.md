# projects/{slug}/{date}.md — rendering template

How `notella-project-synthesis` renders `projects/{slug}/{date}.json` into the matching `.md`. Deterministic: same JSON → same markdown. No model call. The brief opens with the momentum paragraph as its executive summary, then says what moved since the previous brief before re-stating the full picture.

**Placeholders:** `{{double-curly}}`; `{{#each}}` loops; `{{#if}}` conditionals. Empty arrays render `_None._` under their heading.

## Sort orders

- `commitments_assessment`: status blocked → at_risk → on_track, then as returned.
- `since_last.commitments_changed`: retired rows (`to_status` done → dropped → removed) first, then status changes in the order of `commitments_assessment`.
- `since_last.new_drift_signals`: as returned.
- `next_actions`: priority high → medium → low, then as returned.
- `drift_signals`, `blockers`: as returned.

## Markers

| status / priority | marker |
| --- | --- |
| blocked / high | `[!!]` |
| at_risk / medium | `[!]` |
| on_track / low | `[ ]` |

| overall_risk_level | badge |
| --- | --- |
| low | `LOW` |
| moderate | `MODERATE` |
| high | `HIGH` |
| critical | `CRITICAL` |

| risk_delta | arrow |
| --- | --- |
| up | `↑ up` |
| same | `→ same` |
| down | `↓ down` |

## Page links

Evidence strings that contain a page id (`YYYY-MM-DD-xxxx`) or a date that matches exactly one page in the bundle get the id turned into `[id](../../pages/{{id}}/)`. Otherwise evidence is rendered as plain text. Evidence strings beginning `verdict:` render as `{note} (review verdict)` — the part after ` — `, or the whole remainder when there is no note — with no page link.

## Template

```markdown
# {{project_name}} — project brief {{date}}

**{{pages_analyzed}} pages** · {{since}} → {{until}} · overall risk **{{badge overall_risk_level}}** · generated {{generated_at}}

{{momentum_assessment}}

## Since last brief{{#if since_last}} ({{since_last.previous_brief_date}}){{/if}}

{{#if since_last}}
{{since_last.note}}

- Pages added: {{since_last.pages_added}}
- Risk: {{badge previous_risk_level}} → {{badge overall_risk_level}} ({{arrow since_last.risk_delta}})
- Commitments changed:
{{#each since_last.commitments_changed}}
  - {{commitment}}: {{from_status}} → {{to_status}} — {{linkify_or_verdict evidence}}
{{/each}}
- New drift signals:
{{#each since_last.new_drift_signals}}
  - {{linkify this}}
{{/each}}
{{else}}
First brief for this project; no predecessor.
{{/if}}

## Timeline

{{timeline_summary}}

## Commitments

| | Commitment | Owner | Status | Evidence |
| --- | --- | --- | --- | --- |
{{#each commitments_assessment}}
| {{marker status}} | {{commitment}} | {{owner_or_dash}} | {{status}} | {{linkify evidence}} |
{{/each}}

## Drift Signals

{{#each drift_signals}}
- {{linkify this}}{{#if (in ../since_last.new_drift_signals this)}} _(new)_{{/if}}
{{/each}}

## Blockers

{{#each blockers}}
- {{this}}
{{/each}}

## Next Actions

{{#each next_actions}}
- {{marker priority}} {{action}}{{#if owner}} — _{{owner}}_{{/if}}
{{/each}}

## Risk Summary

{{risk_summary}}

---
*Generated {{generated_at}} by notella-project-synthesis from {{pages_analyzed}} pages: {{#each page_ids}}[{{this}}](../../pages/{{this}}/){{#unless @last}}, {{/unless}}{{/each}}{{#if since_last}}; previous brief [{{since_last.previous_brief_date}}](./{{since_last.previous_brief_date}}.md){{/if}}.*
```

## Helpers

- `owner_or_dash` renders `—` when `owner` is absent.
- `previous_risk_level` is read by the renderer from `projects/{slug}/{since_last.previous_brief_date}.json:overall_risk_level` (the JSON does not repeat it; `risk_delta` is derived from it).
- `linkify_or_verdict` — `linkify` for ordinary evidence; for strings beginning `verdict:`, `{note} (review verdict)`.
- Within "Commitments changed", a `to_status` of `done`, `dropped` or `removed` means the commitment no longer appears in the Commitments table below; the row here is its last appearance.
- "Commitments changed" and "New drift signals" render `  - none` as their single sub-bullet when the array is empty, so the four bullets of the section are always present.
- `in list x` — true when `x` is an element of `list`; the Drift Signals section marks the entries `since_last.new_drift_signals` names.
- Pipes inside table cells are escaped as `\|`.

## Index file

After writing the dated brief, also rewrite `projects/{slug}/README.md` (not `latest.md` — GitHub and the desktop app both render a README by default):

```markdown
# {{project_name}}

Latest brief: [{{date}}]({{date}}.md) — risk {{badge overall_risk_level}}{{#if since_last}} ({{arrow since_last.risk_delta}} since {{since_last.previous_brief_date}}){{/if}}, {{pages_analyzed}} pages.

| Date | Risk | Δ | Pages | +Pages | Blockers | Open commitments | Changed |
| --- | --- | --- | --- | --- | --- | --- | --- |
{{#each briefs_desc}}
| [{{date}}]({{date}}.md) | {{badge overall_risk_level}} | {{#if since_last}}{{arrow since_last.risk_delta}}{{else}}—{{/if}} | {{pages_analyzed}} | {{#if since_last}}{{since_last.pages_added}}{{else}}—{{/if}} | {{blockers_count}} | {{open_commitments_count}} | {{#if since_last}}{{count since_last.commitments_changed}}{{else}}—{{/if}} |
{{/each}}
```

`open_commitments_count` is the number of commitments with status other than `on_track`. Briefs that predate `since_last` show `—` in the delta columns. The table gives the project's risk trajectory at a glance without opening each brief.

## Example (abbreviated)

```markdown
# Tulevik — project brief 2026-05-02

**14 pages** · 2026-04-12 → 2026-05-02 · overall risk **HIGH** · generated 2026-05-02T19:05:54Z

Momentum is decelerating: pages per week held at three through April, but the dashboard is now blocked on legal and the only movement since 2026-04-25 is the accuracy numbers going out …

## Since last brief (2026-04-25)

The dashboard went from on track to blocked on legal, which is what moved risk from moderate to high.

- Pages added: 5
- Risk: MODERATE → HIGH (↑ up)
- Commitments changed:
  - Send the April accuracy numbers to Alice: at_risk → done — sent 2026-04-30 (review verdict)
  - Deliver staleness dashboard to JP Morgan contact: on_track → blocked — "no access until legal signs" — [2026-04-28-m2q7](../../pages/2026-04-28-m2q7/)
- New drift signals:
  - Dashboard scope now includes a freshness SLA that the April plan did not mention ([2026-05-01-h8s3](../../pages/2026-05-01-h8s3/))

## Timeline

Started as a data-staleness probe in early December; the name-matching layer landed in February …

## Commitments

| | Commitment | Owner | Status | Evidence |
| --- | --- | --- | --- | --- |
| [!!] | Deliver staleness dashboard to JP Morgan contact | David | blocked | waiting on data access, 2026-04-28 ([2026-04-28-m2q7](../../pages/2026-04-28-m2q7/)) |
| [ ] | Weekly name-matching accuracy report | — | on_track | no new evidence since 2026-04-25 |

## Drift Signals

- Dashboard scope now includes a freshness SLA that the April plan did not mention ([2026-05-01-h8s3](../../pages/2026-05-01-h8s3/)) _(new)_

…

---
*Generated 2026-05-02T19:05:54Z by notella-project-synthesis from 14 pages: …; previous brief [2026-04-25](./2026-04-25.md).*
```
