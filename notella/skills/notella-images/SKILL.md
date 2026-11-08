---
name: notella-images
description: "Check and repair the page images of the notella facility — image quality (blur, darkness, overexposure, contrast, resolution), orientation (upside down, sideways, mirrored / backwards) and duplicate raw images. Writes `pages/{id}/quality.json`, rebuilds `derived/page.jpg` from `raw/` with a rotation or flip, marks duplicate pages. Use whenever the user says 'check image quality', 'scan image quality', 'is this page upside down', 'which pages are upside down', 'is page X backwards', 'fix the orientation of page X', 'rotate page X', 'flip page X', 'which pages are blurry', 'bad photos', 'find duplicate pages', 'mark duplicate', 'page X is a duplicate of Y', or any request about the quality or orientation of page photos. Also trigger when notella-orchestrator step 2 finds pages without quality.json, when notella-classify reports an orientation, or when notella-review records an image verdict. Runs `scripts/notella_images.py` (stdlib Python + macOS sips); never modifies raw/."
---

# notella-images — image quality, orientation and duplicates

Every downstream stage reads `derived/page.jpg`. A page photographed upside down, sideways or mirrored, or a blurred photo, costs a full transcription of garbage; a page dropped twice costs a duplicate in every synthesis. This skill measures each page image once, says what is wrong with it, and repairs what can be repaired from `raw/`.

## Purpose

- **Measure**: `quality.json` per page — size, brightness, contrast, sharpness, a perceptual hash, a grade, warnings, and an orientation verdict combined from every signal the facility has.
- **Repair**: rebuild `derived/page.jpg` and `thumb.jpg` from the immutable `raw/` with an absolute rotation/flip, record it, and say which stages must re-run.
- **Deduplicate**: mark a page as `duplicate_of` another so syntheses skip it.

The script does the pixel work; this skill decides when to run it, looks at pages the script cannot decide, and runs the follow-up chain.

## The tool

```bash
python3 "$CLAUDE_PLUGIN_ROOT/scripts/notella_images.py" <subcommand> [--root DIR] [--json] ...
```

Facility root: `--root`, else `$NL_DIR`, else `~/notella`. On this machine `NL_DIR=/Users/davidolsson/Documents/notella` — set it (or pass `--root`) on every call. Requirements: macOS `/usr/bin/sips`, Python ≥ 3.9, nothing else. Every subcommand has `--help` and `--json`.

| Subcommand | What it does |
| --- | --- |
| `scan [--pages ID ...] [--all] [--force] [--workers N] [--dry-run]` | write `quality.json` for every page lacking a fresh one (or the listed pages) |
| `fix --page ID [--rotate 0\|90\|180\|270] [--flip none\|horizontal\|vertical] [--reset] [--dry-run]` | set the absolute orientation of one page |
| `fix --all-suggested [--source NAME] [--dry-run]` | apply every concrete suggestion from the last scan |
| `mark-duplicate --page DUP --of ORIGINAL [--note TEXT] [--force] [--dry-run]` | record `duplicate_of` |
| `selftest [--image PATH] [--workdir DIR] [--keep]` | run the self-tests on a scratch fixture (never touches the facility) |

Imports, inbox checks and source-folder audits use the same script and are documented in `notella-import`.

## Inputs and outputs

**Reads:** `pages/{id}/raw/page.*`, `derived/page.jpg`, `meta.yaml`, `classify.json`, `transcribe.json`; `longitudinal/verdicts.ndjson` (image verdicts); `manifest.yaml` (`intake.thumbnail_max_dim_px`, default 800).

**Writes (all atomic, tmp + rename; ndjson lines with a single append):**

| Path | By | Content |
| --- | --- | --- |
| `pages/{id}/quality.json` | scan, fix | the contract below |
| `pages/{id}/derived/page.jpg`, `thumb.jpg` | fix | rebuilt from raw (JPEG q92; thumb long edge 800) |
| `pages/{id}/meta.yaml` | fix, mark-duplicate | `orientation_fix` block / `duplicate_of` + an `errors` note; every other byte unchanged |
| `logs/pipeline.ndjson` | scan, fix, mark-duplicate | one line per page written |
| `events/{date}/{id}.json` + `events/{date}.jsonl` | fix, mark-duplicate | a `correction` event |

Never written: anything under `raw/`.

### `quality.json` (contract read by the desktop app)

```json
{
  "schema_version": "0.1.0",
  "computed_at": "2026-11-08T20:19:52Z",
  "source": "derived",
  "width": 3300, "height": 2550, "megapixels": 8.41,
  "exif_orientation": null,
  "brightness": 244.4, "contrast": 23.4, "sharpness": 2496.4,
  "dark_fraction": 0.0, "bright_fraction": 0.714,
  "sha256_raw": "54c9…", "dhash": "83dcccc4a4291ee3",
  "grade": "good",
  "warnings": [],
  "orientation": {"status": "suspected", "suggested": {"rotate": 180, "flip": "none"}, "sources": ["stamp-position"]}
}
```

- `source`: `derived` when `derived/page.jpg` exists (metrics are of what the models see), else `raw`. `exif_orientation`, `sha256_raw` and `dhash` are always of `raw/`.
- `warnings` ⊆ `blurry, dark, overexposed, low-contrast, low-resolution, exif-rotated`; `grade` is `poor` with ≥ 2 quality warnings, `fair` with 1, else `good` (`exif-rotated` is informational and not counted). Thresholds and the measured distribution: `references/quality-thresholds.md`.
- `orientation.status`: `fixed` (meta has `orientation_fix`), `suspected`, `ok`, `unknown`. `suggested` is the absolute transform `fix` should apply, or `null` when a page needs a look. `sources` name the signals: `orientation-fix`, `classify`, `stamp-position`, `classify-legacy`, `exif`, `low-transcript-confidence`, `review-cleared`. Rules and precedence: `references/image-analysis.md`.

### `meta.yaml` fields this skill owns

```yaml
orientation_fix:                 # absolute transform applied to raw (EXIF first), set by fix
  rotate: 180                    # clockwise degrees: 0 | 90 | 180 | 270
  flip: none                     # none | horizontal | vertical (applied after the rotation)
  applied_at: 2026-11-08T20:19:52Z
  by: notella-images
duplicate_of: 2025-12-01-4794    # set by mark-duplicate; the page is excluded from synthesis
```

## How a run executes

### Scan

```bash
NL_DIR=/Users/davidolsson/Documents/notella python3 "$CLAUDE_PLUGIN_ROOT/scripts/notella_images.py" scan
```

1. Pick pages: `--pages` or every page. Skip a page when its `quality.json` is newer than `derived/page.jpg`, `classify.json`, `transcribe.json` and `meta.yaml` (any of them changing makes it stale); `--force` recomputes.
2. For each page, in a process pool: take the page lock (`locks/pages/{id}.lock`, 5 min TTL; a held lock skips the page as `locked`), decode, measure, combine orientation signals, write `quality.json`, release.
3. Append one `pipeline.ndjson` line per page written (`artifact: quality`).
4. Print counts by grade, orientation status and warning, and every suspected page with its suggestion.

`--dry-run` computes and prints without writing anything (useful for calibration). The whole 412-page facility takes ~10 s.

### Fix one page

Confirm the transform first — either the scan's concrete suggestion, the classify orientation at confidence ≥ 0.7 (notella-classify calls this itself), or your own look (below). Then:

```bash
python3 "$CLAUDE_PLUGIN_ROOT/scripts/notella_images.py" fix --page 2026-04-09-y534 --rotate 180 --dry-run
python3 "$CLAUDE_PLUGIN_ROOT/scripts/notella_images.py" fix --page 2026-04-09-y534 --rotate 180
```

- The transform is **absolute relative to raw** (EXIF orientation applied first): rotate clockwise, then flip. Running the same fix twice changes nothing; a different fix replaces the first; `--reset` rebuilds with EXIF only and removes `orientation_fix`.
- `fix --rotate 0 --flip none` on a page whose raw carries an unapplied EXIF orientation bakes the EXIF rotation into `derived/` (the `exif` source's suggestion).
- The script recomputes `quality.json` (status becomes `fixed`), logs `pipeline.ndjson` (`action: orientation-fix`), and writes a `correction` event:

```json
{"id": "correction-2026-11-08-1651c5", "kind": "correction", "timestamp": "…", "page_id": "2026-04-09-y534",
 "entry_id": null, "project_slug": null,
 "evidence": {"correction_type": "orientation-fix", "rotate": 180, "flip": "none", "previous": null, "reset": false},
 "ingested_at": "…", "harvester_version": "notella-images@0.1.0"}
```

The id is `correction-{date}-{first 6 hex of sha256("{page}|{rotate}|{flip}|{date}")}`, so the same fix on the same day is recorded once.

### Fix many pages

After a scan, `fix --all-suggested --dry-run` lists every page whose status is `suspected` **with** a concrete suggestion; `--source stamp-position` (or `classify`) narrows it to one signal. Show the list, say how many are already transcribed (each needs the reprocess chain, which costs model calls — roughly $0.15 per page through first-pass and actions, plus the affected dailies), and run it without `--dry-run` only on a yes. Pages with `suggested: null` are never touched by `--all-suggested`.

### Vision pass — suspected pages with no suggestion

`suggested: null` means a signal fired that cannot say which way is up (low transcript confidence, a mirror-like stamp position, a legacy `rotated_90`). For each such page:

1. Read `pages/{id}/derived/thumb.jpg` (the Read tool shows the image; use `derived/page.jpg` if the thumbnail is too small to read).
2. Decide what makes the page upright and readable, using the notebook convention: the **date stamp** (e.g. `Dec 11/25`, with a circled page number under it) belongs **top-right**; the small **red series stamp** (`12-24`) belongs **bottom-right**; the notebook is landscape; text lines run left to right, top to bottom; letterforms are not mirrored (a mirrored page reads right-to-left with reversed `d/b`, `N`, `S`).
   - upside down → `--rotate 180`; text running bottom-to-top → `--rotate 90`; top-to-bottom → `--rotate 270`; mirror writing → `--flip horizontal`; mirrored and upside down → `--flip vertical`.
3. Say what you saw and how sure you are. Fix when you are sure; otherwise leave it for the person (it appears in notella-review under "Image attention").
4. A page that is upright after all: record a `wrong` image verdict through notella-review (or tell the person to), then `scan --pages ID --force` so the status becomes `ok` with source `review-cleared`.

### After a fix

`fix` prints the follow-up; it never calls a model. For a page that had already been transcribed, run with `--reprocess`, in order:

1. `notella-classify {id} --reprocess` (route plan and orientation on the corrected image);
2. `notella-transcribe {id} --reprocess`;
3. the L1 fan-out the route plan asks for — `notella-composition`, `notella-metadata`, and `notella-diagram` / `-sketch` / `-table` where routed — each `--reprocess`;
4. `notella-first-pass {id} --reprocess`, then `notella-actions {id} --reprocess` if the page has `actions.json`;
5. `notella-daily-synthesis {date} --reprocess` for the page's authoritative date (and the weekly will be flagged stale by the orchestrator).

A page fixed before transcription only needs `notella-classify --reprocess`.

### Mark a duplicate

```bash
python3 "$CLAUDE_PLUGIN_ROOT/scripts/notella_images.py" mark-duplicate --page 2026-01-02-02h0 --of 2025-12-01-4794
```

Sets `duplicate_of: ORIGINAL` on DUP, appends an `errors` note (`"duplicate raw image of … ; excluded from synthesis"`, the convention of the 15 pages from the 2026-01-02 batch), writes a `correction` event with `correction_type: "duplicate-raw-image"`, and leaves the phase alone. It refuses when ORIGINAL is itself a duplicate (mark against the root instead) and when the two images do not look alike (dhash distance > 12) unless `--force`. The syntheses skip `duplicate_of` pages on their next run; re-synthesize a daily that already counted the page.

`notella-import`'s `audit` lists facility-internal duplicate pairs and whether they are marked.

### Which pages are blurry / dark / poor

Run `scan` (cheap when fresh), then read the summary or filter `--json` output; `quality.json` per page holds the numbers. Show the poor pages first with their warnings and suggest re-photographing (the raw cannot be improved by a re-decode). Low contrast alone usually means a near-empty page.

## Idempotency

- `scan` skips fresh pages; `--force` rewrites the same values (only `computed_at` changes).
- `fix` is absolute: repeating it produces the same `derived/` and the same event id (written once per day).
- `mark-duplicate` on an already-marked page changes nothing and its event is a duplicate.
- `raw/` is never modified; any fix can be undone with `--reset`.

## Failure modes

| Failure | Behavior |
| --- | --- |
| `/usr/bin/sips` missing (not macOS) | Every subcommand exits 2 with a message; nothing is written. |
| A page has no `raw/` image | `scan` measures `derived/page.jpg` alone (`sha256_raw: null`, dhash of the derived image) — the validator should flag the page; `fix` refuses, there is nothing to rebuild from. |
| Page lock held by another stage | `scan` reports the page as `locked` and moves on; `fix` / `mark-duplicate` exit 3 — retry after the stage finishes. |
| `sips` fails on a file (corrupt, unsupported) | That page is reported under `errors` with sips's message; other pages continue; exit code 1. |
| `quality.json` stale after a review verdict | Verdicts do not change file mtimes; run `scan --pages ID --force` after recording one. |
| Classify and the stamp disagree | Status `suspected`, both in `sources`, classify's suggestion wins; do the vision pass. |
| `mark-duplicate` on unlike pages | Refused unless `--force`; check the two thumbnails first. |

## What this skill does NOT do

- Does not modify or delete `raw/`, and never deletes a page.
- Does not call a model. The vision pass is done by the Claude session running this skill, by looking at the thumbnail.
- Does not re-run transcription or synthesis after a fix — it names the chain; the orchestrator or the person runs it.
- Does not improve a blurred or dark photo; it says so and suggests re-photographing.
- Does not stage imports or check the inbox — that is `notella-import`.

## Examples

### "Which pages are upside down?"

```
notella-images scan (/Users/davidolsson/Documents/notella): 412 scanned, 0 fresh (skipped), 0 errors, 0 locked in 10.3s
  grade: good 392 · fair 20 · poor 0
  orientation: ok 303 · suspected 104 · fixed 0 · unknown 5
  warnings: low-contrast 20
  ? 2026-01-09-a8eq  rotate 180 flip none  (stamp-position)
  ? 2026-04-03-cknd  rotate 90 flip none  (stamp-position)
  ? 2026-04-09-y534  rotate 180 flip none  (classify-legacy, stamp-position)
  ...
```

104 pages have their red stamp in the wrong corner: 64 upside down, 40 sideways. All are already transcribed, so fixing them means re-running each through transcribe → first-pass. Offer `fix --all-suggested --source stamp-position --dry-run` and the cost before doing anything.

### "Fix the orientation of page 2026-04-09-y534"

Scan says `suspected, rotate 180 (classify-legacy, stamp-position)`; the thumbnail confirms the date stamp is bottom-left and upside down. `fix --page 2026-04-09-y534 --rotate 180` → status `fixed`; follow-up: classify, transcribe, L1, first-pass, actions with `--reprocess`, then the daily for 2026-04-09.

### "Is page 2026-03-31-ater the right way up?" (status unknown)

Look at `derived/thumb.jpg`: date stamp top-right, stamp bottom-right, text reads normally → "Yes, it is upright." Nothing to fix.

### "Page 2026-01-02-02h0 is the same photo as 2025-12-01-4794"

`mark-duplicate --page 2026-01-02-02h0 --of 2025-12-01-4794` → identical bytes, distance 0, `duplicate_of` set, correction event written.

## Reference files

- `references/quality-thresholds.md` — metric definitions, the measured facility distribution, simulated blur, the chosen thresholds and how to re-calibrate.
- `references/image-analysis.md` — sips decoding and EXIF behaviour, BMP parsing, the dhash definition and measured distances, orientation sources and precedence, the red-stamp heuristic, the transform convention.
- `../../scripts/notella_images.py` — the tool (`--help` per subcommand; `selftest` exercises every path on a scratch fixture).
