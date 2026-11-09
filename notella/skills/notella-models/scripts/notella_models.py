#!/usr/bin/env python3
"""notella-models — the deterministic halves of the mental-models skill.

The skill records the named thinking structures in David's notebook
(frameworks, matrices, hierarchies, loops, pipelines, maps, metaphors) as
durable objects with a lifecycle. The Claude session does one reasoning step;
this script does everything that can be counted. Stdlib only, Python 3.9+.

Subcommands
  prepass   --nl-dir DIR --out FILE          candidate constructs, clustered, with pages and roles
  bundle    --nl-dir DIR --candidates FILE --out FILE
                                             the reasoning bundle (markdown) for the model step
  finalize  --nl-dir DIR --proposal FILE [--write] [--report FILE]
                                             validate the model's JSON, compute stages, readiness,
                                             history, stability, status; apply verdicts; render md and
                                             context; with --write: models.json, snapshot, activity, event
  today     --nl-dir DIR [--date YYYY-MM-DD] model of the day (same rule as the desktop app)
  context   --nl-dir DIR                     print longitudinal/models-context.md
  export    --nl-dir DIR MODEL_ID [--out-dir D]
                                             one-pager for a model → drafts/<id>.md

Lifecycle rules (SKILL.md §3) — all computed here, never by the model:
  glimpse     one assertion page
  forming     ≥ 2 pages, two of them within forming_window_days (90)
  functional  cites a decision, generated a commitment, or applied to a project on ≥ 3 pages
  ready       documented (a document page or deployment of kind document/one-pager) and
              (shape stable, or named ≥ 3 times when there are < 2 drawings) and functional
  deployed    a deployment of kind client | product | skill | post | talk
  dormant     no assertion in the last dormant_days (90) of the corpus
  contested   a tension cites a page in the last contested_days (60) and the model has not been
              asserted since the start of that window
A promote / demote verdict sets verdict_stage, which wins over the evidence stage.
"""
import argparse
import datetime as _dt
import glob
import hashlib
import json
import os
import re
import sys
import unicodedata

VERSION = "notella-models@0.1.0"
STAGES = ["glimpse", "forming", "functional", "ready", "deployed"]
KINDS = ["matrix", "hierarchy", "loop", "pipeline", "map", "stack", "lens", "metaphor", "principle-set", "architecture"]
DOMAINS = ["product", "company", "method", "personal", "creative"]
PROVS = ["borrowed", "adapted", "original"]
DEPLOY_KINDS = ["client", "document", "one-pager", "product", "skill", "post", "talk", "other"]
DELIVERED_KINDS = {"client", "product", "skill", "post", "talk"}
DOCUMENT_KINDS = {"document", "one-pager"}
RELATIONS = ["feeds", "shares-vocabulary", "converging", "supersedes"]
READINESS = ["named", "drawn_twice", "shape_stable", "applied", "informed_decision", "documented", "shared", "delivered"]
RULES = {"dormant_days": 90, "contested_days": 60, "forming_window_days": 90, "stable_shape_max_change": 0.4}
OPEN_STATES = {"proposed", "owner_confirmed", "in_progress"}
FRAMEWORK_DOCTYPES = {"framework-diagram", "framework_diagram", "strategy-map", "strategy_map", "ecosystem-map", "ecosystem_map"}

STOPWORDS = set(
    """a an the and or but of to in on at for with by from as is are be been was were it its this that these
    those not no do does did so than then there their we our i my me you your he she they them his her vs via
    per into over under up out off if when what why how which who whom will would can could should must just
    also only very more most less much many any all each every some new one two three four five""".split()
)
CONSTRUCT_RE = re.compile(
    r"\b(framework|frameworks|model|models|matrix|matrices|hierarch\w*|loop|loops|ladder|canvas|map|maps|pipeline|"
    r"pipelines|stack|flywheel|funnel|tier|tiers|layer|layers|architecture|ontology|pattern|patterns|playbook|cycle|"
    r"grid|2x2|2×2|quadrant|spectrum|axis|lens|kernel|engine|motion|machine|taxonomy|topology|schema|protocol|"
    r"methodology|analogue|analogues|principle|principles|triad|trinity|dimension|dimensions|continuum|flow)\b", re.I)
STRONG_CONSTRUCT_RE = re.compile(
    r"\b(framework|matrix|hierarch\w*|pipeline|loop|flywheel|canvas|architecture|ontology|kernel|2x2|2×2|quadrant|"
    r"ladder|playbook|taxonomy|triad)\b", re.I)
CHAIN_RE = re.compile(r"([^→\n;.|]{2,40}?(?:\s*(?:→|->|⇒|⟶)\s*[^→\n;.|]{2,40}?){2,})(?=$|[\n;.|])")
NAMED_RE = re.compile(r"\b([A-Z][A-Z0-9]{2,}(?:[-_][A-Z0-9]{2,})*)\b")
ACRONYM_STOP = set(
    """MVP API CRM LLM LLMS CLI MCP MCPS URL PDF CSV JSON YAML SLA SLAS NRC NRCAN JPM CEO CTO COO CFO GM BD PM UX UI
    AI ML IP IPS Q1 Q2 Q3 Q4 TODO DONE NOTE NOTES MOST IMPORTANT THEME THEMES NEXT WEEK TODAY AM PM USD CAD EUR GBP
    OK KPI KPIS ROI SEO SAAS B2B B2C R&D RD IT HR QA QC PR RFP RFI SOW NDA MSA PO ASAP FYI EOD EOW ETA TBD TBC NA
    USA UK EU UN NYC LA SF BC ON AB GPT GPTS AWS GCP AZURE SQL NOSQL HTML CSS JS TS NPM PIP OS IOS MAC WIN
    DAVID DAVE JAN FEB MAR APR MAY JUN JUL AUG SEP SEPT OCT NOV DEC MON TUE WED THU FRI SAT SUN""".split()
)
BORROWED = [
    ("Eisenhower matrix", re.compile(r"\beisenhower\b|\burgent\W+important\b", re.I)),
    ("2×2 matrix", re.compile(r"\b2\s*[x×]\s*2\b", re.I)),
    ("S-curve", re.compile(r"\bs[- ]?curves?\b", re.I)),
    ("OKR", re.compile(r"\bokrs?\b", re.I)),
    ("flywheel", re.compile(r"\bflywheel\b", re.I)),
    ("Wardley map", re.compile(r"\bwardley\b", re.I)),
    ("Cynefin", re.compile(r"\bcynefin\b", re.I)),
    ("Towers of Hanoi", re.compile(r"\btowers? of hanoi\b", re.I)),
    ("Sankey", re.compile(r"\bsankey\b", re.I)),
    ("Venn", re.compile(r"\bvenn\b", re.I)),
    ("SWOT", re.compile(r"\bswot\b", re.I)),
    ("Lean canvas", re.compile(r"\blean canvas\b", re.I)),
    ("Business model canvas", re.compile(r"\bbusiness model canvas\b", re.I)),
    ("OODA loop", re.compile(r"\booda\b", re.I)),
    ("PDCA", re.compile(r"\bpdca\b|\bplan[- ]do[- ]check[- ]act\b", re.I)),
    ("Pareto", re.compile(r"\bpareto\b|\b80\s*/\s*20\b", re.I)),
    ("First principles", re.compile(r"\bfirst principles?\b", re.I)),
    ("Maslow", re.compile(r"\bmaslow\b", re.I)),
    ("RICE", re.compile(r"\bRICE\b")),
    ("MoSCoW", re.compile(r"\bmoscow\b", re.I)),
    ("Jobs to be done", re.compile(r"\bjobs?[- ]to[- ]be[- ]done\b|\bjtbd\b", re.I)),
    ("Technology readiness levels", re.compile(r"\btrl\b", re.I)),
    ("Kanban", re.compile(r"\bkanban\b", re.I)),
    ("AARRR funnel", re.compile(r"\baarrr\b|\bpirate metrics\b", re.I)),
    ("Porter's five forces", re.compile(r"\bfive forces\b|\bporter'?s\b", re.I)),
    ("Hero's journey", re.compile(r"\bhero'?s journey\b", re.I)),
    ("Golden circle", re.compile(r"\bgolden circle\b|\bstart with why\b", re.I)),
]
ISO_RE = re.compile(r"^\d{4}-\d{2}-\d{2}")


# ─── small helpers ───────────────────────────────────────────────────────────

def read_json(path):
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return None


def read_text(path):
    try:
        with open(path, encoding="utf-8", errors="replace") as fh:
            return fh.read()
    except OSError:
        return ""


def write_atomic(path, text):
    path = os.path.abspath(path)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        fh.write(text)
    os.replace(tmp, path)


def facility_day(nl, iso_ts):
    """Calendar date of iso_ts in the facility timezone (manifest facility.timezone), else UTC."""
    tz = None
    m = re.search(r"^\s+timezone:\s*(\S+)", read_text(os.path.join(nl, "manifest.yaml")), re.M)
    if m:
        try:
            from zoneinfo import ZoneInfo
            tz = ZoneInfo(m.group(1).strip("\"'"))
        except Exception:
            tz = None
    t = _dt.datetime.strptime(iso_ts, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=_dt.timezone.utc)
    return (t.astimezone(tz) if tz else t).date().isoformat()


def now_iso():
    return _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def date_of(s):
    try:
        return _dt.date.fromisoformat(str(s)[:10])
    except (TypeError, ValueError):
        return None


def shift(day_s, days):
    d = date_of(day_s)
    return (d + _dt.timedelta(days=days)).isoformat() if d else None


def days_between(a, b):
    da, db = date_of(a), date_of(b)
    return (db - da).days if da and db else None


def strip_accents(s):
    return "".join(c for c in unicodedata.normalize("NFKD", s) if not unicodedata.combining(c))


def normalise(text):
    s = strip_accents(str(text or "")).lower()
    s = s.replace("→", " to ").replace("->", " to ").replace("⇒", " to ").replace("&", " and ").replace("≠", " not ")
    s = s.replace("’", "'").replace("'s ", " ").replace("×", "x")
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


def jaccard(a, b):
    if not a or not b:
        return 0.0
    return len(a & b) / float(len(a | b))


def kebab(s):
    s = normalise(s)
    s = re.sub(r"\s+", "-", s).strip("-")
    return s[:60] or "model"


def parse_meta_lists(text, keys):
    """Tiny YAML reader for meta.yaml list keys (inline [a, b] or block '- a')."""
    out = {k: [] for k in keys}
    scalars = {}
    lines = text.splitlines()
    i = 0
    while i < len(lines):
        line = lines[i]
        m = re.match(r"^([A-Za-z_]+):\s*(.*)$", line)
        if m:
            key, val = m.group(1), m.group(2).strip()
            if key in keys:
                if val.startswith("["):
                    inner = val.strip("[]")
                    out[key] = [v.strip().strip("\"'") for v in inner.split(",") if v.strip()]
                elif val == "" or val == "|":
                    j = i + 1
                    while j < len(lines) and re.match(r"^\s+-\s+", lines[j]):
                        out[key].append(re.sub(r"^\s+-\s+", "", lines[j]).strip().strip("\"'"))
                        j += 1
                    i = j - 1
            else:
                scalars[key] = val.strip("\"'")
        i += 1
    return out, scalars


# ─── facility loading ────────────────────────────────────────────────────────

def load_pages(nl):
    pages = {}
    for pdir in sorted(glob.glob(os.path.join(nl, "pages", "*"))):
        if not os.path.isdir(pdir):
            continue
        pid = os.path.basename(pdir)
        if not ISO_RE.match(pid):
            continue
        lists, scalars = parse_meta_lists(read_text(os.path.join(pdir, "meta.yaml")),
                                          ["project_attributions", "person_attributions"])
        dup = scalars.get("duplicate_of") or ""
        md = read_json(os.path.join(pdir, "metadata.json"))
        md = md if isinstance(md, dict) else {}
        fp = read_json(os.path.join(pdir, "first-pass.json"))
        fp = fp if isinstance(fp, dict) else {}
        tr = read_json(os.path.join(pdir, "transcribe.json"))
        tr = tr if isinstance(tr, dict) else {}
        dg = read_json(os.path.join(pdir, "diagram.json"))
        dg = dg if isinstance(dg, dict) else {}
        tb = read_json(os.path.join(pdir, "table.json"))
        tb = tb if isinstance(tb, dict) else {}
        date = md.get("date") if ISO_RE.match(str(md.get("date") or "")) else pid[:10]
        nodes = [n for n in (dg.get("nodes") or []) if isinstance(n, dict)]
        edges = [e for e in (dg.get("edges") or []) if isinstance(e, dict)]
        reps = []
        for ds in fp.get("diagram_semantics") or []:
            if isinstance(ds, dict) and ds.get("representation_type"):
                reps.append(str(ds["representation_type"]))
        tables = [str(t.get("structural_type")) for t in (tb.get("tables") or []) if isinstance(t, dict) and t.get("structural_type")]
        emph = []
        for sp in tr.get("emphasis") or []:
            if isinstance(sp, str):
                emph.append(sp)
            elif isinstance(sp, dict) and sp.get("span_text"):
                emph.append(str(sp["span_text"]))
        transcript = tr.get("cleanedTranscript") or tr.get("structured_markdown") or tr.get("verbatim") or tr.get("rawTranscript") or ""
        if not isinstance(transcript, str):
            transcript = json.dumps(transcript, ensure_ascii=False)
        sm = fp.get("structural_map") if isinstance(fp.get("structural_map"), dict) else {}
        pages[pid] = {
            "id": pid, "date": str(date)[:10], "duplicate": bool(dup and dup not in ("null", "~")),
            "title": str(md.get("title") or ""), "summary": str(fp.get("content_summary") or md.get("summary") or ""),
            "ideas": [str(i) for i in (md.get("ideas") or []) if i], "doc_type": str(md.get("documentType") or ""),
            "projects": lists["project_attributions"] or [str(p) for p in (md.get("projects") or [])],
            "people": lists["person_attributions"] or [str(p) for p in (md.get("people") or [])],
            "nodes": nodes, "edges": edges, "node_text": normalise(" ".join(str(n.get("label") or "") for n in nodes)),
            "reps": reps, "tables": tables, "emphasis": emph, "transcript": transcript,
            "clusters": [str(c) for c in (sm.get("clusters") or []) if c],
            "layout": str(dg.get("layout_semantics") or ""), "utility": str(dg.get("utility_statement") or ""),
            "cross_refs": md.get("cross_references") or [],
        }
    return pages


def corpus_window(pages):
    dates = sorted(p["date"] for p in pages.values() if not p["duplicate"] and p["date"])
    return (dates[0], dates[-1]) if dates else (None, None)


def load_ndjson(path):
    rows = []
    for line in read_text(path).splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except ValueError:
            continue
    return rows


def load_names(nl, pages):
    names = set()

    def add(v):
        n = normalise(v)
        if n:
            names.add(n)
            for t in n.split():
                if len(t) >= 3:
                    names.add(t)
    for row in load_ndjson(os.path.join(nl, "longitudinal", "people.ndjson")):
        add(row.get("name") or "")
        add(row.get("canonical") or "")
        for a in row.get("aliases") or []:
            add(a)
    for line in read_text(os.path.join(nl, "manifest.yaml")).splitlines():
        m = re.match(r"^\s*-?\s*(slug|name):\s*(.+)$", line)
        if m:
            add(m.group(2).strip().strip("\"'"))
    for p in pages.values():
        for v in p["people"]:
            add(v)
    return names


def manifest_projects(nl):
    out = []
    slug = None
    in_projects = False
    for line in read_text(os.path.join(nl, "manifest.yaml")).splitlines():
        if re.match(r"^projects:\s*$", line):
            in_projects = True
            continue
        if in_projects and re.match(r"^[A-Za-z_]+:", line):
            in_projects = False
        if not in_projects:
            continue
        m = re.match(r"^-\s*slug:\s*(.+)$", line)
        if m:
            slug = m.group(1).strip().strip("\"'")
            out.append({"slug": slug, "name": slug})
            continue
        m = re.match(r"^\s+name:\s*(.+)$", line)
        if m and out:
            out[-1]["name"] = m.group(1).strip().strip("\"'")
    return out


# ─── prepass ─────────────────────────────────────────────────────────────────

def borrowed_match(text):
    for name, rx in BORROWED:
        if rx.search(text):
            return name
    return None


def kind_hint(text, source):
    t = text.lower()
    if source == "chain" or re.search(r"\bpipeline|funnel|sequence|→", t):
        return "pipeline"
    if re.search(r"matrix|2x2|2×2|quadrant|grid", t):
        return "matrix"
    if re.search(r"hierarch|tier|level|tree|pyramid|waterfall", t):
        return "hierarchy"
    if re.search(r"loop|cycle|flywheel|wheel", t):
        return "loop"
    if re.search(r"stack|layer", t):
        return "stack"
    if re.search(r"\bmap\b|ecosystem|landscape|territory", t):
        return "map"
    if re.search(r"architecture|router|rail|engine|system|protocol", t):
        return "architecture"
    if re.search(r"principle|kernel|rule", t):
        return "principle-set"
    if re.search(r"\bas\b|metaphor|analog", t):
        return "metaphor"
    return "lens"


def prepass(nl, out_path, top=0):
    pages = load_pages(nl)
    names = load_names(nl, pages)
    since, until = corpus_window(pages)
    stats = {"pages_total": len(pages), "pages_duplicate_skipped": 0, "pages_scanned": 0,
             "ideas_seen": 0, "ideas_construct": 0, "framework_pages": 0, "chains": 0, "named": 0,
             "borrowed": 0, "themes_evolution": 0, "items_kept": 0, "dropped": {}}
    items = []

    def consider(text, source, pid, hint=None, borrowed_from=None, extra_pages=(), min_tokens=2):
        text = re.sub(r"\s+", " ", str(text or "")).strip(" -–—:;,.")
        norm = normalise(text)
        toks = [t for t in content_tokens(norm) if re.search(r"[a-z]", t)]
        reason = None
        if not norm:
            reason = "empty"
        elif len(toks) < min_tokens:
            reason = "label"
        elif source in ("idea", "chain") and all(t in names for t in norm.split() if t not in STOPWORDS):
            reason = "names"
        elif len(text) > 160:
            reason = "sentence"
        if reason:
            stats["dropped"][reason] = stats["dropped"].get(reason, 0) + 1
            return
        items.append({"text": text, "norm": norm, "tokens": set(toks), "source": source, "page_id": pid,
                      "hint": hint or kind_hint(text, source), "borrowed_from": borrowed_from or borrowed_match(text),
                      "extra_pages": list(extra_pages)})

    for pid, p in pages.items():
        if p["duplicate"]:
            stats["pages_duplicate_skipped"] += 1
            continue
        stats["pages_scanned"] += 1
        for idea in p["ideas"]:
            stats["ideas_seen"] += 1
            if CONSTRUCT_RE.search(idea) or CHAIN_RE.search(idea) or borrowed_match(idea):
                stats["ideas_construct"] += 1
                consider(idea, "idea", pid)
        if p["doc_type"] in FRAMEWORK_DOCTYPES and p["title"]:
            stats["framework_pages"] += 1
            consider(p["title"], "framework-page", pid)
        for c in p["clusters"]:
            if CONSTRUCT_RE.search(c):
                consider(c, "cluster", pid)
        haystack = "\n".join(p["ideas"] + p["emphasis"]) + "\n" + p["transcript"][:6000]
        haystack = re.sub(r"<!--.*?-->", " ", haystack, flags=re.S)
        haystack = re.sub(r"\[(?:Diagram|diagram|Sketch|sketch|box[^\]]*)[^\]]*\]", " ", haystack)
        haystack = re.sub(r"[①②③④⑤⑥⑦⑧⑨⑩]", " ", haystack)
        for m in CHAIN_RE.finditer(haystack):
            chain = m.group(1).strip()
            parts = [s.strip() for s in re.split(r"\s*(?:→|->|⇒|⟶)\s*", chain) if s.strip()]
            parts = [s.strip(" -–—:*_#>[]()") for s in parts]
            if len(parts) < 3 or any(len(s.split()) > 5 for s in parts):
                continue
            if sum(1 for s in parts if re.search(r"[A-Za-z]{3,}", s) and not re.match(r"^\d+\s*(am|pm)?$", s, re.I)) < 3:
                stats["dropped"]["chain-debris"] = stats["dropped"].get("chain-debris", 0) + 1
                continue
            stats["chains"] += 1
            consider(" → ".join(parts), "chain", pid, hint="pipeline", min_tokens=2)
        for line in p["ideas"] + p["emphasis"]:
            construct_line = bool(CONSTRUCT_RE.search(line))
            for m in NAMED_RE.finditer(line):
                tok = m.group(1)
                if tok in ACRONYM_STOP or tok.upper() in ACRONYM_STOP or normalise(tok) in names:
                    continue
                # A bare acronym is a label unless it is compound (LEDGER-RAIL) or sits on a line naming a construct.
                if not ("-" in tok or "_" in tok or construct_line):
                    stats["dropped"]["bare-acronym"] = stats["dropped"].get("bare-acronym", 0) + 1
                    continue
                stats["named"] += 1
                consider(tok if "-" in tok or "_" in tok else line, "named", pid, min_tokens=1)
        for bname, rx in BORROWED:
            if rx.search(haystack):
                stats["borrowed"] += 1
                consider(bname, "borrowed", pid, borrowed_from=bname, min_tokens=1)

    theme_files = sorted(glob.glob(os.path.join(nl, "longitudinal", "themes", "*.json")))
    latest = os.path.join(nl, "longitudinal", "themes.json")
    if os.path.exists(latest):
        theme_files.append(latest)
    seen = set()
    for tp in theme_files:
        th = read_json(tp)
        if not isinstance(th, dict):
            continue
        for ev in th.get("conceptual_evolution") or []:
            if not isinstance(ev, dict):
                continue
            concept = str(ev.get("concept") or "")
            kp = [k for k in (ev.get("key_pages") or []) if k in pages and not pages[k]["duplicate"]]
            key = (normalise(concept), tuple(kp))
            if key in seen or not concept:
                continue
            seen.add(key)
            stats["themes_evolution"] += 1
            consider(concept, "themes", kp[0] if kp else None, extra_pages=kp[1:], min_tokens=1)
    stats["items_kept"] = len(items)

    freq = {}
    for it in items:
        freq[it["norm"]] = freq.get(it["norm"], 0) + 1
    order = sorted(range(len(items)), key=lambda i: (-freq[items[i]["norm"]], items[i]["norm"]))
    clusters = []
    for i in order:
        it = items[i]
        placed = None
        for c in clusters:
            if c["norm"] == it["norm"] or (it["borrowed_from"] and it["borrowed_from"] == c["borrowed_from"] and it["source"] == "borrowed" and c["source"] == "borrowed"):
                placed = c
                break
            if len(it["tokens"]) >= 2 and jaccard(c["tokens"], it["tokens"]) >= 0.5:
                placed = c
                break
        if placed is None:
            placed = {"norm": it["norm"], "tokens": set(it["tokens"]), "members": [], "borrowed_from": it["borrowed_from"], "source": it["source"]}
            clusters.append(placed)
        placed["members"].append(it)

    out = []
    for c in clusters:
        mem = c["members"]
        pids = []
        for m in mem:
            for pid in ([m["page_id"]] if m["page_id"] else []) + m["extra_pages"]:
                if pid in pages and pid not in pids:
                    pids.append(pid)
        pids.sort(key=lambda pid: (pages[pid]["date"], pid))
        if not pids:
            continue
        toks = {t for t in c["tokens"] if len(t) >= 4}
        chain_pages = {m["page_id"] for m in mem if m["source"] == "chain" and m["page_id"]}
        page_rows = []
        for pid in pids:
            p = pages[pid]
            drawn = pid in chain_pages or p["doc_type"] in FRAMEWORK_DOCTYPES or (
                bool(p["nodes"]) and any(t in p["node_text"] for t in toks))
            page_rows.append({"id": pid, "date": p["date"], "role": "drawn" if drawn else "named", "title": p["title"]})
        variants = []
        for m in mem:
            if m["text"] not in variants:
                variants.append(m["text"])
        srcs = {}
        for m in mem:
            srcs[m["source"]] = srcs.get(m["source"], 0) + 1
        projects = {}
        for pid in pids:
            for s in pages[pid]["projects"]:
                projects[s] = projects.get(s, 0) + 1
        hints = {}
        for m in mem:
            hints[m["hint"]] = hints.get(m["hint"], 0) + 1
        reps = {}
        for r in page_rows:
            if r["role"] == "drawn":
                for rep in pages[r["id"]]["reps"]:
                    reps[rep] = reps.get(rep, 0) + 1
        name = max(variants, key=lambda v: (sum(1 for m in mem if m["text"] == v), -len(v)))
        dates = [r["date"] for r in page_rows]
        out.append({
            "name": name, "normalized": c["norm"], "variants": variants[:10], "assertions": len(mem),
            "distinct_pages": len(pids), "pages": page_rows, "first_seen": dates[0], "last_seen": dates[-1],
            "sources": srcs, "kind_hint": max(hints, key=hints.get), "borrowed_from": c["borrowed_from"],
            "projects": projects, "representation_types": reps,
            "drawn_pages": sum(1 for r in page_rows if r["role"] == "drawn"),
            "strong_construct": bool(STRONG_CONSTRUCT_RE.search(name)),
        })
    out.sort(key=lambda c: (-c["distinct_pages"], -c["assertions"], c["normalized"]))
    for n, c in enumerate(out, 1):
        c["id"] = "c-%04d" % n
    stats.update({"clusters": len(out), "clusters_multi_page": sum(1 for c in out if c["distinct_pages"] >= 2),
                  "clusters_drawn": sum(1 for c in out if c["drawn_pages"]),
                  "clusters_borrowed": sum(1 for c in out if c["borrowed_from"]),
                  "shortlist": sum(1 for c in out if shortlisted(c))})
    result = {"schema_version": "0.1.0", "generator": VERSION, "generated_at": now_iso(), "nl_dir": nl,
              "corpus": {"pages": stats["pages_scanned"], "since": since, "until": until},
              "stats": stats, "candidates": out[:top] if top else out}
    text = json.dumps(result, indent=1, ensure_ascii=False) + "\n"
    if out_path:
        write_atomic(out_path, text)
        sys.stderr.write("wrote %s (%d candidates, %d shortlisted)\n" % (out_path, len(out), stats["shortlist"]))
    else:
        sys.stdout.write(text)
    return 0


def shortlisted(c):
    src = set(c["sources"])
    if src <= {"named", "cluster"} and not c["strong_construct"]:
        return c["distinct_pages"] >= 3
    return (c["distinct_pages"] >= 2 or bool(src & {"chain", "framework-page", "themes", "borrowed"})
            or c["strong_construct"])


# ─── bundle ──────────────────────────────────────────────────────────────────

def bundle(nl, cand_path, out_path, limit=240):
    cand = read_json(cand_path)
    if not isinstance(cand, dict):
        sys.stderr.write("cannot read candidates %s\n" % cand_path)
        return 2
    pages = load_pages(nl)
    since, until = cand["corpus"]["since"], cand["corpus"]["until"]
    short = [c for c in cand["candidates"] if shortlisted(c)][:limit]
    prev = read_json(os.path.join(nl, "longitudinal", "models.json"))
    verdicts = [r for r in load_ndjson(os.path.join(nl, "longitudinal", "verdicts.ndjson")) if r.get("target_kind") == "model"]
    commitments = load_ndjson(os.path.join(nl, "longitudinal", "commitments.ndjson"))
    decisions = load_ndjson(os.path.join(nl, "longitudinal", "decisions.ndjson"))
    people = load_ndjson(os.path.join(nl, "longitudinal", "people.ndjson"))
    projects = manifest_projects(nl)
    L = []
    w = L.append
    w("# notella-models — reasoning bundle")
    w("Corpus: %d pages, %s → %s. Rules: %s" % (cand["corpus"]["pages"], since, until, json.dumps(RULES)))
    w("Dormant cutoff: %s · tension window since: %s" % (shift(until, -RULES["dormant_days"]), shift(until, -RULES["contested_days"])))
    w("")
    w("## Projects (slug: name)")
    w(", ".join("%s: %s" % (p["slug"], p["name"]) for p in projects))
    w("")
    w("## Borrowed-model dictionary (provenance 'borrowed' or 'adapted' when matched)")
    w(", ".join(n for n, _ in BORROWED))
    w("")
    w("## Shortlisted candidate constructs (%d of %d clusters)" % (len(short), len(cand["candidates"])))
    w("Each: id · name · kind hint · pages (id · date · role · title) · projects · sources · variants · page notes.")
    w("")
    for c in short:
        w("### %s · %s · hint:%s%s" % (c["id"], c["name"], c["kind_hint"], (" · borrowed_from:%s" % c["borrowed_from"]) if c["borrowed_from"] else ""))
        w("pages %d (%s → %s) · drawn %d · projects %s · sources %s · reps %s" % (
            c["distinct_pages"], c["first_seen"], c["last_seen"], c["drawn_pages"], json.dumps(c["projects"]),
            json.dumps(c["sources"]), json.dumps(c["representation_types"])))
        if len(c["variants"]) > 1:
            w("variants: " + " | ".join(c["variants"][:6]))
        for r in c["pages"][:8]:
            p = pages.get(r["id"])
            if not p:
                continue
            note = p["summary"][:160].replace("\n", " ")
            w("- %s · %s · %s · %s — %s" % (r["id"], r["date"], r["role"], r["title"][:70], note))
            if r["role"] == "drawn" and p["layout"]:
                w("    diagram: %s" % p["layout"][:160].replace("\n", " "))
        if c["distinct_pages"] > 8:
            w("- … %d more pages: %s" % (c["distinct_pages"] - 8, ", ".join(r["id"] for r in c["pages"][8:20])))
        w("")
    w("## Previous record (ids carry forward; retired ids are never re-proposed)")
    if isinstance(prev, dict) and prev.get("models"):
        for m in prev["models"]:
            w("- %s · %s · stage %s · status %s%s%s · aliases %s" % (
                m.get("id"), m.get("name"), m.get("stage"), m.get("status"),
                " · confirmed" if m.get("confirmed") else "", " · pinned" if m.get("pinned") else "",
                json.dumps(m.get("aliases") or [])))
    else:
        w("(none — first run)")
    w("")
    w("## Model verdicts (target_kind: model)")
    if verdicts:
        for v in verdicts:
            w("- %s · %s · %s · %s" % (v.get("ts"), v.get("target_id"), v.get("verdict"), v.get("note") or ""))
    else:
        w("(none)")
    w("")
    w("## Decisions ledger (date · page · decision)")
    for d in decisions:
        w("- %s · %s · %s" % (d.get("date"), d.get("source_page_id"), str(d.get("decision") or "")[:150]))
    w("")
    w("## Open commitments (task_id · date · task), newest first")
    opn = [c for c in commitments if c.get("state") in OPEN_STATES]
    opn.sort(key=lambda c: str(c.get("source_date") or ""), reverse=True)
    for c in opn[:180]:
        w("- %s · %s · %s" % (c.get("task_id"), c.get("source_date"), str(c.get("task") or "")[:120]))
    w("")
    w("## People (canonical names, by mentions)")
    people.sort(key=lambda r: -(r.get("mentions_total") or 0))
    w(", ".join(str(r.get("canonical") or r.get("name")) for r in people[:50]))
    w("")
    w("## Output")
    w("Return JSON only, following references/models-prompt.md. Fields the script computes (stage, status, history, readiness, stability) must NOT be in your output.")
    write_atomic(out_path, "\n".join(L) + "\n")
    sys.stderr.write("wrote %s (%d candidates, %d decisions, %d open commitments)\n" % (out_path, len(short), len(decisions), len(opn)))
    return 0


# ─── finalize ────────────────────────────────────────────────────────────────

def node_set(p, node_ids=None):
    nodes = p["nodes"]
    if node_ids:
        nodes = [n for n in nodes if str(n.get("id")) in set(node_ids)] or nodes
    toks = set()
    for n in nodes:
        toks.update(t for t in content_tokens(normalise(str(n.get("label") or ""))) if len(t) >= 3)
    return toks


def find_quote(p, text):
    hay = normalise(p["transcript"] + " " + " ".join(p["emphasis"]))
    return normalise(text) in hay


def latest_verdicts(rows):
    """Per model id: the latest of each verb that matters."""
    out = {}
    for r in rows:
        if r.get("target_kind") != "model" or not r.get("target_id"):
            continue
        tid = r["target_id"]
        out.setdefault(tid, []).append(r)
    for tid in out:
        out[tid].sort(key=lambda r: str(r.get("ts") or ""))
    return out


def apply_verdicts(m, rows):
    m["confirmed"] = False
    m["pinned"] = False
    m["verdict_stage"] = None
    retired = False
    merged_into = None
    for r in rows:
        v = r.get("verdict")
        note = str(r.get("note") or "")
        if v == "done":
            m["confirmed"] = True
            mm = re.match(r"\s*rename:\s*(.+)$", note, re.I)
            if mm:
                old = m["name"]
                m["name"] = mm.group(1).strip()
                if old and old not in m["aliases"]:
                    m["aliases"].append(old)
        elif v in ("wrong", "drop"):
            retired = True
        elif v == "pin":
            m["pinned"] = True
        elif v in ("promote", "demote"):
            mm = re.search(r"to:\s*([a-z-]+)", note, re.I)
            st = (mm.group(1).lower() if mm else "")
            if st in STAGES:
                m["verdict_stage"] = st
            elif v == "promote":
                m["verdict_stage"] = STAGES[min(4, STAGES.index(m["stage"]) + 1)]
            else:
                m["verdict_stage"] = STAGES[max(0, STAGES.index(m["stage"]) - 1)]
        elif v == "merge":
            mm = re.search(r"into:\s*([a-z0-9-]+)", note, re.I)
            if mm:
                merged_into = mm.group(1)
                retired = True
        elif v == "borrowed-from":
            mm = re.match(r"\s*(.+)$", note)
            if mm and mm.group(1).strip():
                m["borrowed_from"] = mm.group(1).strip()
                if m["provenance"] == "original":
                    m["provenance"] = "adapted"
    return retired, merged_into


def finalize(nl, proposal_path, write, report_path=None, dump_path=None):
    prop = read_json(proposal_path)
    if not isinstance(prop, dict) or not isinstance(prop.get("models"), list):
        sys.stderr.write("proposal must be a JSON object with a models[] list\n")
        return 2
    pages = load_pages(nl)
    since, until = corpus_window(pages)
    dormant_cutoff = shift(until, -RULES["dormant_days"])
    tension_since = shift(until, -RULES["contested_days"])
    commitments = {str(c.get("task_id")): c for c in load_ndjson(os.path.join(nl, "longitudinal", "commitments.ndjson"))}
    decisions = load_ndjson(os.path.join(nl, "longitudinal", "decisions.ndjson"))
    dec_norm = [(normalise(d.get("decision") or ""), d) for d in decisions]
    verdicts = latest_verdicts(load_ndjson(os.path.join(nl, "longitudinal", "verdicts.ndjson")))
    prev = read_json(os.path.join(nl, "longitudinal", "models.json"))
    prev_ids = {m.get("id") for m in (prev.get("models") if isinstance(prev, dict) else []) or []}
    project_slugs = {p["slug"] for p in manifest_projects(nl)}
    errors, warnings, notes = [], [], [str(n) for n in (prop.get("notes") or [])]
    models = []
    seen_ids = set()

    def valid_page(pid):
        return pid in pages and not pages[pid]["duplicate"]

    for raw in prop["models"]:
        if not isinstance(raw, dict):
            continue
        name = str(raw.get("name") or "").strip()
        mid = str(raw.get("id") or kebab(name)).strip()
        if not re.match(r"^[a-z0-9]+(-[a-z0-9]+)*$", mid):
            mid = kebab(mid)
        if mid in seen_ids:
            errors.append("duplicate id %s" % mid)
            continue
        if not name:
            errors.append("model %s has no name" % mid)
            continue
        seen_ids.add(mid)
        kind = str(raw.get("kind") or "lens")
        if kind not in KINDS:
            warnings.append("%s: kind %r → lens" % (mid, kind))
            kind = "lens"
        domain = str(raw.get("domain") or "method")
        if domain not in DOMAINS:
            warnings.append("%s: domain %r → method" % (mid, domain))
            domain = "method"
        prov = str(raw.get("provenance") or "original")
        if prov not in PROVS:
            prov = "original"
        borrowed_from = raw.get("borrowed_from") if isinstance(raw.get("borrowed_from"), str) and raw.get("borrowed_from").strip() else None
        if prov == "original" and borrowed_from:
            prov = "adapted"
        # assertion pages
        ap = []
        for a in raw.get("assertion_pages") or []:
            if isinstance(a, str):
                a = {"page_id": a, "role": "named"}
            if not isinstance(a, dict):
                continue
            pid = str(a.get("page_id") or "")
            role = "drawn" if str(a.get("role") or "named") == "drawn" else "named"
            if not valid_page(pid):
                warnings.append("%s: dropped unknown/duplicate page %s" % (mid, pid))
                continue
            if all(x["page_id"] != pid for x in ap):
                ap.append({"page_id": pid, "role": role, "date": pages[pid]["date"]})
            elif role == "drawn":
                for x in ap:
                    if x["page_id"] == pid:
                        x["role"] = "drawn"
        if not ap:
            errors.append("%s: no valid assertion pages" % mid)
            continue
        ap.sort(key=lambda x: (x["date"], x["page_id"]))
        drawn = [x for x in ap if x["role"] == "drawn"]
        first_seen, last_asserted = ap[0]["date"], ap[-1]["date"]
        # canonical shape + stability
        canon_pid = raw.get("canonical_page_id") if valid_page(str(raw.get("canonical_page_id") or "")) else None
        if canon_pid is None and drawn:
            canon_pid = max(drawn, key=lambda x: (len(pages[x["page_id"]]["nodes"]), x["date"]))["page_id"]
        node_ids = [str(n) for n in (raw.get("canonical_node_ids") or [])]
        canonical_shape = None
        shape_signature = None
        if canon_pid:
            cp = pages[canon_pid]
            ids_present = [n for n in node_ids if any(str(x.get("id")) == n for x in cp["nodes"])]
            nodes_used = [x for x in cp["nodes"] if str(x.get("id")) in set(ids_present)] if ids_present else cp["nodes"]
            node_set_ids = {str(x.get("id")) for x in nodes_used}
            edges_used = [e for e in cp["edges"] if not ids_present or (str(e.get("from")) in node_set_ids and str(e.get("to")) in node_set_ids)]
            rep = cp["reps"][0] if cp["reps"] else (cp["tables"][0] if cp["tables"] else None)
            canonical_shape = {"page_id": canon_pid, "node_ids": [str(x.get("id")) for x in nodes_used],
                               "edge_ids": [str(e.get("visual_element_id") or ("%s>%s" % (e.get("from"), e.get("to")))) for e in edges_used],
                               "representation_type": rep}
            shape_signature = {"nodes": len(nodes_used), "edges": len(edges_used), "representation": rep} if nodes_used else None
        sets = []
        for x in drawn:
            s = node_set(pages[x["page_id"]], node_ids if x["page_id"] == canon_pid else None)
            if s:
                sets.append(s)
        stability = None
        if len(sets) >= 2:
            js = [jaccard(sets[i], sets[i + 1]) for i in range(len(sets) - 1)]
            stability = round(sum(js) / len(js), 2)
        # ledgers
        applied_to = [s for s in (raw.get("applied_to") or []) if isinstance(s, str) and s in project_slugs]
        if not applied_to:
            counts = {}
            for x in ap:
                for s in pages[x["page_id"]]["projects"]:
                    counts[s] = counts.get(s, 0) + 1
            applied_to = sorted([s for s, n in counts.items() if n >= 2 and s in project_slugs], key=lambda s: -counts[s])
        dec_out = []
        for d in raw.get("decisions_informed") or []:
            if isinstance(d, str):
                d = {"decision": d}
            if not isinstance(d, dict):
                continue
            text = normalise(d.get("decision") or "")
            hit = None
            for dn, row in dec_norm:
                if text and (text == dn or (len(text) > 20 and (text in dn or dn in text)) or jaccard(set(content_tokens(text)), set(content_tokens(dn))) >= 0.6):
                    hit = row
                    break
            if hit:
                dec_out.append({"date": str(hit.get("date") or ""), "decision": str(hit.get("decision") or ""), "source_page_id": hit.get("source_page_id")})
            else:
                warnings.append("%s: decision not in ledger, dropped: %s" % (mid, str(d.get("decision") or "")[:60]))
        com_out = []
        for c in raw.get("commitments_generated") or []:
            tid = c.get("task_id") if isinstance(c, dict) else c
            tid = str(tid or "")
            if tid in commitments:
                com_out.append({"task_id": tid, "task": str(commitments[tid].get("task") or "")})
            else:
                warnings.append("%s: commitment %s not in ledger, dropped" % (mid, tid))
        deployments = []
        for dp in raw.get("deployments") or []:
            if not isinstance(dp, dict):
                continue
            k = str(dp.get("kind") or "other")
            if k not in DEPLOY_KINDS:
                k = "other"
            ev = [p for p in (dp.get("evidence_pages") or []) if valid_page(str(p))]
            dt = str(dp.get("date") or "")[:10] if dp.get("date") else (pages[ev[0]]["date"] if ev else None)
            if not ev and k in DELIVERED_KINDS:
                warnings.append("%s: deployment %s/%s has no evidence page; kept as unverified" % (mid, k, dp.get("target")))
            deployments.append({"kind": k, "target": str(dp.get("target") or ""), "date": dt, "evidence_pages": ev})
        documented_pages = [p for p in (raw.get("documented_pages") or []) if valid_page(str(p))]
        quotes = []
        for q in raw.get("evidence_quotes") or []:
            if not isinstance(q, dict):
                continue
            pid, text = str(q.get("page_id") or ""), str(q.get("text") or "").strip()
            if valid_page(pid) and text and len(text.split()) <= 15 and find_quote(pages[pid], text):
                quotes.append({"page_id": pid, "text": text})
            else:
                warnings.append("%s: quote dropped (not found or > 15 words): %s" % (mid, text[:50]))
        tensions = []
        for t in raw.get("tensions") or []:
            if isinstance(t, str):
                t = {"text": t, "evidence_pages": []}
            if not isinstance(t, dict) or not t.get("text"):
                continue
            ev = [p for p in (t.get("evidence_pages") or []) if valid_page(str(p)) and pages[p]["date"] >= (tension_since or "")]
            if ev:
                tensions.append({"text": str(t["text"]), "evidence_pages": ev})
            else:
                warnings.append("%s: tension without a page in the last %d days, dropped" % (mid, RULES["contested_days"]))
        people = [str(p) for p in (raw.get("people_shared_with") or []) if p]
        vocab = [str(v) for v in (raw.get("vocabulary") or []) if v][:12]
        aliases = [str(a) for a in (raw.get("aliases") or []) if a and str(a) != name]
        # readiness
        named = bool(name) and (len(ap) - len(drawn) >= 1 or bool(aliases) or len(drawn) == 0)
        readiness = {
            "named": named,
            "drawn_twice": len(drawn) >= 2,
            "shape_stable": stability is not None and stability >= 1 - RULES["stable_shape_max_change"],
            "applied": bool(applied_to),
            "informed_decision": bool(dec_out) or bool(com_out),
            "documented": bool(documented_pages) or any(d["kind"] in DOCUMENT_KINDS for d in deployments),
            "shared": bool(people),
            "delivered": any(d["kind"] in DELIVERED_KINDS for d in deployments),
        }
        # stage with dated history
        hist = [{"stage": "glimpse", "date": first_seen, "evidence_pages": [ap[0]["page_id"]]}]
        forming_date = None
        for i in range(1, len(ap)):
            if days_between(ap[i - 1]["date"], ap[i]["date"]) is not None and days_between(ap[i - 1]["date"], ap[i]["date"]) <= RULES["forming_window_days"]:
                forming_date = ap[i]["date"]
                break
        if forming_date is None and len(ap) >= 2 and drawn and len(ap) - len(drawn) >= 1:
            forming_date = ap[1]["date"]
        stage = "glimpse"
        if forming_date:
            stage = "forming"
            hist.append({"stage": "forming", "date": forming_date, "evidence_pages": [x["page_id"] for x in ap if x["date"] <= forming_date][-2:]})
        func_dates = [d["date"] for d in dec_out if d["date"]] + [str(commitments[c["task_id"]].get("source_date") or "") for c in com_out]
        if applied_to:
            proj_pages = [x for x in ap if set(pages[x["page_id"]]["projects"]) & set(applied_to)]
            if len(proj_pages) >= 3:
                func_dates.append(proj_pages[2]["date"])
        func_dates = [d for d in func_dates if d]
        if stage == "forming" and func_dates:
            stage = "functional"
            fd = max(min(func_dates), forming_date)
            ev = [d["source_page_id"] for d in dec_out if d.get("source_page_id") and valid_page(str(d["source_page_id"]))][:2] or [x["page_id"] for x in ap if x["date"] <= fd][-1:]
            hist.append({"stage": "functional", "date": fd, "evidence_pages": ev})
        if stage == "functional" and readiness["documented"] and (readiness["shape_stable"] or (len(drawn) < 2 and len(ap) >= 3)):
            doc_dates = [pages[p]["date"] for p in documented_pages] + [d["date"] for d in deployments if d["kind"] in DOCUMENT_KINDS and d["date"]]
            rd = max(min(doc_dates), hist[-1]["date"]) if doc_dates else hist[-1]["date"]
            stage = "ready"
            hist.append({"stage": "ready", "date": rd, "evidence_pages": documented_pages[:2] or [e for d in deployments if d["kind"] in DOCUMENT_KINDS for e in d["evidence_pages"]][:2]})
        if readiness["delivered"]:
            dd = [d["date"] for d in deployments if d["kind"] in DELIVERED_KINDS and d["date"]]
            dd = max(min(dd), hist[-1]["date"]) if dd else hist[-1]["date"]
            for s in STAGES[STAGES.index(stage) + 1:4]:
                hist.append({"stage": s, "date": dd, "evidence_pages": [], "note": "implied by deployment"})
            stage = "deployed"
            hist.append({"stage": "deployed", "date": dd, "evidence_pages": [e for d in deployments if d["kind"] in DELIVERED_KINDS for e in d["evidence_pages"]][:2],
                         "note": ", ".join("%s: %s" % (d["kind"], d["target"]) for d in deployments if d["kind"] in DELIVERED_KINDS)})
        m = {
            "id": mid, "name": name, "aliases": aliases, "kind": kind, "domain": domain, "provenance": prov,
            "borrowed_from": borrowed_from, "statement": str(raw.get("statement") or "").strip(),
            "stage": stage, "status": "active", "stage_history": hist,
            "first_seen": first_seen, "last_asserted": last_asserted,
            "times_drawn": len(drawn), "times_named": len(ap) - len(drawn),
            "assertion_pages": [x["page_id"] for x in ap],
            "evidence_pages": [], "evidence_quotes": quotes,
            "canonical_shape": canonical_shape, "shape_signature": shape_signature, "shape_stability": stability,
            "vocabulary": vocab, "applied_to": applied_to, "decisions_informed": dec_out,
            "commitments_generated": com_out, "people_shared_with": people, "deployments": deployments,
            "readiness": readiness, "next_step": (str(raw.get("next_step") or "").strip() or None),
            "tensions": tensions,
            "related_models": [r for r in (raw.get("related_models") or []) if isinstance(r, dict) and r.get("id") and r.get("relation") in RELATIONS],
            "lineage": {"parent": (str(raw.get("parent")) if raw.get("parent") else None), "children": [],
                        "inferred": bool(raw.get("parent_inferred", True))},
            "confirmed": False, "pinned": False, "verdict_stage": None,
            "_documented_pages": documented_pages, "_one_line": str(raw.get("one_line") or "").strip(),
        }
        # evidence pages ≤ 8: canonical, earliest, latest, strongest drawn, then spread
        ev = []
        for pid in ([canon_pid] if canon_pid else []) + [ap[0]["page_id"], ap[-1]["page_id"]] + [x["page_id"] for x in drawn] + [x["page_id"] for x in ap]:
            if pid and pid not in ev:
                ev.append(pid)
            if len(ev) >= 8:
                break
        m["evidence_pages"] = ev
        # verdicts
        retired, merged_into = apply_verdicts(m, verdicts.get(mid, []))
        if merged_into:
            notes.append("%s merged into %s by verdict" % (mid, merged_into))
        # status
        if retired:
            m["status"] = "retired"
        elif dormant_cutoff and last_asserted < dormant_cutoff:
            m["status"] = "dormant"
        elif tensions and tension_since and last_asserted < tension_since:
            m["status"] = "contested"
        if m["verdict_stage"] and m["verdict_stage"] != stage:
            m["stage_history"].append({"stage": m["verdict_stage"], "date": until, "evidence_pages": [], "note": "by verdict"})
        models.append(m)

    ids = {m["id"] for m in models}
    for m in models:
        if m["lineage"]["parent"] and m["lineage"]["parent"] not in ids:
            warnings.append("%s: parent %s unknown, cleared" % (m["id"], m["lineage"]["parent"]))
            m["lineage"]["parent"] = None
        m["related_models"] = [r for r in m["related_models"] if r["id"] in ids and r["id"] != m["id"]]
    for m in models:
        if m["lineage"]["parent"]:
            for p in models:
                if p["id"] == m["lineage"]["parent"]:
                    p["lineage"]["children"].append(m["id"])
    for pid in prev_ids - ids:
        notes.append("previous model %s not re-proposed this run" % pid)

    generated_at = now_iso()
    record = {
        "schema_version": "0.1.0", "generated_at": generated_at,
        "corpus": {"pages": sum(1 for p in pages.values() if not p["duplicate"]), "since": since, "until": until},
        "rules": dict(RULES, dormant_cutoff=dormant_cutoff, tension_since=tension_since),
        "prepass": prop.get("prepass") if isinstance(prop.get("prepass"), dict) else None,
        "models": [{k: v for k, v in m.items() if not k.startswith("_")} for m in models],
        "notes": notes,
    }
    record_day = facility_day(nl, generated_at)
    md = render_md(record)
    ctx = render_context(dict(record, _day=record_day), models)
    counts = {s: sum(1 for m in models if m["stage"] == s and m["status"] != "retired") for s in STAGES}
    active = sum(1 for m in models if m["status"] == "active")
    report = {"status": "ok" if not errors else "errors", "errors": errors, "warnings": warnings,
              "models": len(models), "active": active, "by_stage": counts, "notes": notes}
    if report_path:
        write_atomic(report_path, json.dumps(report, indent=1, ensure_ascii=False) + "\n")
    if dump_path:
        write_atomic(dump_path, json.dumps(record, indent=1, ensure_ascii=False) + "\n")
        write_atomic(os.path.splitext(dump_path)[0] + ".md", md)
        write_atomic(os.path.splitext(dump_path)[0] + "-context.md", ctx)
    if errors and not write:
        sys.stdout.write(json.dumps(report, indent=1, ensure_ascii=False) + "\n")
        return 1
    if write:
        if errors:
            sys.stdout.write(json.dumps(report, indent=1, ensure_ascii=False) + "\n")
            sys.stderr.write("refusing to write: %d errors\n" % len(errors))
            return 1
        lon = os.path.join(nl, "longitudinal")
        text = json.dumps(record, indent=1, ensure_ascii=False) + "\n"
        day = facility_day(nl, generated_at)
        write_atomic(os.path.join(lon, "models", day + ".json"), text)
        write_atomic(os.path.join(lon, "models.md"), md)
        write_atomic(os.path.join(lon, "models-context.md"), ctx)
        write_atomic(os.path.join(lon, "models.json"), text)
        h6 = hashlib.sha256(("%s|%d|%d" % (generated_at, len(models), active)).encode()).hexdigest()[:6]
        eid = "models.refreshed-%s-%s" % (day, h6)
        event = {"id": eid, "kind": "models.refreshed", "timestamp": generated_at, "page_id": None, "entry_id": None,
                 "project_slug": None, "evidence": {"count": len(models), "active": active, "by_stage": counts,
                                                     "path": "longitudinal/models.json"},
                 "ingested_at": generated_at, "harvester_version": VERSION}
        evdir = os.path.join(nl, "events", day)
        evpath = os.path.join(evdir, eid + ".json")
        if not os.path.exists(evpath):
            write_atomic(evpath, json.dumps(event, indent=2, ensure_ascii=False) + "\n")
            with open(os.path.join(nl, "events", day + ".jsonl"), "a", encoding="utf-8") as fh:
                fh.write(json.dumps(event, ensure_ascii=False) + "\n")
            with open(os.path.join(nl, "logs", "activity.ndjson"), "a", encoding="utf-8") as fh:
                fh.write(json.dumps({"ts": generated_at, "actor": VERSION, "event": "models.refreshed",
                                     "count": len(models), "active": active}) + "\n")
        report["written"] = ["longitudinal/models.json", "longitudinal/models/%s.json" % day, "longitudinal/models.md",
                             "longitudinal/models-context.md", "events/%s/%s.json" % (day, eid)]
    sys.stdout.write(json.dumps(report, indent=1, ensure_ascii=False) + "\n")
    return 0


# ─── renders ─────────────────────────────────────────────────────────────────

def render_md(rec):
    ms = rec["models"]
    L = ["# Models — the notebook's thinking structures",
         "**Generated %s | %d pages | %s → %s | %d models: %s**" % (
             rec["generated_at"], rec["corpus"]["pages"], rec["corpus"]["since"], rec["corpus"]["until"], len(ms),
             ", ".join("%d %s" % (sum(1 for m in ms if m["stage"] == s and m["status"] != "retired"), s) for s in STAGES)),
         "",
         "A model is a named, re-usable structure David thinks with: a framework, matrix, hierarchy, loop, pipeline, map, "
         "stack, lens, metaphor or principle set. Stage is computed from evidence (glimpse → forming → functional → ready → "
         "deployed) unless a verdict moved it; dormant means no page in the last %d days of the corpus; contested means recent "
         "pages pull against it. Unconfirmed until confirmed in `notella review`." % rec["rules"]["dormant_days"], ""]
    for s in reversed(STAGES):
        group = sorted([m for m in ms if m["stage"] == s and m["status"] != "retired"], key=lambda m: (-len(m["assertion_pages"]), m["id"]))
        L.append("## %s" % s.capitalize())
        if not group:
            L.append("None.")
            L.append("")
            continue
        for m in group:
            L.append("### %s" % m["name"])
            L.append("`%s` · %s · %s · %s%s · %s · %d pages (%d drawn) · %s → %s%s%s" % (
                m["id"], m["kind"], m["domain"], m["provenance"], (" from %s" % m["borrowed_from"]) if m["borrowed_from"] else "",
                m["status"], len(m["assertion_pages"]), m["times_drawn"], m["first_seen"], m["last_asserted"],
                " · confirmed" if m["confirmed"] else " · unconfirmed", " · pinned" if m["pinned"] else ""))
            if m["aliases"]:
                L.append("Also written as: " + " · ".join(m["aliases"]))
            if m["statement"]:
                L.append("")
                L.append(m["statement"])
            L.append("")
            L.append("**Lifecycle** " + " → ".join("%s %s" % (h["stage"], h["date"]) for h in m["stage_history"]))
            r = m["readiness"]
            L.append("**Readiness** " + " · ".join(("✓ " if r[k] else "✗ ") + k.replace("_", " ") for k in READINESS))
            if m["shape_signature"]:
                L.append("**Shape** %s nodes, %s edges, %s · stability %s" % (
                    m["shape_signature"]["nodes"], m["shape_signature"]["edges"], m["shape_signature"]["representation"] or "—",
                    "%.2f" % m["shape_stability"] if m["shape_stability"] is not None else "n/a"))
            if m["applied_to"]:
                L.append("**Applied to** " + ", ".join(m["applied_to"]))
            if m["evidence_quotes"]:
                L.append("**In his words**")
                for q in m["evidence_quotes"]:
                    L.append("- \"%s\" — %s" % (q["text"], q["page_id"]))
            L.append("Evidence pages: " + ", ".join(m["evidence_pages"]))
            if m["decisions_informed"]:
                L.append("**Decisions informed**")
                for d in m["decisions_informed"]:
                    L.append("- %s · %s" % (d["date"], d["decision"]))
            if m["deployments"]:
                L.append("**Deployments**")
                for d in m["deployments"]:
                    L.append("- %s: %s%s" % (d["kind"], d["target"], (" (%s)" % d["date"]) if d["date"] else ""))
            if m["tensions"]:
                L.append("**Tensions**")
                for t in m["tensions"]:
                    L.append("- %s (%s)" % (t["text"], ", ".join(t["evidence_pages"])))
            if m["lineage"]["parent"] or m["lineage"]["children"]:
                L.append("**Lineage** %s%s" % (("from %s" % m["lineage"]["parent"]) if m["lineage"]["parent"] else "",
                                               (" → " + ", ".join(m["lineage"]["children"])) if m["lineage"]["children"] else ""))
            if m["next_step"]:
                L.append("**Next step** " + m["next_step"])
            L.append("")
    retired = [m for m in ms if m["status"] == "retired"]
    L.append("## Retired")
    L.extend(["- %s" % m["name"] for m in retired] or ["None."])
    L.append("")
    L.append("## Notes")
    L.extend(["- %s" % n for n in rec["notes"]] or ["None."])
    return "\n".join(L) + "\n"


def render_context(rec, models):
    live = [m for m in models if m["status"] in ("active", "contested") and STAGES.index(m["stage"]) >= 1]
    live.sort(key=lambda m: (not m["pinned"], -STAGES.index(m["stage"]), -len(m["assertion_pages"]), m["id"]))
    head = ["# Models in play — %s" % rec.get("_day", rec["generated_at"][:10]),
            "The structures David thinks with, from his notebook (%s → %s); name one when it fits the work at hand." % (
                rec["corpus"]["since"], rec["corpus"]["until"]), ""]
    body = []
    for m in live:
        tail = m.get("_one_line") or m["next_step"] or m["statement"]
        body.append("- %s (%s · %s%s)%s" % (m["name"], m["stage"], m["domain"], " · contested" if m["status"] == "contested" else "",
                                           (" — " + tail) if tail else ""))
    foot = ["", "(Full record: ~/notella/longitudinal/models.md)"]
    room = 25 - len(head) - len(foot)
    if len(body) > room:
        extra = len(body) - (room - 1)
        body = body[:room - 1] + ["… %d more in models.md" % extra]
    return "\n".join(head + body + foot) + "\n"


# ─── today / context ─────────────────────────────────────────────────────────

def model_of_the_day(models, date_s, until):
    def rank(m):
        st = m.get("verdict_stage") or m.get("stage")
        r = m.get("readiness") or {}
        if st == "ready" and not r.get("delivered"):
            return 0
        if st == "functional" and not r.get("documented"):
            return 1
        gap = days_between(m.get("last_asserted"), until)
        if st == "forming" and gap is not None and gap >= 30:
            return 2
        return 3
    elig = [m for m in models if m.get("status") in ("active", "contested") or m.get("confirmed")]
    elig = [m for m in elig if m.get("status") != "retired" and STAGES.index(m.get("verdict_stage") or m.get("stage") or "glimpse") >= 1]
    elig.sort(key=lambda m: (not m.get("pinned"), rank(m), -STAGES.index(m.get("verdict_stage") or m.get("stage")), str(m.get("id"))))
    if not elig:
        return None
    pinned = [m for m in elig if m.get("pinned")]
    if pinned:
        return pinned[0]
    d = date_of(date_s) or _dt.date.today()
    days = (d - _dt.date(1970, 1, 1)).days
    top = [m for m in elig if rank(m) == rank(elig[0])]
    return top[days % len(top)]


def today(nl, date_s):
    rec = read_json(os.path.join(nl, "longitudinal", "models.json"))
    if not isinstance(rec, dict):
        sys.stdout.write("no longitudinal/models.json yet — run /notella-models\n")
        return 1
    m = model_of_the_day(rec.get("models") or [], date_s, rec.get("corpus", {}).get("until"))
    if not m:
        sys.stdout.write("no eligible model today\n")
        return 0
    r = m.get("readiness") or {}
    missing = [k for k in READINESS if not r.get(k)]
    sys.stdout.write("%s — %s · %s · %s\n%s\nReadiness %d/8%s\nNext: %s\n" % (
        m["name"], m.get("verdict_stage") or m["stage"], m["domain"], m["status"], m.get("statement") or "",
        8 - len(missing), (" · missing: " + missing[0].replace("_", " ")) if missing else "", m.get("next_step") or "—"))
    return 0


def export(nl, mid, out_dir):
    """One-pager for a model, rendered from the record: drafts/<id>.md (never overwrites without a new date line)."""
    rec = read_json(os.path.join(nl, "longitudinal", "models.json"))
    ms = {m.get("id"): m for m in (rec.get("models") if isinstance(rec, dict) else []) or []}
    m = ms.get(mid)
    if not m:
        sys.stderr.write("no model %r in longitudinal/models.json\n" % mid)
        return 2
    pages = load_pages(nl)
    L = ["# %s" % m["name"], "",
         "*%s · %s · %s%s · stage %s · %s → %s*" % (m["kind"], m["domain"], m["provenance"],
             (" (from %s)" % m["borrowed_from"]) if m.get("borrowed_from") else "", m.get("verdict_stage") or m["stage"],
             m.get("first_seen"), m.get("last_asserted")), ""]
    if m.get("statement"):
        L += [m["statement"], ""]
    if m.get("vocabulary"):
        L += ["## Parts", ", ".join(m["vocabulary"]), ""]
    cs = m.get("canonical_shape") or {}
    if cs.get("page_id") and cs["page_id"] in pages:
        p = pages[cs["page_id"]]
        labels = [str(n.get("label")) for n in p["nodes"] if str(n.get("id")) in set(cs.get("node_ids") or [])]
        L += ["## The drawing", "Canonical page %s — %s" % (cs["page_id"], p["title"])]
        if labels:
            L.append("Nodes: " + " · ".join(labels))
        if p["layout"]:
            L.append(p["layout"])
        L.append("")
    if m.get("applied_to"):
        L += ["## Where it has been used", ", ".join(m["applied_to"]), ""]
    if m.get("decisions_informed"):
        L += ["## Decisions it informed"] + ["- %s — %s" % (d.get("date"), d.get("decision")) for d in m["decisions_informed"]] + [""]
    if m.get("deployments"):
        L += ["## Outside the notebook"] + ["- %s: %s%s" % (d["kind"], d["target"], (" (%s)" % d["date"]) if d.get("date") else "") for d in m["deployments"]] + [""]
    if m.get("evidence_quotes"):
        L += ["## In David's words"] + ['- "%s" (%s)' % (q["text"], q["page_id"]) for q in m["evidence_quotes"]] + [""]
    L += ["## Evidence pages", ", ".join(m.get("evidence_pages") or []), ""]
    if m.get("next_step"):
        L += ["## Next step", m["next_step"], ""]
    L += ["---", "Exported %s by %s from longitudinal/models.json. A draft: file it as a document page or record a `document` deployment in review for it to count as documented." % (_dt.date.today().isoformat(), VERSION)]
    out = os.path.join(out_dir or os.path.join(nl, "drafts"), "%s.md" % mid)
    write_atomic(out, "\n".join(L) + "\n")
    sys.stdout.write("wrote %s\n" % out)
    return 0


def context(nl):
    p = os.path.join(nl, "longitudinal", "models-context.md")
    if not os.path.exists(p):
        sys.stdout.write("no longitudinal/models-context.md yet — run /notella-models\n")
        return 1
    sys.stdout.write(read_text(p))
    return 0


# ─── cli ─────────────────────────────────────────────────────────────────────

def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--nl-dir", default=os.environ.get("NL_DIR") or os.path.expanduser("~/notella"))
    sub = ap.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("prepass"); a.add_argument("--out"); a.add_argument("--top", type=int, default=0)
    b = sub.add_parser("bundle"); b.add_argument("--candidates", required=True); b.add_argument("--out", required=True); b.add_argument("--limit", type=int, default=240)
    f = sub.add_parser("finalize"); f.add_argument("--proposal", required=True); f.add_argument("--write", action="store_true"); f.add_argument("--report"); f.add_argument("--dump", help="write the computed record (+ .md, -context.md) here; never touches the facility")
    t = sub.add_parser("today"); t.add_argument("--date", default=_dt.date.today().isoformat())
    sub.add_parser("context")
    e = sub.add_parser("export"); e.add_argument("model_id"); e.add_argument("--out-dir")
    args = ap.parse_args(argv)
    nl = os.path.abspath(os.path.expanduser(args.nl_dir))
    if not os.path.isdir(os.path.join(nl, "pages")):
        sys.stderr.write("no pages/ under %s\n" % nl)
        return 2
    if args.cmd == "prepass":
        return prepass(nl, args.out, args.top)
    if args.cmd == "bundle":
        return bundle(nl, args.candidates, args.out, args.limit)
    if args.cmd == "finalize":
        return finalize(nl, args.proposal, args.write, args.report, args.dump)
    if args.cmd == "today":
        return today(nl, args.date)
    if args.cmd == "context":
        return context(nl)
    if args.cmd == "export":
        return export(nl, args.model_id, args.out_dir)
    return 2


if __name__ == "__main__":
    sys.exit(main())
