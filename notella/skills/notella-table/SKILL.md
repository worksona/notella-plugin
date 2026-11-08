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

Use the prompt in `references/table-prompt.md` — the complete system and user prompt shipped with this plugin (no app counterpart; the prompt is native to the plugin). In outline, the system prompt asks the model to reconstruct the grid the author intended and produce, per table:

- `id` (`tb_NNN`), `bbox_pct`
- `structural_type` — comparison-matrix | decision-grid | eisenhower | 2x2 | data-table | unknown (`references/structural-type-rules.md`)
- `column_headers[]`, `row_labels[]`, optional `axis_labels`
- `cells[]` — 0-indexed row/col from the first data row/column, verbatim `content`, `visual_element_id` (`tb_NNN_rRcC`); empty cells omitted; spanning cells take the smallest enclosing row/col
- `units`, `interpretation` (one sentence naming what is compared or decided)

plus `table_count`. The user prompt carries the classification context and the transcriber's reading (including any markdown tables it reconstructed) as grounding for illegible cells, while the image is trusted for grid structure. Include `derived/page.jpg`.

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
