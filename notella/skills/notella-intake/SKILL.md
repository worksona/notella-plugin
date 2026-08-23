---
name: notella-intake
description: "Drain `~/notella/inbox/` into the page lifecycle. Mints page-ids, runs HEIC→JPG conversion, generates thumbnails, groups photos into entries by EXIF capture-time window, writes initial `meta.yaml` at phase=intake, emits `page.intake` events. Use whenever the user says 'drain the inbox', 'process my new photos', 'intake notella', 'I dropped photos in the inbox', 'ingest these notes', 'start the pipeline', or any request to bring inbox photos into the facility. Also trigger when notella-orchestrator's decision walk reaches step 1 (inbox drain). Routes all writes through `notella-state`. Idempotent — re-running with the same files produces zero new pages."
---

# notella-intake — the inbox drainer

Every photo in `~/notella/inbox/` is destined for `~/notella/pages/{page-id}/`. This skill is the bridge.

## Purpose

Take whatever sits in `inbox/` and turn it into properly-shaped page records at `phase=intake`. Subsequent pipeline skills (`notella-classify`, `notella-transcribe`, …) advance them from there.

## Inputs and outputs

**Inputs:**
- Files in `~/notella/inbox/*.{jpg,jpeg,heic,heif,png,pdf}`

**Outputs (per accepted file):**
- `pages/{page-id}/meta.yaml` at `phase=intake`
- `pages/{page-id}/raw/page.{ext}` (immutable copy of the original)
- `pages/{page-id}/derived/page.jpg` (decoded JPG; HEIC sources are converted)
- `pages/{page-id}/derived/thumb.jpg` (long-edge ≤ `manifest.intake.thumbnail_max_dim_px`)
- One `events/YYYY-MM-DD/{event-id}.json` per page with `kind: page.intake`
- Optional `entries/{entry-id}/meta.yaml` if the entry-grouping rule binds multiple new pages together
- Inbox file removed after successful page record creation
- One `inbox.drained` event summarizing the batch

## How a drain runs

### Step 1 — Read configuration

Via `notella-state get-manifest`:
- `manifest.intake.heic_convert`
- `manifest.intake.generate_thumbnail`
- `manifest.intake.thumbnail_max_dim_px`
- `manifest.intake.preserve_originals`
- `manifest.intake.entry_grouping_window_minutes`

### Step 2 — Enumerate inbox files

```bash
find ~/notella/inbox -maxdepth 1 -type f \
  \( -iname '*.jpg' -o -iname '*.jpeg' -o -iname '*.heic' -o -iname '*.heif' \
     -o -iname '*.png' -o -iname '*.pdf' \) | sort
```

Sort by EXIF capture-time when present, otherwise by mtime, then by filename. Stable order is required for entry grouping.

### Step 3 — Read EXIF capture-time per file

For images: `exiftool -DateTimeOriginal -CreateDate -j {file}` (preferred) or fall back to mtime.
For PDFs: best-effort via `exiftool -CreateDate`; otherwise mtime.

Record `source_capture_time` per file; null if no EXIF and PDF metadata both fail.

### Step 3b — Extract page-embedded date and page numbers via vision

After producing `derived/page.jpg`, make a single lightweight vision call (claude-haiku-4-5) to extract structured metadata written directly on the page:

**Top-right corner:** pages always carry a date stamp and a page number in the format `MM-DD` (e.g. `12-23` = December 23rd). The year is inferred from the EXIF capture year (or current year if EXIF is absent).

**Bottom-right corner:** pages carry a series page number indicating their position within that month's notebook (e.g. `p.47` or just `47`). This is separate from the top-right per-day page number.

Prompt:
```
Look at the top-right and bottom-right corners of this handwritten page.

1. Top-right: extract the date stamp (format MM-DD, e.g. "12-23" means December 23rd) and the page number for that date. Return as {"top_right_date": "MM-DD", "top_right_page": <int or null>}.

2. Bottom-right: extract the series page number for this month's notebook (a number, possibly prefixed with "p."). Return as {"bottom_right_series_page": <int or null>}.

Return only JSON, no explanation. If a field is not visible or legible, return null for that field.
```

Parse the JSON response. On failure (malformed, vision error), all fields are null — do not block intake.

Store results on `meta.yaml` as:
```yaml
page_date_stamp: "12-23"          # MM-DD as written, null if not found
page_date_year: 2025              # inferred year
page_number_daily: 3              # top-right page number for that day, null if not found
page_number_series: 47            # bottom-right series number for the month, null if not found
```

When `page_date_stamp` is present, compute `source_capture_time` from it even if EXIF was absent:
```
source_capture_time = f"{year}-{month:02d}-{day:02d}T00:00:00Z"
```
This becomes the authoritative date for entry grouping and page-id minting (taking precedence over mtime).

Log the vision call to `logs/llm-calls.ndjson` with `task: "intake-page-metadata"`.

### Step 4 — Group into entries by EXIF window

Walk the sorted file list. Open a new entry whenever the gap to the previous file's `source_capture_time` exceeds `entry_grouping_window_minutes`, or whenever a previous capture-time was null. Within an entry, files keep their sorted order; this becomes `entries/{entry-id}/meta.yaml:page_order`.

If a file has null capture-time, it gets a single-page entry of its own.

Mint `entry-id` deterministically: `ent_{date-of-earliest-page}-{shortuuid4(seed=earliest_capture_time + first_filename)}`. Re-running with the same files produces the same entry-id.

### Step 5 — Mint page-id per file

Compute deterministically:

```python
seed = (source_capture_time or mtime).strftime("%Y-%m-%d") + "|" + sha256(file_bytes)[:16]
short = base32_crockford(seed_hash)[:4]   # alphabet abcdefghjkmnpqrstuvwxyz23456789
page_id = f"{capture_date}-{short}"
```

Re-running with the same source bytes yields the same page-id; if `pages/{page-id}/` already exists, this file is a no-op.

### Step 6 — Acquire the page lock

```
notella-state acquire-page-lock {page-id, actor: notella-intake@<version>}
```

If held by another actor, skip the file and continue with the next; surface skipped files in the batch summary.

### Step 7 — Materialize the page folder

```
pages/{page-id}/
├── raw/page.{original-ext}     ← byte-for-byte copy of inbox file
├── derived/page.jpg            ← decoded JPG (see HEIC handling below)
└── derived/thumb.jpg
```

### HEIC handling

If the source is HEIC/HEIF and `manifest.intake.heic_convert` is true:

```bash
heif-convert -q 92 raw/page.heic derived/page.jpg
```

Falls back to `magick raw/page.heic derived/page.jpg` if `heif-convert` is unavailable. JPG is the canonical decode used by every downstream vision call.

For non-HEIC sources, `derived/page.jpg` is produced by re-encoding to JPG at quality 92 (PNG sources lose nothing the vision API cares about; JPG sources get a normalized re-encode).

### Thumbnail generation

```bash
magick derived/page.jpg -resize ${thumb_max}x${thumb_max} derived/thumb.jpg
```

Where `thumb_max = manifest.intake.thumbnail_max_dim_px` (default 800).

### Step 8 — Write meta.yaml

```yaml
schema_version: "0.1.0"
id: 2026-05-02-x7k2
entry_id: ent_2026-05-02-aab1
phase: intake
phase_history:
  intake: 2026-05-02T09:14:22Z
source_filename: IMG_4421.HEIC
source_capture_time: 2026-05-02T09:13:51Z
ingested_at: 2026-05-02T09:14:22Z
page_date_stamp: "12-23"          # MM-DD as written on page top-right; null if not found
page_date_year: 2025              # inferred year
page_number_daily: 3              # top-right page number for that day; null if not found
page_number_series: 47            # bottom-right series page number for the month; null if not found
content_mix: null                 # filled by classify
confidence: null
tags: []
project_attributions: []
person_attributions: []
links_to: []
errors: []
```

Write via `notella-state log-page-artifact {page-id, artifact: "meta", payload}`. (`meta` is special — it sits at the page root, not as `meta.json`.)

Atomic write through `notella-state` ensures the per-page lock is honored.

### Step 9 — Emit `page.intake` event

```yaml
id: page.intake-2026-05-02-{6-char-hash}
kind: page.intake
timestamp: 2026-05-02T09:14:22Z       # ingested_at; or source_capture_time if available
page_id: 2026-05-02-x7k2
entry_id: ent_2026-05-02-aab1
project_slug: null
evidence:
  source_filename: IMG_4421.HEIC
  source_capture_time: 2026-05-02T09:13:51Z
  size_bytes: 2918432
  width_px: 4032
  height_px: 3024
  decoded_to_jpg: true                 # was HEIC source
  thumb_dim_px: 800
ingested_at: 2026-05-02T09:14:22Z
harvester_version: notella-intake@0.1.0
```

`hash` over `(page_id + source_filename + size_bytes)` so re-running with the same source produces the same event-id and the second write is a no-op.

### Step 10 — Write entry meta if multi-page

If the entry contains multiple pages, write `entries/{entry-id}/meta.yaml`:

```yaml
schema_version: "0.1.0"
id: ent_2026-05-02-aab1
created_at: 2026-05-02T09:14:22Z
page_order: [2026-05-02-x7k2, 2026-05-02-w9m3, 2026-05-02-r6t8]
title: null                # optional; can be set later
summary: null
tags: []
project_attributions: []
```

For single-page entries the file is still written so `entries/` is uniformly indexed.

### Step 11 — Move inbox file to processed

After all artifacts are written successfully, remove the inbox file:

```bash
rm "${inbox_file}"
```

Failure handling: if any write fails before this, leave the inbox file in place. Re-running picks up where we left off (idempotent thanks to deterministic ids).

### Step 12 — Release the page lock

```
notella-state release-page-lock {page-id, actor: notella-intake}
```

### Step 13 — Finalize the batch

After all files in this run are processed:

```
notella-state finalize-batch {
  actor: notella-intake@<version>,
  kind: page.intake,
  count: <new pages created>,
  max_timestamp: <max ingested_at>
}
```

Emit one `inbox.drained` event summarizing the run:

```yaml
kind: inbox.drained
evidence:
  files_seen: 7
  pages_created: 5
  pages_skipped_duplicate: 2
  entries_created: 2
  errors: []
```

## Idempotency

Every operation is idempotent:

- Re-running on the same files: deterministic page-ids collide with existing folders → no-op.
- Re-running with a partial failure: any file that didn't get fully processed still exists in `inbox/`; this run picks it up.
- Re-running entry grouping: the `ent_*` id is deterministic over the seed pages, so the same group always produces the same entry-id.

## Failure modes

| Failure                                      | Behavior                                                 |
| -------------------------------------------- | -------------------------------------------------------- |
| `heif-convert` and `magick` both unavailable | Skip HEIC files; surface in batch summary; user installs the dependency. |
| EXIF unreadable                              | Use mtime; record `source_capture_time: null`; the page becomes its own entry. |
| Page folder write fails midway               | Inbox file remains; partial folder is left for the validator to flag. Manual cleanup may be needed. |
| Page lock held by another actor              | Skip and continue; surface in batch summary.             |
| Inbox file is not an image / PDF             | Skip with a warning logged; leave file in inbox.         |

## What this skill does NOT do

- **Does not classify, transcribe, or analyze.** That's downstream pipeline skills.
- **Does not delete originals from `raw/`.** They are immutable.
- **Does not advance phase past `intake`.** That's the next skill's job.
- **Does not infer projects or people from the photo.** Attributions stay empty until metadata/first-pass run.

## Examples

### "Drain the inbox"

Reads `~/notella/inbox/`, processes every supported file, returns a summary:

```
Processed 5 files (4 HEIC, 1 JPG):
- Created 5 new pages: 2026-05-02-{x7k2, w9m3, r6t8, p4q1, n2v5}
- Created 2 entries: ent_2026-05-02-aab1 (3 pages), ent_2026-05-02-bcd2 (2 pages)
- Skipped 0 duplicates
- Errors: 0

All pages now at phase=intake. Run notella-orchestrator to advance.
```

### "Re-run intake"

```
Processed 5 files:
- All 5 pages already exist (deterministic ids); skipped silently.
- Created 0 new entries.
- Errors: 0

No changes.
```

## Reference files

- `references/exif-extraction.md` — the exact `exiftool` invocation per file type and the fallback behavior.
- `references/heic-conversion.md` — quality settings, color-profile preservation, fallbacks.
- `references/page-id-derivation.md` — the deterministic seed and base32 alphabet.

If reference files are missing, the SKILL.md instructions above are self-sufficient.
