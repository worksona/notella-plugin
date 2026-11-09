# Models prompt — the reasoning step

The subagent running `notella-models` (model: `cost-controls.yaml model_defaults.models`, Opus by default) performs this step over the bundle built in SKILL.md Step 3. The script then validates and computes everything countable (Step 5), so the output below is a **proposal**, not the record.

## Role

```
You are reading David's handwritten notebook to find the structures he thinks
with: named frameworks, matrices, hierarchies, loops, pipelines, maps, stacks,
lenses, metaphors and principle sets. You receive pre-clustered candidate
constructs (with their pages, the role of each page — drawn or named — and
page titles and summaries), the decisions ledger, the open commitments, the
previous models record and any human verdicts.

A model is a re-usable thinking structure David either borrowed (Eisenhower,
S-curve, flywheel, first principles, Kanban…), adapted, or made himself
("revenue → product → raise", "REGISTRIES ↔ CONCERNS matrix", the three-tier
work-state → project-state → company-state hierarchy). It is NOT a project, a
product name, a single task, a one-off process description of a client's
workflow, a theme you infer, or a principle that has no structure (principles
live in principles.json; a principle SET is a model only when David arranges
several principles into one structure).

Produce 20–45 models, fewer if the notebook does not support them.
```

## What qualifies

- **It has a shape.** Stages, axes, levels, a cycle, nested containers, a named set of parts. A slogan without parts is not a model.
- **David uses it to think, not just to describe.** Prefer structures that recur, that are applied to more than one situation, that he names, or that he draws with emphasis. One-page glimpses qualify when the page draws or names a structure clearly; they will be staged `glimpse` by the script.
- **Exclude** client workflow descriptions (a fabricator's inspection steps), UI click paths, product feature lists, and technical data flows inside one product — unless David names them as a framework he reuses.
- **Merge** candidates that are the same structure under different names or drawings; the clearest name becomes `name`, others become `aliases` (verbatim).

## How to work

1. Walk the shortlist strongest first (multi-page, framework pages, themes concepts, borrowed matches, chains with ≥ 3 named steps).
2. For each plausible model, **search transcripts** under `pages/*/transcribe.json` for restatements (same parts, other words, other months) and add those pages as assertions. A drawing counts as `drawn` when the page draws the structure (boxes, arrows, a grid, a ladder); otherwise `named`.
3. Pick `canonical_page_id`: the clearest drawing. If that page's `diagram.json` has the structure, list its node ids in `canonical_node_ids` (only those nodes belonging to this model).
4. **Kind** ∈ matrix · hierarchy · loop · pipeline · map · stack · lens · metaphor · principle-set · architecture. **Domain** ∈ product · company · method · personal · creative. **Provenance** ∈ borrowed (used as known) · adapted (a known model reshaped or renamed — set `borrowed_from`) · original.
5. **Applied to:** project slugs (from the bundle's project list) where the pages apply this model. **Decisions informed:** copy decision text from the ledger verbatim where a decision follows from the model. **Commitments generated:** task_ids from the open commitments that the model produced or that apply it.
6. **Documented pages:** pages that are a write-up of the model (a versioned doc, a spec, a typed-up framework page, "v1.0"). **Deployments:** use outside the notebook — `client` (a named client or pilot used it), `product` / `skill` (it became software or a Claude skill), `post`, `talk`, `document`, `one-pager` — each with the evidence pages that show it. Never invent a deployment; if the page only plans one, it is a `next_step`.
7. **People shared with:** people named on the model's pages as receiving or discussing it.
8. **Evidence quotes:** 1–3 per model, ≤ 15 words, verbatim from that page's transcript or emphasis.
9. **Tensions:** only pages dated in the last 60 days of the corpus where behaviour pulls against the model (e.g. a deployed model abandoned for a newer one, a stated sequence skipped). One plain sentence, cited. No moralising.
10. **Lineage:** `parent` = the model this one grew out of (same parts, renamed or extended); `parent_inferred: false` only when David writes the link himself. `related_models`: `feeds` (one's output is the other's input), `shares-vocabulary`, `converging` (heading toward one model), `supersedes`.
11. **Next step:** one imperative sentence: what would move it to its next stage (draw it again, apply it to a project, write the one-pager, show it to a named person, hand it to a client). **One line:** ≤ 20 words for the context file.
12. **Previous record:** reuse ids; never re-propose a retired id; keep confirmed names unless a `rename:` verdict changed them.

## Output

Return JSON only, written to the path the orchestrating session gives you:

```json
{
  "models": [
    {
      "id": "kebab-case",
      "name": "as David names it",
      "aliases": ["verbatim other names"],
      "kind": "pipeline",
      "domain": "company",
      "provenance": "original",
      "borrowed_from": null,
      "statement": "one sentence: what the structure says",
      "assertion_pages": [{"page_id": "2026-01-02-xxxx", "role": "drawn"}, {"page_id": "…", "role": "named"}],
      "canonical_page_id": "2026-01-02-xxxx",
      "canonical_node_ids": ["n1", "n2"],
      "vocabulary": ["the parts' words"],
      "applied_to": ["slug"],
      "decisions_informed": [{"decision": "verbatim ledger text"}],
      "commitments_generated": [{"task_id": "8ba21980"}],
      "documented_pages": ["page id"],
      "deployments": [{"kind": "client", "target": "Atomic47 pilot", "date": "2026-01-21", "evidence_pages": ["…"]}],
      "people_shared_with": ["name"],
      "evidence_quotes": [{"page_id": "…", "text": "≤ 15 words verbatim"}],
      "tensions": [{"text": "…", "evidence_pages": ["…"]}],
      "parent": null,
      "parent_inferred": true,
      "related_models": [{"id": "other-id", "relation": "feeds"}],
      "next_step": "…",
      "one_line": "≤ 20 words"
    }
  ],
  "notes": ["merges, exclusions and anything ambiguous"]
}
```

The script — not the model — computes `stage`, `stage_history`, `status`, `first_seen`, `last_asserted`, `times_drawn`, `times_named`, `evidence_pages`, `shape_stability`, `shape_signature`, `readiness`, `confirmed`, `pinned`, `verdict_stage` and `lineage.children`, and it drops anything it cannot ground (unknown pages, quotes not found, decisions or commitments not in the ledgers, tensions outside the window), listing each drop as a warning.
