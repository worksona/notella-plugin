# Quality thresholds — calibration

How `notella_images.py` turns pixel metrics into `warnings[]` and a `grade`, and the measurements the thresholds were set from. The thresholds live in one dict at the top of the script (`THRESHOLDS`); change them there and re-run `scan --force` — no other file encodes them.

## The metrics (all on the 512 px decode)

Every image is decoded once by `sips` to a BMP whose long edge is 512 px (EXIF orientation applied by the decoder), converted to luminance `Y = (77R + 150G + 29B) >> 8`, and measured:

| Field | Definition |
| --- | --- |
| `brightness` | mean of Y, 0–255, 1 decimal |
| `contrast` | standard deviation of Y, 1 decimal |
| `sharpness` | variance of the 4-neighbour Laplacian `4c − l − r − u − d` over interior pixels, 1 decimal |
| `dark_fraction` | share of pixels with Y < 40, 3 decimals |
| `bright_fraction` | share of pixels with Y > 245, 3 decimals |
| `megapixels` | full-resolution width × height / 10⁶ of the analysed file, 2 decimals |
| edge ratio *(internal, not written)* | `sharpness / mean((c−r)² + (c−d)²)` — Laplacian energy over gradient energy |

Why the edge ratio: on notebook pages the Laplacian variance mostly measures **how much ink is on the page**. The five lowest-sharpness pages in the facility are near-empty pages (one date stamp, a few words), not blurred ones, while a blurred dense page can still out-score them. Blur removes second-derivative energy faster than first-derivative energy, so the ratio drops with blur whatever the ink density, and flat regions (paper, sticky notes) contribute to neither term.

## Measured distribution — 412 facility pages, 2026-11-08

Measured read-only on `derived/page.jpg` of every page (`scan --dry-run --json`, plus a scratch measurement for the edge ratio). The facility is flatbed scans at 300 dpi: 368 pages 3300×2550, 44 pages 2550×3300, all 8.41 MP, no EXIF orientation on any raw file.

| Metric | min | p1 | p2 | p5 | p10 | p25 | p50 | p75 | p90 | p95 | p99 | max |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| brightness | 225.5 | 231.9 | 237.5 | 241.1 | 241.9 | 243.0 | 244.4 | 245.9 | 247.3 | 247.9 | 249.2 | 250.0 |
| contrast | 10.4 | 12.3 | 13.4 | 16.0 | 17.8 | 20.7 | 23.4 | 25.9 | 27.7 | 28.9 | 51.9 | 54.6 |
| sharpness | 452.6 | 698.0 | 767.9 | 1042.8 | 1411.4 | 1947.5 | 2496.4 | 3077.6 | 3502.4 | 3740.8 | 4027.4 | 4744.7 |
| edge ratio | 2.646 | 2.856 | 2.922 | 2.990 | 3.043 | — | 3.153 | — | — | — | — | 3.328 |
| dark_fraction | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.001 | 0.001 |
| bright_fraction | 0.537 | 0.624 | 0.657 | 0.680 | 0.686 | 0.697 | 0.714 | 0.731 | 0.749 | 0.759 | 0.772 | 0.789 |

Notes on the tails:

- **Low contrast / low sharpness** (bottom 5%): near-empty pages — e.g. `2026-01-02-19r5` (a date stamp on a blank grid, contrast 10.4, sharpness 452.6).
- **High contrast / low brightness** (top 1%): pages carrying a large red or orange sticky note (`2025-12-13-9276`, contrast 54.5, brightness 225.5). Nothing is dark.
- Scanned white paper puts ~70% of pixels above 245, so `bright_fraction` is high on every page; it is not an overexposure signal on its own.

### Simulated degradation

Every 14th page (30 pages) was blurred by downscaling to 1/k of 3300 px and back up with `sips`, then measured:

| Version | edge ratio min – max (median) | sharpness min – max (median) |
| --- | --- | --- |
| original | 2.646 – 3.328 (3.153) | 714 – 4537 (2453) |
| 1/4 (≈825 px effective) | 2.558 – 2.856 (2.756) | 432 – 2712 (1481) |
| 1/6 | 2.131 – 2.375 (2.278) | — |
| 1/8 (≈412 px effective, handwriting smeared) | 2.023 – 2.262 (2.186) | 170 – 1093 (593) |
| 1/16 | — | 20 – 87 (50) |
| downscaled to 1400 px long edge (≈1.5 MP) | — | 573 – 3592 (1957) |

The sharpness range of the 1/8 blur overlaps the sharp near-empty pages; the edge ratio does not.

## The thresholds

The scanned corpus has no blurred, dark or overexposed tail, so flagging its worst 5–10% on those metrics would only produce false alarms. Those thresholds sit outside the corpus range at levels the simulated (or plainly visible) degradation reaches. `low-contrast` is set at the corpus p5, as asked; it lands on near-empty pages, which is harmless (one warning = `fair`).

| Warning | Rule | Facility pages flagged |
| --- | --- | --- |
| `blurry` | edge ratio < **2.45** or sharpness < **150** | 0 (every 1/6 and 1/8 blur is flagged; 1/4 blur is not — it is still legible) |
| `dark` | brightness < **120** or dark_fraction > **0.15** | 0 |
| `overexposed` | bright_fraction > **0.92** | 0 (corpus max 0.789) |
| `low-contrast` | contrast < **16.0** (corpus p5) | 20 (4.9%) |
| `low-resolution` | megapixels < **2.0** | 0 |
| `exif-rotated` | raw EXIF orientation ∉ {null, 1} | 0 — informational, see below |

`exif-rotated` describes the file, not its quality: every portrait phone photo carries EXIF orientation 6. It is listed in `warnings[]` so the desktop app can show it, but it **does not count toward the grade**.

## Grade

Counting quality warnings only (everything except `exif-rotated`):

| Warnings | Grade |
| --- | --- |
| 0 | `good` |
| 1 | `fair` |
| ≥ 2 (this includes "blurry + anything") | `poor` |

Facility result at these thresholds: good 392 · fair 20 · poor 0.

## Re-calibrating

Phone photos will move every distribution: brightness 150–200 on white paper under room light is normal and legible, so `dark` stays an absolute floor (120) rather than a percentile. When the first few dozen phone-photographed pages exist:

1. `notella_images.py scan --dry-run --json > /tmp/q.json` (writes nothing) and look at `results[].brightness / contrast / sharpness`, split by `source_filename` (scan vs photo).
2. Look at the bottom five pages per metric (`derived/thumb.jpg`) before moving a threshold — the low tail of these metrics is often "little ink", not "bad photo".
3. Edit `THRESHOLDS`, update the tables above with the new measurement date, then `scan --force`.
