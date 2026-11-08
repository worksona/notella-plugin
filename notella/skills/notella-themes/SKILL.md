---
name: notella-themes
description: "Detect longitudinal themes across the entire notella corpus — recurring patterns, momentum shifts, emergent topics, fading concerns, conceptual evolution — and measure how they moved since the last refresh. Use whenever the user says 'what themes have been recurring', 'longitudinal patterns', 'what's emerging', 'show theme trajectory', 'refresh themes', 'what changed in the themes', or any request to identify patterns across all pages. Cadence-driven (monthly, orchestrator Step 6; `--themes-now` forces). Reads through `notella-state`; writes a dated snapshot `longitudinal/themes/{date}.json`, copies it to `longitudinal/themes.json`, re-renders `longitudinal/themes.md`. Emits `themes.refreshed` event."
---

# notella-themes — the longitudinal pattern detector

The deepest synthesis layer. Looks across the entire page corpus and identifies what's recurring, what's emerging, what's fading, and how concepts are evolving — and, because every refresh is kept as a dated snapshot, it can say *measurably* what changed since last time instead of asserting it.

## Purpose

Daily and weekly briefs are time-bounded. Themes ignore the calendar and ask: across everything you've written down, what patterns are durable? What was once peripheral and is now central? What was central and has gone quiet? Where is your thinking actually going?

Two things make this layer trustworthy rather than merely eloquent:

1. **History.** Each run writes `longitudinal/themes/{YYYY-MM-DD}.json`. `longitudinal/themes.json` is only the latest copy. A transition like "emergent → primary" is visible as a diff between two files, not a sentence the model chose to write.
2. **A deterministic delta.** Before the model is called, the skill compares the pre-aggregated signals against the previous snapshot and computes a `delta` block. The model receives the delta and must agree with it or explain, in `delta_notes`, why it disagrees.

This is the layer that makes the long-term value of the corpus visible, and the monthly brief (`notella-monthly-synthesis`) reads two snapshots side by side to build its `theme_arc`.

## Inputs and outputs

**Input:** Optional flags:
- `--since YYYY-MM-DD` — narrows the corpus window. **Default: all pages, from the earliest page's authoritative date.** The authoritative date is resolved exactly as `notella-daily-synthesis` does it: `metadata.json:date` → `transcribe.json:extractedDate` → `meta.yaml:source_capture_time` → `meta.yaml:ingested_at`. The window never starts later than the earliest page unless `--since` says so. (A snapshot that reports `date_range.since` after the earliest page date is a validation failure — see Step 6.)
- `--themes-now` — force a refresh regardless of cadence (passed through by the orchestrator).
- `--dry-run` — compute the pre-aggregation and the delta, print them, do not call the model or write anything.

Reads:
- Every `pages/*/first-pass.json` (the structural_map, value_hypotheses, tags, follow_up_queries are the primary signals)
- Every `pages/*/metadata.json` (themes, ideas, projects, people fields)
- Every `daily/*.json` (momentum_signals already detected per day)
- Every `weekly/*.json` (key_themes already detected per week, including `prior_weight` / `weeks_active` where present)
- The previous snapshot from `longitudinal/themes/` (via `notella-state get-themes-snapshot previous`; may be null on the first run)

**Output:**
- `longitudinal/themes/{YYYY-MM-DD}.json` — the dated snapshot (date = run date in `identity.timezone`)
- `longitudinal/themes.json` — byte-identical copy of the snapshot (latest pointer; the path every other tool reads)
- `longitudinal/themes.md` — rendered from the json on **every** run
- `themes.refreshed` event
- `state.json:last_longitudinal_at` updated (unchanged behaviour)

## How a run executes

### Step 1 — Read configuration, corpus, and previous snapshot

```
notella-state get-manifest → cost-controls.yaml:model_defaults.themes, manifest.bootstrap_themes, identity.timezone
notella-state list-pages --phase=archived      # plus --since when given
notella-state list-dailies
notella-state list-weeklies
notella-state get-themes-snapshot previous     # null on first run
```

Resolve the window: `since = --since or min(authoritative_date over all pages)`; `until = max(authoritative_date)`.

**First run after this version** (no `longitudinal/themes/` directory, but a legacy `longitudinal/themes.json` exists): treat the legacy file as the previous snapshot. `notella-state get-themes-snapshot previous` performs this migration — it copies the legacy file to `longitudinal/themes/{its generated_at date}.json` before returning it — so the first delta is measured against the last overwritten refresh rather than against nothing.

Build the corpus bundle. For large corpora, use a sampling strategy: every page's themes/tags/value_hypotheses summary, but not the full first-pass body.

### Step 2 — Pre-aggregate signals computationally

Before calling the model, compute deterministic aggregations cheaply:

- **Tag frequency over time** — `{tag: [(week, count)]}` for every tag that appears in ≥ 3 pages.
- **Theme frequency over time** — same for `metadata.json:themes`.
- **Project mention frequency over time** — same.
- **Person mention frequency over time** — same.
- **Idea co-occurrence** — pairs of ideas that appear in the same page ≥ 2 times.
- **Value hypothesis recurrence** — hypotheses with high confidence that appear in multiple pages.
- **Follow-up query persistence** — questions raised that have not been resolved in subsequent pages.
- **Theme footprints** — for each theme in the previous snapshot, the set of page-ids that support it: its `evidence_pages` plus every page whose `metadata.json:themes` or tags match the theme name or any of its `related_themes`. Footprints are what the delta is measured on.

These aggregations form the input bundle the model reasons over.

### Step 3 — Compute the delta (deterministic, before the model)

Compare the footprints and signals against the previous snapshot. Every field below is computed by rule, never by the model. Thresholds live in `references/signal-aggregation.md`; the defaults are stated here so the skill is self-sufficient.

**Measured weight** of a theme, from its footprint within the window:

| Measured weight | Rule |
| --------------- | ---- |
| `primary`       | footprint ≥ 10% of pages in window AND ≥ 1 footprint page in the last 30 days |
| `secondary`     | footprint ≥ 4% of pages in window AND ≥ 1 footprint page in the last 60 days |
| `emerging`      | below `secondary` share, but ≥ 60% of its footprint pages fall in the last 60 days |
| `fading`        | zero footprint pages in the last 60 days |

**Measured trajectory**: compare footprint pages in the most recent 30-day window against the 30 days before it — `rising` (> 1.5×), `declining` (< 0.67×), `episodic` (two or more gaps > 45 days between footprint pages), else `steady`.

```yaml
delta:
  previous_snapshot: "longitudinal/themes/2026-05-09.json"   # null on first run
  pages_added_since: 41                                       # pages whose ingested_at > previous.generated_at
  themes_new: [string]            # signal clusters (theme/tag with ≥ 5 pages across ≥ 2 distinct weeks) matching no previous theme name or related_themes
  themes_gone: [string]           # previous themes with zero footprint pages added since the previous snapshot AND measured weight = fading
  weight_changes:                 # previous weight → measured weight, where they differ
    - { theme: string, from: primary|secondary|emerging|fading, to: primary|secondary|emerging|fading }
  trajectory_changes:             # previous trajectory → measured trajectory, where they differ
    - { theme: string, from: rising|steady|declining|episodic, to: rising|steady|declining|episodic }
  emergent_promoted: [string]     # previous emergent_topics whose footprint now meets the theme threshold (≥ 5 pages across ≥ 2 distinct weeks)
  emergent_dropped: [string]      # previous emergent_topics with zero footprint pages added since the previous snapshot
```

On the first run (`previous_snapshot: null`) every list is empty and `pages_added_since` equals `pages_total`.

`--dry-run` stops here and prints the delta.

### Step 4 — Build the prompt

System prompt:

```
You are a longitudinal theme analyst for a personal notes corpus. You receive
pre-aggregated signals (tag/theme/project/person frequency over time, idea
co-occurrence, recurring hypotheses, persistent open questions), the previous
themes snapshot, and a MEASURED DELTA computed from the data. You produce a
themes report.

The delta is ground truth about movement. For every theme that existed in the
previous snapshot, your `weight` and `trajectory` must equal the measured
values in the delta. If you believe the measurement is wrong for a theme
(for example, a theme was renamed, or its footprint is polluted by a tag that
means something else), keep YOUR value and explain the disagreement, naming
the theme, in `delta_notes`. A disagreement without an explanation is an error.
Themes listed in `themes_gone` may only be kept if `delta_notes` says why.
Topics listed in `emergent_promoted` should appear in `themes`, not in
`emergent_topics`, unless `delta_notes` says why not.

Your output covers:

## themes (array)
Each theme is a coherent pattern visible across multiple pages over time:
- name: short slug (lowercase-hyphenated); reuse the previous snapshot's name for a continuing theme
- description: one paragraph
- weight: primary | secondary | emerging | fading
- first_seen: ISO date (earliest evidence)
- last_seen: ISO date (most recent evidence)
- pages_count: how many pages contribute
- trajectory: rising | steady | declining | episodic
- evidence_pages: up to 5 representative page-ids, every one of which must exist
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
accelerating, what's stabilizing, what's pivoting. Refer to the delta where
it is informative ("two themes moved from emerging to secondary this month").

## delta_notes
A string. Empty when you agree with every measurement. Otherwise one sentence
per disagreement, each naming the theme.

Return ONLY valid JSON matching ThemesSchema. Do not emit a `delta` field; the
skill writes the measured delta into the file itself.
```

User prompt: the pre-aggregated signals as JSON, the `delta` block as JSON, the previous snapshot's `themes` / `emergent_topics` / `fading_topics` (names, weights, trajectories, first/last seen only — not descriptions), plus a short summary of the corpus shape (pages_total, date range, top-5 most common projects).

### Step 5 — Call the model

Runs on the model in `cost-controls.yaml` `model_defaults.themes` (currently `opus`, chosen by the 2026-11-08 eval: whole-corpus pattern reasoning, monthly). When the orchestrator runs this stage it dispatches a subagent with that model; run directly, it uses the session model.

### Step 6 — Validate

```yaml
schema_version: "0.2.0"
generated_at: ISO-8601
corpus_summary:
  pages_total: int
  date_range: { since, until }          # since == min(authoritative_date) unless --since narrowed it
  top_projects: [string]
delta:                                  # written by the skill from Step 3, overriding anything the model emitted
  previous_snapshot, pages_added_since, themes_new, themes_gone,
  weight_changes, trajectory_changes, emergent_promoted, emergent_dropped
delta_notes: string
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

Checks, in order; any failure refuses the write and allows exactly one retry with stricter instructions:

1. **Grounding** — every id in `themes[].evidence_pages`, `conceptual_evolution[].key_pages`, and `persistent_open_questions[].latest_page` exists (`notella-state get-page` returns a record).
2. **Window** — `corpus_summary.date_range.since` equals the resolved `since`.
3. **Delta consistency** — for every theme whose name is in the previous snapshot: `weight` equals the measured weight and `trajectory` equals the measured trajectory, OR `delta_notes` contains the theme's name. Every name in `themes_gone` that is still present, and every name in `emergent_promoted` still listed under `emergent_topics`, must likewise be named in `delta_notes`.

### Step 7 — Render the markdown

Rendered deterministically from the validated json, every run. Sections, in order:

```
# Longitudinal Themes — notella Corpus
**Generated {generated_at} | {pages_total} pages | {since} → {until} | previous snapshot {previous_snapshot or "none"}**

## Since last refresh                    ← the delta: pages added, new / gone, weight & trajectory tables, promoted / dropped; then delta_notes verbatim
## Trajectory summary                    ← momentum_summary
## Primary themes                        ← one subsection per theme: "**{pages_count} pages | {first_seen} → {last_seen} | {trajectory}**", description, evidence page-ids, related
## Secondary themes
## Emerging themes
## Fading themes
## Emergent topics                       ← table: name, first_seen, pages, why_notable
## Fading topics                         ← table: name, last mention, prior weight, why it might matter
## Persistent open questions             ← table: question, first raised, times, latest page
## Conceptual evolution
```

Empty sections are rendered with a single line "None." so the md and json always carry the same section set.

### Step 8 — Write & emit event

```
notella-state log-longitudinal {kind: themes, json, md}
```

`log-longitudinal` writes `longitudinal/themes/{YYYY-MM-DD}.json` (atomic tmp + rename), copies it to `longitudinal/themes.json` (atomic), writes `longitudinal/themes.md`, updates `state.json:last_longitudinal_at`, and emits `themes.refreshed` with evidence:

```json
{
  "pages_total": 412,
  "date_range": { "since": "2025-12-01", "until": "2026-05-08" },
  "themes_count": 10, "emergent_count": 4, "fading_count": 2,
  "snapshot_path": "longitudinal/themes/2026-06-01.json",
  "previous_snapshot": "longitudinal/themes/2026-05-09.json",
  "delta_counts": {
    "pages_added_since": 41, "themes_new": 1, "themes_gone": 0,
    "weight_changes": 3, "trajectory_changes": 2,
    "emergent_promoted": 1, "emergent_dropped": 2
  },
  "model": "claude-opus-5-5"
}
```

## Idempotency

- One snapshot per calendar day: a second run on the same date overwrites `longitudinal/themes/{today}.json` and the latest copy; the previous-day snapshot is untouched, so the history stays one-per-refresh-day.
- `longitudinal/themes.json` and `themes.md` are always regenerated from the snapshot just written — they can never be newer or older than it.
- The activity log and `events/` preserve every refresh; the snapshots preserve every result.
- Re-running with no pages added since the previous snapshot is allowed (`--themes-now`) and yields a delta with `pages_added_since: 0`; the orchestrator does not schedule such a run.

## Cadence

Monthly. The orchestrator (Step 6 — Longitudinal refresh) invokes this skill when `state.last_longitudinal_at` is null or more than 30 days old; the scheduled monthly task runs `/notella-themes --themes-now` on the 1st, followed by `/notella-monthly-synthesis --month last`, which needs the fresh snapshot and the one before it. Weekly refreshes re-detect the same themes and spend compute for noise; if you want "what have I been thinking about lately", run with `--since` instead.

## Failure modes

| Failure                                                | Behavior |
| ------------------------------------------------------ | -------- |
| Corpus too small (< 10 pages)                          | Run anyway; the output is sparse; this is correct. |
| Massive corpus (1000+ pages)                           | Use the sampling/aggregation pre-step; the model never sees raw page text directly. |
| Model produces themes not grounded in `evidence_pages` | Refuse the write; one retry with stricter grounding instructions. Still failing → `{status: "ungrounded"}`, nothing written. |
| Model's weight/trajectory disagrees with the delta without a `delta_notes` entry | Refuse the write; one retry quoting the offending themes. Still failing → `{status: "delta-inconsistent"}`, nothing written. |
| `corpus_summary.date_range.since` later than the earliest page | Refuse the write; the window is computed by the skill, so this indicates the model rewrote it — one retry. |
| No previous snapshot and no legacy `themes.json`        | First run: `delta.previous_snapshot: null`, all lists empty. Normal. |
| Previous snapshot unparseable                          | Proceed with `previous_snapshot: null`, record the path and error in `delta_notes`, surface in the report. |
| Markdown render fails                                   | Refuse the whole write (json and md are written together); never leave the md stale relative to the json. |

## What this skill does NOT do

- Does not modify any pages.
- Does not write to `manifest.bootstrap_themes`. New theme names surface in the snapshot and the user can promote them by hand.
- Does not produce daily, weekly or monthly outputs — those are separate skills. The monthly brief reads two snapshots; this skill does not read the monthly.
- Does not delete or rewrite earlier snapshots in `longitudinal/themes/`. History is append-only; a bad refresh is superseded by the next one and recorded in the event stream.
- Does not run cheaply: opus-grade synthesis over the full corpus (~$1.80 per refresh at current estimates). Cadence is monthly.
- Does not invent movement. Weight and trajectory changes are measured; the model's job is to describe and, where it must, dispute them.

## Examples

### "Refresh themes"

```
Reading corpus: 453 pages from 2025-12-01 to 2026-06-01
Previous snapshot: longitudinal/themes/2026-05-09.json (412 pages)
Pre-aggregating signals: 94 tags, 33 themes, 15 projects, 24 people
Delta: +41 pages | new 1 (project-state-governance) | gone 0 |
       weight changes 3 | trajectory changes 2 |
       emergent promoted 1 (ascencion-governance-framework) | emergent dropped 2
Synthesizing with claude-opus-5-5...
Validated: grounding ✓ window ✓ delta consistency ✓ (delta_notes: 1 disagreement, explained)
Wrote longitudinal/themes/2026-06-01.json → copied to longitudinal/themes.json
Rendered longitudinal/themes.md
- 11 themes (6 primary, 3 secondary, 2 emerging)
- 3 emergent topics
- 2 fading topics
- 6 persistent open questions
- 3 conceptual evolutions tracked
themes.refreshed event emitted.
```

### "Themes since 2026-04-01"

Restricts the input window. Useful for "what have I been thinking about lately". The snapshot records `date_range.since: 2026-04-01`, and the delta is still measured against the previous snapshot — expect many `fading` measurements for themes whose footprint predates the window; that is the window talking, not the corpus.

### "What changed in the themes?"

Read-only. `notella-state get-themes-snapshot latest` and print its `delta` and `delta_notes`. No model call.

## Reference files

- `references/themes-prompt.md` — full prompt.
- `references/signal-aggregation.md` — the deterministic pre-aggregation rules, footprint construction, and the delta thresholds (measured weight / trajectory, theme threshold, gone / dropped rules).
- `references/grounding-rules.md` — what counts as evidence for a theme vs an unsupported inference.
- `references/themes-md-template.md` — markdown rendering.
