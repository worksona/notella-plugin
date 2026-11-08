# Candidate extraction — the deterministic pre-pass

`scripts/extract_candidates.py` turns the facility into a ranked list of candidate statements. It never decides what a principle is; it decides what is worth a look and counts it. Stdlib only, Python 3.9+.

```
python3 "$CLAUDE_PLUGIN_ROOT/skills/notella-principles/scripts/extract_candidates.py" \
  [--nl-dir DIR]        # default $NL_DIR, else ~/notella
  [--out FILE]          # default stdout; written atomically (tmp + rename)
  [--typed-only]        # ignore untyped (bare string) emphasis spans
  [--min-tokens 2]      # label filter threshold
  [--jaccard 0.6]       # clustering threshold
  [--top N]             # emit only the top N clusters (stats still cover all)
```

## 1. Page set

Every directory under `pages/`. A page whose `meta.yaml` has a non-empty `duplicate_of:` is skipped (counted in `stats.pages_duplicate_skipped`). Page date = `metadata.json:date` when it is ISO `YYYY-MM-DD…`, else the page id's prefix. `corpus.since/until` are the min/max page dates.

## 2. Sources

| Source | What becomes a candidate | Page evidence |
|---|---|---|
| `transcribe.json` `emphasis[]`, typed span (`{span_text, mark_type, intensity}`) | `span_text` when `intensity ≥ 2` **or** `mark_type ∈ {star, box, double-underline, circle}` | that page |
| `transcribe.json` `emphasis[]`, untyped span (bare string) | the string; flagged `typed: false` | that page |
| `weekly/*.json` `ideas_and_insights[]` | the idea text | none (ref `weekly/<week>.json`) |
| `longitudinal/themes/*.json`, `longitudinal/themes.json` `conceptual_evolution[]` | `concept` (deduplicated across snapshots by concept + key_pages) | its existing `key_pages` |

Typed spans that fail the gate are counted in `spans_gated_out`. Untyped spans have no mark or intensity to gate on; they are included because otherwise whole months (Feb–Apr 2026 on this facility) contribute nothing.

## 3. Normalisation

1. Unicode NFKD, strip combining marks, lowercase.
2. `→` and `->` become " to ", `&` becomes " and ", `≠` becomes " not ".
3. Everything but `[a-z0-9 ]` becomes a space; collapse whitespace.
4. Content tokens = tokens not in the stop list and not pure digits, lightly stemmed (`-ies → -y`, trailing `-s` dropped on tokens longer than 3 that do not end in `-ss`).

## 4. Filters (in order; first match drops the item and is counted)

| Reason | Rule |
|---|---|
| `empty` | nothing left after normalisation |
| `date` | the whole text is a date, weekday, month, quarter, week number or year |
| `numeric` | only digits, currency, %, separators, `k`/`m`, `x` |
| `names` | every non-stopword token is a known name: `people.ndjson` name/canonical/aliases, `manifest.yaml` project slugs and names, every `metadata.json` people / projects / organizations value (and their single tokens) |
| `label` | fewer than `--min-tokens` alphabetic content tokens |
| `owned-task` | a task verb (send, call, email, schedule, review, draft, submit, fix, update, …) in the first three words **and** an owner marker: `Name:` / `Name –` prefix, `@handle`, trailing `(Name)` or `→ Name`, a checkbox / TODO, or a known name followed by "to" or a task verb |

## 5. Clustering

Items are ordered by how often their exact normalisation occurs (most frequent first), then alphabetically. Each item joins the first existing cluster whose representative (seed) normalisation is identical or whose content-token set has **Jaccard ≥ 0.6** with the item's; otherwise it seeds a new cluster. Greedy and order-stable: same input, same clusters.

## 6. Output

```yaml
schema_version: "0.1.0"
generator: notella-principles@0.1.0
generated_at: ISO-8601
nl_dir: path
params: { typed_only, min_tokens, jaccard }
corpus: { pages, since, until }
stats:
  pages_total, pages_duplicate_skipped, pages_scanned, pages_with_emphasis,
  spans_total, spans_typed, spans_untyped, spans_gated_out, spans_untyped_excluded,
  weekly_ideas, themes_evolution, items_kept,
  dropped: { label, names, date, numeric, empty, owned-task },
  clusters, clusters_multi_page, clusters_intensity3_or_star,
  clusters_statement_like, clusters_statement_like_emphasis,
  clusters_from_weekly, clusters_from_themes
candidates:                         # sorted: distinct_pages desc, assertions desc, max_intensity desc
  - id: c-0001
    text: string                    # most frequent variant (shortest on ties)
    normalized: string
    variants: [string]              # up to 10 verbatim forms
    assertions: int                 # items in the cluster
    distinct_pages: int
    first_seen, last_seen: date
    evidence_pages: [page_id]       # ≤ 8: strongest marks first, then chronological spread
    sources: { emphasis: n, weekly: n, themes: n }
    refs: [path]                    # non-page sources
    typed: bool                     # any member came from a typed span
    max_intensity: int | null
    mark_types: [string]
    statement_like: bool            # ≥ 3 words with a claim word (not, never, always, is, over, than, first, only, …)
                                    # or an arrow/equals sign, or ≥ 5 content words
```

## 7. Measured yield (facility as of 2026-11-08)

| Measure | Value |
|---|---|
| Pages | 412 total, 15 duplicates skipped, 397 scanned (2025-12-01 → 2026-05-05) |
| Emphasis spans | 1294 (556 typed, 738 untyped from 220 Feb–Apr pages) |
| Typed spans gated out (intensity 1 and weak mark) | 85 |
| Dropped by filter | label 290, names 154, date 26, numeric 16, empty 5, owned-task 5 |
| Weekly ideas / themes concepts | 62 (9 weeklies carry the field) / 4 |
| Items kept → clusters | 779 → 699 |
| Clusters on ≥ 2 pages | 54 |
| Clusters with intensity 3 or star / double-underline | 52 |
| Statement-like clusters | 191 (129 from emphasis) |
| Shortlist handed to the model step | 256 |
| `--typed-only` | 350 clusters, 13 multi-page |

What the numbers say: emphasis is mostly used for names and headings, so recurrence of the *exact* phrase is rare (54 multi-page clusters, of which only a handful are claims — "AI never locks inspector out", "ORCHESTRATION LIVES as STATE not SKILLS", "NO NEW WORKFLOWS"). Most principles surface as a single strongly marked statement whose restatements are in plain transcript text, which is why the model step searches transcripts for paraphrases rather than trusting cluster counts alone. `times_asserted` in `principles.json` is therefore counted by the model step over assertion pages, not copied from `assertions`.
