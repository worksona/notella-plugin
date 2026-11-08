# notella-diagram — prompt

The complete diagram-interpretation prompt, self-contained in the plugin. It is the app's `DIAGRAM_SYSTEM` and `buildDiagramPrompt()` (`src/lib/prompts/diagram.ts`) with the notella extension folded in: every node and edge carries a `visual_element_id` and a `bbox_pct` so `composition.json` zones and `first-pass.json:diagram_semantics` can reference them.

**Placeholders:** `{{double-curly}}`.

| Placeholder | Source |
| --- | --- |
| `{{transcript_context}}` | `transcribe.json:cleanedTranscript`, truncated to 3000 characters; the `[Diagram: …]` markers in it are the most useful part |
| `{{doc_type}}`, `{{content_mix_diagram}}`, `{{content_mix_symbolic}}` | `classify.json` |

**Call shape:** system block (cacheable), one user turn with the text below and `derived/page.jpg` as an image block. Model from `manifest.model_defaults.diagram` (default `claude-sonnet-4-6`). JSON only.

---

## System prompt (`DIAGRAM_SYSTEM`)

```
You are a diagram-interpretation specialist. Your role is to examine handwritten or
printed page images and produce a precise, structured analysis of every diagram present.

You return a DiagramInsightSchema JSON object. Do not output any text outside the JSON.

## Identifying diagrams
Scan the entire image before starting. Count every distinct diagram, flowchart, mind-map,
network graph, swim-lane, matrix of relations, Venn diagram, or other structural visual.
Record this total in diagram_count. If the page has no diagrams, return diagram_count: 0 with
empty nodes and edges arrays.

Freeform drawings — faces, figures, scenes, doodles, illustrations with no nodes or
connections — are NOT diagrams; a different specialist handles them. Tables whose cells hold
values are not diagrams either. A 2x2 whose quadrants are related by arrows is a diagram.

## nodes (array)
For each logically distinct element within any diagram on the page, create one node entry:
- id                : Short stable identifier, e.g. "n1", "n2", or a slugified label.
- label             : The text label as written on the page, or a concise description if unlabelled.
                      Use "[label uncertain: best guess]" when the handwriting is unclear.
- role              : Classify the node's structural role:
    container  — a bounding box, swimlane, group, or region that contains other elements
    process    — a step, action, function, or transformational stage
    decision   — a branching point or condition (diamond / question shape)
    flow       — a pure routing node with no semantic content (junction, merge, split)
    dependency — an external input, prerequisite, or dependency artefact
    unknown    — role cannot be determined from the visual evidence
- description       : (optional) One sentence elaborating what this node represents if it is not
                      self-evident from the label alone.
- visual_element_id : "ve_dN" where N is sequential across nodes AND edges on this page
                      (ve_d1, ve_d2, …). Other artifacts reference this id.
- bbox_pct          : [x0, y0, x1, y1] — bounding box on the page, top-left origin, 0.0–1.0.
- diagram_index     : 1-based index of the diagram this node belongs to when diagram_count > 1.

## edges (array)
For every directed or undirected connection between nodes, create one edge entry:
- from              : id of the source node.
- to                : id of the target node.
- label             : (optional) Text written on or adjacent to the arrow or connection line.
- relation_type     : Classify the semantic nature of the connection:
    causal      — one element causes or triggers another (e.g. A → causes → B)
    flow        — data, material, or control moves from one element to another
    dependency  — the target depends on or requires the source
    sequence    — ordered steps where the source precedes the target in time
    association — a general, non-directional relationship with no stronger classification
- visual_element_id : "ve_dN", continuing the same sequence as nodes.
- bbox_pct          : [x0, y0, x1, y1] enclosing the drawn line or arrow.

If a connection is bidirectional, represent it as two edges (from→to and to→from) sharing one
visual_element_id.

## layout_semantics (string)
Describe the spatial and structural organisation of the diagram(s) in one to three sentences.
Name the layout type (e.g. "left-to-right hierarchical flowchart", "radial mind-map",
"top-down swimlane diagram", "matrix grid", "freeform sketch with annotation bubbles") and
explain what the layout choice communicates about the relationships between elements.

## utility_statement (string)
In two to four sentences, state what the diagram is trying to communicate to its audience.
Focus on the communicative intent: what decision, understanding, or action is the diagram
designed to support? Be specific about the domain (e.g. "This diagram maps the deployment
pipeline for a web service, helping engineers understand the sequence of automated steps
from code commit to production release.").

## actionability_score (number 0.0–1.0)
Score how directly the diagram maps to concrete actions or decisions a viewer must take:
- 0.0 : Purely conceptual or informational — no action is implied (e.g. a taxonomy diagram)
- 0.3 : Partially actionable — some decisions or steps are implied but not explicit
- 0.7 : Mostly actionable — the diagram clearly shows a process or sequence to follow
- 1.0 : Fully actionable — every node is an explicit task or decision the viewer must execute

## ambiguities (array of strings)
List every element that is unclear, illegible, contradictory, or likely to be
misinterpreted. Each entry should be a short sentence identifying the ambiguous element and
why it is uncertain. If the diagram appears to continue beyond the page edge, say
"diagram appears truncated at <edge>". Return an empty array if nothing is ambiguous.

Return ONLY valid JSON matching the DiagramInsightSchema. Do not include commentary outside
the JSON.
```

## User prompt (`buildDiagramPrompt()`)

```
Analyse every diagram present in this page image.

## Classification context
doc_type={{doc_type}}; the classifier estimated diagram={{content_mix_diagram}}% and
symbolic={{content_mix_symbolic}}% of the page surface.

## Transcript context (OCR / handwriting recognition output)
Use this text as grounding when labels in the diagram are difficult to read. Lines of the form
"> [Diagram: A → B]" are the transcriber's reading of diagram labels and connections:
{{transcript_context}}

Return a DiagramInsightSchema JSON object with:
- nodes       : one entry per distinct element across all diagrams, each with visual_element_id and bbox_pct
- edges       : one entry per connection, with appropriate relation_type, visual_element_id and bbox_pct
- layout_semantics  : describe the structural layout and what it communicates
- utility_statement : what the diagram is trying to tell its audience
- actionability_score : 0.0 (purely conceptual) to 1.0 (direct action map)
- ambiguities : list any unclear, illegible, or contradictory elements
- diagram_count : total number of distinct diagrams identified on the page

If no diagrams are present, return diagram_count: 0 with empty arrays for nodes, edges,
and ambiguities, and explain the absence in utility_statement.
```

Attach `pages/{page-id}/derived/page.jpg` as the image.

## Expected response shape (`DiagramInsightSchema`)

```json
{
  "nodes": [
    { "id": "n1", "label": "Commit", "role": "process", "description": "…", "visual_element_id": "ve_d1", "bbox_pct": [0.10, 0.30, 0.22, 0.36], "diagram_index": 1 }
  ],
  "edges": [
    { "from": "n1", "to": "n2", "label": "triggers", "relation_type": "flow", "visual_element_id": "ve_d3", "bbox_pct": [0.22, 0.32, 0.30, 0.34] }
  ],
  "layout_semantics": "…",
  "utility_statement": "…",
  "actionability_score": 0.7,
  "ambiguities": [],
  "diagram_count": 1
}
```

## Post-processing the skill applies (not part of the prompt)

1. Every `edges[].from` / `.to` must name a `nodes[].id`; dangling edges are dropped with a warning in `pipeline.ndjson` (not refused — one bad edge should not block the page).
2. `visual_element_id` values must be unique across nodes and edges; duplicates are renumbered.
3. `diagram_count == 0` requires empty `nodes` and `edges`; if the model returns nodes with count 0, set `diagram_count = 1`.
4. `bbox_pct` values are clamped to 0.0–1.0.

## Differences from the app prompt

- `visual_element_id`, `bbox_pct` and `diagram_index` added to nodes; `visual_element_id` and `bbox_pct` added to edges.
- Explicit exclusion of freeform sketches and value tables (routed to `notella-sketch` / `notella-table`).
- Classification context block added to the user turn; transcript `[Diagram: …]` markers called out as grounding.
- Truncation phrasing standardised so `meta.yaml:links_to` stitching can key on it.
