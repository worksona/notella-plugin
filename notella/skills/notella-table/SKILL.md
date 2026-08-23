---
name: notella-table
description: "Extract tabular content from a notella page — cells, column headers, row labels, structural type (comparison-matrix / decision-grid / 2x2 / data-table), units, interpretation. Use whenever the user says 'parse the table on page X', 'extract this matrix', 'read the grid', 'what's in the 2x2', or any request to structure tabular content. Conditional: runs when classify.json:route_plan includes table_extraction. Reads through `notella-state`; writes `table.json`."
---

# notella-table — the table extractor

Tables in handwritten notes are rarely uniform — they're 2×2s, decision grids, comparison matrices, Eisenhower boxes. This skill captures their content and structural intent.

## Purpose

Make tabular content queryable across pages. "Find every 2×2 about pricing" or "show all comparison matrices that mention Project Atlas" only works if tables are stored as cells with structural metadata.

## Inputs and outputs

**Input:** Page at `phase=transcribed` with `route_plan` containing `table_extraction`. Reads `derived/page.jpg`, `transcribe.json`, `classify.json`.

**Output:**
- `pages/{page-id}/table.json`
- No phase advance.
- `pipeline.ndjson` line.

## How a run executes

### Step 1 — Read configuration & page

```
notella-state get-manifest → manifest.model_defaults.table
notella-state get-page-artifact {page-id, artifact: transcribe}
```

Verify `phase >= transcribed` and `route_plan` includes `table_extraction`.

### Step 2 — Acquire the page lock

### Step 3 — Build the prompt

System prompt:

```
You are a table-extraction specialist for handwritten notebook pages. Identify
every table, matrix, grid, or 2D-structured layout on the page and extract its
content as cells.

For each table, produce:

## structural_type
comparison-matrix | decision-grid | eisenhower | 2x2 | data-table | unknown
- comparison-matrix : rows are options, columns are criteria
- decision-grid     : actions vs conditions
- eisenhower        : urgent/important quadrants
- 2x2               : any 2-axis 2-value grid (BCG, RACI subset, etc.)
- data-table        : straightforward tabular data
- unknown           : structure unclear

## column_headers
Array of strings, in left-to-right order. Empty if no headers.

## row_labels
Array of strings, in top-to-bottom order. Empty if no row labels.

## cells
For each cell that has content:
- row: 0-indexed
- col: 0-indexed
- content: verbatim text of the cell
- visual_element_id: reference for cross-artifact linking

Cells outside the canonical row/col grid (e.g. a header that spans 2 columns)
get the smallest enclosing row/col.

## units
String describing units if applicable ("USD", "FTE-weeks", "score 1-5"), else null.

## interpretation
One sentence describing what the table is comparing or asking. This is the
analytical hook for downstream synthesis.

Return ONLY valid JSON matching TableSchema.
```

Include `derived/page.jpg` and the transcript text.

### Step 4 — Call the model

Default: `claude-sonnet-4-6`.

### Step 5 — Validate

```yaml
tables:
  - id, bbox_pct, structural_type, column_headers[], row_labels[], cells[], units, interpretation
table_count: int
```

Sanity: `len(tables) == table_count`. Each cell's `(row, col)` is non-negative; cells across tables may share row/col indices but not within one table.

### Step 6 — Write & release lock

## Idempotency

Standard.

## Failure modes

| Failure                                                | Behavior |
| ------------------------------------------------------ | -------- |
| Classifier flagged table_extraction but no table       | Return empty arrays. |
| Hand-drawn 2×2 with sparse cell content                | Cells with empty text are simply omitted; consumers infer absence. |
| Misaligned columns / rows                              | Best-effort gridding; surface confusion in `interpretation` ("axis labels appear ambiguous"). |

## What this skill does NOT do

- Does not perform numerical analysis on cell values — that's downstream.
- Does not infer the question the table is answering — only the literal content + a one-sentence interpretation.

## Examples

### "Extract the table on page 2026-05-02-x7k2"

```json
{
  "tables": [
    {
      "id": "tb_001",
      "structural_type": "2x2",
      "column_headers": ["Easy", "Hard"],
      "row_labels": ["High value", "Low value"],
      "cells": [
        { "row": 0, "col": 0, "content": "Quick wins" },
        { "row": 0, "col": 1, "content": "Major projects" },
        { "row": 1, "col": 0, "content": "Fill-ins" },
        { "row": 1, "col": 1, "content": "Avoid" }
      ],
      "units": null,
      "interpretation": "Effort vs. value prioritization grid for next quarter."
    }
  ],
  "table_count": 1
}
```

## Reference files

- `references/table-prompt.md` — full prompt.
- `references/structural-type-rules.md` — disambiguation.
