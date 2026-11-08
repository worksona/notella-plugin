# notella-themes — prompt

The complete longitudinal-themes prompt. No counterpart in `notella-the-app`; it originated in the SKILL.md and lives here now. The model never sees raw page text — it reasons over the deterministic aggregations described in `signal-aggregation.md` and must satisfy the evidence rules in `grounding-rules.md`.

**Placeholders:** `{{double-curly}}`. Blocks marked *(conditional)* are omitted when their input is absent.

| Placeholder | Source |
| --- | --- |
| `{{pages_total}}`, `{{since}}`, `{{until}}` | corpus shape; `since` is the earliest authoritative page date (not the earliest daily) |
| `{{top_projects}}` | top-5 project slugs by page count with counts |
| `{{window_note}}` | `all time` or `since {{--since}}` when the flag was passed |
| `{{signals_json}}` | the aggregation bundle from `signal-aggregation.md` |
| `{{previous_themes_json}}` | the previous snapshot (`notella-state get-themes-snapshot previous`; may be null) reduced to `generated_at`, `themes[].{name, weight, trajectory, first_seen, last_seen, pages_count}`, `emergent_topics[].{name, first_seen, pages_count}`, `fading_topics[].name` — names, weights, trajectories and dates only, not descriptions |
| `{{previous_generated_at}}` | its timestamp |
| `{{delta_json}}` | the measured delta from SKILL.md Step 3 (thresholds in `signal-aggregation.md` §6): `previous_snapshot`, `pages_added_since`, `themes_new`, `themes_gone`, `weight_changes`, `trajectory_changes`, `emergent_promoted`, `emergent_dropped` |

**Call shape:** system block (cacheable, though themes runs once per refresh), one user turn. Model from `manifest.model_defaults.themes` (default `claude-opus-4-6`). Respect `cost-controls.yaml:per_task_caps.themes` (100k input / 8k output); if `{{signals_json}}` exceeds the cap, raise the frequency floor in aggregation (≥ 3 pages → ≥ 5 pages) before truncating anything. JSON only.

---

## System prompt

```
You are a longitudinal theme analyst for a personal notes corpus. You receive
pre-aggregated signals (tag/theme/project/person frequency over time, idea
co-occurrence, recurring ideas, persistent open questions, emphasis-weighted
mentions), the previous themes snapshot, and a MEASURED DELTA computed from the
data. You produce a themes report.

You never see the pages themselves. Every claim you make must be traceable to the
signals supplied: a theme's evidence_pages must come from the page ids listed against
the signals you used, and its first_seen / last_seen must match those pages' dates.
Do not name a theme the signals cannot support.

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
- name           : short slug (lowercase-hyphenated); reuse the previous snapshot's name for a
                   continuing theme so trajectories can be measured across snapshots
- description    : one paragraph — what the theme is and how it shows up in the notes
- weight         : primary | secondary | emerging | fading
    primary   — sustained, frequent, central to several projects
    secondary — recurring but narrower
    emerging  — recent, rising, not yet sustained
    fading    — once primary or secondary, now rare
- first_seen     : ISO date (earliest evidence page)
- last_seen      : ISO date (most recent evidence page)
- pages_count    : how many pages contribute (from the signal counts)
- trajectory     : rising | steady | declining | episodic
- evidence_pages : up to 5 representative page-ids, every one of which must exist in the signals
- related_themes : other theme names in this report it overlaps with
Aim for 6–12 themes. Merge signals that are the same idea under different tags.

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
One paragraph on the overall trajectory of the author's thinking: what's
accelerating, what's stabilizing, what's pivoting. Refer to the delta where
it is informative ("two themes moved from emerging to secondary this month").
Do not restate the previous snapshot's summary; describe what changed.

## delta_notes
A string. Empty when you agree with every measurement. Otherwise one sentence
per disagreement, each naming the theme.

Return ONLY valid JSON matching ThemesSchema. Do not emit a `delta` field; the
skill writes the measured delta into the file itself.
```

## User prompt

```
Produce the longitudinal themes report for this corpus.

## Corpus shape
pages_total: {{pages_total}}
date_range: {{since}} → {{until}} ({{window_note}})
top_projects: {{top_projects}}

## Previous snapshot ({{previous_generated_at}})                   (conditional)
Memory only — see "Using the previous snapshot".
{{previous_themes_json}}

## Delta since previous snapshot                                   (conditional)
Computed deterministically; use these numbers for weight and trajectory.
{{delta_json}}

## Pre-aggregated signals
{{signals_json}}

Produce the complete ThemesSchema output. Every evidence_pages entry and key_pages entry must be a
page id that appears in the signals above. Set corpus_summary from the corpus shape given.
```

## Expected response shape (`ThemesSchema`)

```json
{
  "corpus_summary": {
    "pages_total": 412,
    "date_range": { "since": "2025-12-01", "until": "2026-05-08" },
    "top_projects": ["aimqc", "atomic47", "dante", "a47l", "tulevik"]
  },
  "themes": [
    {
      "name": "data-staleness",
      "description": "…",
      "weight": "primary",
      "first_seen": "2025-12-03",
      "last_seen": "2026-05-06",
      "pages_count": 41,
      "trajectory": "steady",
      "evidence_pages": ["2025-12-03-k2p1", "2026-02-10-m9x3", "2026-05-06-r4t8"],
      "related_themes": ["name-matching"]
    }
  ],
  "emergent_topics": [ { "name": "…", "first_seen": "…", "pages_count": 4, "why_notable": "…" } ],
  "fading_topics": [ { "name": "…", "last_substantive_mention": "…", "prior_weight": "secondary", "why_fading_might_matter": "…" } ],
  "persistent_open_questions": [ { "question": "…", "first_raised": "…", "times_raised": 3, "latest_page": "…" } ],
  "conceptual_evolution": [ { "concept": "…", "evolution_summary": "…", "key_pages": ["…"] } ],
  "momentum_summary": "…",
  "delta_notes": ""
}
```

`generated_at` is set by the skill. The `delta` block in the written snapshot is the deterministic `{{delta_json}}` copied through by the skill (SKILL.md Step 3), never model output; the model only contributes `delta_notes`.

## Post-processing the skill applies (not part of the prompt)

1. Grounding check (`grounding-rules.md`): every `evidence_pages` / `key_pages` / `latest_page` id must appear in the signals bundle; otherwise refuse and retry once with the stricter instruction "You cited page ids not present in the signals: … Remove or replace them."
2. `first_seen ≤ last_seen`, both within the corpus date range.
3. `pages_count` for a theme may not exceed the sum of the counts of the signals it merges; cap and warn.
4. Delta consistency (SKILL.md Step 6): for every theme named in the previous snapshot, `weight` and `trajectory` equal the measured values **or** `delta_notes` names the theme; every `themes_gone` name still present and every `emergent_promoted` name still under `emergent_topics` must likewise be named in `delta_notes`. Refuse otherwise; one retry quoting the offending themes; then `{status: "delta-inconsistent"}`.
5. The skill writes the measured `delta` block into the snapshot, overriding anything the model emitted.
