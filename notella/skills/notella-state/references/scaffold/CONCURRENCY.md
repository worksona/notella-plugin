# CONCURRENCY — `~/notella/`

The notella facility may be touched by multiple actors at once: an inbox drain triggered manually, a pipeline catch-up running through several pages in parallel, a synthesis skill reading pages while another finishes enriching them, ad-hoc skill invocations from inside Claude. This document defines the rules that keep them from clobbering each other.

## Actors

- **Intake skill** (`notella-intake`) — drains `inbox/`, mints page-ids, creates page folders, writes initial `meta.yaml` at `phase=intake`. Logs `page.intake` events.
- **Pipeline skills** (`notella-classify`, `notella-transcribe`, `notella-first-pass`, `notella-actions`, `notella-diagram`, `notella-sketch`, `notella-table`, `notella-composition`, `notella-metadata`) — read a page in a specific phase, write one artifact, request phase advance. Each holds the per-page lock for its stage's duration.
- **Synthesis skills** (`notella-daily-synthesis`, `notella-weekly-synthesis`, `notella-project-synthesis`, `notella-themes`) — read pages and write derived files in `daily/`, `weekly/`, `projects/`, `longitudinal/`.
- **Foundation skill** (`notella-state`) — the only skill allowed to mutate `state.json`, `manifest.yaml`, `logs/`, page artifacts, and event files. Every other skill routes through it.
- **Reader skills** — read-only over pages + events + derived files.
- **Orchestrator** (`notella-orchestrator`) — schedules other skills, never writes state directly.

## File classes & their concurrency rules

| Class                         | Examples                                         | Rule                                  |
| ----------------------------- | ------------------------------------------------ | ------------------------------------- |
| **Append-only logs**          | `logs/activity.ndjson`, `logs/pipeline.ndjson`, `logs/llm-calls.ndjson`, `events/YYYY-MM-DD.jsonl` | Open with `O_APPEND`. POSIX guarantees atomic writes for entries up to `PIPE_BUF` (4096 bytes on macOS/Linux). Lines are bounded; no lock needed. |
| **Per-event JSON files**      | `events/YYYY-MM-DD/*.json`                        | Write-once. Filename is deterministic (id-based); the second writer with the same id is a no-op. No lock needed. |
| **Page artifact files**       | `pages/{id}/*.json`, `pages/{id}/meta.yaml`      | Per-page lock + atomic rename. See "Per-page write protocol" below. |
| **Page revisions**            | `pages/{id}/revisions/*.json`                    | Append-only (one file per revision). Filename is `{ts}-{author}.json`. No lock needed. |
| **Singleton mutable files**   | `state.json`, `manifest.yaml`                    | Singleton lockfile + atomic rename. See "Singleton write protocol" below. |
| **Derived files**             | `daily/*.{md,json}`, `weekly/*.{md,json}`, `projects/{slug}/*.{md,json}`, `longitudinal/*.json` | Single writer per file; lock + atomic rename. Last-writer-wins is acceptable since these are regenerable. |

## Singleton write protocol

For any mutation to `state.json`, `manifest.yaml`, or a singleton derived file:

```
1. Check lock:   read locks/<target>.lock
                 if exists and (acquired + ttl_seconds) > now: WAIT (up to 30s) or ABORT
2. Acquire:      atomic-create locks/<target>.lock with {actor, acquired, ttl_seconds: 300}
                 (atomic-create = open with O_CREAT|O_EXCL, refuses if exists)
3. Read current: load target file (or treat as empty)
4. Stale check:  if caller passed base_last_modified and current.last_modified > base: CONFLICT
5. Mutate:       apply changes in memory
6. Atomic write: write to <target>.tmp, fsync, rename to <target>
7. Append log:   logs/activity.ndjson += {ts, actor, event, ...}
8. Release:      delete locks/<target>.lock
```

If the actor crashes between step 2 and step 8, the lockfile is left behind. The TTL (5 minutes) makes it self-healing: any subsequent actor sees the lock as expired and proceeds. `notella-state validate` reports stale locks but does not auto-clear them.

## Per-page write protocol

Pipeline skills write artifacts and advance phases on a page. To prevent two stages clobbering each other (e.g. classify and intake re-running concurrently on a stuck page), each page has its own lock at `locks/pages/{page-id}.lock`.

```
1. Check lock:   read locks/pages/{page-id}.lock
                 if exists and (acquired + ttl_seconds) > now and actor != mine: WAIT or ABORT
2. Acquire:      atomic-create locks/pages/{page-id}.lock with {actor, acquired, ttl_seconds: 300, stage: <stage>}
3. Read meta:    load pages/{page-id}/meta.yaml
4. Phase check:  verify the page's current phase is the expected predecessor for this stage
                 (e.g. transcribe expects phase=classified)
5. Write artifact: write the artifact JSON to pages/{page-id}/{artifact}.json (atomic tmp + rename)
6. Advance phase: update meta.yaml: phase = <new-phase>; phase_history[<new-phase>] = now
                  atomic write meta.yaml
7. Append log:   logs/pipeline.ndjson += {ts, actor, page_id, artifact, status, duration_ms}
8. Emit event:   log-event with kind=page.<new-phase>
9. Release:      delete locks/pages/{page-id}.lock
```

The lock is held for the full stage — read meta, write artifact, advance phase, emit event — so a concurrent caller can't observe a half-written state.

## Per-event writes — the optimistic path

Event writes use deterministic ids and atomic file creation; no lock needed.

```
1. Compute deterministic id: {kind}-{date}-{hash(canonical_payload)}.
2. Compute path: events/YYYY-MM-DD/{id}.json.
3. If the path exists, this event was already written — skip silently. (Re-running a pipeline run is safe and idempotent.)
4. Otherwise, write atomically (tmp + rename).
5. Append the event to events/YYYY-MM-DD.jsonl (under O_APPEND, single line).
```

After a batch of events (e.g. a full inbox drain that emits N `page.intake` events), the calling skill takes the `state.json` lock once via `notella-state finalize-batch` to bump counters and the cursor. One lock, not N.

## Idempotency

Every operation must be idempotent.

- Re-running intake on the same source file produces zero new pages — the page-id is deterministic over EXIF capture-time + file-content-hash, so a second attempt finds the page folder already exists.
- Re-running a pipeline stage on a page already past that phase: the skill should detect the artifact is present and skip, OR overwrite is permitted only with explicit `--reprocess` flag (which writes a new revision, never overwriting blindly).
- Re-running a synthesis with the same date: last-writer-wins, but the activity log shows both runs.

## Append-only logs in detail

`logs/activity.ndjson`, `logs/pipeline.ndjson`, `logs/llm-calls.ndjson`, and `events/YYYY-MM-DD.jsonl` are append-only:

- Never rewrite. Never truncate. Corrections go in via new entries.
- Each line is bounded to **< 4 KB** to stay within `PIPE_BUF` for atomic appends. If a payload would exceed that, write the heavy data to a separate file and put a reference in the log.
- Writers open with `O_WRONLY | O_APPEND`, write a single line ending in `\n`, close.
- Readers can race writers freely (POSIX guarantees no torn lines for sub-`PIPE_BUF` writes).

## Conflict resolution

If a caller passes `base_last_modified` and discovers the file has moved on:

1. Caller receives `CONFLICT` with the current `last_modified`.
2. Caller is responsible for deciding: re-read, re-merge, retry. `notella-state` does not auto-merge.
3. For derived files (`daily/`, `weekly/`, `projects/`, `longitudinal/`), conflicts are usually benign — last writer wins, regenerable.
4. For `state.json`, conflicts on counter updates retry automatically (up to 3 times, 100ms backoff).
5. For page `meta.yaml`, the per-page lock should make conflicts rare; if one occurs, the caller must reload, validate phase, and retry.

## Stuck pages and orphaned locks

A page is **stuck** if it has been in the same phase for > 4 hours without an error logged. The orchestrator surfaces stuck pages and offers to:
- Re-queue (acquire the lock if expired, retry the next stage)
- Mark errored (write to `meta.yaml:errors`)
- Open `meta.yaml` for inspection

A lock is **orphaned** if its TTL has expired. `notella-state validate` reports orphaned locks; they self-heal as new actors arrive (atomic-create succeeds because the lockfile is treated as absent past TTL).

## What can go wrong, what we do about it

| Failure                                              | Outcome                                                       |
| ---------------------------------------------------- | ------------------------------------------------------------- |
| Pipeline skill crashes mid-stage                     | Page artifact partially written? No — atomic rename means it's all-or-nothing. Lock orphaned but self-healing. Phase not advanced. Re-run is safe. |
| Two pipeline skills run the same stage concurrently  | Per-page lock blocks the second. The first completes; the second sees phase already advanced and either skips or proceeds to the next stage. |
| Two intakes drain the inbox concurrently             | Page-id is deterministic; both write the same id; second is a no-op. Both write inbox.drained events; one is a duplicate id. Counters stay correct. |
| Lockfile orphaned by a killed process                | TTL expires after 5 min; next actor proceeds. `notella-state validate` reports the stale lock. |
| `state.json` corrupted (partial write)               | Atomic rename prevents this. If it happens anyway: `notella-state rebuild-state-counters` walks pages and events to reconstruct. |
| `events/YYYY-MM-DD.jsonl` corrupted                  | `notella-state rebuild-events-index YYYY-MM-DD` regenerates from per-event JSONs. |
| `pages/{id}/meta.yaml` corrupted                     | The page is unrecoverable from on-disk artifacts alone unless you keep raw + derived. The orchestrator surfaces it as errored; a manual `meta.yaml` rebuild is supported. |
| `manifest.yaml` edited by hand into invalid YAML     | Every skill that loads it fails fast. `notella-state validate` reports. |

## Invariants the validator enforces

- Every page folder in `pages/` has a `meta.yaml` with a valid `phase`.
- Every artifact required by the page's phase is present (e.g. phase=transcribed → classify.json AND transcribe.json present).
- Every file in `events/YYYY-MM-DD/` appears as a line in `events/YYYY-MM-DD.jsonl`.
- Every line in `events/YYYY-MM-DD.jsonl` corresponds to a file in `events/YYYY-MM-DD/`.
- `state.json:counters.pages_total` equals the count of `pages/*/meta.yaml`.
- `state.json:counters.pages_by_phase[X]` equals the count of pages with `phase=X`.
- No two page folders share an `id`.
- No two event files share an `id`.
- All page-ids match the pattern `{date}-{shortuuid4}`.
- All event-ids match the pattern `{kind}-{date}-{hash}`.
- Every event references a `page_id` that exists, OR has `page_id: null` (synthesis events).
- Every `project_attribution` references a project in manifest.
- Lockfiles older than 1 hour are reported as suspicious.
- Page lockfiles whose actor is no longer running (best-effort) are flagged.
