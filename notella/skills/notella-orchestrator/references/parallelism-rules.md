# Parallelism rules

What `notella-orchestrator` may fan out concurrently and what it must serialise. The constraint model is simple: **one writer per page at a time** (the per-page lock in `notella-state`), **one writer per synthesis file**, and **append-only logs that tolerate interleaving**. Everything else is a throughput or budget choice.

## The lock model

- `notella-state acquire-page-lock {page-id, actor}` is exclusive. Two specialists for the *same* page cannot hold it at once.
- L1 specialists (composition, metadata, diagram, sketch, table) for the same page are therefore **not** truly simultaneous at the write step: each acquires the lock, writes its artifact, releases. Their model calls — the slow part — overlap freely because the lock is taken only around the write. The SKILL.md's "fan out concurrently" means: launch the five calls together, serialise only the ~50 ms writes.
- Across pages there is no shared lock; parallelism is bounded only by API rate limits and the budget.
- Synthesis files (`daily/{date}`, `weekly/{week}`, `projects/{slug}/{date}`, `longitudinal/themes/*`, `monthly/{month}`) are written through `notella-state log-synthesis`, which takes a file-level lock. Two dailies for different dates run in parallel; two runs for the same date cannot.
- `activity.ndjson`, `pipeline.ndjson`, `llm-calls.ndjson`, `events/` are append-only, one JSON per line/file, written with O_APPEND or tmp+rename. Interleaving is safe.

## Safe to fan out

| Work | Parallel across | Notes |
| --- | --- | --- |
| classify | pages | Haiku; 10–20 at once is fine |
| transcribe | pages | Sonnet vision; 6–8 at once keeps under typical rate limits |
| L1 fan-out (composition, metadata, diagram, sketch, table) | specialists **and** pages | the five specialists for one page launch together; writes serialise on the page lock automatically |
| first-pass | pages | after the integrity gate; benefits from a shared cached system prompt — launch them within the 5-minute cache window |
| actions | pages | same |
| advance enriched / indexed | pages | metadata-only; trivially parallel |
| daily synthesis | dates | Opus; 2–3 at once — these are the expensive calls and the budget guard is per-call |
| weekly synthesis | weeks | 2 at once; usually only one is due |
| project synthesis | slugs | 2–3 at once |
| ledgers aggregation | — | single process; runs after dailies |
| image scan (`notella_images.py scan`) | pages | one process; it runs its own pool (one worker per CPU, `sips` is the bottleneck) |

## Must serialise

| Order | Reason |
| --- | --- |
| classify → transcribe → L1 → first-pass → actions → enriched → indexed **per page** | phase order; each stage reads the previous artifact |
| **all L1 for a page → first-pass for that page** | the integrity gate (`integrity-rules.md` G-first-pass) |
| metadata for the batch → project discovery → (if confirmed) `metadata --reprocess` → first-pass | first-pass reads canonical slugs; running it before backfill means re-running it |
| daily synthesis for a date → weekly for the week containing it | weekly reads dailies |
| weekly for the weeks in a month, themes refresh → monthly synthesis | monthly reads weeklies and the themes delta |
| inbox check → hold → intake (step 1) | the hold moves duplicates out of `inbox/` before intake enumerates it |
| intake → image scan → classify **per page** | classify reads `quality.json`'s orientation suggestion; the scan takes the page lock, so it runs after intake releases it |
| classify's orientation fix → re-classify → transcribe **per page** | the fix rebuilds `derived/page.jpg`; transcribe must read the corrected image |
| themes refresh → principles refresh (step 7) | principles read the fresh snapshot's `conceptual_evolution` |
| daily → ledgers aggregation (step 10) | ledgers read `daily/*.json:new_decisions` and `actions.json` |
| everything → review (step 11) | review reads the run's outputs and `logs/review-pending.md` |
| themes refresh | one at a time, globally — it writes the themes pointer |
| stuck-page auto-archive | after pipeline catch-up (a page may have been unstuck this run) |

## Concurrency limits

Defaults; overridable per run with `--concurrency N` (applies to the vision and synthesis pools separately as `N` and `max(1, N/3)`):

| Pool | Default | Governing constraint |
| --- | --- | --- |
| Haiku calls (classify, composition, metadata) | 12 | rate limit |
| Sonnet vision calls (transcribe, diagram, sketch, table) | 8 | rate limit, image upload bandwidth |
| Sonnet text calls (first-pass, actions) | 8 | cache window — keep the batch inside 5 minutes |
| Opus synthesis (daily, weekly, project, themes, monthly) | 3 | cost; the budget guard checks `cost-controls.yaml` before each call |

When the budget guard returns `on_breach: hard` the Opus pool drops to 0 and the run finishes pipeline work only.

## Two orchestrators at once

Possible when the inbox watcher fires during a scheduled run. Safe by construction: page locks prevent double-writes; both runs read the same state and will *plan* overlapping work, but the second to reach a page finds the lock held, waits up to 30 s, then skips it (`lock-held` in its report). To avoid the waste, the orchestrator takes a facility-level advisory lock `locks/orchestrator.lock` (pid + started_at) at Phase C start; a second run that finds a live lock exits with `{status: "another-run-active", pid}` unless invoked with `--force`. A dead lock (pid gone) is reaped (`integrity-rules.md` I-12).

## Failure isolation

- A failed specialist on one page never cancels others in the same stage. Collect; continue; report.
- A failed stage (every page in it errored — usually an API outage) stops *subsequent stages for those pages* but not synthesis for dates whose pages are already indexed.
- A failed daily does not block other dailies; it does block the weekly that contains it (weekly would be incomplete; I-9 would flag it next run anyway).
- A failed themes refresh blocks monthly for this run (monthly needs the delta); monthly is re-planned next run.

## Order of a full `--auto` run, as executed

```
A  plan (read-only; integrity checks; cost estimate)
C1 inbox drain                                   serial
C2 classify ×N  →  transcribe ×N  →  L1 ×5×N  →  [discovery]  →  first-pass ×N  →  actions ×N  →  advance
C3 daily ×D        (parallel ≤3)
C4 weekly ×W       (parallel ≤2)
C5 project ×P      (parallel ≤3)
C6 themes          (single)
C7 monthly ×M      (single, after C6)
C8 stuck-page archive
C9 ledgers aggregation (decisions, commitments, people)
C10 review (--report under --auto)
D  report; state.json:last_orchestrator_run
```
