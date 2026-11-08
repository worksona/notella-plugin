#!/usr/bin/env python3
"""notella_images.py - image management for the notella facility.

Image quality, orientation (upside down / mirrored), duplicate detection and
import management for photographed notebook pages. Python 3.9+, standard
library only; every pixel operation shells out to macOS `sips`.

Facility root: --root, else $NL_DIR, else ~/notella.

Safety rules (enforced by every subcommand):
  * raw/ files and files in --source folders are never modified or deleted.
  * every file write is atomic (tmp + fsync + os.replace).
  * append-only files (*.ndjson, events/*.jsonl) get exactly one os.write per line.

Subcommands: scan, fix, mark-duplicate, audit, inbox-check, stage, hold,
release, selftest. Run `notella_images.py <subcommand> --help` for each.
"""

import argparse
import concurrent.futures
import datetime as _dt
import hashlib
import json
import os
import re
import shutil
import struct
import subprocess
import sys
import tempfile
import time

VERSION = "0.1.0"
ACTOR = "notella-images"
HARVESTER = "notella-images@" + VERSION
SCHEMA_VERSION = "0.1.0"

IMAGE_EXTS = (".jpg", ".jpeg", ".heic", ".heif", ".png")
ANALYSIS_LONG_EDGE = 512
JPEG_QUALITY = 92
DEFAULT_THUMB = 800
DEFAULT_NEAR = 6
LOCK_TTL = 300

# Calibrated on the 412-page facility on 2026-11-08 plus simulated blur (see
# skills/notella-images/references/quality-thresholds.md for the measured
# distribution and the reasoning). The scanned corpus has no dark, overexposed
# or blurry tail, so those thresholds sit outside its range at levels that
# simulated or real degradation reaches; low-contrast sits at the corpus p5.
THRESHOLDS = {
    "blurry_edge_ratio_below": 2.45,     # Laplacian variance / gradient energy (scale-free blur measure)
    "blurry_sharpness_below": 150.0,     # hard floor on Laplacian variance (512px gray)
    "dark_brightness_below": 120.0,      # mean luminance 0-255
    "dark_fraction_above": 0.15,         # share of pixels < 40
    "overexposed_bright_fraction_above": 0.92,   # share of pixels > 245
    "low_contrast_below": 16.0,          # luminance std-dev
    "low_resolution_mp_below": 2.0,      # megapixels
}
GRADE_ORDER = {"poor": 0, "fair": 1, "good": 2}
# warnings that describe the file rather than its quality; excluded from grade
INFORMATIONAL_WARNINGS = ("exif-rotated",)

CLASSIFY_SUSPECT_CONFIDENCE = 0.6
LOW_TRANSCRIPT_CONFIDENCE = 0.45

LEGACY_ORIENTATION = {
    "upright": None,
    "rotated_180": {"rotate": 180, "flip": "none"},
    "upside_down": {"rotate": 180, "flip": "none"},
    "upside-down": {"rotate": 180, "flip": "none"},
    "rotated_90": None,          # direction unknown: needs a look
    "rotated_90_cw": {"rotate": 270, "flip": "none"},   # content turned cw -> turn back ccw
    "rotated_90_ccw": {"rotate": 90, "flip": "none"},
    "rotated_270": {"rotate": 90, "flip": "none"},
    "mirrored": {"rotate": 0, "flip": "horizontal"},
    "mirrored_horizontal": {"rotate": 0, "flip": "horizontal"},
    "mirrored_vertical": {"rotate": 0, "flip": "vertical"},
}

# EXIF orientation -> (clockwise rotation, flip) that makes the stored pixels
# upright. Rotation first, then flip.
EXIF_TO_TRANSFORM = {
    1: (0, "none"), 2: (0, "horizontal"), 3: (180, "none"), 4: (0, "vertical"),
    5: (90, "horizontal"), 6: (90, "none"), 7: (270, "horizontal"), 8: (270, "none"),
}


# --------------------------------------------------------------------------
# small utilities
# --------------------------------------------------------------------------

def now_iso():
    return _dt.datetime.now(_dt.timezone.utc).replace(microsecond=0).strftime("%Y-%m-%dT%H:%M:%SZ")


def today_utc():
    return _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%d")


def facility_root(arg_root):
    root = arg_root or os.environ.get("NL_DIR") or os.path.join(os.path.expanduser("~"), "notella")
    return os.path.abspath(os.path.expanduser(root))


def atomic_write_bytes(path, data):
    d = os.path.dirname(path) or "."
    os.makedirs(d, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix="." + os.path.basename(path) + ".", suffix=".tmp", dir=d)
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(data)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, path)
    except BaseException:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise


def atomic_write_json(path, obj):
    atomic_write_bytes(path, (json.dumps(obj, indent=2, ensure_ascii=False) + "\n").encode("utf-8"))


def atomic_install(src_tmp, dest):
    """Move a finished temp file into place atomically (same filesystem)."""
    d = os.path.dirname(dest)
    os.makedirs(d, exist_ok=True)
    fd, staged = tempfile.mkstemp(prefix="." + os.path.basename(dest) + ".", suffix=".tmp", dir=d)
    os.close(fd)
    try:
        shutil.copyfile(src_tmp, staged)
        with open(staged, "rb+") as fh:
            os.fsync(fh.fileno())
        os.replace(staged, dest)
    except BaseException:
        if os.path.exists(staged):
            os.unlink(staged)
        raise


def append_line(path, obj):
    """Append one JSON line with a single os.write (POSIX O_APPEND)."""
    line = (json.dumps(obj, ensure_ascii=False, separators=(",", ":")) + "\n").encode("utf-8")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    fd = os.open(path, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o644)
    try:
        os.write(fd, line)
    finally:
        os.close(fd)


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def hamming(a, b):
    if a is None or b is None:
        return None
    return bin(int(a, 16) ^ int(b, 16)).count("1")


def read_json(path, default=None):
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return default


def read_text(path):
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return fh.read()
    except OSError:
        return None


def read_ndjson(path):
    rows = []
    try:
        with open(path, "r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    rows.append(json.loads(line))
                except ValueError:
                    continue
    except OSError:
        pass
    return rows


def unique_name(directory, name):
    base, ext = os.path.splitext(name)
    cand = name
    n = 1
    while os.path.exists(os.path.join(directory, cand)):
        cand = "%s-%d%s" % (base, n, ext)
        n += 1
    return cand


class Lock(object):
    """Per-page advisory lock: locks/pages/{id}.lock, 5-minute TTL."""

    def __init__(self, root, page_id):
        self.path = os.path.join(root, "locks", "pages", page_id + ".lock")
        self.held = False

    def acquire(self):
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        payload = json.dumps({"actor": ACTOR, "acquired": now_iso(), "ttl_seconds": LOCK_TTL}).encode()
        for _ in range(2):
            try:
                fd = os.open(self.path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644)
                os.write(fd, payload)
                os.close(fd)
                self.held = True
                return True
            except FileExistsError:
                info = read_json(self.path, {}) or {}
                try:
                    age = time.time() - os.path.getmtime(self.path)
                except OSError:
                    continue
                if age > int(info.get("ttl_seconds", LOCK_TTL)):
                    try:
                        os.unlink(self.path)   # stale: may be force-released
                    except OSError:
                        pass
                    continue
                return False
        return False

    def release(self):
        if self.held:
            try:
                os.unlink(self.path)
            except OSError:
                pass
            self.held = False


# --------------------------------------------------------------------------
# image I/O via sips
# --------------------------------------------------------------------------

def run_sips(args):
    p = subprocess.run(["/usr/bin/sips"] + args, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if p.returncode != 0:
        raise RuntimeError("sips %s failed: %s" % (" ".join(args[:4]), p.stderr.decode("utf-8", "replace").strip()))
    return p.stdout.decode("utf-8", "replace")


def jpeg_header(path):
    """Parse a JPEG's stored dimensions and EXIF orientation without decoding.

    Returns (width, height, orientation|None) or None if not a parseable JPEG.
    """
    try:
        with open(path, "rb") as fh:
            data = fh.read(256 * 1024)
    except OSError:
        return None
    if data[:2] != b"\xff\xd8":
        return None
    i = 2
    orientation = None
    while i + 4 <= len(data):
        if data[i] != 0xFF:
            i += 1
            continue
        marker = data[i + 1]
        if marker in (0xD8, 0x01) or 0xD0 <= marker <= 0xD7:
            i += 2
            continue
        if marker == 0xFF:
            i += 1
            continue
        seglen = struct.unpack(">H", data[i + 2:i + 4])[0]
        seg = data[i + 4:i + 2 + seglen]
        if marker == 0xE1 and seg[:6] == b"Exif\x00\x00" and orientation is None:
            orientation = _exif_orientation(seg[6:])
        if marker in (0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF):
            if len(seg) >= 5:
                h, w = struct.unpack(">HH", seg[1:5])
                return (w, h, orientation)
            return None
        if marker == 0xDA:
            return None
        i += 2 + seglen
    return None


def _exif_orientation(tiff):
    try:
        if tiff[:2] == b"II":
            e = "<"
        elif tiff[:2] == b"MM":
            e = ">"
        else:
            return None
        off = struct.unpack(e + "I", tiff[4:8])[0]
        n = struct.unpack(e + "H", tiff[off:off + 2])[0]
        for k in range(n):
            ent = tiff[off + 2 + 12 * k: off + 14 + 12 * k]
            tag, typ, cnt = struct.unpack(e + "HHI", ent[:8])
            if tag == 0x0112:
                val = struct.unpack(e + "H", ent[8:10])[0]
                return val if 1 <= val <= 8 else None
    except (struct.error, IndexError):
        return None
    return None


def image_props(path):
    """(stored_width, stored_height, exif_orientation|None)."""
    hdr = jpeg_header(path)
    if hdr is not None:
        return hdr
    out = run_sips(["-g", "pixelWidth", "-g", "pixelHeight", "-g", "orientation", path])
    w = h = None
    o = None
    for line in out.splitlines():
        line = line.strip()
        if line.startswith("pixelWidth:"):
            w = int(line.split(":", 1)[1])
        elif line.startswith("pixelHeight:"):
            h = int(line.split(":", 1)[1])
        elif line.startswith("orientation:"):
            v = line.split(":", 1)[1].strip()
            o = int(v) if v.isdigit() else None
    if w is None or h is None:
        raise RuntimeError("sips could not read dimensions of %s" % path)
    return (w, h, o)


def parse_bmp(data):
    """Decode an uncompressed 24- or 32-bit BMP.

    Returns (width, height, rows) where rows is a top-down list of
    (r, g, b) byte strings, one byte per pixel per channel.
    """
    if data[:2] != b"BM":
        raise ValueError("not a BMP")
    pix_off = struct.unpack("<I", data[10:14])[0]
    dib = struct.unpack("<I", data[14:18])[0]
    width, height = struct.unpack("<ii", data[18:26])
    bpp = struct.unpack("<H", data[28:30])[0]
    comp = struct.unpack("<I", data[30:34])[0] if dib >= 40 else 0
    if bpp not in (24, 32):
        raise ValueError("unsupported BMP bit depth %d" % bpp)
    if comp not in (0, 3, 6):
        raise ValueError("compressed BMP not supported (compression=%d)" % comp)
    top_down = height < 0
    height = abs(height)
    step = bpp // 8
    ri, gi, bi = 2, 1, 0
    if bpp == 32 and comp in (3, 6):
        if dib >= 52:
            masks = struct.unpack("<III", data[54:66])
        else:
            masks = struct.unpack("<III", data[14 + dib:14 + dib + 12])

        def byte_index(m):
            for k in range(4):
                if m == 0xFF << (8 * k):
                    return k
            raise ValueError("unsupported BMP channel mask %#x" % m)
        ri, gi, bi = byte_index(masks[0]), byte_index(masks[1]), byte_index(masks[2])
    row_size = ((bpp * width + 31) // 32) * 4
    rows = []
    for y in range(height):
        src_y = y if top_down else height - 1 - y
        start = pix_off + src_y * row_size
        row = data[start:start + width * step]
        if len(row) < width * step:
            raise ValueError("truncated BMP")
        rows.append((row[ri::step], row[gi::step], row[bi::step]))
    return width, height, rows


def decode_small(path, tmpdir, long_edge=ANALYSIS_LONG_EDGE, props=None):
    """Decode an image to RGB rows whose long edge is `long_edge` px.

    sips applies the EXIF orientation while decoding, so the rows are the
    image as it is meant to be displayed.
    """
    w, h, o = props or image_props(path)
    if w >= h:
        W, H = long_edge, max(1, int(round(h * long_edge / float(w))))
    else:
        H, W = long_edge, max(1, int(round(w * long_edge / float(h))))
    fd, out = tempfile.mkstemp(suffix=".bmp", dir=tmpdir)
    os.close(fd)
    try:
        run_sips(["-s", "format", "bmp", "-z", str(H), str(W), path, "--out", out])
        with open(out, "rb") as fh:
            data = fh.read()
    finally:
        if os.path.exists(out):
            os.unlink(out)
    return parse_bmp(data)


# --------------------------------------------------------------------------
# pixel metrics
# --------------------------------------------------------------------------

def to_gray(rows):
    gray = []
    for r, g, b in rows:
        gray.append(bytes([(77 * rr + 150 * gg + 29 * bb) >> 8 for rr, gg, bb in zip(r, g, b)]))
    return gray


def gray_stats(gray):
    n = 0
    s = 0
    s2 = 0
    dark = 0
    bright = 0
    sq = [i * i for i in range(256)]
    for row in gray:
        n += len(row)
        s += sum(row)
        s2 += sum(sq[v] for v in row)
        dark += sum(1 for v in row if v < 40)
        bright += sum(1 for v in row if v > 245)
    mean = s / float(n)
    var = max(0.0, s2 / float(n) - mean * mean)
    return mean, var ** 0.5, dark / float(n), bright / float(n)


def edge_stats(gray):
    """(variance of the 4-neighbour Laplacian, mean squared forward gradient).

    The Laplacian variance alone mostly measures how much ink is on the page;
    its ratio to the gradient energy is a scale-free blur measure (blur removes
    second-derivative energy faster than first-derivative energy).
    """
    s = 0
    s2 = 0
    g2 = 0
    n = 0
    for y in range(1, len(gray) - 1):
        up, c, dn = gray[y - 1], gray[y], gray[y + 1]
        vals = [4 * cc - ll - rr - uu - dd for cc, ll, rr, uu, dd in
                zip(c[1:-1], c[:-2], c[2:], up[1:-1], dn[1:-1])]
        s += sum(vals)
        s2 += sum(v * v for v in vals)
        g2 += sum((cc - rr) * (cc - rr) + (cc - dd) * (cc - dd) for cc, rr, dd in zip(c[1:-1], c[2:], dn[1:-1]))
        n += len(vals)
    if n == 0:
        return 0.0, 0.0
    mean = s / float(n)
    return s2 / float(n) - mean * mean, g2 / float(n)


def laplacian_variance(gray):
    return edge_stats(gray)[0]


def dhash_gray(gray):
    """64-bit difference hash: box-average to 9x8, compare horizontal neighbours."""
    h = len(gray)
    w = len(gray[0]) if h else 0
    if w < 9 or h < 8:
        raise ValueError("image too small for dhash")
    cells = []
    for cy in range(8):
        y0, y1 = cy * h // 8, (cy + 1) * h // 8
        line = []
        for cx in range(9):
            x0, x1 = cx * w // 9, (cx + 1) * w // 9
            tot = 0
            for y in range(y0, y1):
                tot += sum(gray[y][x0:x1])
            line.append(tot / float((y1 - y0) * (x1 - x0)))
        cells.append(line)
    bits = 0
    for line in cells:
        for x in range(8):
            bits = (bits << 1) | (1 if line[x] > line[x + 1] else 0)
    return "%016x" % bits


def transform_gray(gray, rotate=0, flip="none"):
    """Rotate clockwise by `rotate`, then flip. Returns new list of bytes rows."""
    g = gray
    if rotate == 90:
        g = [bytes(col) for col in zip(*g[::-1])]
    elif rotate == 180:
        g = [row[::-1] for row in g[::-1]]
    elif rotate == 270:
        g = [bytes(col) for col in zip(*g)][::-1]
    if flip == "horizontal":
        g = [row[::-1] for row in g]
    elif flip == "vertical":
        g = g[::-1]
    return g


def _is_red(rr, gg, bb):
    return rr > 120 and rr - gg > 40 and rr - bb > 25


def stamp_corner(rows):
    """Find the red page-number stamp. Returns 'tl'|'tr'|'bl'|'br' or None.

    The notebook convention puts a small red series stamp (e.g. "12-24") in
    the bottom-right corner of every page. On the 512px decode it is a compact
    cluster of 10-60 reddish pixels inside the corner's 15% x 15% box. Red
    sticky notes and red headings are rejected: the cluster must be compact,
    alone among the corners, and not continue into the band next to it.
    """
    h = len(rows)
    w = len(rows[0][0]) if h else 0
    if w < 40 or h < 40:
        return None
    cw, ch = int(w * 0.15), int(h * 0.15)
    st = {}
    for k in ("tl", "tr", "bl", "br"):
        st[k] = {"n": 0, "x0": w, "x1": -1, "y0": h, "y1": -1, "nb": 0}
    for y, (r, g, b) in enumerate(rows):
        if ch * 2 <= y < h - ch * 2:
            continue
        reds = [x for x, (rr, gg, bb) in enumerate(zip(r, g, b)) if _is_red(rr, gg, bb)]
        if not reds:
            continue
        for x in reds:
            v = "t" if y < ch else ("b" if y >= h - ch else None)
            hz = "l" if x < cw else ("r" if x >= w - cw else None)
            if v and hz:
                c = st[v + hz]
                c["n"] += 1
                c["x0"] = min(c["x0"], x)
                c["x1"] = max(c["x1"], x)
                c["y0"] = min(c["y0"], y)
                c["y1"] = max(c["y1"], y)
            # neighbour bands: the next 15% inward, horizontally and vertically
            if v and not hz:
                if x < 2 * cw:
                    st[v + "l"]["nb"] += 1
                elif x >= w - 2 * cw:
                    st[v + "r"]["nb"] += 1
            if hz and not v:
                if y < 2 * ch:
                    st["t" + hz]["nb"] += 1
                elif y >= h - 2 * ch:
                    st["b" + hz]["nb"] += 1
    best = max(st, key=lambda k: st[k]["n"])
    c = st[best]
    if not (8 <= c["n"] <= 600):
        return None
    if (c["x1"] - c["x0"] + 1) > 0.12 * w or (c["y1"] - c["y0"] + 1) > 0.12 * h:
        return None
    if any(st[k]["n"] > 0.25 * c["n"] for k in st if k != best):
        return None
    if c["nb"] > 0.3 * c["n"]:
        return None
    return best


_CORNER_XY = {"tl": (0, 0), "tr": (1, 0), "bl": (0, 1), "br": (1, 1)}


def _apply_to_corner(xy, rotate, flip):
    x, y = xy
    if rotate == 90:
        x, y = 1 - y, x
    elif rotate == 180:
        x, y = 1 - x, 1 - y
    elif rotate == 270:
        x, y = y, 1 - x
    if flip == "horizontal":
        x = 1 - x
    elif flip == "vertical":
        y = 1 - y
    return (x, y)


def stamp_transform(corner, landscape):
    """The one (rotate, flip) that brings the stamp to bottom-right on a landscape page."""
    for rot in (0, 90, 180, 270):
        for flip in ("none", "horizontal", "vertical"):
            if flip == "vertical" and rot in (90, 270):
                continue      # same set as the other flip; keep one spelling per transform
            land_after = landscape if rot in (0, 180) else not landscape
            if land_after and _apply_to_corner(_CORNER_XY[corner], rot, flip) == (1, 1):
                return {"rotate": rot, "flip": flip}
    return None


def analyze_image(path, tmpdir, want_variants=False, want_stamp=False):
    """Decode once and compute every metric we need for one image file."""
    w, h, o = image_props(path)
    _, _, rows = decode_small(path, tmpdir, props=(w, h, o))
    gray = to_gray(rows)
    mean, std, dark, bright = gray_stats(gray)
    lap, grad = edge_stats(gray)
    disp_w, disp_h = (h, w) if o in (5, 6, 7, 8) else (w, h)
    res = {
        "width": disp_w,
        "height": disp_h,
        "stored_width": w,
        "stored_height": h,
        "megapixels": round(w * h / 1e6, 2),
        "exif_orientation": o,
        "brightness": round(mean, 1),
        "contrast": round(std, 1),
        "sharpness": round(lap, 1),
        "edge_ratio": round(lap / grad, 3) if grad > 0 else 0.0,
        "dark_fraction": round(dark, 3),
        "bright_fraction": round(bright, 3),
        "dhash": dhash_gray(gray),
    }
    if want_variants:
        res["dhash_variants"] = {
            "rot90": dhash_gray(transform_gray(gray, 90)),
            "rot180": dhash_gray(transform_gray(gray, 180)),
            "rot270": dhash_gray(transform_gray(gray, 270)),
            "flip-h": dhash_gray(transform_gray(gray, 0, "horizontal")),
        }
    if want_stamp:
        res["stamp"] = stamp_corner(rows)
    return res


def quality_warnings(m):
    t = THRESHOLDS
    warns = []
    if m["sharpness"] < t["blurry_sharpness_below"] or m.get("edge_ratio", 99) < t["blurry_edge_ratio_below"]:
        warns.append("blurry")
    if m["brightness"] < t["dark_brightness_below"] or m["dark_fraction"] > t["dark_fraction_above"]:
        warns.append("dark")
    if m["bright_fraction"] > t["overexposed_bright_fraction_above"]:
        warns.append("overexposed")
    if m["contrast"] < t["low_contrast_below"]:
        warns.append("low-contrast")
    if m["megapixels"] < t["low_resolution_mp_below"]:
        warns.append("low-resolution")
    if m.get("exif_orientation") not in (None, 1):
        warns.append("exif-rotated")
    return warns


def grade_for(warnings):
    q = [w for w in warnings if w not in INFORMATIONAL_WARNINGS]
    if len(q) >= 2:            # covers "blurry + anything"
        return "poor"
    if len(q) == 1:
        return "fair"
    return "good"


# --------------------------------------------------------------------------
# facility helpers
# --------------------------------------------------------------------------

def page_dir(root, pid):
    return os.path.join(root, "pages", pid)


def list_page_ids(root):
    d = os.path.join(root, "pages")
    if not os.path.isdir(d):
        return []
    return sorted(p for p in os.listdir(d) if os.path.isfile(os.path.join(d, p, "meta.yaml")))


def raw_path(root, pid):
    d = os.path.join(page_dir(root, pid), "raw")
    if not os.path.isdir(d):
        return None
    for name in sorted(os.listdir(d)):
        if name.startswith("page.") and not name.startswith("."):
            return os.path.join(d, name)
    return None


def meta_field(text, key):
    if text is None:
        return None
    m = re.search(r"^%s:[ \t]*(.*?)[ \t]*$" % re.escape(key), text, re.M)
    if not m:
        return None
    v = m.group(1).strip()
    if v in ("", "null", "~"):
        return None
    return v.strip("\"'")


def meta_block(text, key):
    """(start, end) offsets of a top-level `key:` line plus its indented / list continuation lines."""
    if text is None:
        return None
    m = re.search(r"^%s:.*(?:\n|$)" % re.escape(key), text, re.M)
    if not m:
        return None
    end = m.end()
    cont = re.compile(r"(?:[ \t]+\S|-[ \t]).*(?:\n|$)")
    while end < len(text):
        lm = cont.match(text, end)
        if not lm or lm.end() == end:
            break
        end = lm.end()
    return (m.start(), end)


def parse_orientation_fix(text):
    blk = meta_block(text, "orientation_fix")
    if not blk:
        return None
    body = text[blk[0]:blk[1]]
    out = {}
    m = re.search(r"\{(.*)\}", body)
    pairs = m.group(1).split(",") if m else body.splitlines()[1:]
    for p in pairs:
        if ":" in p:
            k, v = p.split(":", 1)
            out[k.strip()] = v.strip().strip("\"'")
    try:
        rot = int(out.get("rotate", 0))
    except ValueError:
        rot = 0
    return {"rotate": rot, "flip": out.get("flip", "none") or "none",
            "applied_at": out.get("applied_at"), "by": out.get("by")}


def set_meta_block(text, key, block_text):
    """Replace a top-level block, or append it at the end. block_text ends with \\n."""
    blk = meta_block(text, key)
    if blk:
        return text[:blk[0]] + block_text + text[blk[1]:]
    if text and not text.endswith("\n"):
        text += "\n"
    return text + block_text


def remove_meta_block(text, key):
    blk = meta_block(text, key)
    if not blk:
        return text
    return text[:blk[0]] + text[blk[1]:]


def yaml_quote(s):
    return '"' + s.replace("\\", "\\\\").replace('"', '\\"') + '"'


def add_meta_error(text, note):
    """Append a note to the top-level `errors` list, preserving everything else."""
    q = yaml_quote(note)
    if q in text:
        return text
    m = re.search(r"^errors:[ \t]*(.*)$", text, re.M)
    if not m:
        if text and not text.endswith("\n"):
            text += "\n"
        return text + "errors:\n  - " + q + "\n"
    rest = m.group(1).strip()
    if rest == "[]" or rest == "":
        if rest == "[]":
            return text[:m.start()] + "errors:\n  - " + q + text[m.end():]
        blk = meta_block(text, "errors")
        ins = blk[1]
        item = re.search(r"^([ \t]*)-[ \t]", text[m.end():ins], re.M)
        indent = item.group(1) if item else "  "
        prefix = "" if text[:ins].endswith("\n") else "\n"
        return text[:ins] + prefix + indent + "- " + q + "\n" + text[ins:]
    if rest.startswith("[") and rest.endswith("]"):
        inner = rest[1:-1].strip()
        new = "[" + (inner + ", " if inner else "") + q + "]"
        return text[:m.start()] + "errors: " + new + text[m.end():]
    return text  # unrecognised shape: leave untouched


def set_meta_scalar(text, key, value):
    m = re.search(r"^%s:.*$" % re.escape(key), text, re.M)
    line = "%s: %s" % (key, value)
    if m:
        return text[:m.start()] + line + text[m.end():]
    if text and not text.endswith("\n"):
        text += "\n"
    return text + line + "\n"


def write_event(root, kind, page_id, evidence, id_seed, entry_id=None):
    """Write a deterministic event file + one jsonl index line. Idempotent."""
    ts = now_iso()
    date = ts[:10]
    eid = "%s-%s-%s" % (kind, date, hashlib.sha256(id_seed(date).encode("utf-8")).hexdigest()[:6])
    path = os.path.join(root, "events", date, eid + ".json")
    if os.path.exists(path):
        return {"status": "duplicate", "id": eid, "path": path}
    ev = {
        "id": eid, "kind": kind, "timestamp": ts, "page_id": page_id,
        "entry_id": entry_id, "project_slug": None, "evidence": evidence,
        "ingested_at": now_iso(), "harvester_version": HARVESTER,
    }
    atomic_write_json(path, ev)
    append_line(os.path.join(root, "events", date + ".jsonl"), ev)
    return {"status": "written", "id": eid, "path": path}


def cleared_by_review(root):
    """Pages whose latest image verdict is `wrong` (false alarm)."""
    latest = {}
    for row in read_ndjson(os.path.join(root, "longitudinal", "verdicts.ndjson")):
        if row.get("target_kind") == "image" and row.get("target_id"):
            latest[row["target_id"]] = row.get("verdict")
    return set(k for k, v in latest.items() if v == "wrong")


def orientation_status(root, pid, meta_text, raw_exif, derived_info, cleared):
    """Combine every orientation signal for one page into the quality.json block.

    Suggestions are ABSOLUTE transforms relative to raw/ with EXIF applied (what
    `fix` takes). Precedence when several signals suggest something:
    classify (new object form) > stamp-position > classify-legacy > exif.
    """
    fix = parse_orientation_fix(meta_text)
    if fix:
        return {"status": "fixed", "suggested": None, "sources": ["orientation-fix"]}
    pdir = page_dir(root, pid)
    known = False
    sources = []
    sugg = {}
    cls = read_json(os.path.join(pdir, "classify.json"), {}) or {}
    o = cls.get("orientation") if isinstance(cls, dict) else None
    if isinstance(o, dict):
        known = True
        try:
            rot = int(o.get("rotate", 0)) % 360
        except (TypeError, ValueError):
            rot = 0
        flip = o.get("flip") or "none"
        conf = o.get("confidence")
        conf = float(conf) if isinstance(conf, (int, float)) else 0.0
        if (rot != 0 or flip != "none") and conf >= CLASSIFY_SUSPECT_CONFIDENCE:
            sources.append("classify")
            sugg["classify"] = {"rotate": rot, "flip": flip}
    elif isinstance(o, str):
        known = True
        key = o.strip().lower()
        if key != "upright":
            sources.append("classify-legacy")
            sugg["classify-legacy"] = LEGACY_ORIENTATION.get(key)
    stamp = derived_info.get("stamp")
    verified = False          # positive evidence the page is upright (not just "nobody said otherwise")
    if isinstance(o, dict) and o.get("rotate") is not None:
        try:
            verified = int(o.get("rotate", 0)) % 360 == 0 and (o.get("flip") or "none") == "none" \
                and float(o.get("confidence") or 0) >= 0.7
        except (TypeError, ValueError):
            verified = False
    if stamp:
        known = True
        t = stamp_transform(stamp, derived_info.get("landscape", True))
        if t and (t["rotate"] != 0 or t["flip"] != "none"):
            sources.append("stamp-position")
            # a stamp in a mirrored position may also be a rotation: needs a look
            sugg["stamp-position"] = t if t["flip"] == "none" else None
        elif t:
            verified = True
    if raw_exif not in (None, 1):
        known = True
        if not derived_info.get("auto_oriented", False):
            sources.append("exif")
            # fix always applies EXIF first, so the absolute transform is identity
            sugg["exif"] = {"rotate": 0, "flip": "none"}
    tr = read_json(os.path.join(pdir, "transcribe.json"), None)
    if isinstance(tr, dict) and isinstance(tr.get("transcriptConfidence"), (int, float)):
        known = True
        if tr["transcriptConfidence"] < LOW_TRANSCRIPT_CONFIDENCE:
            sources.append("low-transcript-confidence")
    if pid in cleared:
        return {"status": "ok", "suggested": None, "sources": ["review-cleared"]}
    if sources:
        suggestion = None
        for k in ("classify", "stamp-position", "classify-legacy", "exif"):
            if sugg.get(k):
                suggestion = sugg[k]
                break
        return {"status": "suspected", "suggested": suggestion, "sources": sources}
    if not verified:
        # No stamp found and no confident vision verdict: the legacy classifier's "upright"
        # proved unreliable (2026-11-08 pilot: upside-down May pages passed as ok), so the
        # page needs a vision check (notella-images) before it is trusted.
        return {"status": "unknown", "suggested": None, "sources": ["no-stamp"]}
    return {"status": "ok" if known else "unknown", "suggested": None, "sources": []}


def derived_auto_oriented(raw_props, derived_path, raw_sha, derived_sha):
    """Was the derived image produced with the raw's EXIF orientation applied?"""
    rw, rh, ro = raw_props
    if ro in (None, 1):
        return True
    if not derived_path or not os.path.exists(derived_path):
        return False
    try:
        dw, dh, do = image_props(derived_path)
    except RuntimeError:
        return False
    if do not in (None, 1):
        return False          # still relies on the tag
    if raw_sha == derived_sha:
        return False
    if ro in (5, 6, 7, 8):
        return (dw, dh) == (rh, rw)
    return True


def compute_quality(root, pid, cleared, tmpdir):
    pdir = page_dir(root, pid)
    rp = raw_path(root, pid)
    dp = os.path.join(pdir, "derived", "page.jpg")
    if rp is None and not os.path.exists(dp):
        raise RuntimeError("no raw/ or derived/page.jpg")
    has_derived = os.path.exists(dp)
    raw_sha = sha256_file(rp) if rp else None
    derived_sha = sha256_file(dp) if has_derived else None
    src_path = dp if has_derived else rp
    m = analyze_image(src_path, tmpdir, want_stamp=True)
    if rp is None:
        raw_m = m
        raw_props = (m["stored_width"], m["stored_height"], m["exif_orientation"])
    elif raw_sha == derived_sha:
        raw_m = m
        raw_props = (m["stored_width"], m["stored_height"], m["exif_orientation"])
    else:
        raw_props = image_props(rp)
        raw_m = analyze_image(rp, tmpdir)
    warns = quality_warnings(dict(m, exif_orientation=raw_props[2]))
    meta_text = read_text(os.path.join(pdir, "meta.yaml"))
    auto = derived_auto_oriented(raw_props, dp if has_derived else None, raw_sha, derived_sha)
    orient = orientation_status(root, pid, meta_text, raw_props[2],
                                {"auto_oriented": auto, "stamp": m.get("stamp"),
                                 "landscape": m["width"] >= m["height"]}, cleared)
    return {
        "schema_version": SCHEMA_VERSION,
        "computed_at": now_iso(),
        "source": "derived" if has_derived else "raw",
        "width": m["width"],
        "height": m["height"],
        "megapixels": m["megapixels"],
        "exif_orientation": raw_props[2],
        "brightness": m["brightness"],
        "contrast": m["contrast"],
        "sharpness": m["sharpness"],
        "dark_fraction": m["dark_fraction"],
        "bright_fraction": m["bright_fraction"],
        "sha256_raw": raw_sha,
        "dhash": raw_m["dhash"],
        "grade": grade_for(warns),
        "warnings": warns,
        "orientation": orient,
    }


def needs_scan(root, pid):
    """quality.json missing, or older than an input it was computed from."""
    pdir = page_dir(root, pid)
    q = os.path.join(pdir, "quality.json")
    if not os.path.exists(q):
        return True
    qt = os.path.getmtime(q)
    for rel in ("derived/page.jpg", "classify.json", "transcribe.json", "meta.yaml"):
        p = os.path.join(pdir, rel)
        if os.path.exists(p) and os.path.getmtime(p) > qt:
            return True
    return False


def _scan_worker(job):
    root, pid, cleared, write = job
    tmpdir = tempfile.mkdtemp(prefix="nl-img-")
    lock = Lock(root, pid)
    try:
        if write and not lock.acquire():
            return {"page_id": pid, "status": "locked"}
        q = compute_quality(root, pid, cleared, tmpdir)
        if write:
            atomic_write_json(os.path.join(page_dir(root, pid), "quality.json"), q)
        return {"page_id": pid, "status": "written" if write else "computed", "quality": q}
    except Exception as exc:  # noqa: BLE001 - report per page, keep going
        return {"page_id": pid, "status": "error", "error": str(exc)}
    finally:
        lock.release()
        shutil.rmtree(tmpdir, ignore_errors=True)


def _hash_worker(job):
    """sha256 + dhash (+ metrics) for an arbitrary file; used by audit/inbox-check."""
    path, variants = job
    tmpdir = tempfile.mkdtemp(prefix="nl-img-")
    try:
        out = {"path": path, "sha256": sha256_file(path), "size_bytes": os.path.getsize(path)}
        m = analyze_image(path, tmpdir, want_variants=variants)
        warns = quality_warnings(m)
        out.update({
            "dhash": m["dhash"], "dhash_variants": m.get("dhash_variants"),
            "exif_orientation": m["exif_orientation"],
            "quality": {
                "grade": grade_for(warns), "warnings": warns, "width": m["width"],
                "height": m["height"], "megapixels": m["megapixels"],
                "brightness": m["brightness"], "contrast": m["contrast"],
                "sharpness": m["sharpness"], "dark_fraction": m["dark_fraction"],
                "bright_fraction": m["bright_fraction"],
            },
        })
        return out
    except Exception as exc:  # noqa: BLE001
        return {"path": path, "error": str(exc)}
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


def _page_hash_worker(job):
    root, pid = job
    rp = raw_path(root, pid)
    if rp is None:
        return {"page_id": pid, "error": "no raw image"}
    tmpdir = tempfile.mkdtemp(prefix="nl-img-")
    try:
        m = analyze_image(rp, tmpdir)
        return {"page_id": pid, "sha256_raw": sha256_file(rp), "dhash": m["dhash"], "grade": None}
    except Exception as exc:  # noqa: BLE001
        return {"page_id": pid, "error": str(exc)}
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


def pool_map(fn, jobs, workers):
    if not jobs:
        return []
    workers = max(1, min(workers or (os.cpu_count() or 4), len(jobs)))
    if workers == 1:
        return [fn(j) for j in jobs]
    with concurrent.futures.ProcessPoolExecutor(max_workers=workers) as ex:
        return list(ex.map(fn, jobs, chunksize=1))


def facility_index(root, workers):
    """{page_id: {sha256_raw, dhash, grade, duplicate_of}} for every page."""
    idx = {}
    missing = []
    for pid in list_page_ids(root):
        q = read_json(os.path.join(page_dir(root, pid), "quality.json"), None)
        dup = meta_field(read_text(os.path.join(page_dir(root, pid), "meta.yaml")), "duplicate_of")
        if isinstance(q, dict) and q.get("sha256_raw") and q.get("dhash"):
            idx[pid] = {"sha256_raw": q["sha256_raw"], "dhash": q["dhash"], "grade": q.get("grade"),
                        "duplicate_of": dup, "from": "quality.json"}
        else:
            missing.append(pid)
            idx[pid] = {"duplicate_of": dup}
    for r in pool_map(_page_hash_worker, [(root, p) for p in missing], workers):
        if "error" in r:
            idx[r["page_id"]].update({"sha256_raw": None, "dhash": None, "grade": None, "error": r["error"]})
        else:
            idx[r["page_id"]].update({"sha256_raw": r["sha256_raw"], "dhash": r["dhash"], "grade": None,
                                      "from": "computed"})
    return idx


def match_against(idx, sha, dhash, variants, near):
    """Return (status, page_id, distance, transform) for one file vs the facility."""
    for pid, e in idx.items():
        if e.get("sha256_raw") == sha:
            return ("in_facility_exact", pid, 0, None)
    best = (None, None, None)
    cands = [("none", dhash)] + sorted((variants or {}).items())
    for pid, e in idx.items():
        if not e.get("dhash"):
            continue
        for tname, h in cands:
            d = hamming(h, e["dhash"])
            if d is not None and (best[1] is None or d < best[1]):
                best = (pid, d, tname)
    if best[1] is not None and best[1] <= near:
        return ("near_duplicate", best[0], best[1], None if best[2] == "none" else best[2])
    return ("new", None, best[1], None)


def facility_duplicates(idx, near):
    pids = sorted(p for p in idx if idx[p].get("sha256_raw"))
    by_sha = {}
    for p in pids:
        by_sha.setdefault(idx[p]["sha256_raw"], []).append(p)
    exact = []
    for group in by_sha.values():
        for i in range(len(group)):
            for j in range(i + 1, len(group)):
                exact.append([group[i], group[j]])
    exact_set = set(tuple(x) for x in exact)
    nearl = []
    hashes = [(p, int(idx[p]["dhash"], 16)) for p in pids if idx[p].get("dhash")]
    for i in range(len(hashes)):
        a, ha = hashes[i]
        for j in range(i + 1, len(hashes)):
            b, hb = hashes[j]
            d = bin(ha ^ hb).count("1")
            if d <= near and (a, b) not in exact_set:
                nearl.append({"a": a, "b": b, "distance": d, "marked": _marked(idx, a, b)})
    exact_out = [{"a": a, "b": b, "marked": _marked(idx, a, b)} for a, b in exact]
    return exact_out, nearl


def _marked(idx, a, b):
    return idx.get(a, {}).get("duplicate_of") == b or idx.get(b, {}).get("duplicate_of") == a


# --------------------------------------------------------------------------
# output helpers
# --------------------------------------------------------------------------

def emit(args, obj, human_lines):
    if getattr(args, "json", False):
        sys.stdout.write(json.dumps(obj, indent=2, ensure_ascii=False) + "\n")
    else:
        for line in human_lines:
            print(line)


def require_facility(root):
    if not os.path.isdir(os.path.join(root, "pages")):
        sys.stderr.write("notella-images: %s is not a notella facility (no pages/). Set NL_DIR or --root.\n" % root)
        sys.exit(2)


# --------------------------------------------------------------------------
# subcommand: scan
# --------------------------------------------------------------------------

def cmd_scan(args):
    root = facility_root(args.root)
    require_facility(root)
    all_ids = list_page_ids(root)
    if args.pages:
        unknown = [p for p in args.pages if p not in all_ids]
        if unknown:
            sys.stderr.write("unknown page id(s): %s\n" % ", ".join(unknown))
            return 2
        ids = list(args.pages)
    else:
        ids = all_ids
    todo = [p for p in ids if args.force or args.dry_run or needs_scan(root, p)]
    skipped = len(ids) - len(todo)
    cleared = cleared_by_review(root)
    t0 = time.time()
    results = pool_map(_scan_worker, [(root, p, cleared, not args.dry_run) for p in todo], args.workers)
    if not args.dry_run:
        for r in results:
            if r["status"] == "written":
                append_line(os.path.join(root, "logs", "pipeline.ndjson"),
                            {"ts": now_iso(), "actor": ACTOR, "page_id": r["page_id"],
                             "artifact": "quality", "status": "written",
                             "grade": r["quality"]["grade"],
                             "orientation": r["quality"]["orientation"]["status"]})
    ok = [r for r in results if r["status"] in ("written", "computed")]
    grades = {"good": 0, "fair": 0, "poor": 0}
    orient = {"ok": 0, "suspected": 0, "fixed": 0, "unknown": 0}
    warn_counts = {}
    for r in ok:
        q = r["quality"]
        grades[q["grade"]] += 1
        orient[q["orientation"]["status"]] += 1
        for w in q["warnings"]:
            warn_counts[w] = warn_counts.get(w, 0) + 1
    errors = [r for r in results if r["status"] == "error"]
    locked = [r["page_id"] for r in results if r["status"] == "locked"]
    suspected = [{"page_id": r["page_id"], "suggested": r["quality"]["orientation"]["suggested"],
                  "sources": r["quality"]["orientation"]["sources"]}
                 for r in ok if r["quality"]["orientation"]["status"] == "suspected"]
    poor = [{"page_id": r["page_id"], "warnings": r["quality"]["warnings"]}
            for r in ok if r["quality"]["grade"] == "poor"]
    summary = {
        "facility": root, "dry_run": bool(args.dry_run), "pages_considered": len(ids),
        "scanned": len(ok), "skipped_fresh": skipped, "locked": locked, "errors": errors,
        "grades": grades, "orientation": orient, "warnings": warn_counts,
        "suspected": suspected, "poor": poor, "seconds": round(time.time() - t0, 1),
    }
    if args.dry_run and args.json:
        summary["results"] = [dict(page_id=r["page_id"], **r["quality"]) for r in ok]
    lines = ["notella-images scan (%s)%s: %d scanned, %d fresh (skipped), %d errors, %d locked in %.1fs"
             % (root, " [dry-run]" if args.dry_run else "", len(ok), skipped, len(errors), len(locked),
                summary["seconds"]),
             "  grade: good %(good)d · fair %(fair)d · poor %(poor)d" % grades,
             "  orientation: ok %(ok)d · suspected %(suspected)d · fixed %(fixed)d · unknown %(unknown)d" % orient]
    if warn_counts:
        lines.append("  warnings: " + " · ".join("%s %d" % kv for kv in sorted(warn_counts.items())))
    for s in suspected[:25]:
        sug = s["suggested"]
        lines.append("  ? %s  %s  (%s)" % (s["page_id"],
                     ("rotate %d flip %s" % (sug["rotate"], sug["flip"])) if sug else "needs a look",
                     ", ".join(s["sources"])))
    if len(suspected) > 25:
        lines.append("  ... and %d more suspected" % (len(suspected) - 25))
    for e in errors[:10]:
        lines.append("  ! %s: %s" % (e["page_id"], e["error"]))
    emit(args, summary, lines)
    return 1 if errors else 0


# --------------------------------------------------------------------------
# subcommand: fix
# --------------------------------------------------------------------------

def render_derived(raw, rotate, flip, thumb_max, tmpdir):
    """raw -> (page.jpg tmp path, thumb.jpg tmp path). EXIF applied by the decode."""
    bmp = os.path.join(tmpdir, "full.bmp")
    run_sips(["-s", "format", "bmp", raw, "--out", bmp])
    if rotate:
        run_sips(["-r", str(rotate), bmp])
    if flip != "none":
        run_sips(["-f", flip, bmp])
    page = os.path.join(tmpdir, "page.jpg")
    run_sips(["-s", "format", "jpeg", "-s", "formatOptions", str(JPEG_QUALITY), bmp, "--out", page])
    thumb = os.path.join(tmpdir, "thumb.jpg")
    run_sips(["-s", "format", "jpeg", "-s", "formatOptions", "85", "-Z", str(thumb_max), page, "--out", thumb])
    return page, thumb


def thumb_max_dim(root):
    text = read_text(os.path.join(root, "manifest.yaml")) or ""
    m = re.search(r"^\s*thumbnail_max_dim_px:\s*(\d+)", text, re.M)
    return int(m.group(1)) if m else DEFAULT_THUMB


def fix_page(root, pid, rotate, flip, reset, dry_run):
    """Apply one absolute transform. Returns (exit_code, result_dict, human_lines)."""
    pdir = page_dir(root, pid)
    meta_path = os.path.join(pdir, "meta.yaml")
    if not os.path.isfile(meta_path):
        return 2, {"page_id": pid, "status": "error", "error": "no such page"}, ["no such page: %s" % pid]
    raw = raw_path(root, pid)
    if raw is None:
        return 2, {"page_id": pid, "status": "error", "error": "no raw image"}, \
            ["page %s has no raw/ image; cannot rebuild" % pid]
    if reset:
        rotate, flip = 0, "none"
    meta_text = read_text(meta_path)
    prev_fix = parse_orientation_fix(meta_text)
    previous = {"rotate": prev_fix["rotate"], "flip": prev_fix["flip"]} if prev_fix else None
    transcribed = os.path.exists(os.path.join(pdir, "transcribe.json"))
    plan = {"page_id": pid, "rotate": rotate, "flip": flip, "reset": bool(reset),
            "previous": previous, "raw": raw, "dry_run": bool(dry_run), "transcribed": transcribed}
    if dry_run:
        return 0, dict(plan, status="planned"), [
            "[dry-run] %s: rebuild derived/page.jpg + thumb.jpg from %s with EXIF applied, rotate %d, flip %s; "
            "%s orientation_fix%s" % (pid, os.path.relpath(raw, root), rotate, flip,
                                      "remove" if reset else "record", " (transcribed: reprocess needed)" if transcribed else "")]
    lock = Lock(root, pid)
    if not lock.acquire():
        return 3, {"page_id": pid, "status": "locked"}, ["page %s is locked by another actor; try again later" % pid]
    tmpdir = tempfile.mkdtemp(prefix="nl-fix-")
    try:
        page_tmp, thumb_tmp = render_derived(raw, rotate, flip, thumb_max_dim(root), tmpdir)
        atomic_install(page_tmp, os.path.join(pdir, "derived", "page.jpg"))
        atomic_install(thumb_tmp, os.path.join(pdir, "derived", "thumb.jpg"))
        if reset:
            new_text = remove_meta_block(meta_text, "orientation_fix")
        else:
            block = ("orientation_fix:\n  rotate: %d\n  flip: %s\n  applied_at: %s\n  by: %s\n"
                     % (rotate, flip, now_iso(), ACTOR))
            new_text = set_meta_block(meta_text, "orientation_fix", block)
        if new_text != meta_text:
            atomic_write_bytes(meta_path, new_text.encode("utf-8"))
        q = compute_quality(root, pid, cleared_by_review(root), tmpdir)
        atomic_write_json(os.path.join(pdir, "quality.json"), q)
        append_line(os.path.join(root, "logs", "pipeline.ndjson"),
                    {"ts": now_iso(), "actor": ACTOR, "page_id": pid,
                     "action": "orientation-reset" if reset else "orientation-fix",
                     "status": "ok", "rotate": rotate, "flip": flip, "previous": previous})
        evidence = {"correction_type": "orientation-fix", "rotate": rotate, "flip": flip,
                    "previous": previous, "reset": bool(reset)}
        ev = write_event(root, "correction", pid, evidence,
                         lambda date: "%s|%d|%s|%s" % (pid, rotate, flip, date))
    finally:
        lock.release()
        shutil.rmtree(tmpdir, ignore_errors=True)
    follow = []
    if transcribed:
        follow = ["notella-classify %s --reprocess (route plan + orientation on the corrected image)" % pid,
                  "notella-transcribe %s --reprocess" % pid,
                  "then the L1 fan-out (composition, diagram/sketch/table as routed, metadata) with --reprocess",
                  "notella-first-pass %s --reprocess" % pid,
                  "notella-actions %s --reprocess (if it had actions.json)" % pid,
                  "re-synthesize the page's daily brief (notella-daily-synthesis <date> --reprocess)"]
    elif os.path.exists(os.path.join(pdir, "classify.json")):
        follow = ["notella-classify %s --reprocess (classified on the old image)" % pid]
    out = dict(plan, status="reset" if reset else "fixed", event=ev,
               quality={"grade": q["grade"], "orientation": q["orientation"]}, follow_up=follow)
    lines = ["%s %s: derived/page.jpg + thumb.jpg rebuilt from raw (rotate %d, flip %s); event %s (%s)"
             % ("Reset" if reset else "Fixed", pid, rotate, flip, ev["id"], ev["status"])]
    return 0, out, lines


def cmd_fix(args):
    root = facility_root(args.root)
    require_facility(root)
    if args.all_suggested:
        if args.page or args.rotate is not None or args.flip is not None or args.reset:
            sys.stderr.write("--all-suggested takes no --page/--rotate/--flip/--reset\n")
            return 2
        targets = []
        for pid in list_page_ids(root):
            q = read_json(os.path.join(page_dir(root, pid), "quality.json"), None)
            o = (q or {}).get("orientation") or {}
            if o.get("status") != "suspected" or not o.get("suggested"):
                continue
            if args.source and args.source not in (o.get("sources") or []):
                continue
            targets.append((pid, int(o["suggested"]["rotate"]), o["suggested"]["flip"]))
        results = []
        lines = []
        worst = 0
        for pid, rot, fl in targets:
            rc, out, ls = fix_page(root, pid, rot, fl, False, args.dry_run)
            worst = max(worst, rc)
            results.append(out)
            lines += ls
        transcribed = [r["page_id"] for r in results if r.get("transcribed")]
        lines.append("%s %d page(s) with a concrete suggestion%s." % (
            "[dry-run] would fix" if args.dry_run else "Fixed", len(targets),
            (" (source %s)" % args.source) if args.source else ""))
        if transcribed:
            lines.append("%d of them were already transcribed: run the reprocess chain for each "
                         "(notella-images skill, 'After a fix'); this script calls no models." % len(transcribed))
        emit(args, {"dry_run": bool(args.dry_run), "count": len(targets), "results": results,
                    "transcribed": transcribed}, lines)
        return worst
    if not args.page:
        sys.stderr.write("fix needs --page ID (or --all-suggested)\n")
        return 2
    if not args.reset and args.rotate is None and args.flip is None:
        sys.stderr.write("fix needs --rotate and/or --flip, or --reset\n")
        return 2
    rc, out, lines = fix_page(root, args.page, int(args.rotate or 0), args.flip or "none", args.reset, args.dry_run)
    if rc != 0 and not args.json:
        sys.stderr.write(lines[0] + "\n")
        return rc
    if out.get("follow_up"):
        lines.append("Follow-up (this script calls no models):")
        lines += ["  - " + f for f in out["follow_up"]]
    emit(args, out, lines)
    return rc


# --------------------------------------------------------------------------
# subcommand: mark-duplicate
# --------------------------------------------------------------------------

def cmd_mark_duplicate(args):
    root = facility_root(args.root)
    require_facility(root)
    dup, orig = args.page, args.of
    if dup == orig:
        sys.stderr.write("a page cannot be a duplicate of itself\n")
        return 2
    for p in (dup, orig):
        if not os.path.isfile(os.path.join(page_dir(root, p), "meta.yaml")):
            sys.stderr.write("no such page: %s\n" % p)
            return 2
    meta_path = os.path.join(page_dir(root, dup), "meta.yaml")
    text = read_text(meta_path)
    orig_dup = meta_field(read_text(os.path.join(page_dir(root, orig), "meta.yaml")), "duplicate_of")
    if orig_dup:
        sys.stderr.write("%s is itself a duplicate of %s; mark against %s instead\n" % (orig, orig_dup, orig_dup))
        return 2
    idx = {}
    tmpdir = tempfile.mkdtemp(prefix="nl-dup-")
    try:
        for p in (dup, orig):
            q = read_json(os.path.join(page_dir(root, p), "quality.json"), None)
            if isinstance(q, dict) and q.get("sha256_raw") and q.get("dhash"):
                idx[p] = (q["sha256_raw"], q["dhash"])
            else:
                rp = raw_path(root, p)
                idx[p] = (sha256_file(rp), analyze_image(rp, tmpdir)["dhash"]) if rp else (None, None)
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)
    exact = idx[dup][0] is not None and idx[dup][0] == idx[orig][0]
    dist = hamming(idx[dup][1], idx[orig][1])
    if not exact and (dist is None or dist > 12) and not args.force:
        sys.stderr.write("%s and %s do not look alike (dhash distance %s); pass --force if you are sure\n"
                         % (dup, orig, dist))
        return 2
    current = meta_field(text, "duplicate_of")
    note = args.note or ("duplicate raw image of %s (%s, dhash distance %s); excluded from synthesis"
                         % (orig, "identical bytes" if exact else "near-identical image", dist))
    plan = {"page_id": dup, "duplicate_of": orig, "exact": exact, "distance": dist,
            "previous_duplicate_of": current, "note": note, "dry_run": bool(args.dry_run)}
    if args.dry_run:
        emit(args, plan, ["[dry-run] would set %s duplicate_of: %s (%s, distance %s)"
                          % (dup, orig, "exact" if exact else "near", dist)])
        return 0
    lock = Lock(root, dup)
    if not lock.acquire():
        sys.stderr.write("page %s is locked by another actor\n" % dup)
        return 3
    try:
        new = text
        if current != orig:
            new = add_meta_error(new, note)
            new = set_meta_scalar(new, "duplicate_of", orig)
        if new != text:
            atomic_write_bytes(meta_path, new.encode("utf-8"))
        ev = write_event(root, "correction", dup,
                         {"correction_type": "duplicate-raw-image", "duplicate_of": orig,
                          "previous_duplicate_of": current, "exact": exact, "distance": dist,
                          "note": note},
                         lambda date: "%s|%s|%s" % (dup, orig, date))
        append_line(os.path.join(root, "logs", "pipeline.ndjson"),
                    {"ts": now_iso(), "actor": ACTOR, "page_id": dup, "action": "mark-duplicate",
                     "status": "ok" if new != text else "unchanged", "duplicate_of": orig})
    finally:
        lock.release()
    out = dict(plan, status="marked" if new != text else "unchanged", event=ev)
    emit(args, out, ["%s duplicate_of: %s (%s); event %s (%s). Phase unchanged; syntheses skip duplicate_of pages "
                     "on their next run — re-synthesize the affected daily if it already counted this page."
                     % (dup, orig, "marked" if new != text else "already marked", ev["id"], ev["status"])])
    return 0


# --------------------------------------------------------------------------
# subcommand: audit
# --------------------------------------------------------------------------

def walk_sources(sources, recursive):
    found = []
    skipped = []
    for src in sources:
        src = os.path.abspath(os.path.expanduser(src))
        if not os.path.isdir(src):
            skipped.append({"path": src, "status": "skipped", "reason": "not-a-directory"})
            continue
        if recursive:
            walker = os.walk(src)
        else:
            walker = [(src, [], sorted(os.listdir(src)))]
        for d, dirs, files in walker:
            dirs[:] = sorted(x for x in dirs if not x.startswith("."))
            for name in sorted(files):
                p = os.path.join(d, name)
                if name.startswith(".") or not os.path.isfile(p):
                    continue
                ext = os.path.splitext(name)[1].lower()
                if ext in IMAGE_EXTS:
                    found.append(p)
                else:
                    skipped.append({"path": p, "status": "skipped",
                                    "reason": "pdf-not-supported" if ext == ".pdf" else "unsupported-type",
                                    "size_bytes": os.path.getsize(p)})
    return found, skipped


def classify_files(hashed, idx, near, within_label):
    seen = {}
    out = []
    for h in hashed:
        if "error" in h:
            out.append({"path": h["path"], "status": "error", "error": h["error"]})
            continue
        status, pid, dist, tf = match_against(idx, h["sha256"], h["dhash"], h.get("dhash_variants"), near)
        row = {"path": h["path"], "size_bytes": h["size_bytes"], "sha256": h["sha256"], "dhash": h["dhash"],
               "status": status, "page_id": pid, "distance": dist if status != "new" else None,
               "nearest_distance": dist, "quality_grade": h["quality"]["grade"],
               "quality_warnings": h["quality"]["warnings"], "exif_orientation": h["exif_orientation"]}
        if tf:
            row["match_transform"] = tf
        if status != "in_facility_exact" and h["sha256"] in seen:
            row["status"] = within_label
            row["same_as"] = seen[h["sha256"]]
        seen.setdefault(h["sha256"], h["path"])
        out.append(row)
    return out


def cmd_audit(args):
    root = facility_root(args.root)
    require_facility(root)
    t0 = time.time()
    files, skipped = walk_sources(args.source, args.recursive)
    idx = facility_index(root, args.workers)
    hashed = pool_map(_hash_worker, [(p, True) for p in files], args.workers)
    rows = classify_files(hashed, idx, args.near, "duplicate_within_source")
    rows += skipped
    exact, nearl = facility_duplicates(idx, args.near)
    counts = {}
    for r in rows:
        counts[r["status"]] = counts.get(r["status"], 0) + 1
    report = {
        "schema_version": SCHEMA_VERSION, "generated_at": now_iso(), "generator": HARVESTER,
        "facility": root, "sources": [os.path.abspath(os.path.expanduser(s)) for s in args.source],
        "recursive": bool(args.recursive), "near_threshold": args.near,
        "summary": {"files": len(rows), "counts": counts, "facility_pages": len(idx),
                    "facility_pages_hashed_on_the_fly": sum(1 for v in idx.values() if v.get("from") == "computed"),
                    "facility_exact_pairs": len(exact), "facility_near_pairs": len(nearl),
                    "facility_pairs_unmarked": sum(1 for x in exact + nearl if not x["marked"]),
                    "seconds": round(time.time() - t0, 1)},
        "files": rows,
        "facility_duplicates": {"exact": [[x["a"], x["b"]] for x in exact],
                                "exact_detail": exact, "near": nearl},
    }
    out_path = os.path.join(root, "logs", "inventory-audit.json")
    atomic_write_json(out_path, report)
    lines = ["Inventory audit — %d files in %d source folder(s) vs %d facility pages (%.1fs)"
             % (len(rows), len(args.source), len(idx), report["summary"]["seconds"])]
    for k in ("new", "in_facility_exact", "near_duplicate", "duplicate_within_source", "skipped", "error"):
        if counts.get(k):
            lines.append("  %-24s %d" % (k, counts[k]))
    for r in rows:
        if r["status"] == "near_duplicate":
            lines.append("  ~ %s ≈ %s (distance %s%s)" % (os.path.basename(r["path"]), r["page_id"], r["distance"],
                         ", " + r["match_transform"] if r.get("match_transform") else ""))
    lines.append("Facility-internal: %d exact pair(s), %d near pair(s); %d not marked duplicate_of"
                 % (len(exact), len(nearl), report["summary"]["facility_pairs_unmarked"]))
    for x in exact + nearl:
        if not x["marked"]:
            lines.append("  unmarked: %s ~ %s%s" % (x["a"], x["b"],
                         " (distance %d)" % x["distance"] if "distance" in x else " (identical bytes)"))
    lines.append("Report: %s" % out_path)
    if counts.get("new") or counts.get("near_duplicate"):
        lines.append("Next: notella_images.py stage --from-audit [--include near] [--min-grade fair] --dry-run")
    emit(args, report, lines)
    return 0


# --------------------------------------------------------------------------
# subcommands: inbox-check, stage, hold, release
# --------------------------------------------------------------------------

def inbox_files(root):
    d = os.path.join(root, "inbox")
    if not os.path.isdir(d):
        return []
    return sorted(os.path.join(d, n) for n in os.listdir(d)
                  if not n.startswith(".") and os.path.isfile(os.path.join(d, n))
                  and os.path.splitext(n)[1].lower() in IMAGE_EXTS)


def run_inbox_check(root, near, workers, write=True):
    files = inbox_files(root)
    idx = facility_index(root, workers) if files else {}
    hashed = pool_map(_hash_worker, [(p, True) for p in files], workers)
    rows = classify_files(hashed, idx, near, "duplicate_within_inbox")
    out = []
    for r, h in zip(rows, hashed):
        if r["status"] == "error":
            out.append({"name": os.path.basename(r["path"]), "status": "error", "error": r["error"]})
            continue
        item = {"name": os.path.basename(r["path"]), "sha256": r["sha256"], "dhash": r["dhash"],
                "status": r["status"], "page_id": r["page_id"], "distance": r["distance"],
                "quality": h["quality"], "exif_orientation": h["exif_orientation"],
                "size_bytes": r["size_bytes"]}
        if r.get("match_transform"):
            item["match_transform"] = r["match_transform"]
        if r.get("same_as"):
            item["same_as"] = os.path.basename(r["same_as"])
        out.append(item)
    report = {"schema_version": SCHEMA_VERSION, "generated_at": now_iso(), "generator": HARVESTER,
              "near_threshold": near, "files": out}
    if write:
        atomic_write_json(os.path.join(root, "logs", "inbox-check.json"), report)
    return report


def cmd_inbox_check(args):
    root = facility_root(args.root)
    require_facility(root)
    rep = run_inbox_check(root, args.near, args.workers)
    lines = ["Inbox check — %d file(s)" % len(rep["files"])]
    for f in rep["files"]:
        q = f.get("quality") or {}
        lines.append("  %-28s %-22s %s%s  grade %s%s%s" % (
            f["name"], f["status"], f.get("page_id") or "",
            (" d=%s" % f["distance"]) if f.get("distance") else "",
            q.get("grade", "?"), (" [" + ", ".join(q.get("warnings", [])) + "]") if q.get("warnings") else "",
            (" exif=%s" % f["exif_orientation"]) if f.get("exif_orientation") not in (None, 1) else ""))
    held = sum(1 for f in rep["files"] if f["status"] in ("in_facility_exact", "near_duplicate"))
    if held:
        lines.append("%d file(s) duplicate the facility — run `notella_images.py hold` before intake." % held)
    lines.append("Report: %s" % os.path.join(root, "logs", "inbox-check.json"))
    emit(args, rep, lines)
    return 0


def released_shas(root):
    latest = {}
    for row in read_ndjson(os.path.join(root, "longitudinal", "imports.ndjson")):
        if row.get("sha256") and row.get("decision") in ("released", "held_exact", "held_near"):
            latest[row["sha256"]] = row["decision"]
    return set(k for k, v in latest.items() if v == "released")


def cmd_hold(args):
    root = facility_root(args.root)
    require_facility(root)
    rep = run_inbox_check(root, args.near, args.workers, write=not args.dry_run)
    released = released_shas(root)
    held_dir = os.path.join(root, "inbox", "_held")
    moved = []
    kept = []
    for f in rep["files"]:
        if f["status"] not in ("in_facility_exact", "near_duplicate"):
            continue
        if f["sha256"] in released:
            kept.append({"name": f["name"], "reason": "released earlier"})
            continue
        decision = "held_exact" if f["status"] == "in_facility_exact" else "held_near"
        if args.dry_run:
            moved.append({"name": f["name"], "decision": decision, "page_id": f["page_id"],
                          "distance": f["distance"]})
            continue
        os.makedirs(held_dir, exist_ok=True)
        dest_name = unique_name(held_dir, f["name"])
        os.replace(os.path.join(root, "inbox", f["name"]), os.path.join(held_dir, dest_name))
        note = {"held_at": now_iso(), "by": HARVESTER, "decision": decision, "original_name": f["name"],
                "matched_page": f["page_id"], "distance": f["distance"], "sha256": f["sha256"],
                "dhash": f["dhash"], "quality_grade": (f.get("quality") or {}).get("grade"),
                "match_transform": f.get("match_transform")}
        atomic_write_json(os.path.join(held_dir, dest_name + ".held.json"), note)
        append_line(os.path.join(root, "longitudinal", "imports.ndjson"),
                    {"ts": now_iso(), "source_path": os.path.join(root, "inbox", f["name"]),
                     "sha256": f["sha256"], "dhash": f["dhash"], "decision": decision,
                     "matched_page": f["page_id"], "distance": f["distance"],
                     "quality_grade": (f.get("quality") or {}).get("grade"),
                     "inbox_name": f["name"], "held_name": dest_name})
        moved.append({"name": f["name"], "held_name": dest_name, "decision": decision,
                      "page_id": f["page_id"], "distance": f["distance"]})
    out = {"dry_run": bool(args.dry_run), "held": moved, "kept_released": kept}
    lines = ["%s %d inbox file(s) into inbox/_held/" % ("[dry-run] would hold" if args.dry_run else "Held", len(moved))]
    for m in moved:
        lines.append("  %s → %s (%s%s)" % (m["name"], m["page_id"], m["decision"],
                                          ", distance %s" % m["distance"] if m["decision"] == "held_near" else ""))
    for k in kept:
        lines.append("  %s left in inbox (%s)" % (k["name"], k["reason"]))
    emit(args, out, lines)
    return 0


def cmd_release(args):
    root = facility_root(args.root)
    require_facility(root)
    held_dir = os.path.join(root, "inbox", "_held")
    src = os.path.join(held_dir, args.name)
    if os.path.basename(args.name) != args.name or not os.path.isfile(src) or args.name.endswith(".held.json"):
        sys.stderr.write("no held file named %s in %s\n" % (args.name, held_dir))
        return 2
    note = read_json(src + ".held.json", {}) or {}
    target = unique_name(os.path.join(root, "inbox"), note.get("original_name") or args.name)
    sha = note.get("sha256") or sha256_file(src)
    if args.dry_run:
        emit(args, {"dry_run": True, "name": args.name, "inbox_name": target},
             ["[dry-run] would release %s → inbox/%s" % (args.name, target)])
        return 0
    os.replace(src, os.path.join(root, "inbox", target))
    if os.path.exists(src + ".held.json"):
        os.unlink(src + ".held.json")       # our own sidecar note, not user data
    append_line(os.path.join(root, "longitudinal", "imports.ndjson"),
                {"ts": now_iso(), "source_path": src, "sha256": sha, "dhash": note.get("dhash"),
                 "decision": "released", "matched_page": note.get("matched_page"),
                 "distance": note.get("distance"), "quality_grade": note.get("quality_grade"),
                 "inbox_name": target, "note": args.note})
    emit(args, {"released": args.name, "inbox_name": target},
         ["Released %s → inbox/%s; intake will mint it (hold will not re-hold this file)." % (args.name, target)])
    return 0


def cmd_stage(args):
    root = facility_root(args.root)
    require_facility(root)
    if not args.from_audit:
        sys.stderr.write("stage currently supports only --from-audit\n")
        return 2
    audit = read_json(os.path.join(root, "logs", "inventory-audit.json"), None)
    if not audit:
        sys.stderr.write("no logs/inventory-audit.json — run `audit --source DIR` first\n")
        return 2
    include = set(args.include or ["new"])
    min_grade = GRADE_ORDER[args.min_grade]
    inbox = os.path.join(root, "inbox")
    present = {}
    for p in inbox_files(root) + [os.path.join(inbox, "_held", n) for n in
                                  (os.listdir(os.path.join(inbox, "_held")) if os.path.isdir(os.path.join(inbox, "_held")) else [])
                                  if os.path.splitext(n)[1].lower() in IMAGE_EXTS]:
        try:
            present[sha256_file(p)] = os.path.basename(p)
        except OSError:
            pass
    decisions = []
    for f in audit.get("files", []):
        st = f.get("status")
        if st in ("skipped", "error"):
            continue
        dec = None
        if st == "in_facility_exact":
            dec = "skipped_exact"
        elif st == "duplicate_within_source":
            dec = "skipped_within_source"
        elif st == "near_duplicate" and "near" not in include:
            dec = "skipped_near"
        elif st == "new" and "new" not in include:
            continue                      # not asked for: not considered, not logged
        if dec is None and GRADE_ORDER.get(f.get("quality_grade") or "good", 2) < min_grade:
            dec = "skipped_quality"
        if dec is None and f["sha256"] in present:
            dec = "skipped_exact"
            f = dict(f, page_id=None, already_in_inbox=present[f["sha256"]])
        row = {"ts": now_iso(), "source_path": f["path"], "sha256": f["sha256"], "dhash": f.get("dhash"),
               "decision": dec or "staged", "matched_page": f.get("page_id"), "distance": f.get("distance"),
               "quality_grade": f.get("quality_grade"), "inbox_name": f.get("already_in_inbox")}
        if dec is None:
            if not os.path.isfile(f["path"]):
                row["decision"] = "skipped_missing"
            elif not args.dry_run:
                if sha256_file(f["path"]) != f["sha256"]:
                    row["decision"] = "skipped_changed"
                else:
                    name = unique_name(inbox, os.path.basename(f["path"]))
                    os.makedirs(inbox, exist_ok=True)
                    tmp = os.path.join(inbox, "." + name + ".partial")
                    shutil.copy2(f["path"], tmp)
                    os.replace(tmp, os.path.join(inbox, name))
                    row["inbox_name"] = name
                    present[f["sha256"]] = name
            else:
                row["inbox_name"] = os.path.basename(f["path"])
        if not args.dry_run:
            append_line(os.path.join(root, "longitudinal", "imports.ndjson"), row)
        decisions.append(row)
    counts = {}
    for d in decisions:
        counts[d["decision"]] = counts.get(d["decision"], 0) + 1
    out = {"dry_run": bool(args.dry_run), "include": sorted(include), "min_grade": args.min_grade,
           "counts": counts, "decisions": decisions}
    lines = ["%s from %s (include: %s; min grade: %s)" % ("[dry-run] stage plan" if args.dry_run else "Staged",
             os.path.join(root, "logs", "inventory-audit.json"), ", ".join(sorted(include)), args.min_grade)]
    for k, v in sorted(counts.items()):
        lines.append("  %-22s %d" % (k, v))
    if not args.dry_run and counts.get("staged"):
        lines.append("Copied %d file(s) into inbox/ (sources untouched). Next: notella-orchestrator or notella-intake."
                     % counts["staged"])
    emit(args, out, lines)
    return 0


# --------------------------------------------------------------------------
# selftest
# --------------------------------------------------------------------------

def _write_bmp(path, w, h, pixel, bpp=24, top_down=False):
    step = bpp // 8
    row_size = ((bpp * w + 31) // 32) * 4
    rows = []
    for y in range(h):
        line = bytearray()
        for x in range(w):
            r, g, b = pixel(x, y)
            line += bytes([b, g, r]) + (b"\xff" if bpp == 32 else b"")
        line += b"\x00" * (row_size - len(line))
        rows.append(bytes(line))
    if not top_down:
        rows = rows[::-1]
    pixels = b"".join(rows)
    dib = struct.pack("<IiiHHIIiiII", 40, w, -h if top_down else h, 1, bpp, 0, len(pixels), 2835, 2835, 0, 0)
    head = b"BM" + struct.pack("<IHHI", 14 + len(dib) + len(pixels), 0, 0, 14 + len(dib))
    with open(path, "wb") as fh:
        fh.write(head + dib + pixels)
    return step


def _inject_exif_orientation(src, dst, value):
    d = open(src, "rb").read()
    tiff = b"MM" + struct.pack(">HI", 42, 8) + struct.pack(">H", 1) + \
        struct.pack(">HHIHH", 0x0112, 3, 1, value, 0) + struct.pack(">I", 0)
    app1 = b"Exif\x00\x00" + tiff
    seg = b"\xff\xe1" + struct.pack(">H", len(app1) + 2) + app1
    with open(dst, "wb") as fh:
        fh.write(d[:2] + seg + d[2:])


def cmd_selftest(args):
    work = tempfile.mkdtemp(prefix="nl-images-selftest-", dir=args.workdir)
    passed = []
    failed = []

    quiet = bool(args.json)

    def say(line):
        if not quiet:
            print(line)

    def check(name, cond, detail=""):
        (passed if cond else failed).append(name + ((" — " + str(detail)) if detail and not cond else ""))
        d = str(detail) if detail != "" else ""
        if cond and (len(d) > 70 or "\n" in d):
            d = ""          # keep passing lines short; full detail only on failure
        say(("  ok   " if cond else "  FAIL ") + name + ((" (" + d + ")") if d else ""))

    me = os.path.abspath(__file__)

    def cli(*a):
        p = subprocess.run([sys.executable, me] + list(a) + ["--json"], stdout=subprocess.PIPE,
                           stderr=subprocess.PIPE)
        try:
            return p.returncode, json.loads(p.stdout.decode() or "null"), p.stderr.decode()
        except ValueError:
            return p.returncode, None, p.stdout.decode() + p.stderr.decode()

    say("selftest workdir: %s" % work)
    # 1. BMP parser on hand-made files (padding, both row orders, 24/32 bit)
    pat = lambda x, y: ((x * 40) % 256, (y * 60) % 256, (x * y * 7) % 256)  # noqa: E731
    for bpp in (24, 32):
        for td in (False, True):
            p = os.path.join(work, "t%d%s.bmp" % (bpp, "td" if td else "bu"))
            _write_bmp(p, 5, 3, pat, bpp=bpp, top_down=td)
            w, h, rows = parse_bmp(open(p, "rb").read())
            ok = (w, h) == (5, 3) and all(
                (rows[y][0][x], rows[y][1][x], rows[y][2][x]) == pat(x, y) for y in range(3) for x in range(5))
            check("parse_bmp %d-bit %s (5px rows need padding)" % (bpp, "top-down" if td else "bottom-up"), ok)
    # sips-written BMP round trip
    p = os.path.join(work, "pat.bmp")
    _write_bmp(p, 37, 23, lambda x, y: (200 if x < 18 else 30, 120, 60 if y < 11 else 220))
    run_sips(["-s", "format", "bmp", p, "--out", os.path.join(work, "pat_sips.bmp")])
    w, h, rows = parse_bmp(open(os.path.join(work, "pat_sips.bmp"), "rb").read())
    check("parse_bmp reads sips output", (w, h) == (37, 23) and rows[0][0][0] == 200 and rows[22][2][36] == 220,
          "%dx%d" % (w, h))

    # 2. fixture images
    img = args.image
    if img is None:
        froot = facility_root(args.root)
        ids = list_page_ids(froot) if os.path.isdir(os.path.join(froot, "pages")) else []
        cands = [raw_path(froot, i) for i in ids]
        cands = [c for c in cands if c and c.lower().endswith((".jpg", ".jpeg"))]
        img = cands[0] if cands else None
        img2 = cands[len(cands) // 2] if len(cands) > 2 else None
    else:
        img2 = args.image2
    fx = os.path.join(work, "fixture")
    os.makedirs(fx)
    base = os.path.join(fx, "base.jpg")
    other = os.path.join(fx, "other.jpg")
    if img:
        run_sips(["-s", "format", "jpeg", "-s", "formatOptions", "90", "-Z", "1600", img, "--out", base])
        say("  fixture copied from %s" % img)
    else:
        bmp = os.path.join(fx, "syn.bmp")
        _write_bmp(bmp, 400, 300, lambda x, y: (250, 250, 250) if (x // 20 + y // 7) % 3 else (20, 20, 90))
        run_sips(["-s", "format", "jpeg", bmp, "--out", base])
        say("  no facility image found: synthetic fixture")
    if img2:
        run_sips(["-s", "format", "jpeg", "-s", "formatOptions", "90", "-Z", "1600", img2, "--out", other])
    else:
        bmp = os.path.join(fx, "syn2.bmp")
        _write_bmp(bmp, 400, 300, lambda x, y: (250, 250, 250) if (x // 9 * y // 13) % 4 else (90, 20, 20))
        run_sips(["-s", "format", "jpeg", bmp, "--out", other])
    rot = os.path.join(fx, "rot180.jpg")
    shutil.copyfile(base, rot)
    run_sips(["-r", "180", rot])
    mir = os.path.join(fx, "mirror.jpg")
    shutil.copyfile(base, mir)
    run_sips(["-f", "horizontal", mir])
    reenc = os.path.join(fx, "reencoded.jpg")
    run_sips(["-s", "format", "jpeg", "-s", "formatOptions", "55", "-Z", "900", base, "--out", reenc])
    exif6 = os.path.join(fx, "exif6.jpg")
    _inject_exif_orientation(base, exif6, 6)

    # 3. dhash behaviour
    t = os.path.join(work, "tmp")
    os.makedirs(t)
    A = analyze_image(base, t, want_variants=True, want_stamp=True)
    B = analyze_image(reenc, t)
    C = analyze_image(other, t)
    R = analyze_image(rot, t)
    M = analyze_image(mir, t)
    E = analyze_image(exif6, t)
    d_re = hamming(A["dhash"], B["dhash"])
    d_other = hamming(A["dhash"], C["dhash"])
    check("re-encoded copy is a near duplicate (distance <= %d)" % DEFAULT_NEAR, d_re <= DEFAULT_NEAR, d_re)
    check("a different page is far (distance > 12)", d_other > 12, d_other)
    check("rotated copy differs as stored (distance > 12)", hamming(A["dhash"], R["dhash"]) > 12,
          hamming(A["dhash"], R["dhash"]))
    check("rotated copy matches the rot180 variant", hamming(A["dhash_variants"]["rot180"], R["dhash"]) <= DEFAULT_NEAR,
          hamming(A["dhash_variants"]["rot180"], R["dhash"]))
    check("mirrored copy matches the flip-h variant", hamming(A["dhash_variants"]["flip-h"], M["dhash"]) <= DEFAULT_NEAR,
          hamming(A["dhash_variants"]["flip-h"], M["dhash"]))
    check("EXIF orientation 6 parsed from JPEG header", E["exif_orientation"] == 6, E["exif_orientation"])
    check("EXIF-6 image decodes upright-as-intended (dims swapped)",
          (E["width"], E["height"]) == (A["height"], A["width"]), (E["width"], E["height"]))
    check("metrics are finite and in range", 0 <= A["brightness"] <= 255 and A["contrast"] >= 0
          and A["sharpness"] >= 0 and 0 <= A["dark_fraction"] <= 1, A)

    # 4. meta.yaml text editing
    meta0 = ('schema_version: "0.1.0"\nid: X\nphase: indexed\nerrors: []\nlinks_to: []\n')
    m1 = set_meta_block(meta0, "orientation_fix", "orientation_fix:\n  rotate: 180\n  flip: none\n")
    m2 = set_meta_block(m1, "orientation_fix", "orientation_fix:\n  rotate: 90\n  flip: horizontal\n")
    check("orientation_fix appended, rest byte-identical", m1.startswith(meta0) and parse_orientation_fix(m1)["rotate"] == 180)
    check("orientation_fix replaced in place", parse_orientation_fix(m2) == {"rotate": 90, "flip": "horizontal",
          "applied_at": None, "by": None} and m2.count("orientation_fix") == 1)
    check("orientation_fix removed restores original", remove_meta_block(m2, "orientation_fix") == meta0)
    mid = 'a: 1\norientation_fix:\n  rotate: 180\n  flip: none\nb: 2\n'
    check("block in the middle replaced without touching neighbours",
          set_meta_block(mid, "orientation_fix", "orientation_fix:\n  rotate: 0\n  flip: none\n")
          == 'a: 1\norientation_fix:\n  rotate: 0\n  flip: none\nb: 2\n')
    e1 = add_meta_error(meta0, 'dup of "Y"')
    check("errors: [] becomes a block list", 'errors:\n  - "dup of \\"Y\\""\nlinks_to' in e1, e1)
    e2 = add_meta_error(e1, "second")
    check("errors block list gets a new item", e2.count("  - ") == 2 and e2.endswith('links_to: []\n'), e2)
    check("same error note is not added twice", add_meta_error(e2, "second") == e2)

    # 5. scratch facility end-to-end through the CLI
    root = os.path.join(work, "facility")
    for d in ("inbox", "logs", "events", "longitudinal", "locks/pages"):
        os.makedirs(os.path.join(root, d))

    def mkpage(pid, src, classify=None, transcribe=None, extra_meta=""):
        pd = page_dir(root, pid)
        os.makedirs(os.path.join(pd, "raw"))
        os.makedirs(os.path.join(pd, "derived"))
        shutil.copyfile(src, os.path.join(pd, "raw", "page.jpg"))
        shutil.copyfile(src, os.path.join(pd, "derived", "page.jpg"))
        with open(os.path.join(pd, "meta.yaml"), "w") as fh:
            fh.write('schema_version: "0.1.0"\nid: %s\nphase: indexed\nerrors: []\n%s' % (pid, extra_meta))
        if classify is not None:
            with open(os.path.join(pd, "classify.json"), "w") as fh:
                json.dump({"doc_type": "handwritten_text", "orientation": classify}, fh)
        if transcribe is not None:
            with open(os.path.join(pd, "transcribe.json"), "w") as fh:
                json.dump({"transcriptConfidence": transcribe}, fh)

    mkpage("2026-01-01-aaaa", base, classify={"rotate": 0, "flip": "none", "confidence": 0.95}, transcribe=0.9)
    mkpage("2026-01-01-bbbb", rot, classify={"rotate": 180, "flip": "none", "confidence": 0.9,
                                             "evidence": "date stamp bottom-left, upside down"})
    mkpage("2026-01-01-cccc", mir, classify="mirrored")
    mkpage("2026-01-01-dddd", other, transcribe=0.3)
    mkpage("2026-01-01-eeee", exif6)
    mkpage("2026-01-01-ffff", base)       # exact duplicate of aaaa (unmarked)
    mkpage("2026-01-01-gggg", other)
    mkpage("2026-01-01-hhhh", rot)        # upside down, no classify opinion at all

    rc, js, err = cli("scan", "--root", root, "--workers", "4")
    check("scan exits 0", rc == 0 and js is not None, err)
    q = lambda pid: read_json(os.path.join(page_dir(root, pid), "quality.json"))  # noqa: E731
    qa, qb, qc, qd, qe = q("2026-01-01-aaaa"), q("2026-01-01-bbbb"), q("2026-01-01-cccc"), q("2026-01-01-dddd"), q("2026-01-01-eeee")
    keys = ["schema_version", "computed_at", "source", "width", "height", "megapixels", "exif_orientation",
            "brightness", "contrast", "sharpness", "dark_fraction", "bright_fraction", "sha256_raw", "dhash",
            "grade", "warnings", "orientation"]
    check("quality.json carries exactly the contract fields", qa is not None and sorted(qa) == sorted(keys),
          sorted(qa or {}))
    check("upright page: orientation ok", qa["orientation"]["status"] == "ok", qa["orientation"])
    check("upside-down page: suspected, rotate 180 from classify",
          qb["orientation"]["status"] == "suspected" and qb["orientation"]["suggested"] == {"rotate": 180, "flip": "none"}
          and "classify" in qb["orientation"]["sources"], qb["orientation"])
    check("legacy 'mirrored' string: suspected, flip horizontal",
          qc["orientation"]["suggested"] == {"rotate": 0, "flip": "horizontal"}, qc["orientation"])
    check("low transcript confidence: suspected with no suggestion",
          qd["orientation"]["status"] == "suspected" and qd["orientation"]["suggested"] is None
          and qd["orientation"]["sources"] == ["low-transcript-confidence"], qd["orientation"])
    check("EXIF-rotated raw copied without auto-orientation: suspected via exif + warning",
          qe["exif_orientation"] == 6 and "exif" in qe["orientation"]["sources"] and "exif-rotated" in qe["warnings"],
          qe)
    qh = q("2026-01-01-hhhh")
    if A.get("stamp") == "br":
        check("red stamp found bottom-right on the upright fixture", True)
        check("stamp alone flags the upside-down copy: rotate 180 via stamp-position",
              qh["orientation"]["status"] == "suspected" and qh["orientation"]["sources"] == ["stamp-position"]
              and qh["orientation"]["suggested"] == {"rotate": 180, "flip": "none"}, qh["orientation"])
    else:
        say("  skip stamp checks (fixture has no detectable red stamp: %s)" % A.get("stamp"))
    check("stamp_transform: tl landscape -> rotate 180", stamp_transform("tl", True) == {"rotate": 180, "flip": "none"})
    check("stamp_transform: bl portrait -> rotate 270", stamp_transform("bl", False) == {"rotate": 270, "flip": "none"})
    check("stamp_transform: tr portrait -> rotate 90", stamp_transform("tr", False) == {"rotate": 90, "flip": "none"})
    check("stamp_transform: bl landscape -> mirror", stamp_transform("bl", True) == {"rotate": 0, "flip": "horizontal"})
    check("stamp_transform: br landscape -> identity", stamp_transform("br", True) == {"rotate": 0, "flip": "none"})
    if A.get("stamp") == "br":
        rc, js, _ = cli("fix", "--root", root, "--all-suggested", "--source", "stamp-position", "--dry-run")
        check("fix --all-suggested --dry-run lists the stamp-flagged pages, changes nothing",
              js and "2026-01-01-hhhh" in [r["page_id"] for r in js["results"]]
              and parse_orientation_fix(read_text(os.path.join(page_dir(root, "2026-01-01-hhhh"), "meta.yaml"))) is None,
              js and [r["page_id"] for r in js["results"]])
    rc, js, _ = cli("scan", "--root", root)
    check("second scan skips fresh pages", js and js["scanned"] == 0 and js["skipped_fresh"] == 8, js and js["scanned"])

    # fix: rotate the upside-down page
    meta_b0 = read_text(os.path.join(page_dir(root, "2026-01-01-bbbb"), "meta.yaml"))
    raw_b0 = sha256_file(os.path.join(page_dir(root, "2026-01-01-bbbb"), "raw", "page.jpg"))
    rc, js, err = cli("fix", "--root", root, "--page", "2026-01-01-bbbb", "--rotate", "180")
    check("fix exits 0", rc == 0, err)
    fixed = analyze_image(os.path.join(page_dir(root, "2026-01-01-bbbb"), "derived", "page.jpg"), t)
    check("fixed derived image now matches the upright page", hamming(fixed["dhash"], A["dhash"]) <= DEFAULT_NEAR,
          hamming(fixed["dhash"], A["dhash"]))
    meta_b1 = read_text(os.path.join(page_dir(root, "2026-01-01-bbbb"), "meta.yaml"))
    check("meta.yaml keeps old bytes and gains orientation_fix", meta_b1.startswith(meta_b0)
          and parse_orientation_fix(meta_b1)["rotate"] == 180)
    check("raw/ untouched by fix", sha256_file(os.path.join(page_dir(root, "2026-01-01-bbbb"), "raw", "page.jpg")) == raw_b0)
    check("thumb rebuilt with long edge 800",
          max(image_props(os.path.join(page_dir(root, "2026-01-01-bbbb"), "derived", "thumb.jpg"))[:2]) == 800)
    check("quality.json now says fixed", q("2026-01-01-bbbb")["orientation"]["status"] == "fixed")
    evs = [f for f in os.listdir(os.path.join(root, "events", today_utc()))]
    check("correction event written", js and js["event"]["status"] == "written" and len(evs) == 1, evs)
    jl = read_ndjson(os.path.join(root, "events", today_utc() + ".jsonl"))
    check("event envelope complete", jl and jl[0]["evidence"]["correction_type"] == "orientation-fix"
          and jl[0]["harvester_version"] == HARVESTER and jl[0]["entry_id"] is None, jl)
    rc, js, _ = cli("fix", "--root", root, "--page", "2026-01-01-bbbb", "--rotate", "180")
    check("same fix again: event is a duplicate, one jsonl line",
          js and js["event"]["status"] == "duplicate" and len(read_ndjson(os.path.join(root, "events", today_utc() + ".jsonl"))) == 1)
    check("follow-up names nothing for an untranscribed page beyond classify", js and all("transcribe" not in f for f in js["follow_up"]))
    rc, js, _ = cli("fix", "--root", root, "--page", "2026-01-01-bbbb", "--reset")
    check("--reset removes the block (meta back to original bytes)",
          read_text(os.path.join(page_dir(root, "2026-01-01-bbbb"), "meta.yaml")) == meta_b0)
    rc, js, _ = cli("fix", "--root", root, "--page", "2026-01-01-eeee", "--rotate", "0")
    eq = q("2026-01-01-eeee")
    check("EXIF page fixed: derived baked upright, no EXIF tag left",
          eq["orientation"]["status"] == "fixed" and (eq["width"], eq["height"]) == (A["height"], A["width"])
          and image_props(os.path.join(page_dir(root, "2026-01-01-eeee"), "derived", "page.jpg"))[2] in (None, 1), eq)

    # audit: exact, near, rotated, new, within-source, skipped
    src = os.path.join(work, "source")
    os.makedirs(os.path.join(src, "sub"))
    shutil.copyfile(base, os.path.join(src, "exact.jpg"))
    shutil.copyfile(reenc, os.path.join(src, "near.jpg"))
    newimg = os.path.join(src, "new.jpg")
    bmp = os.path.join(work, "new.bmp")
    _write_bmp(bmp, 300, 220, lambda x, y: (255, 255, 255) if (x * x + y) % 97 > 20 else (10, 10, 10))
    run_sips(["-s", "format", "jpeg", bmp, "--out", newimg])
    shutil.copyfile(newimg, os.path.join(src, "sub", "new-copy.jpg"))
    with open(os.path.join(src, "scan.pdf"), "wb") as fh:
        fh.write(b"%PDF-1.4\n")
    src_before = {n: sha256_file(os.path.join(src, n)) for n in ("exact.jpg", "near.jpg", "new.jpg")}
    rc, js, err = cli("audit", "--root", root, "--source", src, "--recursive")
    check("audit exits 0", rc == 0 and js, err)
    st = {os.path.relpath(f["path"], src): f["status"] for f in (js or {}).get("files", [])}
    check("audit statuses", st.get("exact.jpg") == "in_facility_exact" and st.get("near.jpg") == "near_duplicate"
          and st.get("new.jpg") == "new" and st.get("sub/new-copy.jpg") == "duplicate_within_source"
          and st.get("scan.pdf") == "skipped", st)
    fd = (js or {}).get("facility_duplicates", {})
    check("facility-internal exact pair found and unmarked",
          ["2026-01-01-aaaa", "2026-01-01-ffff"] in fd.get("exact", []) and
          any(not x["marked"] for x in fd.get("exact_detail", [])), fd.get("exact"))
    check("source files untouched", all(sha256_file(os.path.join(src, n)) == h for n, h in src_before.items()))

    # stage
    rc, js, _ = cli("stage", "--root", root, "--from-audit", "--dry-run")
    check("stage --dry-run copies nothing", js and js["counts"].get("staged") == 1 and not inbox_files(root), js and js["counts"])
    rc, js, _ = cli("stage", "--root", root, "--from-audit", "--include", "new", "--include", "near")
    names = sorted(os.path.basename(p) for p in inbox_files(root))
    check("stage copies new + near only", names == ["near.jpg", "new.jpg"], names)
    imp = read_ndjson(os.path.join(root, "longitudinal", "imports.ndjson"))
    check("imports ledger has one row per considered file", len(imp) == 4 and
          sorted(r["decision"] for r in imp) == ["skipped_exact", "skipped_within_source", "staged", "staged"],
          [r["decision"] for r in imp])
    rc, js, _ = cli("stage", "--root", root, "--from-audit", "--include", "new", "--include", "near")
    check("re-staging does not duplicate inbox files", sorted(os.path.basename(p) for p in inbox_files(root)) == names
          and js and js["counts"].get("staged") is None, js and js["counts"])

    # inbox-check + hold + release
    shutil.copyfile(base, os.path.join(root, "inbox", "again.jpg"))
    rc, js, _ = cli("inbox-check", "--root", root)
    ist = {f["name"]: f["status"] for f in (js or {}).get("files", [])}
    check("inbox-check statuses", ist == {"again.jpg": "in_facility_exact", "near.jpg": "near_duplicate",
                                         "new.jpg": "new"}, ist)
    rc, js, _ = cli("hold", "--root", root)
    held = sorted(os.listdir(os.path.join(root, "inbox", "_held")))
    check("hold moves exact + near into _held with notes", held == ["again.jpg", "again.jpg.held.json", "near.jpg",
                                                                    "near.jpg.held.json"], held)
    rc, js, _ = cli("release", "--root", root, "near.jpg")
    check("release moves the file back", os.path.exists(os.path.join(root, "inbox", "near.jpg"))
          and not os.path.exists(os.path.join(root, "inbox", "_held", "near.jpg.held.json")))
    rc, js, _ = cli("hold", "--root", root)
    check("a released file is not re-held", os.path.exists(os.path.join(root, "inbox", "near.jpg")), js)

    # mark-duplicate
    meta_f0 = read_text(os.path.join(page_dir(root, "2026-01-01-ffff"), "meta.yaml"))
    rc, js, err = cli("mark-duplicate", "--root", root, "--page", "2026-01-01-ffff", "--of", "2026-01-01-aaaa")
    meta_f1 = read_text(os.path.join(page_dir(root, "2026-01-01-ffff"), "meta.yaml"))
    check("mark-duplicate sets duplicate_of and an errors note",
          rc == 0 and "duplicate_of: 2026-01-01-aaaa" in meta_f1 and "  - \"duplicate raw image of 2026-01-01-aaaa" in meta_f1,
          err or meta_f1)
    check("mark-duplicate keeps the other lines", meta_f1.replace("errors:\n", "errors: []\n", 1).startswith(
          meta_f0.split("errors:")[0]))
    rc, js, err = cli("mark-duplicate", "--root", root, "--page", "2026-01-01-dddd", "--of", "2026-01-01-aaaa")
    check("mark-duplicate refuses unlike pages without --force", rc == 2, err)
    rc, js, _ = cli("mark-duplicate", "--root", root, "--page", "2026-01-01-ffff", "--of", "2026-01-01-aaaa")
    check("mark-duplicate twice is a no-op", js and js["status"] == "unchanged" and js["event"]["status"] == "duplicate", js)

    if not args.keep:
        shutil.rmtree(work, ignore_errors=True)
    if quiet:
        sys.stdout.write(json.dumps({"passed": len(passed), "failed": failed, "fixture": img,
                                     "workdir": work if args.keep else None}, indent=2) + "\n")
    else:
        print("")
        print("selftest: %d passed, %d failed" % (len(passed), len(failed)))
        if args.keep:
            print("kept: %s" % work)
    return 1 if failed else 0


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------

EPILOG = """
facility: --root, else $NL_DIR, else ~/notella. raw/ files and --source
folders are never modified. Every subcommand accepts --json.

examples:
  notella_images.py scan                         # quality.json for pages lacking a fresh one
  notella_images.py scan --pages 2026-04-09-y534 --force
  notella_images.py fix --page 2026-04-09-y534 --rotate 180
  notella_images.py mark-duplicate --page 2026-01-02-02h0 --of 2025-12-01-4794
  notella_images.py audit --source ~/Pictures/notebook --recursive
  notella_images.py stage --from-audit --include new --min-grade fair --dry-run
  notella_images.py inbox-check && notella_images.py hold
  notella_images.py selftest --workdir /tmp/x
"""


def build_parser():
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--root", help="facility root (default $NL_DIR or ~/notella)")
    common.add_argument("--json", action="store_true", help="print machine-readable JSON instead of a summary")

    ap = argparse.ArgumentParser(prog="notella_images.py", description=__doc__.split("\n\n")[0] + " (v" + VERSION + ")",
                                 epilog=EPILOG, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", metavar="SUBCOMMAND")
    sub.required = True

    p = sub.add_parser("scan", parents=[common], help="compute pages/{id}/quality.json",
                       description="Compute pages/{id}/quality.json (metrics, grade, warnings, orientation). "
                                   "Skips pages whose quality.json is newer than derived/page.jpg unless --force.")
    p.add_argument("--pages", nargs="+", metavar="ID", help="only these page ids")
    p.add_argument("--all", action="store_true", help="every page (the default when --pages is absent)")
    p.add_argument("--force", action="store_true", help="recompute even when quality.json is fresh")
    p.add_argument("--workers", type=int, default=0, help="process pool size (default: CPU count)")
    p.add_argument("--dry-run", action="store_true", help="compute and print, write nothing")
    p.set_defaults(fn=cmd_scan)

    p = sub.add_parser("fix", parents=[common], help="set a page's absolute orientation transform",
                       description="Rebuild derived/page.jpg and thumb.jpg from raw/ with EXIF orientation applied, "
                                   "then rotate clockwise by --rotate, then --flip. The transform is ABSOLUTE "
                                   "relative to raw, not cumulative. Records meta.yaml:orientation_fix, recomputes "
                                   "quality.json, logs pipeline.ndjson and a correction event. --reset rebuilds "
                                   "with EXIF only and removes orientation_fix.")
    p.add_argument("--page", metavar="ID")
    p.add_argument("--rotate", type=int, choices=[0, 90, 180, 270], help="clockwise degrees")
    p.add_argument("--flip", choices=["none", "horizontal", "vertical"])
    p.add_argument("--reset", action="store_true", help="back to raw (EXIF applied) and drop orientation_fix")
    p.add_argument("--all-suggested", action="store_true",
                   help="fix every page whose quality.json is suspected WITH a concrete suggestion")
    p.add_argument("--source", help="with --all-suggested: only pages whose sources include this "
                                    "(e.g. stamp-position, classify)")
    p.add_argument("--dry-run", action="store_true")
    p.set_defaults(fn=cmd_fix)

    p = sub.add_parser("mark-duplicate", parents=[common], help="record meta.yaml duplicate_of",
                       description="Set meta.yaml duplicate_of: ORIGINAL on DUP, add an errors note and a "
                                   "correction event (duplicate-raw-image). Refuses pages that do not look alike "
                                   "(dhash distance > 12) unless --force. Does not change the phase.")
    p.add_argument("--page", required=True, metavar="DUP")
    p.add_argument("--of", required=True, metavar="ORIGINAL")
    p.add_argument("--note", help="errors note text (default describes the match)")
    p.add_argument("--force", action="store_true")
    p.add_argument("--dry-run", action="store_true")
    p.set_defaults(fn=cmd_mark_duplicate)

    p = sub.add_parser("audit", parents=[common], help="audit source folders against the facility",
                       description="Hash every jpg/jpeg/heic/heif/png in the source folders (read-only) and compare "
                                   "with every facility page: in_facility_exact, near_duplicate, "
                                   "duplicate_within_source, new; pdf and other files are reported as skipped. Also "
                                   "lists facility-internal duplicates. Writes logs/inventory-audit.json.")
    p.add_argument("--source", action="append", required=True, metavar="DIR")
    p.add_argument("--recursive", action="store_true")
    p.add_argument("--near", type=int, default=DEFAULT_NEAR, help="max dhash Hamming distance for near (default 6)")
    p.add_argument("--workers", type=int, default=0)
    p.set_defaults(fn=cmd_audit)

    p = sub.add_parser("inbox-check", parents=[common], help="duplicate + quality check of inbox/",
                       description="Check every image directly in inbox/ against the facility and each other, with "
                                   "quality and EXIF orientation. Writes logs/inbox-check.json. Moves nothing.")
    p.add_argument("--near", type=int, default=DEFAULT_NEAR)
    p.add_argument("--workers", type=int, default=0)
    p.set_defaults(fn=cmd_inbox_check)

    p = sub.add_parser("stage", parents=[common], help="copy audited source files into inbox/",
                       description="COPY (never move) files from the last audit into inbox/. Exact duplicates are "
                                   "always skipped; near duplicates only with --include near. One row per considered "
                                   "file goes to longitudinal/imports.ndjson.")
    p.add_argument("--from-audit", action="store_true", required=True)
    p.add_argument("--include", action="append", choices=["new", "near"],
                   help="statuses to stage (repeatable; default: new)")
    p.add_argument("--min-grade", choices=["poor", "fair", "good"], default="poor",
                   help="skip files graded below this (default poor = stage everything)")
    p.add_argument("--dry-run", action="store_true")
    p.set_defaults(fn=cmd_stage)

    p = sub.add_parser("hold", parents=[common], help="move inbox duplicates into inbox/_held/",
                       description="Run inbox-check, then move files that duplicate a facility page (exact or near) "
                                   "into inbox/_held/ with a NAME.held.json note, so intake does not mint them. "
                                   "Files released earlier are left alone. Logged to longitudinal/imports.ndjson.")
    p.add_argument("--near", type=int, default=DEFAULT_NEAR)
    p.add_argument("--workers", type=int, default=0)
    p.add_argument("--dry-run", action="store_true")
    p.set_defaults(fn=cmd_hold)

    p = sub.add_parser("release", parents=[common], help="move one held file back into inbox/",
                       description="Move inbox/_held/NAME back into inbox/ (it was not a duplicate). Logged as "
                                   "decision released; hold will not re-hold the same bytes.")
    p.add_argument("name", metavar="NAME")
    p.add_argument("--note")
    p.add_argument("--dry-run", action="store_true")
    p.set_defaults(fn=cmd_release)

    p = sub.add_parser("selftest", parents=[common], help="run the self-tests on a temp fixture",
                       description="Build a scratch facility from one facility image (copied, never modified) or a "
                                   "synthetic image, and exercise the decoder, dhash, meta editing and every "
                                   "subcommand.")
    p.add_argument("--image", help="fixture source image (default: first page of the facility)")
    p.add_argument("--image2", help="a different page for the far-distance check")
    p.add_argument("--workdir", help="parent folder for the temp fixture")
    p.add_argument("--keep", action="store_true", help="keep the fixture folder")
    p.set_defaults(fn=cmd_selftest)
    return ap


def main(argv=None):
    if not os.path.exists("/usr/bin/sips"):
        sys.stderr.write("notella-images needs macOS /usr/bin/sips\n")
        return 2
    args = build_parser().parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
