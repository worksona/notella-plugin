---
name: notella-diagram
description: "Interpret diagrams on a notella page — extract nodes, edges, layout semantics, utility statement, actionability score, ambiguities. Use whenever the user says 'analyze the diagram on page X', 'extract the flowchart', 'interpret this diagram', 'what does this flowchart mean', 'parse the mind-map', or any request to structure visual diagrams. Conditional: only runs when classify.json:route_plan includes diagram_interpretation. Reads through `notella-state`; writes `diagram.json`. Idempotent unless `--reprocess` is passed."
---

# notella-diagram — the diagram interpreter

Specialist for the structural visual content on a page: flowcharts, mind-maps, network graphs, swim-lanes, Venn diagrams, matrices.

## Purpose

Convert structural visual content into queryable typed nodes and edges. A diagram's value lives in its nodes (steps, decisions, containers), its edges (causal/flow/dependency relations), and what it's communicating (utility, actionability).

## Inputs and outputs

**Input:** Page at `phase=transcribed` with `route_plan` containing `diagram_interpretation`. Reads `derived/page.jpg`, `transcribe.json`, `classify.json`.

**Output:**
- `pages/{page-id}/diagram.json`
- No phase advance (Layer-1 specialist).
- `pipeline.ndjson` line.

## How a run executes

### Step 1 — Read configuration & page

```
notella-state get-manifest → manifest.model_defaults.diagram
notella-state get-page-artifact {page-id, artifact: classify}
notella-state get-page-artifact {page-id, artifact: transcribe}
```

Verify `phase >= transcribed` and `route_plan` includes `diagram_interpretation`. Skip cleanly if not.

### Step 2 — Acquire the page lock

```
notella-state acquire-page-lock {page-id, actor: notella-diagram@<version>}
```

### Step 3 — Build the prompt

Use notella-the-app's `DIAGRAM_SYSTEM` and `buildDiagramPrompt()` from `src/lib/prompts/diagram.ts` verbatim, with one extension: each node and edge gets a `visual_element_id` so `composition.json` can reference it.

Include `derived/page.jpg` and the transcript text (for label-disambiguation grounding).

### Step 4 — Call the model

Default: `claude-sonnet-4-6` (vision-capable, structure-heavy).

### Step 5 — Validate

```yaml
nodes:
  - id, label, role, description?, visual_element_id
edges:
  - from, to, label?, relation_type, visual_element_id
layout_semantics: string
utility_statement: string
actionability_score: 0.0-1.0
ambiguities: [string]
diagram_count: int
```

Sanity checks:
- Every `edges[].from` and `.to` appears in `nodes[].id`
- `diagram_count >= 0`
- If `diagram_count == 0`, `nodes` and `edges` must be empty arrays

### Step 6 — Write the artifact

```
notella-state log-page-artifact {page-id, artifact: diagram, payload: <validated>}
```

### Step 7 — Release the page lock

## Idempotency

Standard: no-op on existing artifact unless `--reprocess`.

## Failure modes

| Failure                                                | Behavior |
| ------------------------------------------------------ | -------- |
| Classifier overestimated diagram content (no diagram present) | Return `diagram_count: 0` with empty arrays; this is correct, not an error. |
| Diagram crosses page boundaries (continued on next page) | Capture what's visible; flag in `ambiguities` with "diagram appears truncated"; downstream linking may stitch via `meta.yaml:links_to`. |
| Labels illegible                                       | Use `[label uncertain]` text; flag in `ambiguities`. |

## What this skill does NOT do

- Does not interpret freeform sketches — that's `notella-sketch`. (A flowchart is a diagram; a face is a sketch; a process metaphor with figures is a sketch with diagram-adjacent intent.)
- Does not extract tables — that's `notella-table`.
- Does not write to first-pass.json — first-pass reads diagram.json as input.

## Examples

### "Interpret diagrams on page 2026-05-02-x7k2"

Returns 1 flowchart with 7 nodes (5 process, 2 decision), 8 edges (6 flow, 2 causal), `actionability_score: 0.7` ("clearly shows a deployment sequence"), 0 ambiguities.

## Reference files

- `references/diagram-prompt.md` — full prompt.
- `references/node-role-rules.md` — how to choose container/process/decision/flow/dependency/unknown.
- `references/edge-relation-rules.md` — how to choose causal/flow/dependency/sequence/association.
