# Image analysis — decoding, dhash, orientation signals

How `scripts/notella_images.py` reads pixels with nothing but macOS `sips` and the Python 3.9 standard library, and how it turns them into the `dhash`, the orientation `sources` and the transforms `fix` applies. Read this when changing the script or when a result looks wrong.

## Why sips + BMP

The machine has system Python 3.9 without Pillow, and no ImageMagick, exiftool or libheif. `sips` (always present on macOS) reads JPEG, HEIC/HEIF and PNG, resamples, rotates, flips and writes BMP and JPEG. BMP is the simplest uncompressed format to parse in pure Python, so every measurement is:

```bash
sips -s format bmp -z H W input --out tmp.bmp      # H, W = long edge 512, aspect kept
```

then a ~40-line parser. Behaviour verified on this machine (macOS 26, sips 2.x):

- **EXIF orientation is applied by the decode.** A JPEG tagged orientation 6 stored 600×463 converts to a 463×600 BMP. `-z H W` is interpreted in the *stored* orientation and the rotation happens after the resize. So every pixel the script measures is the image as it is meant to be displayed, and a BMP carries no orientation tag of its own.
- `sips -g orientation` did **not** report an orientation that the decoder honoured on a hand-built EXIF segment, so the script reads the EXIF orientation itself from the JPEG APP1 segment (`jpeg_header()`) and only asks `sips -g` for non-JPEG files (HEIC, PNG).
- `sips` cannot read properties and convert in the same call ("Error 6"), so dimensions come from the JPEG SOF marker (or a separate `sips -g` for HEIC/PNG) — one process per decode, ~70 ms for a 3300×2550 JPEG.

## BMP parsing

`parse_bmp()` handles what `sips` (and other writers) produce:

| Field | Offset | Notes |
| --- | --- | --- |
| magic | 0 | `BM` |
| pixel data offset | 10 (u32) | |
| DIB header size | 14 (u32) | 40 (BITMAPINFOHEADER), 108 (V4), 124 (V5) |
| width, height | 18, 22 (i32) | **negative height = top-down rows** (sips writes top-down); positive = bottom-up |
| bits per pixel | 28 (u16) | 24 or 32 supported |
| compression | 30 (u32) | 0 (BI_RGB); 3/6 (BITFIELDS) for 32-bit — channel byte positions are read from the R/G/B masks |

Rows are padded to a multiple of 4 bytes: `row_size = ((bpp × width + 31) // 32) × 4`. Pixels are stored B, G, R(, A). The parser returns top-down rows of three byte strings (R, G, B) so the metric code can use C-speed slicing (`row[2::3]`).

## dhash (difference hash)

64 bits, written as 16 lowercase hex digits.

1. Luminance of the 512 px decode (`Y = (77R + 150G + 29B) >> 8`).
2. Box-average to **9 columns × 8 rows** (cell `(cx, cy)` covers `x ∈ [cx·w/9, (cx+1)·w/9)`, `y ∈ [cy·h/8, (cy+1)·h/8)`, integer bounds).
3. For each row, for `x = 0..7`: bit = 1 if `cell[x] > cell[x+1]`, else 0.
4. Row-major, most significant bit first → `"%016x"`.

Distance between two hashes is the Hamming distance (popcount of XOR).

- **Facility pages** store the dhash of `raw/` (EXIF applied), so a source file is compared with the original photo, not with a derived image that `fix` may have rotated.
- `audit` and `inbox-check` also hash four transformed variants of each candidate file — rotated 90/180/270 and mirrored horizontally — and take the smallest distance, so a re-photographed or exported page that is upside down or mirrored still matches (`match_transform` in the report).

### Measured on the facility (2026-11-08)

| Pair | Distance |
| --- | --- |
| 15 known duplicate pairs (the 2026-01-02 re-upload, byte-identical) | 0 (exact sha256 match) |
| closest two *different* pages | 10 (1 pair); 11 (4 pairs); 12 (10 pairs); then 13+ |
| closest variant (rot/flip) of one page vs another page | 10 |
| JPEG re-encode q55–q70 at 900–2000 px | 1 – 5 |
| PNG export at 1000 px | 0 |
| HEIC re-encode at 2000 px | 2 |
| rotated 180° + downscaled copy (via the rot180 variant) | 3 – 6 |

The default `--near 6` sits inside the gap between re-encodes (≤ 6) and distinct pages (≥ 10). A second *photograph* of the same page (different framing, perspective, light) is usually not within 6 — that is a judgement for a person, which is why near matches are held for review rather than discarded.

## Orientation signals

`quality.json:orientation` combines these sources. A suggestion is always the **absolute** transform relative to `raw/` with EXIF applied — exactly what `fix --rotate R --flip F` takes.

| Source | Fires when | Suggestion |
| --- | --- | --- |
| `orientation-fix` | `meta.yaml` has an `orientation_fix` block | none — status is `fixed` and nothing else is evaluated |
| `classify` | `classify.json:orientation` is the object form with `rotate ≠ 0` or `flip ≠ none` and `confidence ≥ 0.6` | `{rotate, flip}` from classify |
| `stamp-position` | the red series stamp is found in a corner other than bottom-right (see below) | pure rotations as found; mirror-like positions → `null` (needs a look) |
| `classify-legacy` | `classify.json:orientation` is a legacy string other than `"upright"` | `rotated_180`/`upside_down` → 180; `mirrored` → flip horizontal; `rotated_90_cw` → 270; `rotated_90_ccw`/`rotated_270` → 90; `rotated_90` → `null` |
| `exif` | raw EXIF orientation ∉ {null, 1} and `derived/page.jpg` was not produced with it applied | `{rotate: 0, flip: none}` — `fix` applies EXIF first, so identity is the repair |
| `low-transcript-confidence` | `transcribe.json:transcriptConfidence < 0.45` | adds no suggestion (needs a look) |
| `review-cleared` | the latest `longitudinal/verdicts.ndjson` row with `target_kind: image` for the page is `wrong` | status forced to `ok` |

Precedence when several sources suggest something: `classify` > `stamp-position` > `classify-legacy` > `exif`. Status is `suspected` when any source fires, `ok` when something is known (a classify opinion, a bottom-right stamp, EXIF, or a transcript confidence) and nothing fires, `unknown` otherwise.

"Derived was auto-oriented" means: the derived file carries no orientation tag of its own, differs from raw, and — for EXIF 5–8 — has the raw's stored width and height swapped.

### The red stamp

The notebook convention puts a small red series stamp (`12-24`, `4-10`) in the **bottom-right** corner of every page, and the date stamp top-right. The notebook is used in landscape. On the 512 px decode the red stamp is a compact cluster of 10–60 pixels matching `R > 120, R − G > 40, R − B > 25` (scanned red ink is pinkish, around (220, 140, 160)).

`stamp_corner()` accepts a corner only when all of these hold, so red sticky notes and red headings do not count:

- 8–600 matching pixels inside that corner's 15% × 15% box;
- their bounding box is ≤ 12% of the width and ≤ 12% of the height;
- no other corner has more than 25% as many;
- the band next to the corner (the next 15% inward, horizontally and vertically) holds ≤ 30% as many (text running into the corner is not a stamp).

The corner plus the image aspect gives exactly one transform that brings the stamp to bottom-right on a landscape page (`stamp_transform()`):

| Stamp found | Image | Transform | Meaning |
| --- | --- | --- | --- |
| bottom-right | landscape | identity | upright |
| top-left | landscape | rotate 180 | upside down |
| bottom-left | portrait | rotate 270 | page turned 90° clockwise |
| top-right | portrait | rotate 90 | page turned 90° counter-clockwise |
| bottom-left | landscape | flip horizontal | mirrored — or something else: suggestion withheld |
| top-right | landscape | flip vertical | mirrored upside down — suggestion withheld |

On the facility (2026-11-08, dry run): a corner was accepted on 388 of 412 pages, and every portrait image had its stamp bottom-left or top-right while every landscape image had it bottom-right or top-left — the 44 portrait images are all sideways landscape pages. Every sampled top-left, bottom-left and top-right page was visually confirmed to be upside down / sideways as predicted, including pages the legacy classify prompt had labelled `upright` (`2026-04-10-5jqg`, `2026-04-03-cknd`). The one landscape top-right detection (`2026-02-04-1q0p`, a pink sticky note) was rejected by the neighbour-band rule.

Result of the dry-run scan: orientation `ok` 303, `suspected` 104 (stamp rotate 180: 64, of which 16 also legacy `rotated_180`; rotate 90: 24; rotate 270: 16), `unknown` 5.

## Transform convention (`fix`)

`fix --rotate R --flip F` rebuilds `derived/page.jpg` as:

1. `sips -s format bmp raw/page.* --out full.bmp` — full resolution, EXIF orientation applied, no tag left;
2. `sips -r R full.bmp` — rotate **clockwise** R degrees (skipped for 0);
3. `sips -f horizontal|vertical full.bmp` — then flip (skipped for none);
4. `sips -s format jpeg -s formatOptions 92 full.bmp --out page.jpg`;
5. `sips -s format jpeg -s formatOptions 85 -Z 800 page.jpg --out thumb.jpg` (long edge = `manifest.intake.thumbnail_max_dim_px`, default 800).

Rotation first, then flip. The transform is absolute: `fix --rotate 180` twice is still 180, not 360, and `fix --reset` (= EXIF only) undoes any earlier fix. Each step writes into a temp folder; the two finished JPEGs are moved into `derived/` with `os.replace`.

## Speed

One decode ≈ 70 ms in `sips` plus ≈ 150 ms of pure-Python metrics (gray conversion, Laplacian/gradient pass, stamp scan, 9×8 box average). Pages whose derived image is byte-identical to raw are decoded once; others twice (derived for metrics, raw for the dhash). With a process pool of 10 workers the full 412-page facility scans in ~10 s; `audit` hashes the facility on the fly (when `quality.json` is missing) in ~8 s.
