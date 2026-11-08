# Node role rules

How to choose `nodes[].role` in `diagram.json`. Six values: `container`, `process`, `decision`, `flow`, `dependency`, `unknown`. The role is read by first-pass (to describe what a diagram does), by the desktop app (to colour nodes), and by themes (process-heavy vs concept-heavy pages). Consistency matters more than precision — pick by the tests below in order.

## Decision order

| Order | Role | Test | Typical drawing |
| --- | --- | --- | --- |
| 1 | `container` | The element encloses other nodes, or labels a region/lane that other nodes sit in. | A large box with smaller boxes inside; a swim-lane header; a labelled circle in a Venn; a quadrant of a 2×2 |
| 2 | `decision` | The element asks a question or names a condition with two or more outgoing branches, or is drawn as a diamond. | Diamond; "yes/no" fork; "if X?"; a node whose outgoing edges are labelled with alternatives |
| 3 | `flow` | The element has no content of its own: it only joins, splits or redirects lines. | A dot where arrows meet; an unlabeled small circle; a bracket merging three arrows into one |
| 4 | `dependency` | The element is something the diagram's process needs from outside: an input, a resource, a prerequisite artefact, an external system or person. It has outgoing edges but nothing flows *into* it from inside the diagram. | "Legal sign-off"; "Customer data"; a cylinder (database); a stick figure labelled "client"; a cloud |
| 5 | `process` | The element is a step, state, action, concept, or thing that the diagram is about. Default for labelled boxes and mind-map leaves. | Box labelled "Build"; mind-map branch "Pricing"; timeline milestone; an oval labelled "Launch" |
| 6 | `unknown` | None of the above can be determined — unlabeled shape with ambiguous connections, or illegible. | A scribble connected to two arrows |

## Notes by diagram type

**Flowcharts.** Start/end terminals (rounded boxes "Start", "Done") are `process`. Diamonds are `decision`. Merge dots are `flow`. Off-page connectors are `dependency` with `ambiguities` noting the continuation.

**Mind-maps.** The central topic is `container` (it owns the branches). First-level branches are `process` unless they are clearly category headers that group several leaves and have no content of their own, in which case they too are `container`. Leaves are `process`.

**Swim-lanes.** Each lane header is `container`. Steps inside are `process`/`decision` as usual. The lane itself is not a node; its header is.

**Venn diagrams.** Each set is a `container`; the labels placed in intersections are `process` nodes with edges of `association` to each containing set.

**Matrices / 2×2 with relations.** Axis labels are not nodes (they go in `layout_semantics`). Each quadrant is a `container`; items placed in quadrants are `process`. If the 2×2 has no items — only quadrant labels — it is a table, not a diagram; return `diagram_count: 0` unless arrows connect quadrants.

**Network / ecosystem maps.** Organisations and people are `process` unless drawn as external sources, in which case `dependency`. Hubs with many connections are still `process` — do not use `container` for "important".

**Timelines.** Each dated milestone is `process`; the axis line is not a node. Edges between consecutive milestones are `sequence`.

## Labels

- `label` is the text as written. Do not translate, expand abbreviations, or correct spelling; `description` is where expansion goes ("DB" → description "the production database").
- Unlabelled nodes get a concise description as label in square brackets: `"[unlabelled box between Build and Test]"`.
- Illegible labels: `"[label uncertain: Deploy?]"` and an `ambiguities` entry.

## visual_element_id and bbox_pct

`ve_dN`, sequential across nodes then edges on the page. The bbox is tight around the node's drawn boundary (box edge, circle), not around its label text if the label sits outside. Composition zones reference these ids; keep them stable across `--reprocess` runs when possible by numbering in reading order (top-left to bottom-right).

## Role counts in telemetry

The `pipeline.ndjson` line for a run records `{roles: {container, process, decision, flow, dependency, unknown}}`. A page with `unknown` > 30% of nodes is a candidate for `--reprocess` with a stronger model or a better photo; the orchestrator's report lists such pages.
