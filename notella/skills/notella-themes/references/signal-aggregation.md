# Signal aggregation — the deterministic pre-step

Step 2 of `notella-themes`. Before any model call, the skill computes the signal bundle the model reasons over. This step is pure data work: it reads `first-pass.json`, `metadata.json`, `transcribe.json:emphasis[]`, `daily/*.json` and `weekly/*.json`, costs filesystem I/O only, and is reproducible — the same corpus yields the same bundle. The model never sees raw transcripts; everything it says must trace back to this bundle.

## 1. Corpus selection

```
pages = list-pages --phase>=indexed [--since S]
```

Each page's **authoritative date** is `metadata.date` → `transcribe.extractedDate` → `meta.source_capture_time` → `meta.ingested_at` (ISO only; non-ISO values are skipped in the chain). Pages with no first-pass artifact are excluded and counted in `corpus_summary.pages_without_first_pass`.

Buckets are **ISO weeks** (`YYYY-Www`) by default; for corpora spanning more than 40 weeks the bundle also carries **month** buckets (`YYYY-MM`) so the model can see the longer arc without a 40-column series.

## 2. Normalisation

Tags, themes, ideas and entity names are normalised before counting: NFKC, lowercase, trim, collapse whitespace/underscores to hyphens, strip trailing `s` only when the singular also appears in the corpus. Project slugs are taken from `meta.yaml:project_attributions` (canonical). People are taken from `meta.yaml:person_attributions` when present, else `metadata.json:people` as written and normalised. Aliases from `manifest.people_aliases` are collapsed.

## 3. Series

Every series is `{key: {buckets: {bucket: count}, pages: [page-id…], first_seen, last_seen, total}}`. `pages` lists every contributing page id (this is what the model may cite); when a key has more than 40 pages, `pages` is trimmed to the first 5, the last 5 and the 5 highest-emphasis, with `pages_truncated: true`.

| Series | Source field | Floor |
| --- | --- | --- |
| `tags` | `metadata.json:tags` ∪ `first-pass.json:tags[].name` (confidence ≥ 0.7) | appears in ≥ 3 pages |
| `themes` | `metadata.json:themes` | ≥ 3 pages |
| `projects` | `meta.yaml:project_attributions` | all |
| `people` | `meta.yaml:person_attributions` ∪ normalised `metadata.json:people` | ≥ 2 pages |
| `organisations` | `metadata.json:organisations` | ≥ 2 pages |
| `entities` | `first-pass.json:structural_map.entities` | ≥ 3 pages |
| `clusters` | `first-pass.json:structural_map.clusters` | ≥ 2 pages |
| `document_types` | `metadata.json:documentType` | all |
| `affect` | `sketch.json:sketches[].affective_signal` | all (small) |

Floors are raised uniformly (3 → 5 → 8) until the serialised bundle fits `per_task_caps.themes.max_input_tokens`.

## 4. Derived signals

### 4a. Emphasis weighting

For each page, `emphasis_weight = Σ intensity` over `transcribe.json:emphasis[]`, capped at 15. Each series entry also carries `weighted_total = Σ (1 + emphasis_weight/15)` over its pages. The model is told to use `weighted_total` to break ties when ranking weight — a tag on ten plain pages ranks below a tag on seven heavily starred pages.

### 4b. Idea co-occurrence

Pairs of normalised `metadata.json:ideas` (and `tags`, separately) that occur together on ≥ 2 pages: `{pair: [a, b], count, pages}`. Top 40 pairs by count. This is the raw material for `related_themes` and `conceptual_evolution`.

### 4c. Recurring ideas (value-hypothesis recurrence)

`metadata.json:ideas` strings that recur across ≥ 2 pages after normalisation and fuzzy merge (token Jaccard ≥ 0.6): `{idea, count, first_seen, last_seen, pages}`. Where legacy `first-pass.json` files still carry `value_hypotheses` (the section was removed from the current first-pass schema), hypotheses with confidence ≥ 0.7 are merged into the same series; ideas are the surviving field in new pages.

### 4d. Persistent open questions

From `first-pass.json:follow_up_queries` and `daily/*.json:unresolved_questions`, merged by fuzzy match (Jaccard ≥ 0.5 after stopword removal). A question is **resolved** if a later page's `first-pass.content_summary`, `action_intelligence[].task`, or a later daily's `new_decisions` matches it at Jaccard ≥ 0.5 and contains a resolution token (decided, agreed, resolved, answered, confirmed, done, chose, will). Unresolved questions with `times_raised ≥ 2`: `{question, first_raised, times_raised, latest_page, pages}`.

### 4e. Weekly and daily echoes

- `daily_momentum`: every `daily/*.json:momentum_signals[]` string with its date — top 60 by recency.
- `weekly_themes`: every `weekly/*.json:key_themes[]` with `{theme, weight, iso_week}`; the series of weights per theme name across weeks is the strongest trajectory evidence available and is passed in full.

### 4f. Trajectory hints (computed, not asserted)

For each series key with total ≥ 5, split the bucket range into halves (or the last 8 weeks vs the rest, whichever is shorter) and compute `recent_rate / prior_rate`:

| ratio | hint |
| --- | --- |
| ≥ 1.5 | rising |
| 0.67–1.5 | steady |
| < 0.67 | declining |
| non-zero in ≤ 40% of buckets with gaps ≥ 4 weeks | episodic (overrides) |

Hints are advisory for *new* clusters; the model may disagree but must say why in `description`. For themes that existed in the previous snapshot, the **measured** trajectory in §6c is binding (disagreement goes in `delta_notes`).

## 5. Bundle shape (`{{signals_json}}`)

```json
{
  "buckets": ["2025-W49", "…"],
  "month_buckets": ["2025-12", "…"],
  "series": {
    "tags": { "data-staleness": { "buckets": {"2025-W49": 2, "…": 1}, "total": 41, "weighted_total": 52.3, "first_seen": "2025-12-03", "last_seen": "2026-05-06", "trajectory_hint": "steady", "pages": ["…"] } },
    "themes": {}, "projects": {}, "people": {}, "organisations": {}, "entities": {}, "clusters": {}, "document_types": {}, "affect": {}
  },
  "co_occurrence": { "ideas": [ { "pair": ["…", "…"], "count": 3, "pages": ["…"] } ], "tags": [] },
  "recurring_ideas": [ { "idea": "…", "count": 4, "first_seen": "…", "last_seen": "…", "pages": ["…"] } ],
  "open_questions": [ { "question": "…", "first_raised": "…", "times_raised": 3, "latest_page": "…", "pages": ["…"] } ],
  "daily_momentum": [ { "date": "…", "signal": "…" } ],
  "weekly_themes": [ { "iso_week": "…", "theme": "…", "weight": "primary" } ],
  "page_index": { "2025-12-03-k2p1": { "date": "2025-12-03", "title": "…", "projects": ["tulevik"] } }
}
```

`page_index` gives the model a title per citable page id so `evidence_pages` can be chosen meaningfully. It is the only place page-level text appears, and it is one line per page.

## 6. Footprints and the delta against the previous snapshot

The delta is computed by rule before the model call (SKILL.md Step 3) and written into the snapshot by the skill. The previous snapshot comes from `notella-state get-themes-snapshot previous` (which migrates a legacy `longitudinal/themes.json` into `longitudinal/themes/` on first use); on a first run it is null and every list below is empty with `pages_added_since = pages_total`.

### 6a. Theme footprints

For each theme in the previous snapshot, its **footprint** is the set of page ids that support it:

```
footprint(theme) = theme.evidence_pages
                 ∪ { p : normalise(theme.name) ∈ normalise(metadata(p).themes ∪ metadata(p).tags) }
                 ∪ { p : any r ∈ theme.related_themes, normalise(r) ∈ normalise(metadata(p).themes ∪ metadata(p).tags) }
```

restricted to pages in the corpus window. Footprints are what the delta is measured on; they are also passed to the model as `footprints: {theme_name: {pages_count, pages_added_since, pages: [...]}}` so `evidence_pages` can be drawn from them.

### 6b. Measured weight (defaults; the SKILL.md states the same numbers)

| Measured weight | Rule |
| --- | --- |
| `primary` | footprint ≥ 10% of pages in window AND ≥ 1 footprint page in the last 30 days |
| `secondary` | footprint ≥ 4% of pages in window AND ≥ 1 footprint page in the last 60 days |
| `emerging` | below the `secondary` share, but ≥ 60% of its footprint pages fall in the last 60 days |
| `fading` | zero footprint pages in the last 60 days |

"Last N days" is measured back from the newest authoritative page date in the window, not from the wall clock — a corpus that stopped six months ago should not have every theme fade at once.

### 6c. Measured trajectory

Compare footprint pages in the most recent 30-day window against the 30 days before it:

| Ratio recent / prior | Trajectory |
| --- | --- |
| > 1.5 | `rising` |
| < 0.67 | `declining` |
| two or more gaps > 45 days between footprint pages | `episodic` (overrides) |
| otherwise | `steady` |

With fewer than 3 footprint pages in the two windows combined, trajectory is `steady` unless `episodic` applies.

### 6d. Theme threshold

A signal cluster (a `themes` or `tags` series key, after merging keys that normalise to the same slug) **meets the theme threshold** when it has ≥ 5 pages across ≥ 2 distinct ISO weeks.

### 6e. The delta block

```yaml
delta:
  previous_snapshot: "longitudinal/themes/2026-05-09.json"   # null on first run
  pages_added_since: 41              # pages whose ingested_at > previous.generated_at
  themes_new: [string]               # clusters meeting the theme threshold that match no previous theme name or related_themes
  themes_gone: [string]              # previous themes with zero footprint pages added since the previous snapshot AND measured weight = fading
  weight_changes:                    # previous weight → measured weight, where they differ
    - { theme: string, from: primary|secondary|emerging|fading, to: primary|secondary|emerging|fading }
  trajectory_changes:                # previous trajectory → measured trajectory, where they differ
    - { theme: string, from: rising|steady|declining|episodic, to: rising|steady|declining|episodic }
  emergent_promoted: [string]        # previous emergent_topics whose footprint now meets the theme threshold
  emergent_dropped: [string]         # previous emergent_topics with zero footprint pages added since the previous snapshot
```

Matching a previous emergent topic to current pages uses the same footprint construction as 6a with `related_themes = []`.

The delta is passed to the model as `{{delta_json}}` (the model must agree with it or explain in `delta_notes`, see `themes-prompt.md`) and copied verbatim into the written snapshot so weight changes are auditable without re-running. `--dry-run` stops after this step and prints it.

## 7. Output of this step

`signals_json`, `delta_json`, and a `pipeline.ndjson` line: `{actor: notella-themes, step: aggregate, pages, series_counts: {…}, floors: {…}, bundle_tokens_est, previous_snapshot}`. The orchestrator's report shows `bundle_tokens_est` so a themes run that is about to blow the cap is visible before the Opus call.
