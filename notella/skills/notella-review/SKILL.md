---
name: notella-review
description: "The human verdict loop for the notella facility. Shows a short list of what the notebook left open — yesterday's watch items, questions carried for days, commitments older than two weeks, last week's unscored focus, last month's watchlist, pages whose photo looks upside down / sideways / mirrored or is poor quality, photos held in the inbox as possible duplicates, and newly distilled principles — and records a one-word answer for each: done, drop, carry or wrong (pin for principles). Use whenever the user says 'notella review', 'morning review', 'review notella', 'what did I say I would do', 'close out notella items', 'mark done in notella', 'review held imports', 'review image problems', 'confirm my principles', or any request to confirm, close or correct items the syntheses are tracking. Writes `longitudinal/verdicts.ndjson` and `correction` events through `notella-state`. `--report` mode asks nothing and writes `logs/review-pending.md` for the orchestrator's unattended runs."
---

# notella-review — the human verdict loop

The one place a human verdict enters the facility. Every other skill infers; this one asks. It shows a short list, takes one word per item, and writes the answers where the daily, weekly, monthly and project syntheses and the commitments ledger will find them.

## Purpose

The syntheses now carry memory — items are `carried`, `resolved`, `dropped` — but a model reading notebook pages can only see what was written down. Work finished off the page, intentions quietly abandoned, and misread handwriting all look the same: an item that keeps being carried. Without a verdict the facility cannot tell signal from noise, and its forecasts (`watch_tomorrow`, `suggested_focus`, `next_month_watchlist`) are never scored.

This skill costs the person about two minutes. No model call is made; it is a list and a ledger.

## Inputs and outputs

**Input:** Optional flags:
- `--date YYYY-MM-DD` — the review date (default today). "Yesterday" means the most recent daily brief before this date.
- `--report` — report mode: build the list, write it, ask nothing. The orchestrator uses this in `--auto` runs.
- `--max N` — cap on items shown (default 15).

Mode is `interactive` by default when a person is present; `--report` forces report mode.

**Reads (through `notella-state`):**

| Source | What is taken |
| --- | --- |
| most recent `daily/{d}.json` with `d < date` | `watch_tomorrow[]`; `unresolved_questions[]` with status `carried` and `carried_since` ≥ 3 days before `date` |
| `longitudinal/commitments.ndjson` | rows with `state` in `proposed | owner_confirmed | in_progress` and `source_date` older than 14 days, oldest first |
| latest `weekly/*.json` whose week has closed | `suggested_focus[]` items not yet scored (no `focus_scorecard` row for them in a later weekly, and no `focus` verdict) |
| latest `monthly/{YYYY-MM}.json`, when the month it forecasts has closed | `next_month_watchlist[]` items without a `forecast` verdict |
| `longitudinal/verdicts.ndjson` | existing verdicts, so nothing already answered is shown again |
| `pages/*/quality.json` | pages with `orientation.status == suspected` or `grade == poor` (skipping `duplicate_of` pages) |
| `inbox/_held/*.held.json` | held photos with `decision: held_near` (exact duplicates are not asked about — identical bytes need no judgement) |
| `longitudinal/principles.json` | principles with `confirmed: false` and `status ≠ retired` |

**Writes:**
- `longitudinal/verdicts.ndjson` — one row per verdict, append-only
- one `correction` event per verdict via `notella-state log-event`, `evidence.correction_type: "review-verdict"`
- `logs/review-pending.md` — the pending list, in `--report` mode (overwritten each run)
- a `logs/skills.ndjson` line via `log-skill-run`
- side effects of image and held-import verdicts, through `python3 "$CLAUDE_PLUGIN_ROOT/scripts/notella_images.py"` (no model call): `fix` on an image `done`, `scan --force` on an image `wrong`, `release` on a held-import `wrong`

## The list

Built in this order, each group capped so the whole list stays at `--max` (default 15); a large backlog in one group (for example a hundred pages flagged by the first image scan) shows its oldest items and a "… and N more" line, and `notella-images` handles the backlog in bulk. Items already carrying a verdict are skipped; items whose text hashes to an existing verdict's `target_id` are the same item.

1. **Watch items** — yesterday's `watch_tomorrow`. Verdict `done` means "this happened"; `drop` means "it did not and no longer matters"; `carry` keeps it in view; `wrong` means it was never a sensible thing to watch.
2. **Stale questions** — `unresolved_questions` carried ≥ 3 days.
3. **Old commitments** — ledger rows open for more than 14 days, oldest first. This is usually the longest group; it fills whatever room the first two leave.
4. **Unscored focus** — the last closed week's `suggested_focus`, when the following weekly has not scored it yet or scored it `no_evidence`.
5. **Month watchlist** — the last monthly's `next_month_watchlist`, once that month has ended.

Each line shows: index, kind tag, the item text, where it came from and how old it is.

```
Notella review — 2026-05-06 (yesterday: 2026-05-05)

 1. [watch]      A date is set for the NRCAN Sprint 3 demo              daily/2026-05-05
 2. [watch]      Persistence architecture decision written up            daily/2026-05-05
 3. [question]   Which project has the highest Q1 milestone risk?        carried since 2026-01-02 (124 days)
 4. [commitment] Draft AIMQC Q1 feature roadmap for NRCAN review         proposed 2026-01-02, owner David (124 days)
 5. [commitment] AI Compute: requirements + Robson responsibilities       proposed 2026-04-09, owner Robson (27 days)
 6. [focus]      Write the Sprint 3 scope for AIMQC with dates           weekly/2026-W18 — no evidence in W19
 7. [forecast]   Pharmaliga onboarding starts before month end           monthly/2026-04
 8. [image]      2026-04-09-y534: rotate 180 (classify-legacy, stamp-position)   pages/2026-04-09-y534
 9. [held]       IMG_4422.HEIC ≈ 2026-04-09-75hq (distance 3)               inbox/_held/
10. [principle]  Ship, not spec.                                          principles · 6 pages since 2026-01-01

Answer each with: done | drop | carry | wrong   (add a note after a dash; principles also take pin)
```

Two further groups come from the orchestrator and appear only when present:

6. **Pipeline attention** — pages whose `first-pass` run logged three or more sanity warnings in `logs/pipeline.ndjson` (possible hallucinated entities or ungrounded actions). Verdict `wrong` queues `first-pass --reprocess` for that page; `carry` leaves it.
7. **Project-discovery proposals** — candidate projects the orchestrator wrote to `logs/review-pending.md` under `--auto` (it never edits the manifest alone). Verdict `done` means "add to manifest.yaml" and is carried out through `notella-state update-manifest`; `drop` records the slug in `state.json:discovery_declined[]` so it is not proposed again.

Three more groups come from the image tooling and the principles skill, after the groups above:

8. **Image attention** — pages whose `quality.json` says the photo is mis-oriented (`orientation.status: suspected`) or `grade: poor`. The line shows the suggestion and its sources (`rotate 180 · stamp-position`), or "needs a look", and the quality warnings. Before answering, the person can open `derived/thumb.jpg`.
   - `done` — it is wrong and should be (or has been) fixed. When the page is still `suspected` with a concrete suggestion, review applies it: `notella_images.py fix --page ID --rotate R --flip F`, then prints the reprocess chain (transcribe → L1 → first-pass → actions `--reprocess`, then the daily) for a transcribed page. With no suggestion, `done` records that the person fixed it with `notella-images`. For a poor photo, `done` means "acknowledged — re-photograph"; nothing is changed.
   - `wrong` — false alarm: the page is upright / the photo is fine. Review then runs `notella_images.py scan --pages ID --force`; the scan reads this verdict and sets the orientation to `ok` with source `review-cleared`, so it is not flagged again (and transcription is no longer gated).
   - `carry` — keep it on the list. `drop` is treated as `carry` for images.
9. **Held imports** — photos in `inbox/_held/` held as **near** duplicates of an existing page (`held_near`). The line shows the held file, the page it resembles and the distance.
   - `done` — it is a duplicate. It stays in `_held/`; whether to delete it is the person's call (review never deletes).
   - `wrong` — not a duplicate. Review runs `notella_images.py release NAME`; the next inbox drain mints it, and `hold` will not hold it again.
   - `carry` — decide later. `drop` is treated as `done`.
10. **Proposed principles** — principles `notella-principles` distilled that nobody has confirmed yet, each shown once. Verdicts as that skill defines them: `done` confirms (a note `rename: <text>` rewords it), `wrong` retires it, `carry` keeps it proposed, and the extra verb **`pin`** pins it to the Today screen; `drop` is treated as `wrong`. Review only records the verdict; the next principles refresh applies it.

## Verdict vocabulary

| Verdict | Meaning | Ledger effect (aggregator) |
| --- | --- | --- |
| `done`  | It happened / was answered / was delivered. | commitment → `done` |
| `drop`  | It will not happen and should stop being tracked. | commitment → `abandoned` |
| `carry` | Still live; keep showing it. | unchanged |
| `wrong` | The item is a misreading of the page or a model artefact; it never existed as stated. | commitment → `abandoned`, with the note |
| `pin`   | Principles only: show this principle every day. | none (read by `notella-principles`) |

Image, held-import and principle items reinterpret the four words as described in groups 8–10.

Optional free text after a dash: `done — shipped Tuesday`, `wrong — that was a quote, not a task`. The note is stored verbatim.

## How a run executes

### Step 1 — Resolve the date and gather sources

```
date       = --date or today
yesterday  = max(d for d in notella-state list-dailies if d < date)   # null → no watch/question group
daily      = notella-state get-daily {yesterday}
ledger     = notella-state read-ledger {file: commitments}            # {status: "absent"} → []
weekly     = latest closed week in notella-state list-weeklies; get-weekly for it and, if present, the next week
monthly    = notella-state get-monthly {last of list-monthlies}       # null if none
verdicts   = notella-state read-ledger {file: verdicts}               # all rows; {status: "absent"} → []
```

### Step 2 — Build the candidate list

For each candidate compute `target_kind`, `target_text`, `target_id`, `source_ref`, `age_days`:

| Kind | `target_text` | `target_id` | `source_ref` |
| --- | --- | --- | --- |
| `watch`      | the `watch_tomorrow` string | `hash(target_text)` | `daily/{yesterday}.json#watch_tomorrow[i]` |
| `question`   | the `question` string | `hash(target_text)` | `daily/{yesterday}.json#unresolved_questions[i]` |
| `commitment` | the ledger row's `task` | the ledger row's `task_id` | `longitudinal/commitments.ndjson#{task_id}` |
| `focus`      | the `suggested_focus` string | `hash(target_text)` | `weekly/{iso-week}.json#suggested_focus[i]` |
| `forecast`   | the watchlist item's `prediction` | the watchlist item's `id` (`YYYY-MM-w{n}`, minted by the monthly) | `monthly/{YYYY-MM}.json#next_month_watchlist[i]` |
| `image`      | `"{page_id}: {rotate R flip F \| needs a look} ({sources}); {warnings}"` | the page id | `pages/{page_id}/quality.json` |
| `held_import`| `"{held name} ≈ {page_id} (distance d)"` | the first 16 hex of the held file's sha256 | `inbox/_held/{name}.held.json` |
| `principle`  | the principle's `statement` | the principle's `id` | `longitudinal/principles.json#{id}` |

Four kinds therefore carry an id minted elsewhere (`commitment` from the ledger, `forecast` from the monthly brief, `principle` from the principles record, `image` = the page id); `held_import` is keyed by content so a renamed file keeps its verdict; the other three are keyed by their text.

**`hash(text)`** is the same function the ledger aggregator uses for `task_id`, so a commitment seen through a daily brief and the same commitment seen in the ledger share one id:

```
norm = lowercase(text); replace every run of non-[a-z0-9] with one space; trim
h = 0x811c9dc5
for each byte c of norm:
  h = h XOR c
  h = (h * 16777619) mod 2^32          # FNV-1a 32-bit
target_id = h as 8-digit lowercase hex
```

Drop every candidate whose `target_id` already has a verdict row (any verdict, any date) — except `carry`, which expires: a `carry` older than 7 days no longer hides the item. Order the groups as listed above, truncate to `--max`. If more items exist than fit, end the list with "… and N more; run again or raise --max".

### Step 3a — Report mode (`--report`)

Render the list as markdown and write it:

```
notella-state write-log {path: logs/review-pending.md, content: <list>}   # tmp + rename; no lock
```

Print the same list and stop. No verdicts are written. The orchestrator includes the file in its Phase D report so the person sees it next time they are present.

### Step 3b — Interactive mode

Print the list. Accept answers in either form:

- one line per item, in order (`done`, `carry`, `drop — not this quarter`, …), an empty line meaning "skip the rest";
- or indexed (`3 done`, `4 drop — superseded by Sprint 3 plan`), any order; unanswered items are skipped.

An answer whose first word is not in the vocabulary is rejected once with "answer with done, drop, carry or wrong"; a second unknown answer skips the item. Skipped items are not written and will be shown again next run.

### Step 4 — Write each verdict

For each answered item, in list order:

```
row = {
  ts:          now (ISO-8601),
  target_kind: commitment | question | focus | watch | forecast | image | held_import | principle,
  target_id:   <as computed>,
  target_text: <verbatim>,
  verdict:     done | drop | carry | wrong | pin,
  note:        <free text after the dash, or null>,
  source_ref:  <as computed>
}

event = {
  id:        "correction-{date}-{hash6}",       # hash6 = first 6 hex of hash("{target_id}|{verdict}|{date}")
  kind:      "correction",
  timestamp: row.ts,
  page_id:   null,
  entry_id:  null,
  project_slug: null,
  evidence:  { correction_type: "review-verdict", ...row },
  harvester_version: "notella-review@0.1.0"
}

result = notella-state log-event {event}
if result.status == "written":
  notella-state append-ledger {file: verdicts, row}   # one line appended to longitudinal/verdicts.ndjson
else:
  skip the row (duplicate)                        # same (target_id, verdict, date) already recorded
```

The event is written first because `log-event` is the idempotency gate: its deterministic id means the same verdict on the same item on the same day is recorded once, however many times the command runs. The ndjson row is appended only when the event was new.

Then, only for a newly written row, the side effects of groups 8 and 9 (all through `python3 "$CLAUDE_PLUGIN_ROOT/scripts/notella_images.py"`, no model call; failures are reported and do not undo the verdict):

| Item | Verdict | Command |
| --- | --- | --- |
| `image`, still suspected with a suggestion | `done` | `fix --page {id} --rotate R --flip F` (the suggestion shown on the line) |
| `image` | `wrong` | `scan --pages {id} --force` (the scan reads the verdict → `ok`, `review-cleared`) |
| `held_import` | `wrong` | `release {held name}` |

`--report` mode records nothing and therefore runs nothing.

### Step 5 — Report

```
notella-review 2026-05-06: 7 shown, 6 answered, 1 skipped
  done 3 · drop 1 · carry 1 · wrong 1
  verdicts.ndjson +6 · correction events +6
Next: run notella-orchestrator --only-step 10 (ledgers) to apply done/drop to the commitments ledger.
```

Then `notella-state log-skill-run {skill: notella-review, args, outcome, duration_ms}`.

## Downstream consumers

Verdicts are read, never rewritten, by:

- **notella-daily-synthesis** — `done` moves an item into `resolved_today` with `evidence: "verdict:{target_id} — {note}"`; `drop` gives it a final appearance with `status: dropped`; `wrong` removes it from the carry pool silently; `carry` changes nothing.
- **notella-weekly-synthesis** — `focus` verdicts settle `focus_scorecard` rows (`done` → `happened`; `drop`/`wrong` → `no_evidence` with the note; `carry` → `no_evidence` and re-suggested); `commitment`/`question` verdicts close `action_items_open` entries.
- **notella-monthly-synthesis** — `forecast` (and `watch`) verdicts fix rows of the following month's `forecast_scorecard`: `done` → `held`, `wrong` → `missed`, `carry` → still open, `drop` → unknown with evidence "dropped at review"; commitment verdicts feed `commitments_aging` and the closed/dropped counts.
- **notella-project-synthesis** — `commitment` verdicts retire commitments in `since_last.commitments_changed` (`done` → `done`, `drop` → `dropped`, `wrong` → `removed`).
- **notella-images** (`scan`) — the latest `image` verdict per page: `wrong` clears the orientation suspicion (`review-cleared`).
- **notella-principles** — `principle` verdicts: `done` confirms, `wrong`/`drop` retires, `pin` pins, `carry` keeps.
- **the ledger aggregator** (orchestrator step 10) — for `target_kind: commitment`, maps `done` → `done`, `drop` → `abandoned`, `wrong` → `abandoned` with `state_evidence` set to the note, `carry` → unchanged. A verdict always outranks the aggregator's substring inference.

## Idempotency

- Append-only. Nothing in `verdicts.ndjson` is ever edited or removed; a changed mind is a new row with a later `ts`, and consumers take the latest row per `target_id`.
- Deterministic event id over `(target_id, verdict, date)`: re-running the same answers the same day writes nothing new. A different verdict for the same item on the same day is a new row (different id).
- `--report` overwrites `logs/review-pending.md` in place (tmp + rename); it is a view, not evidence.

## Failure modes

| Failure | Behavior |
| --- | --- |
| `longitudinal/commitments.ndjson` missing or empty | Skip the commitment group; say "ledger not built — run orchestrator step 10". Other groups still show. |
| Ledger rows in the legacy shape (no `task_id`) | Compute `hash(description)` and treat `description` as `task`; note "legacy ledger" once. |
| No previous daily brief | Skip watch and question groups; say so. |
| No weekly or monthly files | Skip those groups silently. |
| Previous daily predates `watch_tomorrow` / `status` fields | Skip the watch group; treat every `unresolved_questions` item as carried since the brief's date. |
| Nothing to show | Print "Nothing pending for review." and stop; in `--report` mode write that one line to `logs/review-pending.md`. |
| User answers with an unknown word | Ask again once for that item; on a second unknown answer skip it. |
| User answers an index that is not on the list | Ignore that line; report it as skipped. |
| `log-event` returns `duplicate` | Expected on re-runs; skip the ndjson row; count it as "already recorded". |
| `verdicts.ndjson` absent on first write | `append-ledger` creates it (`O_CREAT`). |
| No `quality.json` anywhere (images never scanned) | Skip the image group; say "run notella-images scan". |
| `notella_images.py` fails on a side effect (no sips, page locked) | The verdict stays recorded; report the failed command so the person can run it. |
| A held file named in `_held/` has no `.held.json` note | Show it with "reason unknown"; `wrong` still releases it. |
| `pin` given for a non-principle item | Rejected like an unknown word. |
| `principles.json` absent | Skip the principles group silently. |

## What this skill does NOT do

- **Does not call a model.** The list is assembled deterministically from existing syntheses and the ledger.
- Does not edit `daily/`, `weekly/`, `monthly/` or `projects/` files. A verdict takes effect in the next synthesis that reads it.
- Does not rewrite `commitments.ndjson`. The aggregator applies verdicts on its next run.
- Does not invent items. Everything shown has a `source_ref` to a file the facility already wrote.
- Does not run syntheses or the orchestrator; it tells the person what to run next.
- Does not delete or amend a verdict. Evidence is immutable; correct a verdict by recording a new one.
- Does not delete held photos or pages, and never reprocesses a fixed page itself — it prints the chain.

## Examples

### "Morning review"

```
Notella review — 2026-05-06 (yesterday: 2026-05-05)

 1. [watch]      A date is set for the NRCAN Sprint 3 demo              daily/2026-05-05
 2. [question]   Which project has the highest Q1 milestone risk?        carried since 2026-01-02 (124 days)
 3. [commitment] Draft AIMQC Q1 feature roadmap for NRCAN review         proposed 2026-01-02, owner David (124 days)
 4. [focus]      Write the Sprint 3 scope for AIMQC with dates           weekly/2026-W18 — no evidence in W19

Answer each with: done | drop | carry | wrong   (add a note after a dash)

> done — demo set for May 14
> drop — Q1 is over
> done
> carry

notella-review 2026-05-06: 4 shown, 4 answered, 0 skipped
  done 2 · drop 1 · carry 1
  verdicts.ndjson +4 · correction events +4
```

### "Notella review --report" (from the orchestrator)

```
Review pending: 11 items → logs/review-pending.md
  watch 2 · question 1 · commitment 6 · focus 2
```

### "Mark done in notella: the NRCAN roadmap"

Build the list, find the item whose text matches, record `done` for it alone, confirm:

```
Recorded done for [commitment] "Draft AIMQC Q1 feature roadmap for NRCAN review" (task_id 3f9a1c2e).
```

If no item matches, say so and show the list.

## Reference files

None. The SKILL.md is self-sufficient; the `hash` function and the verdict row shape above are the specification other skills align to.
