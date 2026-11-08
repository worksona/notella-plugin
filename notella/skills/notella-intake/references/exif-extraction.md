# EXIF extraction

Step 3 of `notella-intake`: read a capture time from each inbox file so pages sort stably, group into entries, and mint a page-id that starts with the right date. This file gives the exact `exiftool` invocations, the field precedence, the fallbacks, and how the result combines with the on-page date stamp.

## Tooling

`exiftool` (Phil Harvey's, `brew install exiftool`). Check once per run:

```bash
command -v exiftool >/dev/null || echo "exiftool missing — falling back to mtime for every file"
```

Missing exiftool is not fatal. Without it (the case on the facility machine), use Spotlight's reading of the same EXIF capture date before falling back to mtime:

```bash
mdls -raw -name kMDItemContentCreationDate "$file"     # "2026-01-02 01:33:53 +0000", or "(null)"
```

and take the EXIF orientation from the file header (`notella_images.py` parses the JPEG APP1 segment itself; for HEIC/PNG `sips -g orientation "$file"`). The batch summary says which path was used.

## Images (JPG, JPEG, HEIC, HEIF, PNG)

```bash
exiftool -j -n -api QuickTimeUTC=1 \
  -DateTimeOriginal -CreateDate -SubSecDateTimeOriginal -OffsetTimeOriginal -OffsetTime \
  -ImageWidth -ImageHeight -Orientation -Make -Model \
  "$file"
```

`-j` returns a JSON array with one object; `-n` keeps numeric fields numeric (Orientation as 1–8).

Field precedence for `source_capture_time`:

1. `SubSecDateTimeOriginal` (has sub-seconds and often the offset)
2. `DateTimeOriginal`
3. `CreateDate`

EXIF times are local wall-clock with no zone unless `OffsetTimeOriginal` / `OffsetTime` is present. Resolve to UTC:

- If an offset is present (`+02:00`), apply it.
- Else assume `manifest.facility.timezone` (America/Vancouver for this facility). Record `source_capture_time_tz_assumed: true` on `meta.yaml` so a later correction knows the zone was inferred.

Format as ISO-8601 UTC with `Z`: `2026-05-02T16:13:51Z`.

PNG files exported from Photos or screenshots usually have no EXIF; they fall through to mtime.

### HEIC specifics

iPhone HEIC carries EXIF in the same tags; exiftool reads them without conversion, so extract **before** HEIC → JPG conversion (conversion with `heif-convert` drops most EXIF; `magick` keeps some). The decoded `derived/page.jpg` is never the EXIF source.

### Orientation

Record `Orientation` (1–8). `sips -s format bmp` (the default decoder, see `heic-conversion.md`), `heif-convert` and `magick -auto-orient` bake rotation into the decoded image; `derived/page.jpg` must be upright because every vision call reads it. If the decoder did not auto-orient (check `exiftool -Orientation derived/page.jpg` → should be 1 or absent), run `magick derived/page.jpg -auto-orient derived/page.jpg`.

## PDFs

```bash
exiftool -j -n -CreateDate -ModifyDate -PageCount "$file"
```

Precedence: `CreateDate`, then `ModifyDate`. PDF dates carry their own offset (`D:20260502091351-07'00'`); exiftool normalises them. A multi-page PDF is one inbox file but becomes one page per PDF page (`pdftoppm -r 200 -jpeg "$file" derived/page` then one page folder per output); every page shares the PDF's capture time and the entry-grouping rule puts them in one entry in PDF page order.

## Fallback: filesystem mtime

```bash
stat -f %m "$file"      # macOS, seconds since epoch
```

Use when exiftool is absent, the tags are missing, or the parsed date is implausible (before 2000, or more than 1 day in the future). Convert to ISO UTC. Set `source_capture_time: null` on `meta.yaml` (mtime is used for sorting and the id date but is not recorded as a capture time — it is when the file landed in the inbox, which may be weeks later).

## Combining with the on-page date stamp (Step 3b)

The notebook convention is a top-right `MM-DD` stamp. After the vision call returns `page_date_stamp`:

```
year = EXIF year if source_capture_time else current year
if stamp month-day is > 14 days after the EXIF date: year -= 1    # December page photographed in January
authoritative = f"{year}-{MM}-{DD}T00:00:00Z"
```

Precedence for the date used in the page-id and for entry grouping:

1. On-page stamp with resolved year (`page_date_stamp` + `page_date_year`)
2. EXIF capture time
3. mtime

`source_capture_time` on `meta.yaml` keeps the EXIF value (or null); the stamp-derived date is separately visible via `page_date_stamp` + `page_date_year`. Downstream, `notella-metadata` and `notella-daily-synthesis` use their own chain (`metadata.date` → `transcribe.extractedDate` → `source_capture_time` → `ingested_at`), which is why `metadata.date` must be ISO.

## Sorting

Sort key per file: `(authoritative_date, source_capture_time or mtime, filename)`. Stable and deterministic, so re-running the drain reproduces the same entry grouping.

## Recording on meta.yaml

```yaml
source_filename: IMG_4421.HEIC
source_capture_time: 2026-05-02T16:13:51Z     # EXIF, UTC; null if from mtime
source_capture_time_tz_assumed: false
source_width_px: 4032
source_height_px: 3024
source_orientation: 6
source_device: "Apple iPhone 15 Pro"            # Make + Model, or null
```

and in the `page.intake` event evidence: `source_capture_time`, `width_px`, `height_px`, `decoded_to_jpg`.

## Failure handling

| Situation | Behaviour |
| --- | --- |
| exiftool exits non-zero on one file | Treat as no EXIF; use mtime; log `exif-read-failed` with the stderr line in the batch summary. Continue. |
| EXIF date is implausible | Use mtime; log `exif-implausible` with the raw value. |
| Offset missing | Assume facility timezone; set `source_capture_time_tz_assumed: true`. |
| HEIC without EXIF (some AirDrop re-encodes) | mtime path; `source_capture_time: null`; the page relies on the on-page stamp. |
