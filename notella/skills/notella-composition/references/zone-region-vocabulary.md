# Zone region vocabulary

When to use each `zones[].region` label in `composition.json`. The label is a coarse, human-readable position; `bbox_pct` carries the precise one. Consumers query by label ("pages where the conclusion sits bottom-right"), so labels must be assigned the same way on every page.

## The grid

Divide the page into a 3×3 grid of thirds, plus a margin band of ~8% of the page width/height on each side.

```
 margin-top
 ┌─────────────┬─────────────┬─────────────┐
 │  top-left   │     top     │  top-right  │
 ├─────────────┼─────────────┼─────────────┤  m
 │    left     │   center    │    right    │  a  margin-right
 ├─────────────┼─────────────┼─────────────┤  r
 │ bottom-left │   bottom    │ bottom-right│  g
 └─────────────┴─────────────┴─────────────┘  i
 margin-bottom                                n-left
```

## Assignment rules

1. **Margin first.** If the zone's bbox lies entirely inside a margin band (x1 ≤ 0.08, x0 ≥ 0.92, y1 ≤ 0.08, or y0 ≥ 0.92) it is `margin-left` / `margin-right` / `margin-top` / `margin-bottom`. The top-right `MM-DD` date stamp and page number form a `margin-top` or `top-right` zone only if the model chooses to zone them at all; usually they are page furniture and folded into the title zone.
2. **Full-width.** If the zone spans ≥ 80% of the page width (x1 − x0 ≥ 0.8) it is `full-width`, whatever its height. A full page of prose is one `full-width` zone. A title band across the top is `top`, not `full-width`, when its height is under 15%.
3. **Otherwise, by centroid.** Compute the bbox centroid and map it to the 3×3 cell. Horizontal thirds: < 0.33 left, 0.33–0.67 centre column, > 0.67 right. Vertical thirds likewise. The centre column's cells are `top`, `center`, `bottom`; the others combine (`top-left`, `right`, `bottom-right`).
4. **Tall zones.** A zone spanning ≥ 60% of the page height in the left column is `left` (not `top-left`); likewise `right` and `center`.
5. **Ties.** A centroid exactly on a third boundary goes to the cell containing more of the zone's area.

## Examples

| Zone | bbox_pct | region |
| --- | --- | --- |
| Title and date line | [0.05, 0.02, 0.95, 0.10] | `top` (full width but under 15% tall) |
| Body prose, whole page | [0.05, 0.12, 0.95, 0.95] | `full-width` |
| Bulleted list down the left half | [0.05, 0.12, 0.48, 0.90] | `left` (tall) |
| Flowchart on the right half | [0.52, 0.15, 0.95, 0.70] | `right` |
| Action items boxed at the foot | [0.05, 0.80, 0.95, 0.95] | `full-width` (≥ 80% wide) — note: not `bottom`; query "bottom-right conclusions" should also test bbox |
| Short conclusion in the lower right | [0.60, 0.82, 0.95, 0.95] | `bottom-right` |
| Scribbled note in the left gutter | [0.00, 0.30, 0.07, 0.45] | `margin-left` |
| A small 2×2 in the middle | [0.35, 0.40, 0.65, 0.60] | `center` |
| Mind-map hub and branches filling the page | [0.05, 0.10, 0.95, 0.95] | `full-width`, with `dominant_flow: radial` |

## dominant_kind

| Value | Use when |
| --- | --- |
| `text` | prose, bullets, lists, headings |
| `diagram` | nodes/edges structure (matches `notella-diagram`'s definition) |
| `sketch` | freeform drawing |
| `table` | grid with cells |
| `mixed` | two kinds interleaved so finely that splitting into zones would produce more than 8 |
| `empty` | deliberate whitespace that is itself a zone (rare: a blank quadrant in a 2×2 layout) |

## Reading order

Default Western order: top-down, left-right. Deviate only on evidence: numbering written by the author, arrows between zones, a radial layout (hub first, then branches clockwise from 12 o'clock). When the model is unsure, default order wins; `dominant_flow` records the uncertainty as `scattered`.

## Prominence

Rough weights, combined by judgement: area (≥ 25% of page → +2), position (`center` or `top` → +1), emphasis density from the transcript's emphasis marks (≥ 3 marks in the zone → +1), boxing or heavy linework (+1). Start from 2. Clamp to 1–5. The zone with the largest area is not automatically 5 — a dense margin of starred notes can outrank a sparse diagram.

## Why this matters downstream

- `notella-first-pass` receives zones and the top-3 hierarchy; a mis-labelled region changes what it treats as the page's lead.
- `notella-themes` counts where conclusions and decisions land (for example a habit of writing the decision bottom-right) as a conceptual-evolution signal.
- The desktop app draws zones as hover regions on the page image using `bbox_pct`; labels feed its filter chips.
