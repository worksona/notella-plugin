---
name: notella-classify
description: "Classify a notella page — diagnose doc_type, content_mix (text/diagram/table/symbolic %), and produce the route_plan that tells downstream specialists which agents to run. Use whenever the user says 'classify this page', 'what kind of page is this', 'diagnose page X', 'set up the route plan', or any request to determine how a page should be processed. Also trigger automatically when notella-orchestrator finds a page at phase=intake. Reads through `notella-state`; writes `classify.json` and advances phase to `classified`. Idempotent unless `--reprocess` is passed."
---

# notella-classify — the page diagnostician

First specialist in the pipeline. Looks at a page in `phase=intake` and decides what it is and what should run next.

## Purpose

Diagnose the page's structural character and produce the `route_plan` array that downstream specialists consume. Without a good classification, transcription wastes effort on diagrams and the diagram skill gets called on pure prose.

## Inputs and outputs

**Input:**
- A page at `phase=intake`. Reads `pages/{page-id}/derived/page.jpg` (the canonical decode) and `pages/{page-id}/meta.yaml`.

**Output:**
- `pages/{page-id}/classify.json`
- Page advanced to `phase=classified`
- Mirror `content_mix` and `confidence` into `meta.yaml` for fast filtering
- `page.classified` event emitted

## How a run executes

### Step 1 — Read configuration

```
notella-state get-manifest → manifest.model_defaults.classify
notella-state get-page {page-id} → meta.yaml + artifact manifest
```

Verify `phase == intake`. If not, abort with `{status: "wrong-phase", current: <phase>}` (idempotent — already done).

### Step 2 — Acquire the page lock

```
notella-state acquire-page-lock {page-id, actor: notella-classify@<version>}
```

### Step 3 — Build the prompt

System prompt (`CLASSIFY_PAGE_SYSTEM`) — see `references/classify-prompt.md`. Identical to notella-the-app's `src/lib/prompts/classify.ts`, with three additions to the route_plan vocabulary:

```
- sketch_interpretation       — include when the page contains freeform sketches (figures, scenes, doodles) distinct from structural diagrams
- table_extraction            — include when doc_type=table or when content_mix.table >= 15
- composition                 — always include
```

User prompt: `"Classify this page. Return JSON matching the PageClassificationSchema exactly."`

Include `derived/page.jpg` as the image input.

### Step 4 — Call the model

Provider/model from `manifest.model_defaults.classify` (default `claude-haiku-4-5`).

Log via `notella-state log-llm-call`:

```yaml
actor: notella-classify
page_id: {page-id}
task: classify
provider: anthropic
model: claude-haiku-4-5
tokens: { input, output }
latency_ms: <ms>
status: complete
```

### Step 5 — Validate against schema

Parse the JSON and validate against `PageClassificationSchema`:

```yaml
doc_type: handwritten_text | mixed_text_diagram | diagram | sketch | table | checklist | whiteboard | unknown
content_mix:
  text: 0-100
  diagram: 0-100
  table: 0-100
  symbolic: 0-100
route_plan: [string]                    # subset of manifest.route_plan_vocab
confidence: 0.0-1.0
fallback_strategy: string | "none"
```

Refuse to write if validation fails; surface the error and leave the page at phase=intake.

### Step 6 — Apply route_plan minimums

After validation, ensure the route_plan contains the minimum viable set even if the model omitted them:

- `transcription` — always
- `composition` — always
- `tagging` — always

Do not silently drop entries the model added.

### Step 7 — Write the artifact

```
notella-state log-page-artifact {
  page-id,
  artifact: "classify",
  payload: <validated JSON>
}
```

### Step 8 — Mirror content_mix into meta.yaml

```
notella-state update-page-meta {
  page-id,
  fields: { content_mix, confidence }
}
```

This is the only `meta.yaml` mutation classify performs. (notella-state exposes a narrow update operation for this; full meta rewrites stay reserved for phase advances and intake.)

### Step 9 — Advance phase

```
notella-state advance-phase {
  page-id,
  to-phase: classified,
  by-actor: notella-classify
}
```

This emits the `page.classified` event automatically:

```yaml
kind: page.classified
page_id: {page-id}
evidence:
  doc_type: <chosen>
  confidence: <0-1>
  route_plan: [...]
  content_mix: { text, diagram, table, symbolic }
```

### Step 10 — Release the page lock

```
notella-state release-page-lock {page-id, actor: notella-classify}
```

## Idempotency

- Re-running on a page already at `phase >= classified`: no-op unless `--reprocess` is set.
- With `--reprocess`: the existing `classify.json` is overwritten and a `correction` event is emitted. The page does NOT roll back to intake; downstream artifacts remain valid until they're explicitly re-run.

## Failure modes

| Failure                              | Behavior                                                |
| ------------------------------------ | ------------------------------------------------------- |
| Vision API unavailable               | Surface error, leave page at phase=intake, log to pipeline.ndjson with status=error. |
| Model returns invalid JSON           | Retry once with the same prompt; on second failure, surface error. |
| Schema validation fails              | Surface error, do not write artifact, log diagnostics. |
| Confidence < 0.60                    | Apply `fallback_strategy` if the model provided one (typically: "treat as handwritten_text"); proceed but mark `meta.yaml:errors` with a note. |
| Page lock held                       | Wait up to 30s, then abort. |

## What this skill does NOT do

- Does not transcribe — `notella-transcribe` is the next stage.
- Does not infer projects, themes, or people — that's `notella-metadata`.
- Does not look at any other pages.

## Examples

### "Classify page 2026-05-02-x7k2"

Reads the page at phase=intake, calls Haiku 4.5 with the image, returns:

```
doc_type: mixed_text_diagram
content_mix: { text: 60, diagram: 30, table: 0, symbolic: 5 }
route_plan: [transcription, semantic_structuring, diagram_interpretation, action_decision, composition, tagging]
confidence: 0.91
fallback_strategy: "none"
```

Phase advances to `classified`. `meta.yaml` updated with content_mix.

### "Reclassify page 2026-05-02-x7k2 with --reprocess"

Overwrites `classify.json`. Emits a `correction` event referencing the previous classify event-id. Subsequent stages may need re-running with `--reprocess` if the new route_plan differs.

## Reference files

- `references/classify-prompt.md` — full system prompt + user prompt.
- `references/route-plan-vocab.md` — definitions of every route_plan vocabulary entry.
