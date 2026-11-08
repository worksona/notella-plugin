# Project discovery

How `notella-orchestrator` derives candidate projects from `metadata.json` across the corpus, presents them, and backfills attributions once the user confirms. It runs after the metadata fan-out in step 2 whenever `manifest.projects` is empty or the corpus names projects the manifest does not, and on demand with `--discover-projects`.

## Inputs

- Every `pages/*/metadata.json` at `phase ≥ transcribed`: `projects[]`, `organisations[]`, `tags[]`, `people[]`, `themes[]`, `date`.
- `manifest.yaml:projects[]` (slugs, names, keywords) — what is already known.
- `first-pass.json:structural_map.entities[]` where present — secondary evidence.

## Step 1 — Collect mentions

For each page, take `metadata.projects[]` entries that did **not** resolve to a manifest slug (the canonical-attribution matcher in `notella-metadata` leaves these as written). Normalise: NFKC, lowercase, strip "project "/"the ", collapse punctuation and whitespace to a single hyphen, singularise trailing `s` when the singular also occurs.

Also take `metadata.organisations[]` entries that co-occur with `project`-like context words on the page (roadmap, launch, sprint, milestone, deliverable, client, pipeline) — organisations are often projects in this corpus (Tulevik, Decima).

## Step 2 — Merge variants

Cluster normalised mentions by:

1. exact match;
2. one is a prefix/suffix of the other with ≥ 5 shared leading characters (`dante`, `dante-extrakt`);
3. token Jaccard ≥ 0.6 (`atomic47-labs`, `atomic-47`);
4. edit distance ≤ 1 for tokens ≥ 6 characters (`tulevick`/`tulevik`).

Each cluster's **display_name** is the most frequent original casing; its **slug** is the shortest normalised form. Record every variant so it can become a keyword.

## Step 3 — Score

| Metric | How |
| --- | --- |
| `mention_count` | pages whose metadata names any variant |
| `date_span_days` | last − first page date |
| `distinct_weeks` | ISO weeks with ≥ 1 mention |
| `co_people` | top-3 people co-occurring (from `metadata.people`) |
| `co_tags` | top-5 tags co-occurring, excluding the variants themselves |
| `representative_pages` | 3 page ids: earliest, latest, and the one with the most mentions of the cluster in `first-pass.structural_map.entities` |

Candidate threshold: `mention_count ≥ 3` **and** `distinct_weeks ≥ 2`, **or** `mention_count ≥ 5`. Below that the cluster is listed under "also seen" without a proposal.

Existing manifest projects whose keywords match a cluster's variants are **not** candidates; instead the unmatched variant is proposed as a *new keyword* for that slug ("add `tulevick` to tulevik.keywords?").

## Step 4 — Present

```
Discovered project candidates from your corpus (412 pages, 2025-12-01 → 2026-05-08):

  slug        mentions  weeks  first → last            people              keywords
  tulevik     7         3      2025-12-03 → 2026-02-10  Alice, Bob          data-staleness, name-matching, jp-morgan
  aimqc       5         4      2025-12-14 → 2026-04-25  —                   roadmap, voice-interface, nrcan
  dante       8         6      2025-12-01 → 2026-05-06  Carol               pipeline, extraction, segmentor
  atomic47    4         3      2026-01-05 → 2026-03-20  —                   leadership, crm, agency
  decima      3         2      2026-02-16 → 2026-03-08  —                   smiles, segmentor, scale

Keyword additions for existing projects:
  dante: add "extrakt" (seen 3× as "Dante Extrakt")

Also seen (below threshold): robson (2), stonemaps (2), woowoo (1)

Representative pages: tulevik → 2025-12-03-k2p1, 2026-01-20-m9x3, 2026-02-10-r4t8 …

Add these to manifest.yaml? [y/N/edit]
```

`edit` opens the proposal as YAML for the user to change slugs, names and keywords before confirming. Under `--auto` the proposal is **not** applied; it is written to `logs/review-pending.md` for `notella-review` and the report says "project discovery: 5 candidates pending confirmation".

## Step 5 — Apply (on confirmation only)

Write to `manifest.yaml:projects[]`:

```yaml
- slug: tulevik
  name: Tulevik
  description: ""            # user fills in later; discovery does not invent descriptions
  keywords: [tulevik, tulevick, data-staleness, name-matching, jp-morgan]
  active: true
  discovered_at: 2026-11-08T07:30:00Z
  discovered_from_pages: 7
```

Keywords = the cluster's variants + `co_tags` the user left in. Existing entries are never removed or renamed. The write goes through `notella-state update-manifest`, which validates slug uniqueness and format (`^[a-z0-9][a-z0-9-]{1,40}$`) and appends a `manifest.updated` activity entry.

## Step 6 — Backfill

Queue `notella-metadata --reprocess` for every page whose `metadata.projects[]` or `organisations[]` contains a confirmed variant. Reprocessing re-runs the canonical matcher (and the model, since the prompt's known-projects block changed), rewrites `meta.yaml:project_attributions`, and emits a `correction` event per page. Then queue `first-pass --reprocess` for the same pages **only** when `--deep-backfill` is passed; by default first-pass is left alone because its entities are free text and daily/weekly/themes read project attributions from `meta.yaml`, not from first-pass.

After backfill, `state.json:counters.pages_by_project` is rebuilt by `notella-state rebuild-index`.

## People discovery

The same pass, with `metadata.people[]` unmatched against `manifest.people_aliases`, proposes **people aliases** when a normalised name appears on ≥ 3 pages across ≥ 2 weeks. Presented in the same prompt under "People seen repeatedly without an alias". On confirmation, written to `manifest.people_aliases[]` as `{name, aliases: [variants], discovered_at}`. This feeds the people ledger (step 9) and the weekly's `people_and_relationships`.

## Idempotency

Re-running discovery with no manifest changes produces the same candidates (deterministic clustering over the same metadata). Confirmed slugs disappear from the candidate list because their variants now match. Declined candidates are remembered in `state.json:discovery_declined[]` with the date and are not re-proposed for 90 days unless their mention count has doubled.

## What discovery never does

- Invent a project from a single page, however emphatic.
- Write to the manifest without a human `y` (or an explicit `--discover-projects --yes` in an interactive session).
- Rename or merge existing slugs — if two existing projects look like one, it says so in the report and leaves the decision to the user.
