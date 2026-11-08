---
name: notella-daily-synthesis
description: "Produce a daily intelligence brief from all notella pages indexed to a date — theme of the day, new decisions, unresolved questions, top priorities, what yesterday's brief left open and today's pages resolved, momentum signals, key entities active, what to watch tomorrow. Use whenever the user says 'daily brief for today', 'synthesize today's notes', 'daily intelligence for 2026-05-02', 'what happened today', 'today's standup brief', 'what did I resolve today', or any request to consolidate a single day's pages into a coherent operational picture. Reads the previous daily brief, the latest weekly's open actions and any review verdicts through `notella-state`; writes `daily/{date}.{json,md}`. Emits `synthesis.daily` event."
---

# notella-daily-synthesis — the daily intelligence brief

First Layer-3 deriver. Reads every page indexed to a date, plus the brief that came before it, and produces a daily intelligence brief — the operational picture of what happened, what was decided, what was closed, what remains open and what tomorrow should show.

## Purpose

Turn a day's pages into a brief. The day is the natural granularity for human review: "what did I think about today, what did I decide, what did I close, what's still open, what should tomorrow focus on."

The brief has memory. Each daily reads its predecessor, so an open question raised on Monday is **carried** on Tuesday and **resolved** on Wednesday when a page answers it — instead of being rediscovered as new three mornings in a row. A human verdict recorded by `notella-review` overrides the model's judgement on any item.

## Inputs and outputs

**Input:** A date. Reads every page where `meta.yaml:phase >= indexed` and the page's authoritative date is the target date.

The page's authoritative date is, in order: `metadata.json:date`, then `transcribe.json:extractedDate`, then `meta.yaml:source_capture_time`, then `meta.yaml:ingested_at` (the latter only as last resort).

**Context inputs** (all optional; absence is normal on a facility's first days):

| Input | Source | Role |
| --- | --- | --- |
| Previous daily brief | the most recent `daily/{d}.json` with `d < date` (may be null; gaps are skipped, so a Monday reads the previous Friday) | Candidate pool for `carried` and `resolved_today`; defines `carried_since` |
| Open weekly actions | `action_items_open` from the latest `weekly/*.json` whose week ends before `date` | Additional candidates for carried / resolved |
| Monthly watchlist | `next_month_watchlist` from the latest `monthly/{YYYY-MM}.json`, if the file exists | Read-only context: the model notes when a page speaks to a watchlist item |
| Review verdicts | rows of `longitudinal/verdicts.ndjson` with `ts` after the previous brief's `generated_at` and on or before `date`T23:59:59 | Human overrides: `done` and `drop` beat the model's reading |

**Output:**
- `daily/{date}.json` — `DailyIntelligenceSchema` (every pre-existing field kept; additions below)
- `daily/{date}.md` — human-readable narrative rendering of the same content
- `synthesis.daily` event with `evidence: {pages_analyzed, resolved_count, carried_count, new_count}`
- `state.json:last_synthesis_at.daily` updated
- For every page included, advance phase from `indexed` to `archived` and emit `page.archived`

## How a run executes

### Step 1 — Read configuration & pages

```
notella-state get-manifest → manifest.model_defaults.daily_synthesis
notella-state list-pages --since={date}T00:00:00 --until={date}T23:59:59 --phase=indexed
```

If the result is empty, abort with `{status: "no-pages-for-date"}`.

### Step 2 — Read each page's full record

For each page-id in the result:

```
notella-state get-page-artifact {page-id, artifact: first-pass}
notella-state get-page-artifact {page-id, artifact: actions}     # optional
notella-state get-page-artifact {page-id, artifact: metadata}
```

Build the input bundle: `[{page_id, first_pass, metadata, actions?}, ...]`.

### Step 3 — Read the predecessor and the open-items context

```
prev_date = max(d for d in notella-state list-dailies if d < date)   # null on first brief
previous  = notella-state get-daily {prev_date}                        # null if prev_date is null

weekly    = latest week in notella-state list-weeklies whose Sunday < date
open_actions = notella-state get-weekly {weekly}.action_items_open     # [] if none

monthly   = notella-state get-monthly {last of list-monthlies}         # null if none
watchlist = [w.prediction for w in monthly.next_month_watchlist]        # [] if none

verdicts  = notella-state read-ledger {file: verdicts, since: previous.generated_at, until: {date}T23:59:59}
            # {status: "absent"} → []
```

Build the **carry pool**: every item of `previous.new_decisions`, `previous.unresolved_questions`, `previous.top_priorities` whose status is not `resolved` or `dropped`, plus every `open_actions[]` item not already in the pool (match on normalised text). Each pool entry carries its `carried_since` — the predecessor item's `carried_since` if present, else the predecessor's `date` (for weekly actions: the action's `source_date`).

Apply verdicts to the pool before the model sees it:

- `done` → move the item to a **pre-resolved** list with `evidence: "verdict:{target_id} — {note}"` and `evidence_page_id: null`
- `drop` → move the item to a **pre-dropped** list
- `wrong` → remove the item from the pool silently (it was a misreading; it must not reappear)
- `carry` → leave in the pool, unchanged

`watch_tomorrow` from the predecessor is passed to the model as "yesterday said to watch for…" so today's brief can confirm or deny it in `synthesis_notes`.

### Step 4 — Build the prompt

Use notella-the-app's `DAILY_INTELLIGENCE_SYSTEM` and `buildDailyIntelligencePrompt()` from `src/lib/prompts/daily-intelligence.ts` as the base. Pass the bundle as the `analysesJson` input, with a small format adjustment so the model can see metadata + actions per page, not just first-pass.

Append the **memory block** to the user prompt: the carry pool (with `carried_since`), the pre-resolved and pre-dropped lists, yesterday's `watch_tomorrow`, the monthly watchlist, and this guidance verbatim:

```
You are continuing a brief, not starting one. Rules:

1. CARRY, DON'T RE-STATE. If today's pages touch an item from the carry pool,
   reuse the pool wording verbatim and mark it status=carried with its
   carried_since. Only write a new item when the substance is new. An item
   that is merely rephrased is carried, not new. If the pages do not mention a
   pool item at all, carry it anyway — silence is not resolution.

2. RESOLVED NEEDS PAGE EVIDENCE. Mark a pool item resolved only when a page in
   today's bundle answers the question, completes the priority, or supersedes
   the decision. Quote the page (evidence) and name it (evidence_page_id).
   "Probably done by now" is not evidence; carry it instead.

3. DROPPED IS RARE. Mark a pool item dropped only when a page explicitly
   abandons it. Otherwise carry it.

4. THEME OF THE DAY is one sentence naming the dominant thread across the
   pages — what the day was actually about — not a list.

5. WATCH TOMORROW is 1–3 statements a person can check against tomorrow's
   pages and mark true or false: "A date is set for the NRCAN demo", not
   "Keep an eye on AIMQC". Prefer items that follow from today's open threads.

6. Items already in the pre-resolved list go in resolved_today as given. Items
   in the pre-dropped list appear once more in their section with
   status=dropped and nowhere else.
```

### Step 5 — Call the model

Default: `claude-opus-4-6` (synthesis-heavy, reasoning depth pays).

**Use prompt caching** (`cache_control: { type: "ephemeral" }`) on the system prompt block. Daily synthesis often gets re-run (catch-up batches, `--reprocess`, multiple back-to-back days), and the Opus system prompt is large. A single batch covering 7-10 dates pays the system-prompt cost once instead of N times — ~80-90% discount on the cached portion for runs 2..N. The memory block lives in the user turn and is not cached.

### Step 6 — Validate

```yaml
date: "YYYY-MM-DD"
generated_at: ISO-8601
pages_analyzed: int
theme_of_day: string                      # NEW — one sentence
new_decisions:
  - decision, source_page_id, confidence
    status: new | carried | resolved | dropped        # NEW
    carried_since: "YYYY-MM-DD"?                       # NEW — required when status=carried
unresolved_questions:
  - question, context, source_page_id
    status, carried_since?                             # NEW — same rules
top_priorities:
  - priority, urgency, source_page_id
    status, carried_since?                             # NEW — same rules
resolved_today:                                        # NEW
  - item: string                          # the predecessor's wording, verbatim
    origin_date: "YYYY-MM-DD"             # the item's carried_since (first appearance)
    evidence_page_id: string | null       # null only for verdict-driven resolution
    evidence: string                      # page quote, or "verdict:{target_id} — {note}"
watch_tomorrow: [string]                               # NEW — 1..3 items
momentum_signals: [string]
key_entities_active:
  - name, entity_type, activity_summary
synthesis_notes: string
```

`source_page_id` on a carried item is the page that re-raised it today, or the predecessor's `source_page_id` when no page mentioned it.

Sanity:
- `pages_analyzed` matches the input bundle count.
- Every `source_page_id` exists in the input bundle, except on items with `status: carried` that no page mentioned (where it equals the predecessor's).
- `urgency` is one of `high | medium | low`.
- Every `status` is in the enum. When `previous` is null, every status is `new` and `resolved_today` is empty unless a verdict pre-resolved a weekly action.
- Every item with `status: carried` matches (normalised text) an item in the carry pool, and its `carried_since` equals the pool entry's.
- Every `resolved_today[].evidence_page_id` that is non-null exists in the input bundle; a null one requires `evidence` to begin with `verdict:`.
- Every `resolved_today[].item` matches a carry-pool or pre-resolved entry — the model cannot resolve what was never open.
- `watch_tomorrow` has 1 to 3 entries, each a complete sentence.
- `theme_of_day` is one sentence, non-empty.

On a sanity failure, retry once with the violations appended to the prompt; refuse the write on a second failure.

### Step 7 — Render the markdown

Format the JSON into a human-readable narrative using the template in `references/daily-md-template.md`. Sections in order:

```markdown
# Daily Intelligence — {date}

**Theme of the day:** {theme_of_day}

**{N} pages analyzed** · {resolved_count} resolved · {carried_count} carried · {new_count} new

## Synthesis Notes

{synthesis_notes}

## Resolved today

{for each resolved_today: "✓ {item} — open since {origin_date}; {evidence} ({evidence_page_id} link, or 'review verdict')"}
{if any item has status=dropped: "Dropped: {item} (since {carried_since})"}

## Top Priorities

{for each priority, urgency-emoji + text + source-page link; carried items end with "(carried since YYYY-MM-DD)"}

## New Decisions

{decisions with confidence pct + source page; carried items marked "(carried since YYYY-MM-DD)"}

## Unresolved Questions

{questions with context; carried items marked "(carried since YYYY-MM-DD)"}

## Momentum Signals

{plain bullets}

## Key Entities Active

{entities grouped by type, with activity_summary}

## Watch tomorrow

{watch_tomorrow as a checklist: "- [ ] {item}"}

---
*Generated {generated_at} from pages {ids}; predecessor {prev_date or "none"}*
```

Items with `status: dropped` are omitted from Top Priorities / New Decisions / Unresolved Questions and appear only on the "Dropped" line.

### Step 8 — Write the synthesis

```
notella-state log-synthesis {
  kind: synthesis.daily,
  date: {date},
  json: <validated>,
  md: <rendered markdown>,
  evidence: {
    pages_analyzed: N,
    resolved_count: len(resolved_today),
    carried_count: count(status == carried across the three lists),
    new_count:     count(status == new across the three lists)
  }
}
```

This single call:
- Writes `daily/{date}.json` and `daily/{date}.md` atomically
- Emits the `synthesis.daily` event with the evidence above
- Updates `state.json:last_synthesis_at.daily`

### Step 9 — Advance pages to archived

For each page in the input bundle:

```
notella-state advance-phase {page-id, to-phase: archived, by-actor: notella-daily-synthesis}
```

Each emits a `page.archived` event referencing this synthesis.

## Idempotency

- Re-running for a date with `daily/{date}.json` already present: no-op unless `--reprocess`.
- `--reprocess`: pass `reprocess: true` to `log-synthesis`, which overwrites and emits the `correction` event (`correction_type: reprocess`); do NOT re-archive pages (they stay archived from first run).
- `--reprocess` recomputes against the **same predecessor** (the most recent brief before `date`, not the one that happened to exist at first run — these are the same file unless a gap was back-filled, in which case the newer predecessor is correct). Verdict rows are re-read, so a verdict recorded after the first run is honoured on reprocess.
- Reprocessing a date does **not** cascade to later dailies. The day after still holds the `carried_since` and statuses it computed from the old version. If the reprocess changed what was open, reprocess the following dates explicitly, in order.

## Failure modes

| Failure                                                  | Behavior |
| -------------------------------------------------------- | -------- |
| No pages indexed for the date                            | Skip cleanly with `{status: "no-pages-for-date"}`. |
| Pages exist but none reach phase=indexed                 | Skip; orchestrator should run pipeline catch-up first. |
| Model returns inconsistent source_page_ids               | Refuse the write; surface diagnostics. |
| Single page in bundle (sparse day)                       | Run anyway; the brief is short; this is correct behavior. |
| No previous daily brief exists                           | First brief: carry pool is empty, every status is `new`, `resolved_today` is `[]`. Note "no predecessor" in the footer. |
| Previous brief predates the status fields (legacy shape) | Treat every item as `status: carried, carried_since: previous.date`. Legacy briefs are never rewritten. |
| `weekly/`, `monthly/` or `verdicts.ndjson` absent        | Proceed with empty context; not an error. |
| Model marks `carried` an item not in the pool            | Validation failure; retry once with the violation named; then refuse. |
| Model marks `resolved` without a page quote              | Validation failure (evidence empty or page id not in bundle); retry once; then refuse. |
| `watch_tomorrow` empty or > 3                            | Validation failure; retry once; then refuse. |
| Verdict `done` for an item no longer in any pool         | Ignore the verdict for this brief; it was already resolved or dropped earlier. |

## What this skill does NOT do

- Does not run on weekly or project scopes — those are `notella-weekly-synthesis` and `notella-project-synthesis`.
- Does not edit page artifacts.
- Does not modify the manifest.
- Does not write to `longitudinal/verdicts.ndjson` or the commitments ledger. It reads verdicts; `notella-review` records them; the ledger aggregator (orchestrator step 10) consumes `resolved_today` and verdicts to close commitments.
- Does not rewrite earlier dailies when a later brief resolves or drops an item. History stays as written; the resolution is recorded on the day it happened.

## Examples

### "Daily synthesis for 2026-05-02"

```
Pages found at phase=indexed for 2026-05-02: 4
Predecessor: daily/2026-05-01.json (3 decisions, 2 questions, 3 priorities open)
Open weekly actions from 2026-W17: 5 · verdicts since 2026-05-01: 1 (done)
Synthesizing with claude-opus-4-6...
Theme of the day: "Locking the AIMQC Sprint 3 scope before the NRCAN call."
Generated daily/2026-05-02.json — 2 resolved, 4 carried, 5 new
Generated daily/2026-05-02.md (1842 words)
Advanced 4 pages to phase=archived.
synthesis.daily event emitted (resolved_count=2, carried_count=4, new_count=5).
```

### "Re-synthesize today's brief"

```
daily/2026-05-02.json exists. Pass --reprocess to overwrite.
```

### "Daily synthesis for 2025-12-01" (first brief in the facility)

```
Pages found at phase=indexed for 2025-12-01: 4
Predecessor: none (first brief)
Synthesizing with claude-opus-4-6...
Generated daily/2025-12-01.json — 0 resolved, 0 carried, 9 new
```

## Reference files

- `references/daily-md-template.md` — markdown rendering template.
- `references/daily-intelligence-prompt.md` — full system + user prompt with adjusted input format and the memory block.
