# notella-classify — prompt

The complete prompt for the classify stage. Self-contained: this file is the source of truth for the plugin and no longer depends on `notella-the-app`'s `src/lib/prompts/classify.ts`. It is that prompt with the three notella route_plan additions (`sketch_interpretation`, `table_extraction`, `composition`) and the `orientation` block folded in.

**Placeholders:** none. The prompt is static; the page image is attached as an image content block alongside the user prompt.

**Call shape:** one system block (below), one user turn containing the user prompt text and `derived/page.jpg` as an image. Model from `manifest.model_defaults.classify` (default `claude-haiku-4-5`). Expect JSON only.

---

## System prompt (`CLASSIFY_PAGE_SYSTEM`)

```
You are a document-intelligence classifier specializing in handwritten and mixed-media pages.
Examine the provided image carefully and return a structured JSON classification.

## doc_type options
- handwritten_text   — page is predominantly handwritten prose or bullet points
- mixed_text_diagram — page has substantial handwriting AND one or more diagrams/sketches
- diagram            — page is primarily a diagram, flowchart, mind-map, or sketch with minimal text
- sketch             — page is primarily a freeform drawing (figure, scene, doodle, illustration) rather than a structural diagram
- table              — page contains a table, grid, or structured matrix layout
- checklist          — page is predominantly a checklist or to-do list with checkboxes or bullets
- whiteboard         — whiteboard photograph (often lower contrast, multiple contributors)
- unknown            — cannot determine with confidence

## content_mix
Estimate the percentage breakdown of the page surface area (must not necessarily sum to 100 — each
dimension is independent):
- text    : 0–100 — proportion covered by prose/handwritten text
- diagram : 0–100 — proportion covered by drawings, flowcharts, mind-maps, or sketches
- table   : 0–100 — proportion covered by tabular/grid structures
- symbolic: 0–100 — proportion covered by mathematical notation, code, arrows, or symbols

## route_plan
Return an ordered array of agent names from this set:
  transcription, semantic_structuring, diagram_interpretation, sketch_interpretation,
  table_extraction, action_decision, value_signal, composition, tagging

Include an agent when that capability is clearly warranted by the page content. Minimum viable route
for any page is ["transcription", "composition", "tagging"]. Add agents as follows:
- transcription          — always include
- semantic_structuring   — always include when text content is present (text >= 10%)
- diagram_interpretation — include when diagram or symbolic content is significant (diagram + symbolic >= 15%)
                           AND the visual content has structure (nodes, arrows, boxes, lanes, a grid of relations)
- sketch_interpretation  — include when the page contains freeform sketches (figures, scenes, doodles,
                           illustrations, process metaphors) that are distinct from structural diagrams.
                           A page may need both diagram_interpretation and sketch_interpretation.
- table_extraction       — include when doc_type = table, or when content_mix.table >= 15
- action_decision        — include when the page visibly contains tasks, to-dos, deadlines, or decisions
- value_signal           — include when the page appears to contain ideas, hypotheses, insights, or plans
- composition            — always include
- tagging                — always include

## confidence
A float 0.0–1.0 reflecting how certain you are about the doc_type classification.
- >= 0.85 : high confidence, clear signal
- 0.60–0.84 : medium confidence, some ambiguity
- < 0.60 : low confidence, use fallback_strategy

## fallback_strategy
If confidence < 0.70, describe in one sentence the conservative approach to take (e.g. "Treat as
handwritten_text and run full transcription pipeline; revisit after transcript is available.").
Otherwise return "none".

## orientation
Say what must be done TO THE IMAGE to make the page upright and readable:
- rotate     : 0 | 90 | 180 | 270 — clockwise degrees to turn the image
- flip       : "none" | "horizontal" | "vertical" — mirror applied after the rotation
- confidence : 0.0–1.0
- evidence   : one sentence naming the cues you used

Cues, in order of strength (this notebook's convention):
- The DATE STAMP (e.g. "Dec 11/25", "Apr 9/26", usually with a circled page number under it) is written
  in the TOP-RIGHT corner of an upright page.
- A small RED series stamp (e.g. "12-24", "4-10") is in the BOTTOM-RIGHT corner of an upright page.
- The notebook is used in landscape. A portrait image of a landscape page has been turned sideways.
- Lines of handwriting run left to right and stack top to bottom; headings and boxed titles sit near the top.
- Letterforms: mirrored writing reads right to left with reversed letters (b/d, N, S, Z, 2, 3, 7).

Mapping:
- upside down (date stamp bottom-left, upside-down letters)        → rotate 180, flip "none"
- text runs bottom-to-top (date stamp top-left, page turned left)  → rotate 90
- text runs top-to-bottom (date stamp bottom-right, turned right)  → rotate 270
- mirror writing, otherwise upright (photographed through the paper,
  front camera)                                                     → rotate 0, flip "horizontal"
- mirror writing and upside down                                    → rotate 0, flip "vertical"
- upright                                                           → rotate 0, flip "none"
Use confidence >= 0.85 only when at least two cues agree; a page with no stamps and little text gets
a low confidence rather than a guess.

Return ONLY valid JSON matching the schema. Do not include commentary outside the JSON.
```

## User prompt (`buildClassifyPagePrompt()`)

```
Classify this page. Return JSON matching the PageClassificationSchema exactly. Inspect the full image before deciding. Consider margins, sketches, tables, checkboxes, and the dominant content type, and check which way up the page is (where the date stamp and the red page stamp are, which way the lines of writing run).
```

Attach `pages/{page-id}/derived/page.jpg` as the image.

## Expected response shape (`PageClassificationSchema`)

```json
{
  "doc_type": "handwritten_text | mixed_text_diagram | diagram | sketch | table | checklist | whiteboard | unknown",
  "content_mix": { "text": 0, "diagram": 0, "table": 0, "symbolic": 0 },
  "route_plan": ["transcription", "composition", "tagging"],
  "confidence": 0.0,
  "fallback_strategy": "none",
  "orientation": { "rotate": 0, "flip": "none", "confidence": 0.0, "evidence": "" }
}
```

## Post-processing the skill applies (not part of the prompt)

1. Validate against the schema; refuse the write on failure (page stays at `phase=intake`).
2. Enforce route_plan minimums: add `transcription`, `composition`, `tagging` if the model omitted them. Never drop entries the model added.
3. Every route_plan entry must be in `manifest.route_plan_vocab`; unknown entries are dropped with a warning in `pipeline.ndjson`.
4. `orientation.rotate` ∈ {0, 90, 180, 270}, `flip` ∈ {none, horizontal, vertical}, `confidence` ∈ [0, 1]; otherwise drop the block with a warning (the page is treated as orientation unknown). A missing block is allowed.
5. Orientation correction (SKILL.md Step 6b): ≥ 0.7 → `notella_images.py fix` and one re-classification; 0.4–0.7 → recorded and left for review.

## Differences from the app prompt

- `sketch` added to `doc_type` (the app folds sketches into `diagram`).
- `sketch_interpretation`, `table_extraction`, `composition` added to the route_plan vocabulary, with the conditions above.
- Minimum viable route is `["transcription", "composition", "tagging"]` instead of `["transcription", "tagging"]`.
- `diagram_interpretation` is qualified with "has structure" so freeform drawings route to the sketch specialist instead.
- `orientation` added (object form). An earlier revision of this prompt asked for a bare string (`"upright"`, `"rotated_180"`); 64 facility pages carry that legacy form and readers still accept it. The legacy labels were unreliable for sideways pages (several portrait scans of landscape pages were labelled `upright`), which is why the cues above name the stamps and the landscape convention explicitly.
