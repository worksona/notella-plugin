---
name: notella-sketch
description: "Interpret freeform sketches on a notella page — subject, technique, intent, elements, text-association, affective signal. Distinct from diagrams (which have nodes and edges); a sketch is a face, a scene, a doodle, a process metaphor, an illustration. Use whenever the user says 'what's drawn on page X', 'analyze the sketch', 'interpret this drawing', 'is there a sketch here', or any request to structure non-diagram visual content. Conditional: runs when classify.json:route_plan includes sketch_interpretation. Reads through `notella-state`; writes `sketch.json`."
---

# notella-sketch — the sketch interpreter

A diagram has nodes and edges; a sketch has subject and intent. This skill captures the latter.

## Purpose

Many notebook pages contain illustrations that aren't structural — a quick face, a scene metaphor, a doodled icon, an explanatory drawing. They carry signal: tone, mnemonic content, affective state, what the author was reaching for non-verbally. This skill records that signal in queryable form.

## Inputs and outputs

**Input:** Page at `phase=transcribed` with `route_plan` containing `sketch_interpretation`. Reads `derived/page.jpg`, `transcribe.json`, `classify.json`.

**Output:**
- `pages/{page-id}/sketch.json`
- No phase advance.
- `pipeline.ndjson` line.

## How a run executes

### Step 1 — Read configuration & page

```
notella-state get-manifest → cost-controls.yaml:model_defaults.sketch
notella-state get-page-artifact {page-id, artifact: classify}
notella-state get-page-artifact {page-id, artifact: transcribe}
```

Verify `phase >= transcribed` and `route_plan` includes `sketch_interpretation`. Skip cleanly otherwise.

### Step 2 — Acquire the page lock

### Step 3 — Build the prompt

Use the prompt in `references/sketch-prompt.md` — the complete system and user prompt shipped with this plugin (no app counterpart; the prompt is native to the plugin). In outline, the system prompt defines a sketch as a drawing that is NOT a structural diagram (no nodes/edges/swim-lanes), tells the model to skip flowcharts, mind-maps, tables and matrices (and to list borderline drawings in `ambiguities` — see `references/sketch-vs-diagram.md`), and asks for one entry per sketch:

- `id` (`sk_NNN`), `bbox_pct`
- `subject` — short noun phrase
- `technique` — line | shading | cartoon | technical | mixed
- `intent` — decorative | illustrative | explanatory | exploratory | mnemonic
- `elements[]` — kind, bbox_pct, label, visual_element_id (`sk_NNN_eM`)
- `text_association` — adjacent_to_zone (composition zone id or null), relationship explains | illustrates | decorates | unrelated
- `affective_signal` — calm | energetic | playful | serious | uncertain | frustrated, read from execution not subject (`references/affective-signal-rules.md`)
- `confidence`

plus `sketch_count` and `ambiguities[]`. The user prompt carries the classification context, a transcript excerpt and the composition zones when available. Include the image.

### Step 4 — Call the model

Runs on the model in `cost-controls.yaml` `model_defaults.sketch` (currently `sonnet`, chosen by the 2026-11-08 eval: haiku key recall on sketch pages matched sonnet but word recall was weaker; kept with the other vision readers). When the orchestrator runs this stage it dispatches a subagent with that model; run directly, it uses the session model.

### Step 5 — Validate

```yaml
sketches:
  - id, bbox_pct, subject, technique, intent, elements[], text_association, affective_signal, confidence
sketch_count: int
```

Sanity: `len(sketches) == sketch_count`.

### Step 6 — Write & release lock

```
notella-state log-page-artifact {page-id, artifact: sketch, payload}
notella-state release-page-lock {page-id, actor: notella-sketch}
```

## Idempotency

Standard.

## Failure modes

| Failure                                                | Behavior |
| ------------------------------------------------------ | -------- |
| Classifier flagged sketch_interpretation but no sketches found | Return empty arrays; this is a correct outcome, not an error. |
| Borderline sketch-vs-diagram                           | If the model is uncertain, prefer diagram (structural treatment is more useful for ambiguous cases). Surface in `ambiguities`. |
| Cartoon faces on every page (a doodle habit)           | Expected for some users; intent=decorative is fine. |

## What this skill does NOT do

- Does not interpret diagrams (`notella-diagram`).
- Does not infer who the sketched person is unless explicitly labeled — that's `notella-metadata`.
- Does not project affective signal across pages — that aggregation is `notella-themes`.

## Examples

### "Analyze sketches on page 2026-05-02-x7k2"

```json
{
  "sketches": [
    {
      "id": "sk_001",
      "subject": "process metaphor with figures",
      "technique": "line",
      "intent": "explanatory",
      "elements": [
        { "kind": "figure", "label": "user", "bbox_pct": [0.2, 0.5, 0.3, 0.7] },
        { "kind": "figure", "label": "system", "bbox_pct": [0.6, 0.5, 0.7, 0.7] },
        { "kind": "line", "bbox_pct": [0.3, 0.6, 0.6, 0.6] }
      ],
      "text_association": { "adjacent_to_zone": "z2", "relationship": "illustrates" },
      "affective_signal": "playful",
      "confidence": 0.78
    }
  ],
  "sketch_count": 1
}
```

## Reference files

- `references/sketch-prompt.md` — full prompt.
- `references/sketch-vs-diagram.md` — disambiguation rules.
- `references/affective-signal-rules.md` — how to read line weight + repetition.
