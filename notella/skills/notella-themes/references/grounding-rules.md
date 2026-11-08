# Grounding rules — evidence vs inference in themes

`notella-themes` runs the most expensive model in the facility over an abstraction of the corpus. Its failure mode is confident narrative unsupported by pages. These rules define what counts as evidence for each output section, what the skill checks mechanically after the call, and when it refuses the write.

## Principle

A theme is a **measurement with a name**. The signal bundle (`signal-aggregation.md`) supplies the measurements; the model supplies the names and the connective tissue. Anything in the output that cannot be pointed back to a series key, a co-occurrence pair, a recurring idea, an open question, or a weekly theme entry is inference, and inference is allowed only where the schema says so (`description`, `why_notable`, `why_fading_might_matter`, `evolution_summary`, `momentum_summary`).

## Hard checks (refuse on failure, one retry)

| Check | Rule |
| --- | --- |
| **Citable ids** | Every `evidence_pages[]`, `key_pages[]` and `latest_page` must be a page id present in `signals_json.page_index`. |
| **Dates match pages** | `first_seen` and `last_seen` of a theme must equal the dates of pages in the series it merges (within the bundle), not arbitrary dates. `first_raised` of an open question must match the bundle entry. |
| **Counts are bounded** | `pages_count` ≤ the size of the union of `pages` across the series keys the theme merges. The skill cannot know which keys were merged unless the model lists them, so the model is asked (in `description`'s first sentence, or a `signals` array if the schema has one) to name the series keys; absent that, `pages_count` ≤ the largest single series total + 20%. |
| **Weights are earned** | `primary` requires total ≥ 10 pages and presence in ≥ 4 distinct buckets; `secondary` ≥ 5 pages and ≥ 2 buckets; `emerging` requires `first_seen` within the most recent 25% of the date range; `fading` requires `last_seen` earlier than the most recent 25% and prior presence ≥ 5 pages. |
| **Trajectory agrees with the delta** | When a delta is supplied, a theme with `pages_added: 0` may not be `rising`; one whose matched series' recent rate is ≥ 1.5× prior may not be `declining` without a sentence of justification in `description`. |
| **Schema** | All sections present; `themes` non-empty when `pages_total ≥ 10`. |

On refusal the retry appends: "The following claims could not be grounded: …. Remove them or cite page ids from the signals." A second failure surfaces the error and leaves the previous snapshot in place.

## Soft checks (warn in `pipeline.ndjson`, keep the write)

- A theme whose `evidence_pages` all fall within one ISO week ("theme" that is really one busy day).
- Two themes whose evidence page sets overlap ≥ 60% and are not listed in each other's `related_themes`.
- An `emergent_topic` that also appears as a theme.
- A `fading_topic` whose name matches a series key with `trajectory_hint: rising`.
- `momentum_summary` naming a project not in `series.projects`.
- More than 12 themes or fewer than 4 when `pages_total ≥ 50`.

## What is evidence for each section

| Section | Evidence | Inference allowed |
| --- | --- | --- |
| `themes[].name/weight/first_seen/last_seen/pages_count/trajectory/evidence_pages` | series totals, buckets, pages, trajectory_hint, weekly_themes weights | the merge of several series into one theme; the name |
| `themes[].description` | the merged series | yes — what the theme *is about*, kept to one paragraph |
| `themes[].related_themes` | co-occurrence pairs, shared evidence pages | yes, but each relation should have a pair or an overlap behind it |
| `emergent_topics` | series with `first_seen` recent and small total; `new_series_keys` in the delta | `why_notable` |
| `fading_topics` | series with `trajectory_hint: declining`, or prior themes with `pages_added: 0` | `why_fading_might_matter` |
| `persistent_open_questions` | `open_questions` entries only — the model may rephrase but not add | none beyond phrasing |
| `conceptual_evolution` | co-occurrence shifts over buckets, recurring ideas whose wording changed, weekly_themes weight series, affect series shifts | `evolution_summary` |
| `momentum_summary` | everything above | yes — this is the one place for synthesis prose |

## What is never evidence

- A `manifest.projects[].keywords` entry. Keywords describe what a project is about; they do not prove a page discussed it.
- `manifest.bootstrap_themes`. These are the user's priors; a bootstrap theme with no series behind it is not a theme and must not appear.
- The previous snapshot's `description` text. Memory is for names and counts, not for re-asserting last time's narrative.
- The model's general knowledge about the domains named (AI quality, data pipelines). Themes are about this author's notes.

## Reviewing a themes run

The orchestrator report prints, per theme: name, weight, trajectory, pages_count, pages_added (from delta), evidence page count. A human reviewer (or `notella-review`) can mark a theme `wrong` when its evidence pages, opened, do not support the description; that verdict is logged as a `correction` event against the snapshot and the theme name is added to a `disputed` list that the next run's user prompt carries so the model must re-justify or drop it.
