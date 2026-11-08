# Edge relation rules

How to choose `edges[].relation_type` in `diagram.json`. Five values: `causal`, `flow`, `dependency`, `sequence`, `association`. Downstream, first-pass turns these into `diagram_semantics.purpose`/`actionability`, and themes uses the mix (causal-heavy pages are strategy; sequence-heavy pages are plans).

## Decision order

Pick the first that fits.

| Order | relation_type | Test | Drawn as / labelled |
| --- | --- | --- | --- |
| 1 | `causal` | The source *makes the target happen or change*. Removing the source would remove or alter the target. | Arrow labelled "causes", "leads to", "→ so", "drives", "+"/"−" (causal loop diagrams), "because" |
| 2 | `dependency` | The target *needs* the source before it can exist or proceed, but the source does not act on it. | Arrow labelled "needs", "requires", "blocked by", "after X is done"; arrow from an external input / resource node; dotted arrow into a step |
| 3 | `sequence` | Source then target, as steps in time, with no claim of causation or need beyond order. The default for flowchart arrows between process nodes and for timeline links. | Plain arrow in a flowchart; numbered steps; timeline segments; "then", "next" |
| 4 | `flow` | Something concrete (data, money, material, a document, control) moves along the arrow from source to target. | Arrow labelled with the thing moving ("invoice", "data", "$", "request"); pipes; data-flow diagrams |
| 5 | `association` | A relationship exists but the drawing does not say what kind. Default for undirected lines, mind-map branches, and Venn intersections. | Plain line, no arrowhead; double-headed arrow without label; branch from a mind-map hub; "related to" |

### Why sequence before flow

In handwritten flowcharts almost every arrow is a plain arrow between steps. Calling those `flow` would make the type meaningless. `flow` is reserved for when the arrow is labelled with, or obviously carries, *a thing*. A deployment pipeline "Commit → Build → Test" is `sequence`; "Build → (artifact) → Deploy" with the artifact written on the arrow is `flow`.

### Why causal before dependency

Both are "A affects B". Causal is active (A pushes B); dependency is passive (B waits for A). A labelled "unblocks" is causal; "blocked by" is dependency (with from/to reversed so the arrow points from prerequisite to dependent). When the arrow is unlabelled and both readings fit, use `dependency` if the source is a `dependency`-role node, else `causal` if the diagram is explicitly about causes (loops, "why" trees), else `sequence`.

## Direction

- `from` → `to` follows the arrowhead.
- Lines without arrowheads: `association`, with `from` the left/upper node and `to` the right/lower node, so re-runs are stable.
- Double-headed arrows: two edges, same `visual_element_id`, each with the type that fits that direction (often `association` both ways; sometimes `causal` both ways in a feedback loop).
- "Blocked by" / "depends on" written on the arrow pointing *from* the dependent *to* the prerequisite: record as `dependency` with `from` = prerequisite, `to` = dependent, and note the reversal in `label` ("drawn as: blocked by").

## Labels

`label` is the text written on or beside the line, verbatim. Do not synthesise a label from the relation type. A missing label is omitted, not `""`.

## Mind-maps

Hub → branch and branch → leaf links are `association` unless the author wrote a verb on them. Mind-maps are about grouping, not process; forcing `sequence` or `causal` on them misleads first-pass into describing a plan that is not there.

## Matrices and 2×2s

Arrows between quadrants ("move these from Hard to Easy") are `causal` if they express an intended change, `sequence` if they express an order of attack. Placement of items *in* quadrants is not an edge; it is captured by the quadrant `container` and node `bbox_pct`.

## Cross-diagram edges

When `diagram_count > 1` and an arrow links a node in diagram 1 to a node in diagram 2, record it normally; the differing `diagram_index` on the two nodes tells consumers it bridges diagrams. Mention it in `layout_semantics`.

## Edges to nothing

An arrow leaving the page edge, or pointing at text that is not part of a diagram, is not an edge. Note it in `ambiguities` ("arrow from n4 exits the right page edge — diagram may continue"); if it points at body text, the transcriber's `marginalia[]` (kind `arrow-to`) captures it instead.

## Telemetry

The `pipeline.ndjson` line records `{relations: {causal, flow, dependency, sequence, association}}`. Pages where `association` exceeds 80% of edges on a flowchart-type layout are flagged as likely under-typed and are cheap candidates for `--reprocess`.
