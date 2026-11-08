---
name: notella-composition
description: "Map the page-level spatial composition of a notella page — zones, dominant flow, reading order, visual hierarchy, cross-zone connections, whitespace signal. Use whenever the user says 'map the layout of page X', 'what's the composition of this page', 'page-level spatial map', 'where do things sit on the page', or any request about page-level structure (distinct from any single diagram's internal layout). Always runs on every page. Reads through `notella-state`; writes `composition.json`. Idempotent unless `--reprocess` is passed."
---

# notella-composition — the page-level spatial mapper

Every page has a layout, even if it's "scattered". This skill captures it.

## Purpose

Record the page's *macro* spatial structure — which zones contain what, in what reading order, with what hierarchy, connected how. This is distinct from `notella-diagram`'s `layout_semantics` (which describes a single diagram's internal layout).

Composition is what later supports queries like: "show pages where the conclusion sits in the bottom-right" or "find pages with a clear left-right process flow".

## Inputs and outputs

**Input:** Page at `phase=transcribed`. Reads `derived/page.jpg`, `transcribe.json`, optional `diagram.json` / `sketch.json` / `table.json` if they've already run (they may not have).

**Output:**
- `pages/{page-id}/composition.json`
- No phase advance — composition is one of several Layer-1 specialists; phase advances to `enriched` only after all route_plan'd specialists complete (orchestrator's job).
- A `pipeline.ndjson` line; no event (composition completion is rolled into `page.enriched`).

## How a run executes

### Step 1 — Read configuration & page

```
notella-state get-manifest → cost-controls.yaml:model_defaults.composition
notella-state get-page {page-id}
notella-state get-page-artifact {page-id, artifact: transcribe}
```

Always runs (composition is in every page's required minimum). If `phase < transcribed`, abort.

### Step 2 — Acquire the page lock

```
notella-state acquire-page-lock {page-id, actor: notella-composition@<version>}
```

### Step 3 — Build the prompt

Use the prompt in `references/composition-prompt.md` — the complete system and user prompt shipped with this plugin (this skill has no app counterpart; the prompt is native to the plugin). In outline, the system prompt asks for:

- `zones[]` — 2-8 regions, each with `id`, `region` (vocabulary in `references/zone-region-vocabulary.md`), `bbox_pct`, `content_summary`, `dominant_kind`, `visual_element_ids`
- `dominant_flow` — top-down | left-right | right-left | bottom-up | radial | scattered | centered | none
- `reading_order` — zone ids in traversal order
- `visual_hierarchy[]` — prominence 1-5 per zone with reasoning
- `cross_zone_connections[]` — arrow | line | dotted-line | implicit | repeated-motif, with optional `evidence_element_id`
- `whitespace_signal` — dense | balanced | sparse | very-sparse

The user prompt carries a 2000-char transcript excerpt for grounding and the presence/absence (with element ids) of sibling `diagram.json` / `sketch.json` / `table.json`, so zones can reference `ve_d*`, `sk_*`, `tb_*` ids without inventing any.

Include `derived/page.jpg`.

### Step 4 — Call the model

Runs on the model in `cost-controls.yaml` `model_defaults.composition` (currently `haiku`, chosen by the 2026-11-08 eval: layout zoning is a light vision task). When the orchestrator runs this stage it dispatches a subagent with that model; run directly, it uses the session model.

### Step 5 — Validate

Validate against `CompositionSchema`. Sanity checks beyond schema:

- Every `reading_order` id appears in `zones[].id`
- Every `visual_hierarchy[].zone_id` appears in `zones[].id`
- Every `cross_zone_connections[].from` / `.to` appears in `zones[].id`
- bbox_pct values are within 0.0-1.0
- Sum of zone areas is plausible (allowing overlap; flag if > 200% — likely a hallucination)

### Step 6 — Write the artifact

```
notella-state log-page-artifact {page-id, artifact: composition, payload: <validated>}
```

### Step 7 — Release the page lock

```
notella-state release-page-lock {page-id, actor: notella-composition}
```

## Idempotency

- Re-running on a page with composition.json present: no-op unless `--reprocess`.
- With `--reprocess`: overwrite, emit a `correction` event referencing the previous composition write.

## Failure modes

| Failure                                          | Behavior |
| ------------------------------------------------ | -------- |
| Page is too uniform / dense to zone clearly      | Acceptable to return a single zone covering the full page; `dominant_flow=none`; `whitespace_signal=dense`. |
| Vision API returns invalid JSON                  | One retry, then surface error. |
| visual_element_ids reference a missing artifact  | Flag in pipeline.ndjson; do not write — re-run after the missing artifact runs. |

## What this skill does NOT do

- Does not extract diagram structure (nodes/edges) — that's `notella-diagram`.
- Does not transcribe text content of zones — `notella-transcribe` already did.
- Does not interpret meaning — that's `notella-first-pass`.

## Examples

### "Map the composition of page 2026-05-02-x7k2"

```json
{
  "zones": [
    { "id": "z1", "region": "top", "content_summary": "title and date", "dominant_kind": "text" },
    { "id": "z2", "region": "left", "content_summary": "bulleted strategy points", "dominant_kind": "text" },
    { "id": "z3", "region": "right", "content_summary": "flowchart of process", "dominant_kind": "diagram" },
    { "id": "z4", "region": "bottom", "content_summary": "action items list", "dominant_kind": "text" }
  ],
  "dominant_flow": "left-right",
  "reading_order": ["z1", "z2", "z3", "z4"],
  "visual_hierarchy": [
    { "zone_id": "z3", "prominence": 5, "reasoning": "central diagram, heavy linework" },
    { "zone_id": "z4", "prominence": 4, "reasoning": "bottom-bracketed, starred" }
  ],
  "cross_zone_connections": [
    { "from": "z2", "to": "z3", "kind": "arrow" }
  ],
  "whitespace_signal": "balanced"
}
```

## Reference files

- `references/composition-prompt.md` — full prompt.
- `references/zone-region-vocabulary.md` — when to use which region label.
