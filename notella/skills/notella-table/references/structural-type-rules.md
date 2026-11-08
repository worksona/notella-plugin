# Structural type rules

How to choose `tables[].structural_type` in `table.json`. Six values: `comparison-matrix`, `decision-grid`, `eisenhower`, `2x2`, `data-table`, `unknown`. Synthesis queries lean on this field ("every 2×2 about pricing", "all comparison matrices mentioning Tulevik"), so the same shape must get the same label on every page.

## Decision order

| Order | Type | Test |
| --- | --- | --- |
| 1 | `eisenhower` | Exactly 2×2 and the axes (or quadrant labels) are urgent/important in any wording: "urgent / not urgent", "now / later", "important / nice-to-have", "do / schedule / delegate / delete". |
| 2 | `2x2` | Exactly 2 columns × 2 rows of data cells, each axis a pair of opposed values (easy/hard, high/low, build/buy, internal/external). Quadrants typically hold lists of items. Includes effort/value, BCG (growth/share), risk/reward, know/don't-know. |
| 3 | `decision-grid` | Rows are options or actions, columns are conditions, scenarios or outcomes, and the cells say what happens or what to do ("if X and Y then Z"). The table exists to pick a row. Also: weighted scoring sheets with a totals column. |
| 4 | `comparison-matrix` | Rows are options (vendors, approaches, candidates), columns are criteria (cost, speed, risk), cells are judgements (✓/✗, scores, short notes). Also the transpose (criteria as rows). No totals column — if there is one that drives a choice, it is a `decision-grid`. |
| 5 | `data-table` | Rows are records (people, dates, items), columns are attributes (name, date, amount). Cells are facts, not judgements. Includes schedules, budgets, attendee lists, backlog tables. |
| 6 | `unknown` | A grid is clearly present but headers and labels are missing or illegible so the relationship between rows and columns cannot be read. |

## Edge cases

| Case | Verdict |
| --- | --- |
| 2×2 with no axis or quadrant labels, just four groups of items | `2x2`, and `interpretation` says "axis labels not written" |
| 3×3 "nine-box" (performance/potential) | `comparison-matrix` is wrong (no options vs criteria); use `decision-grid` — the grid exists to place and decide |
| RACI chart (people × tasks, cells R/A/C/I) | `data-table` — the cells are assignments, not judgements between options |
| A list with two columns: task and owner | `data-table` (two attributes of a record) |
| A single row of headers with ticks under them — a checklist drawn as a grid | `data-table` with one data row |
| A pros/cons two-column list | `comparison-matrix` with one option and two criteria columns ("pros", "cons") — or, if there is no table structure beyond two headed lists, not a table at all: leave to transcribe |
| Calendar grid (weeks × days) | `data-table`; `units: "dates"` |
| A matrix with arrows between cells | `table` **and** `diagram` — record the cells here; `notella-diagram` records the arrows with each quadrant as a `container` node |
| Table continued from the previous page (no headers on this page) | `data-table` or best guess with `column_headers: []`; `interpretation` notes "headers appear on a prior page"; the orchestrator may stitch via `meta.yaml:links_to` |

## Headers vs labels vs cells

- The top-left corner cell of a grid with both headers and labels is neither; if it carries text (an axis name, a title) put it in `axis_labels` or `interpretation`.
- A header that spans two columns ("Q2" over "Apr" and "May") is recorded as the sub-headers (`["Apr", "May"]`) with the spanning text prepended: `["Q2 · Apr", "Q2 · May"]`.
- When the author wrote the headers vertically (rotated text), read them as headers; do not treat the rotation as a different structure.

## What is not a table

- Two side-by-side bullet lists with no ruled lines and no shared header → text (transcribe captures them; composition zones them).
- A single ruled box around a paragraph → emphasis `box`, not a one-cell table.
- A bracketed grouping (`{` beside three lines) → transcribe hierarchy.
- A scoring rubric described in prose ("1 = low, 5 = high") → `units` on the table it belongs to, not a table itself.

If a page was routed for `table_extraction` and none of the above yields a table, return `table_count: 0`; the classifier over-estimated, which is a correct outcome, not an error.

## Interpretation sentence

The sentence should let someone decide whether to open the page: name what is compared or decided and, if visible, the outcome. "Effort vs. value prioritisation of five workstreams; three marked quick wins, one marked avoid" is good. "A 2×2 grid" is not.
