# notella-monthly-synthesis — deterministic pre-aggregation

The rules Step 3 of the SKILL.md applies before the model is called. Everything here is a pure function of the files read in Step 2; running it twice on the same inputs gives byte-identical output, and the model never changes a value it produces. The result is the `measurements_json` block that `references/monthly-prompt.md` passes in the user turn, and the fields the skill copies back over the model's answer in Step 6.

**Placeholders:** `{{double-curly}}` name values that come from the run (`{{month}}`, `{{month_end}}`); everything else is literal.

---

## 1. Month, days and weeks

```
month        = --month, else the most recent month that has closed in identity.timezone
month_start  = {{month}}-01
month_end    = last calendar day of {{month}}          # with --partial: today in identity.timezone
today        = now in identity.timezone

closed       = today > month_end (without --partial)
```

**Week overlap.** `weeks_overlapping` is every ISO week (`YYYY-Www`, ISO 8601, Monday-first) with at least one calendar day in `[month_start, month_end]`. A month therefore overlaps 5 or 6 weeks, and the first and last of them usually belong partly to the neighbouring months — that is intended: the weekly is the unit of narrative and is not split.

```
weeks_covered = [w for w in weeks_overlapping if get-weekly w is not null]   # sorted ascending
weeks_missing = weeks_overlapping − weeks_covered
```

`len(weeks_covered) == 0` aborts the run (`no-weeklies-for-month`) before anything below is computed.

**Authoritative date of a page** — the same chain every synthesis skill uses, first non-null wins:

1. `metadata.json:date`
2. `transcribe.json:extractedDate`
3. `meta.yaml:source_capture_time` (date part, in `identity.timezone`)
4. `meta.yaml:ingested_at` (date part, in `identity.timezone`)

A page is "in the month" when its authoritative date is in `[month_start, month_end]`. `notella-state list-pages --since={{month_start}} --until={{month_end}}` applies this chain; the skill does not re-derive it.

## 2. Counts

```
pages_total      = len(pages)
pages_by_project = {}
for p in pages:
  slugs = p.meta.project_attributions or ["(none)"]
  for s in slugs: pages_by_project[s] += 1          # a page with two attributions counts for both
pages_by_weekday = {Mon: 0, Tue: 0, Wed: 0, Thu: 0, Fri: 0, Sat: 0, Sun: 0}
for p in pages: pages_by_weekday[weekday(authoritative_date(p))] += 1
```

`pages_by_project` is emitted with keys sorted by count descending, then slug ascending, so the JSON is stable. All seven weekday keys are always present, zeros included. The sum of `pages_by_weekday` equals `pages_total`; the sum of `pages_by_project` is ≥ `pages_total`.

## 3. Theme arc

Inputs: `themes_previous` and `themes_current` (either may be null). A theme is identified by its `name` (lowercase-hyphenated slug, matched exactly — `notella-themes` guarantees a continuing theme keeps its name).

```
names = sorted( {t.name for t in themes_previous.themes} ∪ {t.name for t in themes_current.themes} )
rank  = {primary: 3, secondary: 2, emerging: 1, fading: 0}

for name in names:
  start_weight = weight of name in themes_previous.themes, else null
  end_weight   = weight of name in themes_current.themes,  else null
  direction    = "new"    if start_weight is null
               = "gone"   if end_weight   is null
               = "rising" if rank[end_weight] > rank[start_weight]
               = "fell"   if rank[end_weight] < rank[start_weight]
               = "held"   otherwise
```

Rows are emitted in `names` order (alphabetical), so the table in the markdown is stable across reruns.

**Evidence candidates** per row — the only page ids the model may put in `evidence_pages`:

```
candidates = set()
for snapshot in (themes_previous, themes_current):
  for pid in theme(name).evidence_pages: if authoritative_date(pid) in month: candidates.add(pid)
for p in pages:
  if name in p.metadata.themes: candidates.add(p.page_id)
evidence_candidates = sorted(candidates)
```

A theme named only in a snapshot's `related_themes` does not count; a page whose `metadata.json` is absent contributes nothing. Empty candidates are legal (a `gone` theme usually has none in the month).

**Degenerate cases**

| Case | Result |
| --- | --- |
| Both snapshots null | `theme_arc: []`; `notes` gains `"theme_arc: no themes snapshots; run notella-themes"` |
| Only `themes_current` | every row `direction: new`, `start_weight: null`; `notes` gains `"theme_arc: single snapshot, arc has no start"` |
| Only `themes_previous` | every row `direction: gone`, `end_weight: null`; same note, and `sources.themes_current_stale: true` (see below) |
| Same file returned for both | treat as only `themes_current` (`get-themes-snapshot previous` returns null when there is only one) |

**Staleness.** `sources.themes_current_stale = themes_current is null or date(themes_current.generated_at) < month_end`. When true, the markdown's Theme arc table carries a caption naming the snapshot date, and the run suggests `notella-themes --themes-now` then `--reprocess`. Staleness never aborts the run.

**Sources.** `sources.themes_previous` and `sources.themes_current` are the snapshot paths (`longitudinal/themes/YYYY-MM-DD.json`, the date taken from `generated_at`), or null.

## 4. Decisions

```
rows = read-ledger decisions                     # {status: "absent"} → ledgers.decisions = false, decisions_made = []
decisions_made = []
skipped = 0
for r in rows:
  if r.date not in month: continue
  if not r.description or r.description.strip() == "": skipped += 1; continue
  decisions_made.append({decision: r.description, date: r.date, page_id: r.page_id})
sort decisions_made by (date, page_id, decision)
if skipped: notes.append("decisions.ndjson: {skipped} blank rows skipped")
```

Unparseable lines (invalid JSON) are counted with the blank rows under one note. `revisited` and `revisit_note` are left for the model; the pre-aggregation does not pre-fill them.

## 5. Commitments aging

### Row normalisation

The ledger has two shapes. Normalise every row to `{task, task_id, date, state}` before anything else:

```
task    = r.task    if present else r.description
task_id = r.task_id if present else hash(task)
```

`hash(text)` is the function `notella-review` specifies and the ledger aggregator uses for `task_id` — the three must agree or verdicts will not meet their rows:

```
norm = lowercase(text); replace every run of non-[a-z0-9] with one space; trim
h = 0x811c9dc5
for each byte c of norm (UTF-8):
  h = h XOR c
  h = (h * 16777619) mod 2^32          # FNV-1a 32-bit
task_id = h as 8-digit lowercase hex
```

Rows with no `task`/`description`, no `date`, or a `state` outside `{proposed, owner_confirmed, in_progress, done, abandoned}` are skipped and counted in `notes` as `"commitments.ndjson: {n} unparseable rows skipped"`.

### Verdict precedence

Human verdicts close items the aggregator has not yet seen close, so they are applied before counting:

```
verdicts = list-verdicts --until={{month_end}}T23:59:59          # absent → ledgers.verdicts = false, verdicts = []
closing  = {}                                                    # task_id → latest verdict row
for v in verdicts where v.target_kind == "commitment" and v.verdict in {done, drop, wrong}:
  if v.target_id not in closing or v.ts > closing[v.target_id].ts: closing[v.target_id] = v
```

"Latest row per `target_id` wins": a `carry` after a `done` does not reopen the item for aging purposes — `carry` is not a closing verdict and is ignored here — but a `done` after a `drop` changes which count the item lands in. Only rows with `ts ≤ month_end` are considered; a verdict recorded next month does not rewrite this month.

### Open set

```
open = [r for r in rows
        if r.state in {proposed, owner_confirmed, in_progress}
        and r.date <= month_end
        and r.task_id not in closing]
```

A `wrong` verdict removes the row from `open` and from every count — it was never a commitment.

### Buckets and oldest

```
age(r) = (month_end − r.date) in whole days        # 0 for a row dated month_end

bucket(age) = "<7d"    if age <  7
            = "7-30d"  if 7  <= age <= 30
            = "30-90d" if 30 <  age <= 90
            = ">90d"   if age >  90

buckets = {"<7d": 0, "7-30d": 0, "30-90d": 0, ">90d": 0}
for r in open: buckets[bucket(age(r))] += 1

oldest = sort(open, by (date ascending, task_id ascending))[:5]
         as [{task, source_date: date, state}]
```

The boundary days: 30 falls in `7-30d`, 90 in `30-90d`. The label overlap in the SKILL.md (`7-30d` / `30-90d`) is resolved by closing each range on its upper edge.

### Closed and dropped this month

With `verdicts.ndjson` present:

```
closed_this_month  = count of verdict rows with target_kind == commitment, verdict == done, ts in month
dropped_this_month = count of verdict rows with target_kind == commitment, verdict == drop, ts in month
```

Each row counts once per `target_id` (the latest row in the month per target wins, so a `done` then `drop` on the same item inside one month counts as one `dropped`). `wrong` counts in neither — it is a removal, not a close.

With `verdicts.ndjson` absent:

```
closed_this_month  = count of ledger rows with state == done      and date in month
dropped_this_month = count of ledger rows with state == abandoned and date in month
notes.append("commitments: closed/dropped counts approximate — verdicts.ndjson absent, ledger has no state-change date")
```

`date` on a ledger row is the commitment's source date, so this fallback counts items *made and closed* in the month, not items closed in the month; the note says so.

### Absent ledger

`read-ledger commitments → {status: "absent"}`: `ledgers.commitments = false`, `commitments_aging = {buckets: {all 0}, oldest: [], closed_this_month: 0, dropped_this_month: 0}`, `notes.append("commitments_aging: commitments.ndjson missing")`. The markdown renders "Not available — commitments missing." for the section.

## 6. People movement

From `people.ndjson` rows `{name, canonical, first_seen, last_seen, mentions_total, mentions_by_month: {"YYYY-MM": n}, …}`:

```
this     = {{month}}
earlier  = [m for m in r.mentions_by_month if m < this]         # string compare on YYYY-MM is chronological
n_this   = r.mentions_by_month.get(this, 0)

new        if r.first_seen[:7] == this
steady     if n_this > 0 and any(r.mentions_by_month[m] > 0 for m in earlier)
gone_quiet if n_this == 0 and count(m for m in earlier if r.mentions_by_month[m] > 0) >= 2
```

The three sets are disjoint by construction (`new` requires `first_seen` in the month, so no earlier mention; `steady` and `gone_quiet` differ on `n_this`). A person with mentions this month whose `first_seen` is earlier but who has no earlier month with mentions > 0 (a ledger inconsistency) is placed in `steady` and noted. A person with exactly one earlier active month and none this month is in no list — one quiet month after one active month is not yet a pattern.

Each list holds `canonical` names, sorted by `mentions_total` descending, then `canonical` ascending. Rows whose `canonical` is empty use `name`. Absent ledger: all three lists empty, `ledgers.people = false`, note `"people_movement: people.ndjson missing"`.

With `--partial`, `gone_quiet` is computed as above but the note `"people_movement: partial month, gone_quiet is provisional"` is added — a person may still appear before the month closes.

## 7. Forecast scorecard rows

Rows come from two sources, in this order, and are never reordered or deduplicated against each other (the same prediction made as a watchlist item and as an emergent topic is two forecasts).

### From the previous monthly

```
prev = previous_monthly                              # null → no rows from this source, sources.previous_monthly = null
for i, item in enumerate(prev.next_month_watchlist):
  row = {prediction: item.prediction,
         source: "monthly/{{previous_month}}.json#next_month_watchlist[{i}]",
         id: item.id or "{{previous_month}}-w{i+1}"}
```

`previous_month` is the calendar month before `{{month}}`; if that file is absent the run does not look further back (a gap month has nothing to score and the gap is visible in `sources.previous_monthly: null`).

### From the previous themes snapshot

```
for i, e in enumerate(themes_previous.emergent_topics):
  row = {prediction: "'{e.name}' becomes a theme",
         source: "longitudinal/themes/{{themes_previous_date}}.json#emergent_topics[{i}]",
         hint: "held"    if e.name in {t.name for t in themes_current.themes}
             = "partial" if e.name in {t.name for t in themes_current.emergent_topics}
             = "missed"  otherwise}
```

When `themes_current` is null the hint is `"unknown"` (the snapshot that would decide it does not exist). When `themes_previous` is null there are no rows from this source.

### Applying human verdicts

A verdict row `v` with `target_kind: forecast` (or `watch`, which `notella-review` may use for the same item) matches a scorecard row when any of:

1. `v.source_ref == row.source`
2. `v.target_id == row.id` (watchlist rows only — the `YYYY-MM-w{n}` id `notella-review` writes for forecasts)
3. `v.target_id == hash(row.prediction)` (the text hash, same function as §5)

Latest matching row per scorecard row (by `ts`, considering only `ts ≤ month_end`) wins and fixes the outcome:

| verdict | outcome | evidence |
| --- | --- | --- |
| `done` | `held` | `"verdict:{target_id} — {note}"` |
| `wrong` | `missed` | `"verdict:{target_id} — {note}"` |
| `carry` | `unknown` | `"verdict:{target_id} — still open"` (plus the note when present) |
| `drop` | `unknown` | `"dropped at review"` (plus the note when present) |

A fixed row carries `verdict: {outcome, evidence}` in the measurements block; the model copies it into `outcome` / `evidence` and Step 6 check 4 confirms it did. Rows without a verdict carry no `verdict` key; emergent-topic rows additionally carry their `hint`.

### Watchlist ids for this month

After the model returns, the skill mints `next_month_watchlist[n-1].id = "{{month}}-w{n}"` for `n` in 1..len, overwriting whatever the model returned. These ids are what next month's run and `notella-review` key on.

## 8. Sources block

```
sources = {
  previous_monthly:     "monthly/{{previous_month}}.json" or null,
  themes_current:       "longitudinal/themes/{date}.json" or null,
  themes_previous:      "longitudinal/themes/{date}.json" or null,
  themes_current_stale: bool (§3),
  ledgers: {decisions: bool, commitments: bool, people: bool, verdicts: bool}   # true when read-ledger / list-verdicts did not return absent
}
```

`weeks_covered`, `weeks_missing`, `partial`, `month`, `schema_version: "0.1.0"` complete the fixed part of the block. `generated_at` is set at write time, not here.

## 9. Event evidence

Derived from the finished brief, for `synthesis.monthly`:

```
open_commitments = sum(commitments_aging.buckets.values())
scorecard        = {held: n, partial: n, missed: n, unknown: n}   # counts over forecast_scorecard[].outcome
theme_arc_count  = len(theme_arc)
decisions_count  = len(decisions_made)
watchlist_count  = len(next_month_watchlist)
```

## Worked check

For the SKILL.md example (run 2026-06-01, month 2026-05): `month_end = 2026-05-31`; weeks overlapping are 2026-W18 (Apr 27 – May 3) through 2026-W22 (May 25 – 31), five weeks; a commitment dated 2026-01-14 has age 137 → `>90d`; one dated 2026-05-01 has age 30 → `7-30d`; one dated 2026-05-25 has age 6 → `<7d`. A person first seen `2026-05-19` is `new`; one with `mentions_by_month: {"2026-02": 3, "2026-03": 1, "2026-05": 0}` is `gone_quiet`; one with `{"2026-04": 2}` only is in no list. The previous monthly's fourth watchlist item has `id: 2026-04-w4` and `source: monthly/2026-04.json#next_month_watchlist[3]`.
