# Sketch vs diagram — disambiguation

`notella-sketch` and `notella-diagram` both look at the page's drawn content. They must not both claim the same drawing, and neither should drop one that is really theirs. The classifier's `route_plan` decides which specialists run; this file decides what each keeps.

## The one-line rule

**If the meaning is in the connections, it is a diagram. If the meaning is in the depiction, it is a sketch.**

## Tests, in order

| # | Question | Yes → | No → |
| --- | --- | --- | --- |
| 1 | Are there two or more discrete elements joined by drawn lines or arrows, where removing the lines would lose information? | diagram | continue |
| 2 | Is it a grid, matrix, or axis pair with labelled regions? | diagram (or table — see below) | continue |
| 3 | Does it depict something from the world — a person, object, place, scene, icon? | sketch | continue |
| 4 | Is it a repeated mark, border, or flourish with no referent? | sketch, `intent: decorative` | continue |
| 5 | Is it an isolated symbol (star, arrow, lightning bolt, checkbox) attached to text? | neither — it is emphasis or marginalia, handled by transcribe | — |

## Common cases in this corpus

| Drawing | Verdict | Why |
| --- | --- | --- |
| Boxes with arrows, labelled steps | diagram | connections carry meaning |
| Mind-map: hub word, branches | diagram | branches are connections |
| Stick figure handing a box to another stick figure, captioned | sketch (`process metaphor with figures`) | depiction carries meaning; the single arrow is part of the scene |
| Flowchart whose nodes are drawn as little icons (a cloud, a phone, a person) | diagram; the icons are node labels, not sketches | connections dominate |
| A face in the margin | sketch (`human face`, often `decorative` or `mnemonic`) | no connections |
| A 2×2 with quadrant labels and items placed in quadrants | diagram if arrows connect quadrants or items; table if cells hold list items with no connections | see `notella-table` |
| A timeline with dated ticks | diagram (`sequence` edges) | order is a connection |
| A product mock-up: a phone screen with UI elements | sketch (`technique: technical`, `intent: explanatory`) | depiction; the layout inside is not a graph |
| A floor plan or room layout | sketch (`technical`) | spatial depiction, no graph |
| A graph with axes and a hand-drawn curve | diagram (`layout_semantics` describes the axes; curve as a single node) — or sketch if it is a mood sketch of "things going up" with no axis labels | labelled axes make it structural |
| A Venn diagram | diagram | regions and overlaps are relations |
| A "tree" drawn as an actual tree with words on branches | diagram (mind-map variety) | the words on branches are connected content |
| A tree drawn as a tree with no words | sketch | depiction |
| Arrow cluster showing a swirl / cycle with no labels | sketch (`arrow cluster`, often `exploratory`) | no discrete connected elements |
| Arrow cycle with labelled stages | diagram | labelled nodes in a cycle |

## When both appear on one page

Common: a flowchart in the upper half and a doodled face in the margin. Both specialists run (classifier sets both route_plan entries) and each keeps its own. `composition.json` zones reference both sets of ids (`ve_d*` and `sk_*`).

## When one drawing is genuinely both

A process metaphor with labelled stages connected by arrows *and* expressive figures: the diagram specialist takes the structure (nodes = stages, edges = arrows), the sketch specialist takes the depiction (`subject: process metaphor with figures`, `intent: explanatory`) with `elements[]` covering the figures. Overlapping bboxes are expected; `first-pass` merges them under one `diagram_semantics` entry.

## When uncertain

Prefer **diagram**. The structural treatment is more useful to synthesis, and `notella-diagram` returns `diagram_count: 0` cleanly when it finds no structure. The sketch specialist records the drawing it left out in `ambiguities` so the orchestrator can check that the diagram artifact did claim it; if neither claimed it, the orchestrator flags `unclaimed-visual` in the report.

## What never changes hands

- Tables with cell values → `notella-table`, regardless of how hand-drawn.
- Emphasis marks and marginal arrows → `notella-transcribe` (`emphasis[]`, `marginalia[]`).
- Page furniture (date stamp, page numbers, ruled lines) → nobody.
