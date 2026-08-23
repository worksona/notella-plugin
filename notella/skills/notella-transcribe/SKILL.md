---
name: notella-transcribe
description: "Transcribe a notella page — produce raw verbatim transcript and a structured cleanedTranscript (markdown), extract date and top-right page-no., promote marginalia and emphasis marks to typed spans. Use whenever the user says 'transcribe page X', 'OCR this page', 'read the handwriting', 'extract text from page X', 'transcribe my notes', or any request to convert page imagery into text. Also trigger automatically when notella-orchestrator finds a page at phase=classified. Reads through `notella-state`; writes `transcribe.json` and advances phase to `transcribed`. Idempotent unless `--reprocess` is passed."
---

# notella-transcribe — the page-to-text bridge

Reads the page image, produces faithful verbatim and structured-markdown transcripts, captures marginalia + emphasis as typed spans, and extracts date + top-right page-no.

## Purpose

Convert handwritten content into queryable text without losing structural signal. Marginalia, emphasis, hierarchy, and uncertainty are first-class — they're what later layers read.

## Inputs and outputs

**Input:** Page at `phase=classified`. Reads `pages/{page-id}/derived/page.jpg`, `pages/{page-id}/classify.json`.

**Output:**
- `pages/{page-id}/transcribe.json`
- Page advanced to `phase=transcribed`
- `page.transcribed` event

## How a run executes

### Step 1 — Read configuration & page

```
notella-state get-manifest → manifest.model_defaults.transcribe
notella-state get-page {page-id}
notella-state get-page-artifact {page-id, artifact: classify}
```

Verify `phase == classified`. Skip if `transcription` is not in `route_plan` (unusual but possible).

### Step 2 — Acquire the page lock

```
notella-state acquire-page-lock {page-id, actor: notella-transcribe@<version>}
```

### Step 3 — Build the prompt

Base prompt: notella-the-app's `buildTranscribePrompt()` from `src/lib/prompts/transcribe.ts`. Keep the existing language verbatim (it has been tuned for handwritten business / strategy notes), with two extensions:

**Extension 1 — promote marginalia to a structured array** instead of inline markers. The prompt asks the model to emit a `marginalia[]` array alongside the markdown:

```
For each marginal note, callout, or annotation, emit one entry in the marginalia array:
- position: top | bottom | left | right | inline
- content: the verbatim text of the note
- target_span_id: optional — the id of the cleanedTranscript span this marginalia points to
- kind: annotation | callout | arrow-to | correction | aside
- bbox_pct: [x0, y0, x1, y1] — bounding box on the page, top-left origin, 0.0-1.0
```

**Extension 2 — promote emphasis marks** to a typed array:

```
For every emphasis mark you observe (underlining, double-underlining, circles, stars, boxes, color highlights, exclamation marks, arrows), emit one entry in the emphasis array:
- span_id: the id of the cleanedTranscript span the emphasis applies to
- span_text: the exact text under emphasis
- mark_type: underline | double-underline | circle | star | box | color | exclamation | arrow-to
- intensity: 1 (light) | 2 (clear) | 3 (heavy / multi-mark)
```

The cleanedTranscript still uses markdown `**bold**` for emphasis where appropriate, but the typed `emphasis[]` array carries the full signal.

### Step 4 — Call the model

Provider/model from `manifest.model_defaults.transcribe` (default `claude-sonnet-4-6`). Log the call.

### Step 5 — Validate

Parse against the schema:

```yaml
rawTranscript: string
cleanedTranscript: string
extractedDate: "YYYY-MM-DD" | null
extractedDateConfidence: 0.0-1.0
extractedPageNumber: string | null
extractedPageNumberSource: top-right | other | inferred | null
transcriptConfidence: 0.0-1.0
marginalia: [...]
emphasis: [...]
```

Refuse to write if validation fails.

### Step 6 — Write the artifact

```
notella-state log-page-artifact {page-id, artifact: transcribe, payload: <validated>}
```

### Step 7 — Advance phase

```
notella-state advance-phase {page-id, to-phase: transcribed, by-actor: notella-transcribe}
```

Emits `page.transcribed` event with evidence:

```yaml
evidence:
  transcriptConfidence: 0.86
  extractedDate: "2026-05-02"
  extractedPageNumber: "47"
  char_count: 1842
  marginalia_count: 3
  emphasis_count: 7
```

### Step 8 — Release the page lock

```
notella-state release-page-lock {page-id, actor: notella-transcribe}
```

## Idempotency

- Re-running on `phase >= transcribed`: no-op unless `--reprocess`.
- `--reprocess`: overwrite `transcribe.json`, emit `correction` event. Marginalia and emphasis arrays may differ from previous runs; downstream skills consuming them must re-run.

## Failure modes

| Failure                                           | Behavior |
| ------------------------------------------------- | -------- |
| Confidence below 0.50                             | Write artifact anyway with the low confidence; surface in batch summary; user can request `--reprocess` with a stronger model. |
| Heavily-marked page (`emphasis_count > 30`)       | Often correlates with strategy notes; expected, no special action. |
| Page rotation detected mid-call                   | The model handles intra-call rotation; if confidence remains low, suggest re-photographing. |
| Vision API timeout                                | Retry once; on second failure, surface error and leave at phase=classified. |

## What this skill does NOT do

- Does not interpret diagrams. That's `notella-diagram`. (The transcribe prompt does emit `[diagram label: "..."]` markers in cleanedTranscript for spatial reference, but does not extract structure.)
- Does not infer projects/themes/people. That's `notella-metadata`.
- Does not run on pages whose `route_plan` excludes `transcription` (rare; whiteboard photos sometimes do).

## Examples

### "Transcribe page 2026-05-02-x7k2"

Calls Sonnet 4.6 with the image. Produces ~1800-char rawTranscript, structured markdown cleanedTranscript with hierarchy preserved, marginalia[] = 3 entries, emphasis[] = 7 entries, extractedDate=2026-05-02, extractedPageNumber=47, transcriptConfidence=0.86. Phase advances to `transcribed`.

### "Re-transcribe page 2026-05-02-x7k2 --reprocess --model=claude-opus-4-6"

Overrides default model. Overwrites transcribe.json. Emits correction event.

## Reference files

- `references/transcribe-prompt.md` — full prompt with the marginalia + emphasis extensions.
- `references/marginalia-rules.md` — disambiguation rules (annotation vs callout vs arrow-to).
- `references/emphasis-rules.md` — how to grade intensity 1/2/3.
