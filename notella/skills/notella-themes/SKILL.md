---
name: notella-themes
description: "Detect longitudinal themes across the entire notella corpus — recurring patterns, momentum shifts, emergent topics, fading concerns, conceptual evolution. Use whenever the user says 'what themes have been recurring', 'longitudinal patterns', 'what's emerging', 'show theme trajectory', 'refresh themes', or any request to identify patterns across all pages. Cadence-driven (default weekly). Reads through `notella-state`; writes `longitudinal/themes.json`. Emits `themes.refreshed` event."
---

# notella-themes — the longitudinal pattern detector

The deepest synthesis layer. Looks across the entire page corpus and identifies what's recurring, what's emerging, what's fading, and how concepts are evolving.

## Purpose

Daily and weekly briefs are time-bounded. Themes ignore the calendar and ask: across everything you've written down, what patterns are durable? What was once peripheral and is now central? What was central and has gone quiet? Where is your thinking actually going?

This is the layer that makes the long-term value of the corpus visible.

## Inputs and outputs

**Input:** Optional `--since` (default: all time). Reads:
- Every `pages/*/first-pass.json` (the structural_map, value_hypotheses, tags, follow_up_queries are the primary signals)
- Every `pages/*/metadata.json` (themes, ideas, projects fields)
- Every `daily/*.json` (momentum_signals already detected per day)
- Every `weekly/*.json` (key_themes already detected per week)

**Output:**
- `longitudinal/themes.json`
- `themes.refreshed` event
- `state.json:last_longitudinal_at` updated

## How a run executes

### Step 1 — Read configuration & corpus

```
notella-state get-manifest → manifest.model_defaults.themes, manifest.bootstrap_themes
notella-state list-pages --phase=archived
notella-state list-dailies
notella-state list-weeklies
```

Build the corpus bundle. For large corpora, use a sampling strategy: every page's themes/tags/value_hypotheses summary, but not the full first-pass body.

### Step 2 — Pre-aggregate signals computationally

Before calling the model, compute deterministic aggregations cheaply:

- **Tag frequency over time** — `{tag: [(week, count)]}` for every tag that appears in ≥ 3 pages.
- **Theme frequency over time** — same for themes.
- **Project mention frequency over time** — same.
- **Person mention frequency over time** — same.
- **Idea co-occurrence** — pairs of ideas that appear in the same page ≥ 2 times.
- **Value hypothesis recurrence** — hypotheses with high confidence that appear in multiple pages.
- **Follow-up query persistence** — questions raised that have not been resolved in subsequent pages.

These aggregations form the input bundle the model reasons over.

### Step 3 — Build the prompt

System prompt:

```
You are a longitudinal theme analyst for a personal notes corpus. You receive
pre-aggregated signals (tag/theme/project/person frequency over time, idea
co-occurrence, recurring hypotheses, persistent open questions) and produce a
themes report.

Your output covers:

## themes (array)
Each theme is a coherent pattern visible across multiple pages over time:
- name: short slug (lowercase-hyphenated)
- description: one paragraph
- weight: primary | secondary | emerging | fading
- first_seen: ISO date (earliest evidence)
- last_seen: ISO date (most recent evidence)
- pages_count: how many pages contribute
- trajectory: rising | steady | declining | episodic
- evidence_pages: up to 5 representative page-ids
- related_themes: other theme names this overlaps with

## emergent_topics (array)
Topics that have appeared recently but aren't yet developed enough to be themes:
- name, first_seen, pages_count, why_notable

## fading_topics (array)
Topics that were once prominent and have gone quiet:
- name, last_substantive_mention, prior_weight, why_fading_might_matter

## persistent_open_questions (array)
Follow-up queries that have been raised across multiple pages without resolution:
- question, first_raised, times_raised, latest_page

## conceptual_evolution (array)
Cases where a concept has been reformulated or extended over time:
- concept, evolution_summary, key_pages

## momentum_summary
One paragraph on the overall trajectory of the user's thinking: what's
accelerating, what's stabilizing, what's pivoting.

Return ONLY valid JSON matching ThemesSchema.
```

User prompt: include the pre-aggregated signals as JSON, plus a short summary of the corpus shape (pages_total, date range, top-5 most common projects).

### Step 4 — Call the model

Default: `claude-opus-4-6`.

### Step 5 — Validate

```yaml
generated_at: ISO-8601
corpus_summary:
  pages_total: int
  date_range: { since, until }
  top_projects: [string]
themes:
  - name, description, weight, first_seen, last_seen, pages_count, trajectory, evidence_pages, related_themes
emergent_topics:
  - name, first_seen, pages_count, why_notable
fading_topics:
  - name, last_substantive_mention, prior_weight, why_fading_might_matter
persistent_open_questions:
  - question, first_raised, times_raised, latest_page
conceptual_evolution:
  - concept, evolution_summary, key_pages
momentum_summary: string
```

### Step 6 — Write & emit event

```
notella-state log-longitudinal {kind: themes, json}
```

Updates `state.json:last_longitudinal_at`. Emits `themes.refreshed` event.

## Idempotency

Each run overwrites `longitudinal/themes.json`. The activity log preserves the history of every refresh — you can always see how the themes view changed over time by tailing `activity.ndjson`.

## Failure modes

| Failure                                                | Behavior |
| ------------------------------------------------------ | -------- |
| Corpus too small (< 10 pages)                          | Run anyway; the output is sparse; this is correct. |
| Massive corpus (1000+ pages)                           | Use the sampling/aggregation pre-step; the model never sees raw page text directly. |
| Model produces themes not grounded in `evidence_pages` | Refuse the write; one retry with stricter grounding instructions. |

## What this skill does NOT do

- Does not modify any pages.
- Does not write to `manifest.bootstrap_themes`. New theme names surface in `longitudinal/themes.json` and the user can promote them by hand.
- Does not produce daily or weekly outputs — those are separate skills.
- Does not run cheaply: opus-grade synthesis over the full corpus. Cadence default is weekly.

## Examples

### "Refresh themes"

```
Reading corpus: 247 pages from 2026-01-04 to 2026-05-02
Pre-aggregating signals: 89 tags, 31 themes, 12 projects, 23 people
Synthesizing with claude-opus-4-6...
Generated longitudinal/themes.json:
- 8 primary themes
- 4 emergent topics
- 2 fading topics
- 6 persistent open questions
- 3 conceptual evolutions tracked
themes.refreshed event emitted.
```

### "Themes since 2026-04-01"

Restricts the input window. Useful for "what have I been thinking about lately".

## Reference files

- `references/themes-prompt.md` — full prompt.
- `references/signal-aggregation.md` — the deterministic pre-aggregation rules.
- `references/grounding-rules.md` — what counts as evidence for a theme vs an unsupported inference.
