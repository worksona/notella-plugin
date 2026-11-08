# HEIC conversion

How `notella-intake` produces `derived/page.jpg` and `derived/thumb.jpg` from the immutable `raw/page.{ext}`. The JPG is the canonical decode every vision call reads; its quality and orientation matter more than file size.

## Default on macOS: sips

`sips` is always present on macOS and is the default decoder (the facility machine has no libheif, ImageMagick or exiftool). It reads HEIC/HEIF, JPEG and PNG and applies the EXIF orientation while decoding; converting through BMP leaves no orientation tag in the result:

```bash
sips -s format bmp raw/page.heic --out "$tmp/full.bmp"
sips -s format jpeg -s formatOptions 92 "$tmp/full.bmp" --out derived/page.jpg
sips -s format jpeg -s formatOptions 85 -Z 800 derived/page.jpg --out derived/thumb.jpg
```

This is exactly what `notella_images.py fix` does (plus a rotation/flip), so a page's `derived/` can always be rebuilt the same way. The `magick` recipes below apply when ImageMagick is installed; the verification and size-cap rules apply either way (`sips -g pixelWidth -g pixelHeight` for dimensions, `notella_images.py scan --pages ID` for a non-uniform, plausible decode — a blank decode scores contrast ≈ 0).

## Other tools, in preference order

| Tool | Install | Notes |
| --- | --- | --- |
| `heif-convert` (libheif) | `brew install libheif` | Fast, faithful colour; drops most EXIF (fine — EXIF is read from `raw/` first) |
| `magick` (ImageMagick 7 with libheif delegate) | `brew install imagemagick` | Slower; keeps more metadata; needed anyway for thumbnails and `-auto-orient` |
| `sips` (macOS built-in) | — | Last resort: `sips -s format jpeg -s formatOptions 92 in.heic --out out.jpg`; no colour-profile control |

Check availability once per run; when none can decode HEIC, skip HEIC files, leave them in the inbox, and say so in the batch summary. JPG/PNG sources do not need HEIC support.

## Decode

```bash
# HEIC / HEIF source
heif-convert -q 92 raw/page.heic derived/page.jpg \
  || magick raw/page.heic -auto-orient -quality 92 derived/page.jpg \
  || sips -s format jpeg -s formatOptions 92 raw/page.heic --out derived/page.jpg

# JPG / JPEG source — normalising re-encode, upright
magick raw/page.jpg -auto-orient -strip -quality 92 derived/page.jpg

# PNG source
magick raw/page.png -auto-orient -background white -alpha remove -quality 92 derived/page.jpg

# PDF source — one JPG per page at 200 dpi
pdftoppm -r 200 -jpeg -jpegopt quality=92 raw/page.pdf derived/page
# produces derived/page-1.jpg, page-2.jpg … ; each becomes its own page folder's derived/page.jpg
```

### Quality

92 is the setting. Below ~85 handwriting hairlines start to smear and the transcription confidence drops measurably; above 92 the file grows with no visible gain for the vision models. Do not use lossless — a 12 MP page at quality 100 is 8–10 MB per vision call.

### Orientation

The decoded JPG must be upright. `heif-convert` applies the HEIC `irot`/`imir` transforms itself. `magick -auto-orient` applies EXIF Orientation then resets the tag. After decoding, verify:

```bash
exiftool -s -s -s -Orientation -n derived/page.jpg   # expect 1 or empty
```

If not, `magick derived/page.jpg -auto-orient derived/page.jpg`. A sideways page costs a full transcription of garbage.

### Colour profile

iPhone HEIC is Display P3. `heif-convert` converts to sRGB and embeds the profile; `magick` keeps P3 unless told otherwise. Vision models are indifferent, but the desktop app and browsers render P3 JPGs slightly oversaturated on sRGB displays, so normalise:

```bash
magick derived/page.jpg -colorspace sRGB -strip derived/page.jpg
```

`-strip` removes the embedded profile and all remaining EXIF from the **derived** file only. `raw/` is untouched; it keeps the full EXIF and is the record.

### Size cap

If the long edge of `derived/page.jpg` exceeds `manifest.intake.max_decode_long_edge_px` (default 3000), downscale: `magick derived/page.jpg -resize 3000x3000\> derived/page.jpg`. Vision APIs downsample above ~1568 px anyway; 3000 keeps a margin for zooming in the desktop app without paying for a 12 MP upload.

## Thumbnail

```bash
thumb_max="${manifest_intake_thumbnail_max_dim_px:-800}"
magick derived/page.jpg -resize "${thumb_max}x${thumb_max}>" -quality 80 derived/thumb.jpg
```

Long edge ≤ `thumb_max`; never upscale (`>`). Quality 80 — the thumbnail is a kanban card, not an input.

## Verifying the decode

Before writing `meta.yaml`, check:

```bash
magick identify -format '%w %h %[colorspace]' derived/page.jpg
```

- width and height > 0 and plausible (≥ 600 px long edge; smaller means a thumbnail was dropped in the inbox);
- file size > 20 KB (a near-empty JPG means a failed decode that still produced a file);
- the image is not uniform (`magick derived/page.jpg -format '%[standard-deviation]' info:` > 1000 on the 16-bit scale). A blank result means the decoder wrote a black frame; retry with the next tool in the chain.

A failed verification leaves the inbox file in place, removes the partial `derived/`, and logs `decode-failed` with the tool and its stderr.

## Recording

On `meta.yaml`:

```yaml
decoded_with: heif-convert 1.17.6      # or magick 7.1.1-x / sips / pdftoppm
decoded_quality: 92
derived_width_px: 3000
derived_height_px: 2250
```

In the `page.intake` event: `decoded_to_jpg: true` for HEIC/HEIF/PNG/PDF sources, `false` for JPG re-encodes.

## Why keep raw/

`raw/page.heic` is the original — byte-for-byte, with EXIF, colour profile and the full 12 MP. If a future model wants more resolution, or the decode chain improves, `derived/` can be regenerated from `raw/` with `notella-intake --redecode {page-id}`, which rewrites `derived/` without touching the page id, phase, or any artifact. Deleting `raw/` to save space is never done by any skill.
