# Canonical attribution — alias matching

How `notella-metadata` maps mentions in a transcript to the canonical project slugs and person names defined in `manifest.yaml`. The model is asked to do this in the prompt; the skill then runs the same deterministic matcher over the model's output and over the transcript, so the result in `metadata.json:projects` / `people` and the mirror in `meta.yaml:project_attributions` / `person_attributions` is stable across model versions.

## Sources of truth

```yaml
# manifest.yaml
projects:
  - slug: tulevik
    name: Tulevik
    keywords: [tulevik, data-staleness, name-matching, jp-morgan, collection]
    active: true
people_aliases:
  - name: Alice Example
    aliases: [Alice, A.E., AE, alice@…]
```

`projects[].keywords` are the project aliases. `people_aliases[].aliases` are the person aliases. Both lists are owned by the user; this skill never edits them. The orchestrator's project-discovery pass is the way new slugs get in.

## Normalisation before matching

Apply to both the mention and the alias:

1. Unicode NFKC, then lowercase.
2. Strip possessives (`'s`), trailing punctuation, and surrounding brackets.
3. Collapse `-`, `_`, `/` and whitespace runs to a single hyphen.
4. Remove a leading "the " / "project " / "proj " for projects.
5. For people, also strip honorifics (dr, mr, ms, mrs) and trailing role words in parentheses.

So `Project Tulevik's`, `tulevik`, `TULEVIK/` all normalise to `tulevik`.

## Matching rules, in order

| Order | Rule | Example | Result |
| --- | --- | --- | --- |
| 1 | Exact normalised match against a slug or alias | `JP Morgan` → `jp-morgan` ∈ tulevik.keywords | canonical |
| 2 | Token-boundary containment — the alias appears as a whole token sequence inside the mention | `tulevik staleness dashboard` contains `tulevik` | canonical |
| 3 | Initials match for people — the mention is 2–3 uppercase letters equal to the initials of a canonical name or listed as an alias | `AE` ↔ Alice Example | canonical, confidence 0.8 |
| 4 | Edit distance ≤ 1 on tokens ≥ 6 chars (handwriting OCR slips) | `Tulevick` → `tulevik` | canonical, confidence 0.7, logged |
| 5 | No match | `Project Sunshine` when not in manifest | kept as written |

Stop at the first rule that matches. Rule 4 is only applied when exactly one alias is within distance 1; two candidates at the same distance are an ambiguity (below).

### Multi-word aliases

An alias with several words (`data staleness`) must match all words in order at token boundaries. A single shared word (`data`) is not a match — generic words appear in every project's keyword list.

### Keyword collisions across projects

The manifest allows the same keyword under two projects (`decima` and `segmentor` appear under both `dante` and `decima`). When a mention matches aliases of two or more projects:

- If the mention equals one project's **slug or name** exactly, that project wins.
- Otherwise record **both** slugs in `projects`, log `{"kind": "ambiguous-project", "mention": …, "candidates": […]}` to `pipeline.ndjson`, and let the user tighten the keyword lists. Do not pick one silently.

## People: what gets recorded

- Matched → the canonical `name` from `people_aliases`.
- Unmatched full names (two or more capitalised tokens) → as written, title-cased.
- Unmatched single first names → as written. These are the most common case in this corpus; the user promotes recurring ones into `people_aliases`.
- Roles ("the CFO", "our designer") → as written, lowercased, only when no name is attached. First-pass and actions use roles as `owner_candidates`.
- The author. Notes written in first person do not record the author as a person unless the author's name is literally written. `manifest.facility.owner` is used by `notella-actions` for owner inference, not by metadata.

## Projects: what gets recorded

- Matched → slug.
- Unmatched → the name as written (not slugified). Slugification happens only in project discovery, when the user confirms. Writing an unconfirmed slug into `metadata.json` would pollute `pages_by_project` counters with phantom projects.

## Mirroring into meta.yaml

```
project_attributions: <matched slugs only>
person_attributions:  <matched canonical names only>
```

Unmatched values stay in `metadata.json` but are not mirrored. `meta.yaml` attributions are what `notella-state list-pages --project=` and the desktop app filter on, so they must be canonical.

## Backfill

When the manifest gains new slugs or aliases (after project discovery, or by hand), run `notella-metadata --reprocess` over affected pages. The orchestrator does this automatically after a confirmed discovery pass. Reprocessing emits a `correction` event per page; `meta.yaml:project_attributions` is replaced, not appended.

## Telemetry

Each run appends match statistics to the `pipeline.ndjson` line: `{matched_projects, unmatched_projects, matched_people, unmatched_people, ambiguous}`. Unmatched counts trending up are the signal that the manifest needs attention.
