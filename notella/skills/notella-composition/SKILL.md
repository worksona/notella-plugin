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
notella-state get-manifest → manifest.model_defaults.composition
notella-state get-page {page-id}
notella-state get-page-artifact {page-id, artifact: transcribe}
```

Always runs (composition is in every page's required minimum). If `phase < transcribed`, abort.

### Step 2 — Acquire the page lock

```
notella-state acquire-page-lock {page-id, actor: notella-composition@<version>}
```

### Step 3 — Build the prompt

System prompt (paraphrased):

```
You are a page-composition analyst. Your job is to read a notebook page image
and map its macro spatial structure.

You will produce a composition map covering:

## zones (array)
Identify 2-8 distinct zones on the page. A zone is a coherent region of content
— a paragraph block, a diagram region, a table, a margin annotation, a sketch
area. For each zone:
- id: zN (sequential)
- region: top | top-left | top-right | left | center | right | bottom |
          bottom-left | bottom-right | margin-top | margin-bottom |
          margin-left | margin-right | full-width
- bbox_pct: [x0, y0, x1, y1] in 0.0-1.0 with top-left origin
- content_summary: one sentence
- dominant_kind: text | diagram | sketch | table | mixed | empty
- visual_element_ids: any visual_element ids referenced from sibling artifacts

## dominant_flow
The macro reading direction:
top-down | left-right | right-left | bottom-up | radial | scattered |
centered | none

## reading_order
The order in which a reader would naturally traverse the zones (an array of
zone ids).

## visual_hierarchy
For each zone, a prominence score 1-5 with a short reasoning sentence:
- 5 = dominates the page (large size, central position, heavy emphasis)
- 1 = peripheral or fine-print

## cross_zone_connections
Arrows, lines, or implicit connections between zones:
- from: zone id
- to: zone id
- kind: arrow | line | dotted-line | implicit | repeated-motif
- evidence_element_id: optional visual_element id

## whitespace_signal
Overall density of the page:
dense | balanced | sparse | very-sparse

Return ONLY valid JSON matching the CompositionSchema.
```

User prompt:

```
Map the spatial composition of this page. Return JSON matching CompositionSchema.

## Transcript context (for grounding zone content_summary)
{cleanedTranscript truncated to 2000 chars}

## Sibling artifacts present
- diagram.json: <yes|no, with N diagrams>
- sketch.json: <yes|no, with N sketches>
- table.json: <yes|no, with N tables>

If sibling artifacts are present, reference their visual_element ids in
zones[].visual_element_ids when they overlap.
```

Include `derived/page.jpg`.

### Step 4 — Call the model

Default model: `claude-haiku-4-5` (vision-capable, lighter task).

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
