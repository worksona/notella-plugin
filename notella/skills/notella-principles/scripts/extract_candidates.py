#!/usr/bin/env python3
"""Deterministic candidate pre-pass for notella-principles.

Reads the notella facility and emits clustered candidate statements that the
model step turns into longitudinal/principles.json. Stdlib only, Python 3.9+.

Sources
  1. pages/*/transcribe.json emphasis[] spans. A typed span (dict) passes the
     gate when intensity >= 2 or mark_type in {star, box, double-underline,
     circle}. An untyped span (a bare string, as written by older transcribe
     runs) carries no mark or intensity; it passes and is flagged typed=false
     unless --typed-only is given.
  2. weekly/*.json ideas_and_insights[] (no page evidence of their own).
  3. longitudinal/themes/*.json and longitudinal/themes.json
     conceptual_evolution[] (concept name; key_pages become evidence).

Pages whose meta.yaml carries `duplicate_of:` are skipped.

Filters (each drop is counted by reason)
  empty, date, numeric (numbers/symbols only), names (every content token is a
  known person/project/organisation name), label (fewer than --min-tokens
  content tokens), owned-task (task imperative with an owner marker).

Clustering
  Normalised texts are clustered greedily: an item joins the first cluster
  whose representative token set has Jaccard >= --jaccard (default 0.6).

Usage
  python3 extract_candidates.py [--nl-dir DIR] [--out FILE] [--typed-only]
                                [--min-tokens N] [--jaccard F] [--top N]
"""
import argparse
import datetime as _dt
import glob
import json
import os
import re
import sys
import unicodedata

VERSION = "notella-principles@0.1.0"
STRONG_MARKS = {"star", "box", "double-underline", "circle"}

STOPWORDS = set(
    """a an the and or but of to in on at for with by from as is are be been was
    were it its this that these those not no do does did so than then there their
    we our i my me you your he she they them his her vs via per into over under up
    out off if when what why how which who whom will would can could should must
    just also only very more most less much many any all each every some""".split()
)

TASK_VERBS = set(
    """send email call ring text book schedule set setup arrange prepare draft write
    submit file review check confirm follow chase ping invite meet sign pay invoice
    order buy update fix finish complete deliver ship share upload download install
    deploy test reply respond contact ask tell remind organise organize print post
    register renew request collect get pick""".split()
)

DATE_RE = re.compile(
    r"^\s*(?:\d{1,4}[-/.]\d{1,2}(?:[-/.]\d{1,4})?|"
    r"(?:mon|tue|wed|thu|fri|sat|sun)[a-z]*\.?\s*\d{0,2}|"
    r"(?:jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)[a-z]*\.?\s*\d{0,4}(?:,?\s*\d{2,4})?|"
    r"q[1-4](?:\s*\d{2,4})?|w(?:eek)?\s*\d{1,2}|\d{4})\s*$",
    re.I,
)
NUMERIC_RE = re.compile(r"^[\s\d$€£%#.,:;+\-–—/x×*()\[\]kKmM]*$")
OWNER_RE = re.compile(r"(^\s*@?\w[\w.]*\s*[:\-–—]\s)|(@\w+)|(\(\s*[A-Z][\w.]*\s*\)\s*$)|(→\s*[A-Z][\w.]*\s*$)")
CHECKBOX_RE = re.compile(r"(\[\s?[x ]?\s?\]|☐|☑|✓|✔|\btodo\b)", re.I)


def read_json(path):
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return None


def is_duplicate(page_dir):
    try:
        with open(os.path.join(page_dir, "meta.yaml"), encoding="utf-8") as fh:
            for line in fh:
                if line.startswith("duplicate_of:") and line.split(":", 1)[1].strip() not in ("", "null", "~"):
                    return True
    except OSError:
        pass
    return False


ISO_RE = re.compile(r"^\d{4}-\d{2}-\d{2}")


def page_date(page_id, metadata):
    if isinstance(metadata, dict):
        d = str(metadata.get("date") or "")
        if ISO_RE.match(d):
            return d[:10]
    if ISO_RE.match(page_id):
        return page_id[:10]
    return None


def strip_accents(s):
    return "".join(c for c in unicodedata.normalize("NFKD", s) if not unicodedata.combining(c))


def normalise(text):
    s = strip_accents(text).lower()
    s = s.replace("→", " to ").replace("->", " to ").replace("&", " and ").replace("≠", " not ")
    s = s.replace("’", "'").replace("'s ", " ")
    s = re.sub(r"[^a-z0-9\s]", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def stem(tok):
    if len(tok) > 4 and tok.endswith("ies"):
        return tok[:-3] + "y"
    if len(tok) > 3 and tok.endswith("s") and not tok.endswith("ss"):
        return tok[:-1]
    return tok


def content_tokens(norm):
    return [stem(t) for t in norm.split() if t not in STOPWORDS and not t.isdigit()]


def load_names(nl):
    names = set()

    def add(v):
        if not v:
            return
        n = normalise(str(v))
        if n:
            names.add(n)
            for t in n.split():
                if len(t) >= 2:
                    names.add(t)

    try:
        with open(os.path.join(nl, "longitudinal", "people.ndjson"), encoding="utf-8") as fh:
            for line in fh:
                try:
                    row = json.loads(line)
                except ValueError:
                    continue
                add(row.get("name"))
                add(row.get("canonical"))
                for a in row.get("aliases") or []:
                    add(a)
    except OSError:
        pass
    try:
        with open(os.path.join(nl, "manifest.yaml"), encoding="utf-8") as fh:
            for line in fh:
                m = re.match(r"^\s*-?\s*(slug|name):\s*(.+)$", line)
                if m:
                    add(m.group(2).strip().strip("\"'"))
    except OSError:
        pass
    for p in glob.glob(os.path.join(nl, "pages", "*", "metadata.json")):
        md = read_json(p)
        if isinstance(md, dict):
            for key in ("people", "projects", "organizations"):
                for v in md.get(key) or []:
                    add(v)
    return names


def drop_reason(text, norm, toks, names, min_tokens):
    if not norm:
        return "empty"
    if DATE_RE.match(text.strip()):
        return "date"
    if NUMERIC_RE.match(text):
        return "numeric"
    if not toks:
        return "numeric" if re.search(r"\d", text) else "empty"
    if all(t in names or stem(t) in names for t in norm.split() if t not in STOPWORDS):
        return "names"
    alpha = [t for t in toks if re.search(r"[a-z]", t)]
    if len(alpha) < min_tokens:
        return "label"
    first = norm.split()[0]
    has_verb = first in TASK_VERBS or any(t in TASK_VERBS for t in norm.split()[:3])
    has_owner = bool(OWNER_RE.search(text)) or bool(CHECKBOX_RE.search(text))
    if not has_owner:
        words = norm.split()
        if len(words) >= 2 and (words[0] in names) and (words[1] == "to" or words[1] in TASK_VERBS):
            has_owner = True
    if has_verb and has_owner:
        return "owned-task"
    return None


STATEMENT_WORDS = {"not", "never", "always", "is", "are", "over", "before", "than", "vs", "no", "must",
                   "only", "first", "every", "same", "beat", "beats", "enable", "enables", "lives", "wins"}


def statement_like(text, norm):
    """Cheap shape test: reads as a claim rather than a label."""
    words = norm.split()
    if any(sym in text for sym in ("→", "->", "=", ">", "≠", "∞")) and len(words) >= 3:
        return True
    if any(w in STATEMENT_WORDS for w in words) and len(words) >= 3:
        return True
    return len([w for w in words if w not in STOPWORDS]) >= 5


def jaccard(a, b):
    if not a or not b:
        return 0.0
    return len(a & b) / float(len(a | b))


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--nl-dir", default=os.environ.get("NL_DIR") or os.path.expanduser("~/notella"))
    ap.add_argument("--out")
    ap.add_argument("--typed-only", action="store_true", help="ignore untyped (bare string) emphasis spans")
    ap.add_argument("--min-tokens", type=int, default=2)
    ap.add_argument("--jaccard", type=float, default=0.6)
    ap.add_argument("--top", type=int, default=0, help="emit only the top N clusters (0 = all)")
    args = ap.parse_args(argv)
    nl = os.path.abspath(os.path.expanduser(args.nl_dir))
    if not os.path.isdir(os.path.join(nl, "pages")):
        sys.stderr.write("no pages/ under %s\n" % nl)
        return 2

    names = load_names(nl)
    stats = {
        "pages_total": 0, "pages_duplicate_skipped": 0, "pages_scanned": 0, "pages_with_emphasis": 0,
        "spans_total": 0, "spans_typed": 0, "spans_untyped": 0, "spans_gated_out": 0,
        "spans_untyped_excluded": 0, "weekly_ideas": 0, "themes_evolution": 0,
        "items_kept": 0, "dropped": {},
    }
    items = []
    page_dates = []

    def consider(text, source, page_id, date, ref, typed, intensity, mark, extra_pages=()):
        text = re.sub(r"\s+", " ", str(text or "")).strip()
        norm = normalise(text)
        toks = content_tokens(norm)
        reason = drop_reason(text, norm, toks, names, args.min_tokens)
        if reason:
            stats["dropped"][reason] = stats["dropped"].get(reason, 0) + 1
            return
        items.append({
            "text": text, "norm": norm, "tokens": set(toks), "source": source, "page_id": page_id,
            "date": date, "ref": ref, "typed": typed, "intensity": intensity, "mark": mark,
            "extra_pages": list(extra_pages),
        })

    for pdir in sorted(glob.glob(os.path.join(nl, "pages", "*"))):
        if not os.path.isdir(pdir):
            continue
        pid = os.path.basename(pdir)
        stats["pages_total"] += 1
        if is_duplicate(pdir):
            stats["pages_duplicate_skipped"] += 1
            continue
        tr = read_json(os.path.join(pdir, "transcribe.json"))
        if not isinstance(tr, dict):
            continue
        stats["pages_scanned"] += 1
        date = page_date(pid, read_json(os.path.join(pdir, "metadata.json")))
        if date:
            page_dates.append(date)
        em = tr.get("emphasis") or []
        if isinstance(em, dict):
            em = [em]
        if em:
            stats["pages_with_emphasis"] += 1
        for span in em:
            stats["spans_total"] += 1
            if isinstance(span, str):
                stats["spans_untyped"] += 1
                if args.typed_only:
                    stats["spans_untyped_excluded"] += 1
                    continue
                consider(span, "emphasis", pid, date, "pages/%s/transcribe.json" % pid, False, None, None)
                continue
            if not isinstance(span, dict):
                continue
            stats["spans_typed"] += 1
            try:
                inten = int(span.get("intensity") or 0)
            except (TypeError, ValueError):
                inten = 0
            mark = span.get("mark_type")
            if inten < 2 and mark not in STRONG_MARKS:
                stats["spans_gated_out"] += 1
                continue
            consider(span.get("span_text"), "emphasis", pid, date, "pages/%s/transcribe.json" % pid, True, inten, mark)

    for wp in sorted(glob.glob(os.path.join(nl, "weekly", "*.json"))):
        wk = read_json(wp)
        if not isinstance(wk, dict):
            continue
        dates = wk.get("dates_covered") or []
        wdate = max(dates) if dates else None
        for idea in wk.get("ideas_and_insights") or []:
            if isinstance(idea, dict):
                idea = idea.get("idea") or idea.get("text") or idea.get("insight") or ""
            stats["weekly_ideas"] += 1
            consider(idea, "weekly", None, wdate, os.path.relpath(wp, nl), None, None, None)

    theme_files = sorted(glob.glob(os.path.join(nl, "longitudinal", "themes", "*.json")))
    latest = os.path.join(nl, "longitudinal", "themes.json")
    if os.path.exists(latest):
        theme_files.append(latest)
    seen_concepts = set()
    for tp in theme_files:
        th = read_json(tp)
        if not isinstance(th, dict):
            continue
        for ev in th.get("conceptual_evolution") or []:
            if not isinstance(ev, dict):
                continue
            concept = ev.get("concept") or ""
            key = (normalise(concept), tuple(ev.get("key_pages") or []))
            if key in seen_concepts:
                continue
            seen_concepts.add(key)
            stats["themes_evolution"] += 1
            kp = sorted(k for k in ev.get("key_pages") or [] if os.path.isdir(os.path.join(nl, "pages", k)))
            consider(concept, "themes", kp[0] if kp else None, kp[-1][:10] if kp else None,
                     os.path.relpath(tp, nl), None, None, None, extra_pages=kp[1:])

    stats["items_kept"] = len(items)

    # Greedy clustering: most frequent normalisations seed clusters first.
    freq = {}
    for it in items:
        freq[it["norm"]] = freq.get(it["norm"], 0) + 1
    order = sorted(range(len(items)), key=lambda i: (-freq[items[i]["norm"]], items[i]["norm"], items[i]["date"] or ""))
    clusters = []
    for i in order:
        it = items[i]
        placed = None
        for c in clusters:
            if c["norm"] == it["norm"] or jaccard(c["tokens"], it["tokens"]) >= args.jaccard:
                placed = c
                break
        if placed is None:
            placed = {"norm": it["norm"], "tokens": it["tokens"], "members": []}
            clusters.append(placed)
        placed["members"].append(it)

    out = []
    for c in clusters:
        mem = c["members"]
        pages = sorted({p for m in mem for p in ([m["page_id"]] if m["page_id"] else []) + m["extra_pages"]})
        dates = sorted(m["date"] for m in mem if m["date"])
        # Evidence: strongest first, then chronological spread.
        ranked = sorted(
            [m for m in mem if m["page_id"]],
            key=lambda m: (-(m["intensity"] or 0), m["mark"] not in STRONG_MARKS, m["date"] or ""),
        )
        ev = []
        for m in ranked:
            for p in [m["page_id"]] + m["extra_pages"]:
                if p not in ev:
                    ev.append(p)
        if len(ev) > 8:
            chron = sorted(ev, key=lambda p: p)
            ev = list(dict.fromkeys(ev[:5] + [chron[0], chron[-1]] + chron[len(chron) // 2:len(chron) // 2 + 1]))[:8]
        variants = []
        for m in mem:
            if m["text"] not in variants:
                variants.append(m["text"])
        srcs = {}
        for m in mem:
            srcs[m["source"]] = srcs.get(m["source"], 0) + 1
        intens = [m["intensity"] for m in mem if m["intensity"] is not None]
        marks = sorted({m["mark"] for m in mem if m["mark"]})
        out.append({
            "text": max(variants, key=lambda v: (sum(1 for m in mem if m["text"] == v), -len(v))),
            "normalized": c["norm"],
            "variants": variants[:10],
            "assertions": len(mem),
            "distinct_pages": len(pages),
            "first_seen": dates[0] if dates else None,
            "last_seen": dates[-1] if dates else None,
            "evidence_pages": ev[:8],
            "sources": srcs,
            "refs": sorted({m["ref"] for m in mem if m["source"] != "emphasis"}),
            "typed": any(m["typed"] for m in mem),
            "max_intensity": max(intens) if intens else None,
            "mark_types": marks,
            "statement_like": any(statement_like(m["text"], m["norm"]) for m in mem),
        })
    out.sort(key=lambda c: (-c["distinct_pages"], -c["assertions"], -(c["max_intensity"] or 0), c["normalized"]))
    for n, c in enumerate(out, 1):
        c["id"] = "c-%04d" % n

    recurring = [c for c in out if c["distinct_pages"] >= 2]
    strong = [c for c in out if (c["max_intensity"] or 0) >= 3 or set(c["mark_types"]) & {"star", "double-underline"}]
    stats.update({
        "clusters": len(out),
        "clusters_multi_page": len(recurring),
        "clusters_intensity3_or_star": len(strong),
        "clusters_statement_like": sum(1 for c in out if c["statement_like"]),
        "clusters_statement_like_emphasis": sum(1 for c in out if c["statement_like"] and "emphasis" in c["sources"]),
        "clusters_from_weekly": sum(1 for c in out if "weekly" in c["sources"]),
        "clusters_from_themes": sum(1 for c in out if "themes" in c["sources"]),
    })
    result = {
        "schema_version": "0.1.0",
        "generator": VERSION,
        "generated_at": _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "nl_dir": nl,
        "params": {"typed_only": args.typed_only, "min_tokens": args.min_tokens, "jaccard": args.jaccard},
        "corpus": {
            "pages": stats["pages_scanned"],
            "since": min(page_dates) if page_dates else None,
            "until": max(page_dates) if page_dates else None,
        },
        "stats": stats,
        "candidates": out[: args.top] if args.top else out,
    }
    text = json.dumps(result, indent=1, ensure_ascii=False)
    if args.out:
        tmp = args.out + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            fh.write(text + "\n")
        os.replace(tmp, args.out)
        sys.stderr.write("wrote %s (%d candidates)\n" % (args.out, len(result["candidates"])))
    else:
        sys.stdout.write(text + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
