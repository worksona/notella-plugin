---
name: notella-classify
description: "Classify a notella page — diagnose doc_type, content_mix (text/diagram/table/symbolic %), the page's orientation (upside down, sideways, mirrored — and the rotate/flip that makes it upright), and produce the route_plan that tells downstream specialists which agents to run. Fixes a confidently mis-oriented page via notella-images before advancing. Use whenever the user says 'classify this page', 'what kind of page is this', 'diagnose page X', 'set up the route plan', 'is this page upside down', or any request to determine how a page should be processed. Also trigger automatically when notella-orchestrator finds a page at phase=intake. Reads through `notella-state`; writes `classify.json` and advances phase to `classified`. Idempotent unless `--reprocess` is passed."
---

# notella-classify — the page diagnostician

First specialist in the pipeline. Looks at a page in `phase=intake` and decides what it is and what should run next.

## Purpose

Diagnose the page's structural character and produce the `route_plan` array that downstream specialists consume. Without a good classification, transcription wastes effort on diagrams and the diagram skill gets called on pure prose.

## Inputs and outputs

**Input:**
- A page at `phase=intake`. Reads `pages/{page-id}/derived/page.jpg` (the canonical decode) and `pages/{page-id}/meta.yaml`.

**Output:**
- `pages/{page-id}/classify.json` (including `orientation`)
- Page advanced to `phase=classified`
- Mirror `content_mix` and `confidence` into `meta.yaml` for fast filtering
- `page.classified` event emitted
- When the page is confidently mis-oriented: `derived/page.jpg` rebuilt upright by `notella-images fix` (with its `correction` event) and the classification redone on the corrected image

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

System prompt (`CLASSIFY_PAGE_SYSTEM`) — see `references/classify-prompt.md`, the complete prompt shipped with this plugin. It carries three additions to the route_plan vocabulary beyond the original app prompt (each entry is defined in `references/route-plan-vocab.md`):

```
- sketch_interpretation       — include when the page contains freeform sketches (figures, scenes, doodles) distinct from structural diagrams
- table_extraction            — include when doc_type=table or when content_mix.table >= 15
- composition                 — always include
```

User prompt: `"Classify this page. Return JSON matching the PageClassificationSchema exactly. Inspect the full image before deciding. Consider margins, sketches, tables, checkboxes, and the dominant content type."`

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
orientation:                            # what to do to the image to make the page upright and readable
  rotate: 0 | 90 | 180 | 270            # clockwise degrees
  flip: none | horizontal | vertical    # applied after the rotation
  confidence: 0.0-1.0
  evidence: string                      # one sentence: which cues decided it
```

Refuse to write if validation fails; surface the error and leave the page at phase=intake. A response without `orientation` is accepted (older prompt) and written without it.

**Legacy values.** Older `classify.json` files carry `"orientation": "upright"` or `"rotated_180"` (a string). They stay valid and readable: readers treat `"upright"` as `{rotate: 0, flip: none}`, `"rotated_180"` / `"upside_down"` as rotate 180, `"mirrored"` as flip horizontal, and any other string as "not upright, direction unknown". New writes always use the object form.

### Step 6 — Apply route_plan minimums

After validation, ensure the route_plan contains the minimum viable set even if the model omitted them:

- `transcription` — always
- `composition` — always
- `tagging` — always

Do not silently drop entries the model added.

### Step 6b — Orientation: correct before advancing

Read `classify.orientation` and the page's `quality.json` (written at intake by `notella-images scan`; its `orientation.suggested` may come from the red series stamp found in the wrong corner).

| Classify says | Action |
| --- | --- |
| `rotate == 0` and `flip == none` | Nothing. (If `quality.json` is `suspected` with a concrete suggestion and classify disagrees, leave it: transcribe will hold the page and `notella-review` shows it under "Image attention".) |
| not upright, `confidence ≥ 0.7` — or `≥ 0.4` and it equals `quality.json`'s `suggested` | **Fix and re-classify** (below). |
| not upright, `0.4 ≤ confidence < 0.7`, no agreement | Write the artifact as is, append to `meta.yaml:errors`: `"orientation suspected (rotate R, flip F, confidence C): {evidence}"`, and let `notella-images scan` mark the page `suspected` — review decides. |
| not upright, `confidence < 0.4` | Ignore (noise); keep it in `classify.json` for the record. |

**Fix and re-classify** — at most one correction loop per run:

```bash
python3 "$CLAUDE_PLUGIN_ROOT/scripts/notella_images.py" fix --page {page-id} --rotate R --flip F
```

The transform is absolute relative to `raw/` (the script applies EXIF first): pass exactly what classify returned. The script rebuilds `derived/page.jpg` + `thumb.jpg`, records `meta.yaml:orientation_fix`, recomputes `quality.json` (status `fixed`) and writes a `correction` event (`correction_type: orientation-fix`). Then repeat Steps 3–6 on the corrected image and use **that** classification. If the second classification still says the page is not upright, write it, do not fix again, and add the `meta.yaml:errors` note above — a person looks next.

Release and re-acquire the page lock around the script call (the script takes the page lock itself).

Log the loop in `pipeline.ndjson` (`action: orientation-correction`, `rotate`, `flip`, `confidence`, `reclassified: true`).

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
  orientation: { rotate, flip, confidence }
  orientation_fixed: true | false        # a fix was applied during this run
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
| `notella_images.py fix` fails (no sips, no raw) | Write the classification of the uncorrected image, note the failure in `meta.yaml:errors`, advance; transcribe will hold the page while `quality.json` is `suspected`. |
| Corrected image still not upright | No second fix; errors note; surfaced by review. |
| Classify and the red-stamp signal disagree | No fix unless classify alone is ≥ 0.7; the page waits for a person (review "Image attention"). |

## What this skill does NOT do

- Does not transcribe — `notella-transcribe` is the next stage.
- Does not infer projects, themes, or people — that's `notella-metadata`.
- Does not look at any other pages.
- Does not rotate pixels itself — it calls `notella-images` (`scripts/notella_images.py fix`), which owns `derived/` rebuilds and the `orientation_fix` record.

## Examples

### "Classify page 2026-05-02-x7k2"

Reads the page at phase=intake, calls Haiku 4.5 with the image, returns:

```
doc_type: mixed_text_diagram
content_mix: { text: 60, diagram: 30, table: 0, symbolic: 5 }
route_plan: [transcription, semantic_structuring, diagram_interpretation, action_decision, composition, tagging]
confidence: 0.91
fallback_strategy: "none"
orientation: { rotate: 0, flip: none, confidence: 0.95, evidence: "date stamp top-right, red stamp bottom-right, text reads left to right" }
```

Phase advances to `classified`. `meta.yaml` updated with content_mix.

### "Classify page 2026-05-02-p4q1" (photographed upside down)

First pass returns `orientation: { rotate: 180, flip: none, confidence: 0.92, evidence: "date stamp upside down in the bottom-left; red stamp top-left" }`. The skill runs `notella_images.py fix --page 2026-05-02-p4q1 --rotate 180`, re-classifies the corrected image (now `rotate: 0`, confidence 0.94), writes that, and advances. One `correction` event (orientation-fix) and one `page.classified` event with `orientation_fixed: true`.

### "Reclassify page 2026-05-02-x7k2 with --reprocess"

Overwrites `classify.json`. Emits a `correction` event referencing the previous classify event-id. Subsequent stages may need re-running with `--reprocess` if the new route_plan differs.

## Reference files

- `references/classify-prompt.md` — full system prompt + user prompt.
- `references/route-plan-vocab.md` — definitions of every route_plan vocabulary entry.
