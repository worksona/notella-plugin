# Stuck-page rules

When `notella-orchestrator` treats a page as stuck, what it does about it at each age, and when it auto-archives (checklist step 9).

## Definition

A page is **stuck** when it has not changed phase for longer than the threshold for its phase **and** the orchestrator cannot advance it in the current run (its gate fails, or its last invocation errored). A page that simply has not been processed yet because the orchestrator has not run is *pending*, not stuck; pending pages are the normal queue.

```
hours_in_phase = now - meta.yaml:phase_history[current phase]
last_error      = meta.yaml:errors[-1] if any, with its timestamp
stuck           = hours_in_phase > threshold(phase) AND (gate_fails OR last_error.timestamp > phase_history[phase])
```

## Thresholds by phase

| Phase | Threshold | Why |
| --- | --- | --- |
| `intake` | 4 h | classify is a Haiku call; anything older means the decode or lock failed |
| `classified` | 4 h | same for transcribe |
| `transcribed` | 8 h | L1 fan-out is five specialists; one failing blocks first-pass |
| `first-pass-done` | 24 h | actions may legitimately wait a run |
| `enriched` | 24 h | advance to indexed is free; if it did not happen, mirrors are missing |
| `indexed` | 72 h | waits for daily synthesis; dailies run once a day, and a date may have late pages |
| `archived` | — | terminal |

`--max-pages` backlog does not count: a page excluded from a run by the cap gets `phase_history` untouched but the orchestrator records `deferred_at` in `state.json:deferred[page_id]`; the stuck clock for that page starts from the last run that *could* have taken it.

## Escalation ladder

| Age past threshold | Action |
| --- | --- |
| 0 – 1× threshold | **Retry.** Re-queue the failed stage in this run. Most sticks are transient (rate limit, lock timeout). |
| 1× – 3× threshold | **Retry with help.** Re-queue with `--reprocess` for the failing stage; for vision stages, re-verify `derived/page.jpg` (`heic-conversion.md` checks) and re-decode from `raw/` if it fails. Surface in the plan under "Stuck pages". |
| 3× threshold – 7 days | **Surface, do not retry automatically.** List in plan and report with the last error. Under `--auto`, write the list to `logs/review-pending.md` so `notella-review` shows it. A human decides: fix the photo, `--reprocess` with a stronger model, or archive. |
| > 7 days (168 h) | **Auto-archive** (step 9). `notella-state advance-phase {to: archived, by-actor: notella-orchestrator, reason: "stuck > 7d at <phase>"}`. The page keeps every artifact it has; `meta.yaml:errors` keeps the history; a `page.archived` event with `evidence.stuck: true` is emitted. Synthesis skips it (archived pages without a daily are excluded from I-8 when `evidence.stuck` is set). |

Auto-archive is the only destructive-looking action the orchestrator takes alone, and it is not destructive: nothing is deleted and `notella-state advance-phase {to: <previous phase>, reason: "unstick"}` reverses it. The report always lists auto-archived pages by id so the morning reader sees them.

## What is not stuck

- A page at `indexed` whose date's daily has not run because today is that date (dailies run for closed days).
- A page at `transcribed` waiting on a specialist whose model is disabled in `cost-controls.yaml:skill_toggles` — the orchestrator writes a stub for a disabled specialist (same as a below-threshold skip) and proceeds; it is *configuration*, not a stick.
- A page blocked by the daily budget cap. `budget-paused` is recorded in `state.json`, the clock pauses, and the next run under the cap resumes.
- A page whose lock is held by a live process (another orchestrator run, a manual skill invocation). Wait; `integrity-rules.md` I-12 reaps dead locks.

## Common sticks and their fixes

| Symptom | Likely cause | Fix |
| --- | --- | --- |
| `classify` errors `image too small` | thumbnail or screenshot dropped in inbox | re-photograph; archive the page |
| `transcribe` confidence < 0.3 three runs running | rotated or blurred decode | `notella-intake --redecode`, then `transcribe --reprocess` |
| `diagram` returns invalid JSON twice | page is a dense whiteboard photo | `--reprocess --model=claude-opus-4-6` once; else accept a stub |
| `first-pass` blocked, `composition` missing | composition errored on `visual_element_ids` referencing a missing artifact | run the missing specialist (or stub it), then composition |
| `metadata` loops on `date-normalization-failed` | the page's date is genuinely unreadable | accept `date: null`; the capture-time fallback is correct |
| page at `enriched` for days | mirrors not written because metadata errored | re-run `metadata`; advance |

## Reporting

Plan and report sections:

```
Stuck pages (3):
  - 2026-04-28-m2q7  transcribed  19h   diagram: invalid JSON ×2       → retry --reprocess
  - 2026-03-02-k8x1  intake       3d    classify: image too small       → needs human (review-pending.md)
  - 2026-01-02-02h0  transcribed  9d    composition: missing diagram.json → auto-archived this run
```

`notella-state list-pages --is-stuck --hours-stuck N` is the query behind it.

## Orientation-blocked pages are not stuck

A page held at `phase=classified` because its `quality.json` orientation is `suspected` with a concrete suggestion (the transcribe gate, `integrity-rules.md` G-transcribe) is waiting for a person, not failing. It is excluded from the stuck clock while it is listed in `logs/review-pending.md` under "Image attention" — it is never auto-archived for that reason. The clock starts again from the moment it is fixed (`orientation_fix.applied_at`) or cleared in review.
