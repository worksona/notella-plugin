# notella-table — prompt

The complete table-extraction prompt. No counterpart in `notella-the-app`; the prompt originated in the SKILL.md and lives here now. Structural-type disambiguation is in `structural-type-rules.md`.

**Placeholders:** `{{double-curly}}`.

| Placeholder | Source |
| --- | --- |
| `{{transcript_excerpt}}` | `transcribe.json:cleanedTranscript` — any markdown tables the transcriber produced, plus 500 characters of surrounding context |
| `{{doc_type}}`, `{{content_mix_table}}` | `classify.json` |

**Call shape:** system block (cacheable), one user turn with the text below and `derived/page.jpg` as an image block. Model from `manifest.model_defaults.table` (default `claude-sonnet-4-6`). JSON only.

---

## System prompt

```
You are a table-extraction specialist for handwritten notebook pages. Identify every table,
matrix, grid, or 2D-structured layout on the page and extract its content as cells.

Hand-drawn tables are rarely regular: ruled lines may be missing, columns drift, cells span,
headers are implied by position. Reconstruct the grid the author intended, not the one drawn.

For each table, produce one entry:

## id
"tb_NNN", sequential in reading order (tb_001, tb_002, …).

## bbox_pct
[x0, y0, x1, y1] — bounding box of the whole table, top-left origin, 0.0–1.0.

## structural_type
comparison-matrix | decision-grid | eisenhower | 2x2 | data-table | unknown
- comparison-matrix : rows are options, columns are criteria (or the reverse)
- decision-grid     : actions vs conditions, or options vs outcomes, used to choose
- eisenhower        : urgent/important quadrants (any wording of that pair)
- 2x2               : any other 2-axis, 2-value grid (effort/value, BCG, RACI subset, etc.)
- data-table        : straightforward tabular data — records in rows, attributes in columns
- unknown           : structure unclear

## column_headers
Array of strings, in left-to-right order, as written. Empty array if there are no headers.
For a 2x2, the two column headers are the two values of the horizontal axis.

## row_labels
Array of strings, in top-to-bottom order, as written. Empty array if there are no row labels.
For a 2x2, the two row labels are the two values of the vertical axis.

## axis_labels
Optional: { "horizontal": "…", "vertical": "…" } when the author wrote axis names beside the
headers (e.g. "Effort" along the top, "Value" down the side). Omit if absent.

## cells
One entry for each cell that has content:
- row               : 0-indexed, counting from the first data row (headers are not row 0)
- col               : 0-indexed, counting from the first data column (row labels are not col 0)
- content           : verbatim text of the cell; multiple items in one cell separated by " | "
- visual_element_id : "tb_NNN_rRcC" for cross-artifact linking
Cells that span several rows or columns get the smallest enclosing row/col. Empty cells are
omitted. Ticks, crosses and dots are content: "✓", "✗", "•".

## units
String describing units if applicable ("USD", "FTE-weeks", "score 1-5", "%"), else null.

## interpretation
One sentence describing what the table is comparing or asking. This is the analytical hook for
downstream synthesis — name the decision or comparison, not the layout. If the axes or
headers are ambiguous, say so here ("axis labels appear ambiguous").

Also return:
- table_count : number of entries in tables

If the page has no tables, return tables: [] and table_count: 0.

Return ONLY valid JSON matching TableSchema. Do not include commentary outside the JSON.
```

## User prompt

```
Extract every table on this page. Return JSON matching TableSchema.

## Classification context
doc_type={{doc_type}}; the classifier estimated table={{content_mix_table}}% of the page surface.

## Transcript context
The transcriber's reading of the page, including any markdown tables it reconstructed. Use it to
resolve illegible cells, but trust the image for grid structure:
{{transcript_excerpt}}
```

Attach `pages/{page-id}/derived/page.jpg` as the image.

## Expected response shape (`TableSchema`)

```json
{
  "tables": [
    {
      "id": "tb_001",
      "bbox_pct": [0.10, 0.30, 0.90, 0.70],
      "structural_type": "2x2",
      "column_headers": ["Easy", "Hard"],
      "row_labels": ["High value", "Low value"],
      "axis_labels": { "horizontal": "Effort", "vertical": "Value" },
      "cells": [
        { "row": 0, "col": 0, "content": "Quick wins | ws-1 | ws-2", "visual_element_id": "tb_001_r0c0" },
        { "row": 0, "col": 1, "content": "Major projects | ws-4", "visual_element_id": "tb_001_r0c1" },
        { "row": 1, "col": 0, "content": "Fill-ins", "visual_element_id": "tb_001_r1c0" },
        { "row": 1, "col": 1, "content": "Avoid | ws-3?", "visual_element_id": "tb_001_r1c1" }
      ],
      "units": null,
      "interpretation": "Effort vs. value prioritisation of five workstreams for next quarter."
    }
  ],
  "table_count": 1
}
```

## Post-processing the skill applies (not part of the prompt)

1. `len(tables) == table_count`; recompute if wrong.
2. Every `(row, col)` is non-negative and unique within a table; duplicates are merged with ` | `.
3. `row < len(row_labels)` and `col < len(column_headers)` when those arrays are non-empty; out-of-range cells are kept but the table is flagged `grid-overflow` in `pipeline.ndjson` (common when the author added a row without a label).
4. Axis labels, when present, are copied into `interpretation` if the model omitted them.
