# longitudinal/themes.md — rendering template

How `notella-themes` renders a snapshot (`longitudinal/themes/{date}.json`) into markdown. Rendered deterministically on every run from the validated JSON — including the skill-written `delta` block — and written to `longitudinal/themes.md` next to the pointer copy `themes.json`, so the two can never drift apart. No model call.

**Placeholders:** `{{double-curly}}`; `{{#each}}` loops; `{{#if}}` conditionals. Empty sections render the heading followed by a single line `None.` so the md and json always carry the same section set.

## Sort orders

- Themes within each weight group: `pages_count` descending, then name.
- `emergent_topics`: `pages_count` descending.
- `fading_topics`: `last_substantive_mention` descending (most recently faded first).
- `persistent_open_questions`: `times_raised` descending, then `first_raised` ascending.
- `conceptual_evolution`: as returned.
- Delta tables: by theme name.

## Links

`{{page_link id}}` → `[{{id}}](../pages/{{id}}/)`. `{{snapshot_link path}}` → `[{{basename}}]({{path relative to longitudinal/}})`.

## Template

```markdown
# Longitudinal Themes — notella Corpus

**Generated {{generated_at}} | {{corpus_summary.pages_total}} pages | {{corpus_summary.date_range.since}} → {{corpus_summary.date_range.until}} | previous snapshot {{#if delta.previous_snapshot}}{{snapshot_link delta.previous_snapshot}}{{else}}none{{/if}}**

Top projects: {{#each corpus_summary.top_projects}}`{{this}}`{{#unless @last}}, {{/unless}}{{/each}}

## Since last refresh

{{#if delta.previous_snapshot}}
{{delta.pages_added_since}} pages added since {{delta.previous_snapshot_date}}.

**New themes:** {{#each delta.themes_new}}`{{this}}`{{#unless @last}}, {{/unless}}{{else}}none{{/each}}
**Themes gone:** {{#each delta.themes_gone}}`{{this}}`{{#unless @last}}, {{/unless}}{{else}}none{{/each}}
**Promoted from emergent:** {{#each delta.emergent_promoted}}`{{this}}`{{#unless @last}}, {{/unless}}{{else}}none{{/each}}
**Emergent dropped:** {{#each delta.emergent_dropped}}`{{this}}`{{#unless @last}}, {{/unless}}{{else}}none{{/each}}

| Theme | Weight before → after | Trajectory before → after | Pages added |
| --- | --- | --- | --- |
{{#each delta.weight_changes}}
| {{name}} | {{before_weight}} → {{after_weight}} | {{before_trajectory}} → {{after_trajectory}} | {{pages_added}} |
{{/each}}

{{#if delta_notes}}
> **Analyst notes on the delta:** {{delta_notes}}
{{/if}}
{{else}}
First snapshot — no previous refresh to compare against.
{{/if}}

## Trajectory summary

{{momentum_summary}}

## Primary themes

{{#each themes_by_weight.primary}}
### {{name}}

**{{pages_count}} pages | {{first_seen}} → {{last_seen}} | {{trajectory}}**

{{description}}

Evidence: {{#each evidence_pages}}{{page_link this}}{{#unless @last}}, {{/unless}}{{/each}}
{{#if related_themes}}Related: {{#each related_themes}}`{{this}}`{{#unless @last}}, {{/unless}}{{/each}}{{/if}}

{{/each}}
## Secondary themes

{{> theme_group themes_by_weight.secondary}}

## Emerging themes

{{> theme_group themes_by_weight.emerging}}

## Fading themes

{{> theme_group themes_by_weight.fading}}

## Emergent topics

| Topic | First seen | Pages | Why notable |
| --- | --- | --- | --- |
{{#each emergent_topics}}
| {{name}} | {{first_seen}} | {{pages_count}} | {{why_notable}} |
{{/each}}

## Fading topics

| Topic | Last substantive mention | Prior weight | Why it might matter |
| --- | --- | --- | --- |
{{#each fading_topics}}
| {{name}} | {{last_substantive_mention}} | {{prior_weight}} | {{why_fading_might_matter}} |
{{/each}}

## Persistent open questions

| Question | First raised | Times | Latest page |
| --- | --- | --- | --- |
{{#each persistent_open_questions}}
| {{question}} | {{first_raised}} | {{times_raised}} | {{page_link latest_page}} |
{{/each}}

## Conceptual evolution

{{#each conceptual_evolution}}
### {{concept}}

{{evolution_summary}}

Key pages: {{#each key_pages}}{{page_link this}}{{#unless @last}}, {{/unless}}{{/each}}

{{/each}}
---
*Snapshot {{snapshot_path}} · generated {{generated_at}} by notella-themes · `longitudinal/themes.json` is a copy of this snapshot.*
```

`{{> theme_group}}` repeats the per-theme subsection block shown under Primary themes. `themes_by_weight` is the renderer's grouping of `themes[]` by `weight`. `delta.weight_changes` is the renderer's join of `delta.weight_changed` and `delta.trajectory_changed` on theme name (a theme appearing in either gets one row; unchanged fields repeat the same value on both sides).

## Why re-render every run

The facility had a `themes.md` two days and 300 pages older than its `themes.json`. Rendering is cheap and deterministic; the rule is simply that `log-longitudinal` writes the md from the json it has just written, every time.

## Example (abbreviated)

```markdown
# Longitudinal Themes — notella Corpus

**Generated 2026-11-08T05:12:40Z | 412 pages | 2025-12-01 → 2026-05-08 | previous snapshot [2026-05-09.json](themes/2026-05-09.json)**

Top projects: `aimqc`, `atomic47`, `dante`, `a47l`, `tulevik`

## Since last refresh

37 pages added since 2026-05-09.

**New themes:** `voice-interface`
**Themes gone:** none
**Promoted from emergent:** `data-sovereignty`
**Emergent dropped:** `toronto-office`

| Theme | Weight before → after | Trajectory before → after | Pages added |
| --- | --- | --- | --- |
| data-staleness | primary → primary | steady → steady | 3 |
| data-sovereignty | emerging → secondary | rising → rising | 9 |

> **Analyst notes on the delta:** `name-matching` is kept as secondary despite 0 pages added because its footprint was absorbed by `data-staleness` pages tagged both ways.

## Trajectory summary

…
```
