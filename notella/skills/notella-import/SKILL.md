---
name: notella-import
description: "Bring photos into the notella facility without doubling up. Audits folders of page photos against every page the facility already holds (exact byte match and near-duplicate perceptual hash, including rotated or mirrored copies), checks the inbox for duplicates and image quality, stages only new pages into the inbox as copies, holds inbox duplicates aside and keeps an import history. Use whenever the user says 'import photos from a folder', 'import my notebook photos', 'audit my photos against notella', 'do I already have these pages', 'check this folder for duplicates', 'which of these are new', 'stage new pages', 'what's in the inbox', 'check the inbox', 'held imports', 'release a held photo', 'import history', or any request to move page photos from elsewhere into notella. Also trigger when notella-orchestrator step 1 runs the inbox check. Runs `scripts/notella_images.py` (stdlib Python + macOS sips); source folders are never modified."
---

# notella-import — audited imports, no double-ups

Photos of notebook pages live in many places before they reach notella: the camera roll export, a scanner folder, an old backup. Dropping a folder into `inbox/` blind re-imports pages the facility already has — the 15 duplicate pages of the 2026-01-02 batch got through exactly that way, because intake's page id is seeded with the capture date and a re-dated copy mints a new id. This skill puts an audit in front of the inbox.

## Purpose

- **Audit** a source folder against every facility page and report, per file: already in the facility (exact), near duplicate (same page re-encoded, resized, rotated or mirrored), duplicate inside the folder, or new — plus its image quality.
- **Stage** the new files into `inbox/` as **copies**, with a ledger row per decision.
- **Check and hold** the inbox: before intake mints pages, move files that duplicate the facility into `inbox/_held/` so they are not minted; release any that turn out to be different pages.

## The tool

```bash
python3 "$CLAUDE_PLUGIN_ROOT/scripts/notella_images.py" <subcommand> [--root DIR] [--json] ...
```

Facility root: `--root`, else `$NL_DIR`, else `~/notella` (this machine: `NL_DIR=/Users/davidolsson/Documents/notella`). Needs macOS `/usr/bin/sips` and Python ≥ 3.9.

| Subcommand | What it does |
| --- | --- |
| `audit --source DIR [--source DIR ...] [--recursive] [--near 6] [--workers N]` | compare source folders with the facility → `logs/inventory-audit.json` |
| `stage --from-audit [--include new] [--include near] [--min-grade poor\|fair\|good] [--dry-run]` | copy audited files into `inbox/`, log each decision |
| `inbox-check [--near 6] [--workers N]` | check files in `inbox/` → `logs/inbox-check.json` |
| `hold [--near 6] [--dry-run]` | inbox-check, then move facility duplicates into `inbox/_held/` |
| `release NAME [--note TEXT] [--dry-run]` | move one held file back into `inbox/` |

## Inputs and outputs

**Reads:** source folders (read-only — opened for hashing and copying, never written, moved or deleted); `inbox/`; every page's `quality.json` (`sha256_raw`, `dhash`, `grade`), hashing `raw/` on the fly for pages without one; `meta.yaml:duplicate_of`; `longitudinal/imports.ndjson` (earlier releases).

**Writes:**

| Path | By | Content |
| --- | --- | --- |
| `logs/inventory-audit.json` | audit | the audit report (overwritten each run, tmp + rename) |
| `logs/inbox-check.json` | inbox-check, hold | the inbox report (overwritten) |
| `inbox/{name}` | stage, release | copied / released image |
| `inbox/_held/{name}` + `{name}.held.json` | hold | the held image and a note saying why |
| `longitudinal/imports.ndjson` | stage, hold, release | one row per decision, append-only |

### Statuses

| Status | Meaning |
| --- | --- |
| `in_facility_exact` | sha256 equals a page's `raw/` — byte-identical; `page_id` names it |
| `near_duplicate` | dhash within `--near` (default 6) of a page, possibly via a rotated/mirrored variant (`match_transform`); `page_id`, `distance` |
| `duplicate_within_source` / `duplicate_within_inbox` | same bytes as an earlier file in the same run (`same_as`) |
| `new` | none of the above; `nearest_distance` says how close the closest page was |
| `skipped` | PDF (`pdf-not-supported`) or another non-image file (`unsupported-type`) |

Measured on the facility, distinct pages are never closer than distance 10 and re-encodes of one page are within 6; details in `../notella-images/references/image-analysis.md`.

### `logs/inventory-audit.json`

```json
{
  "schema_version": "0.1.0", "generated_at": "…", "generator": "notella-images@0.1.0",
  "facility": "/Users/davidolsson/Documents/notella",
  "sources": ["/Users/davidolsson/Pictures/notebook"], "recursive": true, "near_threshold": 6,
  "summary": {"files": 7, "counts": {"new": 1, "in_facility_exact": 2, "near_duplicate": 3, "skipped": 1},
              "facility_pages": 412, "facility_pages_hashed_on_the_fly": 0,
              "facility_exact_pairs": 15, "facility_near_pairs": 0, "facility_pairs_unmarked": 0, "seconds": 8.5},
  "files": [{"path": "…/IMG_0003.jpg", "size_bytes": 781743, "sha256": "…", "dhash": "…",
             "status": "near_duplicate", "page_id": "2026-02-09-ny3h", "distance": 6,
             "nearest_distance": 6, "match_transform": "rot180",
             "quality_grade": "fair", "quality_warnings": ["low-contrast"], "exif_orientation": null}],
  "facility_duplicates": {"exact": [["2025-12-01-4794", "2026-01-02-02h0"]],
                          "exact_detail": [{"a": "2025-12-01-4794", "b": "2026-01-02-02h0", "marked": true}],
                          "near": [{"a": "…", "b": "…", "distance": 4, "marked": false}]}
}
```

`facility_duplicates` is the facility auditing itself: pairs of pages with identical raw bytes, and near pairs, each with `marked` = one is `duplicate_of` the other. An unmarked pair is a job for `notella-images mark-duplicate`.

### `logs/inbox-check.json`

```json
{"schema_version": "0.1.0", "generated_at": "…", "near_threshold": 6,
 "files": [{"name": "IMG_4421.HEIC", "sha256": "…", "dhash": "…", "status": "near_duplicate",
            "page_id": "2026-04-09-y534", "distance": 3, "match_transform": "rot180",
            "quality": {"grade": "good", "warnings": [], "width": 4032, "height": 3024, "megapixels": 12.19,
                        "brightness": 188.2, "contrast": 41.0, "sharpness": 2210.5,
                        "dark_fraction": 0.004, "bright_fraction": 0.12},
            "exif_orientation": 6, "size_bytes": 2918432}]}
```

### `longitudinal/imports.ndjson` — the import history

One JSON line per considered file, never edited:

```json
{"ts": "…", "source_path": "/Users/…/IMG_0007.jpg", "sha256": "…", "dhash": "…",
 "decision": "staged", "matched_page": null, "distance": null, "quality_grade": "good", "inbox_name": "IMG_0007.jpg"}
```

| Decision | Written by | Meaning |
| --- | --- | --- |
| `staged` | stage | copied into `inbox/` as `inbox_name` |
| `skipped_exact` | stage | byte-identical to a page (`matched_page`), or already in `inbox/` / `_held/` |
| `skipped_near` | stage | near duplicate and `--include near` not given |
| `skipped_quality` | stage | graded below `--min-grade` |
| `skipped_within_source` | stage | same bytes as another file in the audit |
| `skipped_missing` / `skipped_changed` | stage | the source file vanished or changed since the audit |
| `held_exact` / `held_near` | hold | moved from `inbox/` into `inbox/_held/` (`held_name`) |
| `released` | release | moved back from `_held/` into `inbox/`; `hold` will not re-hold these bytes |

"Import history" questions are answered from this file: what was staged when and from where, what was skipped and why, what is still held.

### `inbox/_held/`

Files intake must not mint. Intake enumerates `inbox/` at depth 1 only, so `_held/` is invisible to it. Each held file has a sidecar `{name}.held.json`: `{held_at, by, decision, original_name, matched_page, distance, sha256, dhash, quality_grade, match_transform}`. Nothing is ever deleted from `_held/` by a skill — discarding a held photo is the person's call (they delete it in Finder).

## How a run executes

### Import from a folder

1. **Audit.** `audit --source DIR [--recursive]`. Always show the summary it prints: counts per status, every near duplicate with its page and distance, facility-internal pairs not yet marked, and the quality grade of the new files.
2. **Look at near duplicates** when there are any: open the source file and `pages/{page_id}/derived/thumb.jpg` side by side. Same page re-exported → leave it out. A different page that happens to look alike (rare: distinct pages measure ≥ 10) → include it.
3. **Ask** what to stage: new only (default), new + near, and whether to drop `poor` photos (`--min-grade fair`) — a poor photo is better re-taken than transcribed. Show `stage --from-audit … --dry-run` first.
4. **Stage** on a yes: `stage --from-audit --include new [--include near] [--min-grade fair]`. Files are copied (`shutil.copy2` to a hidden `.partial` name, then renamed), name collisions get `-1`, `-2` suffixes, and the copy is skipped if the file's sha256 no longer matches the audit.
5. Tell the person the next step: `notella-orchestrator` (or `notella-intake`) drains the inbox.

**Unattended (`--auto`)**: staging without asking is allowed only when the caller passes explicit include flags (`--include new`, optionally `--include near`, and `--min-grade`). Without them, write the audit and stop.

### What's in the inbox

`inbox-check` → list each file with status, matched page, grade and warnings, and EXIF orientation. Files that duplicate the facility should be held before intake runs: offer `hold`.

### Hold and release

- `hold` re-runs the inbox check, then moves every `in_facility_exact` and `near_duplicate` file into `inbox/_held/` with its note and an `imports.ndjson` row (`held_exact` / `held_near`). Files released earlier stay put. The orchestrator runs this in step 1 before intake.
- Held near duplicates surface in `notella-review` under **Held imports**: `done` = it is a duplicate (stays held; deleting it is the person's choice), `wrong` = not a duplicate → `release NAME`.
- `release NAME` moves the file back into `inbox/` under its original name (suffixed on collision), removes the sidecar note, and logs `released`.

## Idempotency

- `audit` and `inbox-check` only rewrite their own report files.
- `stage` re-run after a stage finds the staged files already in `inbox/` (by sha256) and logs `skipped_exact` instead of copying again — but it does log a row each run; run it once per audit.
- `hold` never holds the same bytes twice (they are no longer in the inbox) and never re-holds a released file.
- Nothing in a source folder or in `raw/` is ever written.

## Failure modes

| Failure | Behavior |
| --- | --- |
| `--source` is not a directory | Listed as `skipped` with `not-a-directory`; other sources continue. |
| A source file cannot be decoded by sips | Listed with `status: error` and sips's message; not staged. |
| PDF in the source | `skipped` (`pdf-not-supported`) — sips does not rasterise PDFs; export pages to JPEG first. |
| `stage` without a prior audit | Exit 2: "run audit first". |
| Facility pages without `quality.json` | Hashed from `raw/` on the fly (the summary counts them); run `notella-images scan` so later audits are instant. |
| Name collision in `inbox/` or `_held/` | Numeric suffix; the ledger records the final name. |
| `release` of an unknown name | Exit 2 listing the held folder. |

## What this skill does NOT do

- Never moves, renames or deletes a file in a source folder. Staging copies.
- Never deletes a held file; discarding is the person's decision.
- Does not mint pages — `notella-intake` does, from whatever is in `inbox/`.
- Does not fix orientation or grade pages already in the facility — that is `notella-images`.
- Does not read PDFs.

## Examples

### "Do I already have the photos in ~/Pictures/notebook?"

```
Inventory audit — 214 files in 1 source folder(s) vs 412 facility pages (21.4s)
  new                      31
  in_facility_exact        168
  near_duplicate           12
  duplicate_within_source  2
  skipped                  1
  ~ IMG_2210.jpg ≈ 2026-03-04-8gsr (distance 2)
  ~ IMG_2214.jpg ≈ 2026-04-09-y534 (distance 4, rot180)
  ...
Facility-internal: 15 exact pair(s), 0 near pair(s); 0 not marked duplicate_of
Next: notella_images.py stage --from-audit [--include near] [--min-grade fair] --dry-run
```

"You already have 180 of these (168 identical, 12 re-exports). 31 are new — 2 of them are graded poor (blurry). Stage the 29 good ones?"

### "Stage the new ones"

`stage --from-audit --include new --min-grade fair` → `staged 29 · skipped_exact 168 · skipped_near 12 · skipped_quality 2 · skipped_within_source 2`. "29 copies are in the inbox; run notella to process them."

### "What's in the inbox?"

```
Inbox check — 3 file(s)
  IMG_4421.HEIC                in_facility_exact      2026-04-09-y534  grade good
  IMG_4422.HEIC                near_duplicate         2026-04-09-75hq d=3  grade good exif=6
  IMG_4423.HEIC                new                      grade fair [low-contrast] exif=6
2 file(s) duplicate the facility — run `notella_images.py hold` before intake.
```

### "Release IMG_4422.HEIC, it's a different page"

`release IMG_4422.HEIC` → back in `inbox/`, `released` row written; the next drain mints it.

## Reference files

- `../notella-images/references/image-analysis.md` — dhash definition, measured distances, rotated/mirrored variants, sips decoding.
- `../notella-images/references/quality-thresholds.md` — what the quality grade of an imported file means.
- `../../scripts/notella_images.py` — the tool (`--help` per subcommand).
