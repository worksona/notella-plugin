---
name: notella-state
description: "The shared memory of the notella facility — handwritten note intelligence over time. Read, write, or validate `~/notella/` — manifest, page lifecycle, state.json, events, daily/weekly/monthly/project synthesis, longitudinal intelligence (themes snapshots, ledgers), activity log. Trigger on 'log this page', 'advance the phase of page X', 'tail the activity log', 'check notella-state health', 'validate notella', 'list pages', 'count pages by phase', 'get the manifest', 'rebuild the page index', 'init the notella facility', 'append to the verdicts ledger', 'get the previous themes snapshot', or any request that reads or writes `~/notella/`. Also trigger automatically whenever another notella-* skill (orchestrator, intake, classify, transcribe, first-pass, actions, diagram, sketch, table, composition, metadata, daily-synthesis, project-synthesis, weekly-synthesis, monthly-synthesis, themes, review, kanban) needs to read or write state — they route through this one. Init a new facility if `~/notella/manifest.yaml` doesn't exist."
---

# notella-state — the memory layer

## Purpose

Every `notella-*` skill depends on this one. `notella-state` is the *only* skill that reads and writes `~/notella/` directly; every other skill expresses intent ("write this classify.json for page X", "advance page X to phase=transcribed", "log a synthesis event") and this skill enforces schema, concurrency, and logging.

Without this skill, page artifacts drift from the index, two pipeline skills clobber the same page mid-stage, and the activity log stops being trustworthy.

## Finding the facility

The facility lives at `~/notella/`. There is exactly one per machine.

```bash
NOTELLA="${HOME}/notella"
test -f "${NOTELLA}/manifest.yaml" || echo "Not initialized"
```

If it doesn't exist:
- If the user asked a read-only question, say so and stop.
- If the user asked to log/intake/process, offer to run `init` (see Operations → init below).

## Schema

The canonical schema lives in `~/notella/SCHEMA.md`. This skill validates against that file. The two primary record kinds are **pages** (folders under `pages/{page-id}/`) and **events** (one JSON per file under `events/YYYY-MM-DD/`).

### Page record (folder)

A page folder always contains:

- `meta.yaml` — id, entry_id, phase, phase_history, source_filename, ingested_at, content_mix, confidence, tags, project_attributions, person_attributions, links_to[], errors[]
- `raw/page.{ext}` — immutable original photo
- `derived/page.jpg` — converted JPG (HEIC→JPG happens at intake)
- `derived/thumb.jpg` — thumbnail

Plus zero or more Layer-1 artifacts (`classify.json`, `transcribe.json`, `composition.json`, `diagram.json`, `sketch.json`, `table.json`) and zero or more Layer-2 artifacts (`metadata.json`, `first-pass.json`, `actions.json`).

The `phase` field in `meta.yaml` is the durable state. Allowed values, in order:

```
intake → classified → transcribed → first-pass-done → enriched → indexed → archived
```

### Event envelope

Every event is a JSON object with this shape:

```json
{
  "id": "page.transcribed-2026-05-02-a4b2c1",
  "kind": "page.transcribed",
  "timestamp": "2026-05-02T09:15:12Z",
  "page_id": "2026-05-02-x7k2",
  "entry_id": "ent_2026-05-02-aab1",
  "project_slug": null,
  "evidence": { "...": "kind-specific" },
  "ingested_at": "2026-05-02T09:15:13Z",
  "harvester_version": "notella-transcribe@0.1.0"
}
```

Required envelope fields:

| Field               | Type     | Notes |
| ------------------- | -------- | ----- |
| `id`                | string   | `{kind}-{date}-{hash}`. Deterministic. |
| `kind`              | enum     | See "Event kinds" below. |
| `timestamp`         | ISO-8601 | When the event happened (not when ingested). |
| `page_id`           | string?  | Required for all `page.*` kinds. |
| `entry_id`          | string?  | Optional. |
| `project_slug`      | string?  | Optional; one of `manifest.yaml:projects.*.slug` or null. |
| `evidence`          | object   | Kind-specific structured proof. |
| `ingested_at`       | ISO-8601 | When notella-state wrote the event. |
| `harvester_version` | string   | Semver of the calling skill. |

Refuse to write any event missing required fields.

### Event kinds

| Kind                   | Meaning                                         |
| ---------------------- | ----------------------------------------------- |
| `page.intake`          | A new page was minted from `inbox/`.            |
| `page.classified`      | classify.json written; route_plan determined.   |
| `page.transcribed`     | transcribe.json written.                        |
| `page.first-pass-done` | first-pass.json written.                        |
| `page.enriched`        | All route_plan'd specialists complete.          |
| `page.indexed`         | Entry / day / project attributions written.     |
| `page.archived`        | Page pulled into ≥1 daily synthesis.            |
| `synthesis.daily`      | A daily intelligence report was written.        |
| `synthesis.project`    | A project intelligence report was written.     |
| `synthesis.weekly`     | A weekly synthesis was written.                 |
| `synthesis.monthly`    | A monthly synthesis (month in review) was written. |
| `themes.refreshed`     | Longitudinal themes were rebuilt (a new snapshot under `longitudinal/themes/`). |
| `inbox.drained`        | The intake skill processed the inbox.           |
| `manifest.edited`      | The manifest was updated.                       |
| `correction`           | A correction to an earlier event/artifact. `evidence.correction_type` says which kind: `reprocess` (a synthesis overwritten with `--reprocess`), `review-verdict` (a human verdict recorded by `notella-review`; the same row is appended to `longitudinal/verdicts.ndjson`), or others defined by the emitting skill. |

## Operations

### `init` — first-time setup

Create `~/notella/` with the directory tree from SCHEMA.md, plus seed files:

```
~/notella/
├── manifest.yaml      ← copy from references/scaffold/; user fills in projects
├── state.json         ← copy; empty counters, null cursors
├── SCHEMA.md          ← copy
├── README.md          ← copy
├── CONCURRENCY.md     ← copy
├── inbox/
├── pages/
├── entries/
├── events/
├── daily/
├── weekly/
├── monthly/           ← monthly/{YYYY-MM}.{json,md}
├── projects/
├── longitudinal/
│   └── themes/        ← dated snapshots; longitudinal/themes.json is the latest copy
├── logs/
└── locks/
```

The skill carries reference copies of `manifest.yaml`, `state.json`, `SCHEMA.md`, `README.md`, `CONCURRENCY.md` under `references/scaffold/` and copies them into place. After init, log `facility.initialized` to `logs/activity.ndjson`.

### Read operations (no locking needed)

**get-manifest** → return parsed `manifest.yaml`.

**get-state** → return parsed `state.json`.

**get-page** `page-id` → return parsed `meta.yaml` plus a manifest of which artifacts exist (`{classify: true, transcribe: true, ...}`).

**get-page-artifact** `page-id` `artifact` → return parsed JSON for one of `classify | transcribe | composition | diagram | sketch | table | metadata | first-pass | actions`. Returns `null` if absent.

**list-pages** with optional filters: `phase`, `since`, `until`, `entry_id`, `project_slug`, `tag`, `limit`. Walks `pages/` and reads each `meta.yaml`; filters in memory; returns array.

**count-pages** with same filters as list-pages. Returns `{total, by_phase, by_project, by_entry}`.

**get-event** `id` → look up by id. The id encodes the date, so the file is at `events/YYYY-MM-DD/{id}.json`.

**list-events** with filters: `since`, `until`, `kind`, `page_id`, `project_slug`, `limit`.

**count-events** with same filters as list-events. Returns `{total, by_kind}`.

**get-entry** `entry-id` → return parsed `entries/{entry-id}/meta.yaml` plus the page list.

**get-daily** `date` → parsed `daily/YYYY-MM-DD.json` if it exists.

**list-dailies** → all dates with daily synthesis written.

**get-project-synthesis** `project-slug` `date?` `before?` → parsed `projects/{slug}/{date}.json`. If no date given, return the most recent; with `before: YYYY-MM-DD`, return the most recent brief dated strictly before that date (what `notella-project-synthesis` uses to find its predecessor on a same-day re-run).

**list-weeklies** → all ISO weeks with weekly synthesis written.

**get-weekly** `iso-week` → parsed `weekly/YYYY-Www.json` if it exists, else `null`.

**get-monthly** `YYYY-MM` → parsed `monthly/YYYY-MM.json` if it exists, else `null`.

**list-monthlies** → all `YYYY-MM` months with monthly synthesis written, ascending.

**get-longitudinal** `kind` → parsed `longitudinal/{kind}.json` (themes | trajectory | patterns). For `themes` this is the latest copy; use `get-themes-snapshot` to reach history.

**get-themes-snapshot** `date | latest | previous` → parsed snapshot from `longitudinal/themes/`, plus its `path`:

| Argument     | Returns |
| ------------ | ------- |
| `YYYY-MM-DD` | `longitudinal/themes/{date}.json`, or `null`. |
| `latest`     | The newest file in `longitudinal/themes/` (by filename date). |
| `previous`   | The newest file whose date is strictly before `latest`'s — i.e. the snapshot before the current one. `null` if only one exists. |

Migration: if `longitudinal/themes/` is empty or absent but a legacy `longitudinal/themes.json` exists, copy it to `longitudinal/themes/{its generated_at date}.json` first (atomic), then answer. `latest` then returns that file and `previous` returns `null`. Snapshots are never modified or deleted by any operation.

**read-ledger** `{file, since?, until?, kind?, limit?}` → parsed rows of `longitudinal/{file}.ndjson` where `file ∈ decisions | commitments | people | verdicts`. Rows are returned in file order; `since`/`until` filter on the row's `date` (decisions, commitments) or `ts` (verdicts); `kind` filters verdicts on `target_kind`; `people` ignores them. Returns `{status: "absent", rows: []}` rather than an error when the file does not exist, so callers can skip a section cleanly. Unparseable lines are skipped and counted in `skipped_lines`. `get-longitudinal {commitments | decisions | people | verdicts}` is accepted as a synonym and returns the rows.

**list-verdicts** `{since?, until?, kind?}` → `read-ledger {file: verdicts, ...}`. The name the synthesis skills and `notella-review` use. Consumers take the latest row per `target_id`.

**tail-activity** `n=50` → last n lines of `logs/activity.ndjson`, parsed.

**tail-pipeline** `n=50` → last n lines of `logs/pipeline.ndjson` (the old "queue page"), parsed.

**tail-llm-calls** `n=50` → last n lines of `logs/llm-calls.ndjson` (the old "history page"), parsed.

**validate** → walk every file in the facility, check schema conformance, report deviations. Never auto-fix. Specifically:

- Every page folder has a `meta.yaml` with a valid `phase`
- Every artifact required by the page's phase is present
- Every file in `events/YYYY-MM-DD/` matches an entry in `events/YYYY-MM-DD.jsonl`
- Counters in `state.json` match on-disk evidence
- No duplicate page or event ids
- All ids match their format (`page-id` = `{date}-{shortuuid4}`; `event-id` = `{kind}-{date}-{hash}`)
- No stale lockfiles older than 1 hour
- No orphaned page folders (every page has at least `meta.yaml` and `raw/`)
- Every `project_attribution` references a project in manifest, or is empty

### Write operations

**log-event** `event` (the highest-volume operation; uses optimistic per-event path)

```
1. Validate the event has all required envelope fields. Refuse if not.
2. Compute target path: events/YYYY-MM-DD/{id}.json from the event's timestamp.
3. If the target file already exists, return {status: "duplicate", id} silently. (Idempotent.)
4. Atomic write: write to {target}.tmp, fsync, rename to {target}.
5. Append the event to events/YYYY-MM-DD.jsonl (single-line JSON, < 4 KB).
6. Return {status: "written", id, path}.
```

Counters are NOT updated here — that's the batch-finalize step.

**log-page-artifact** `{page-id, artifact, payload}` — write a Layer-1 or Layer-2 artifact to `pages/{page-id}/{artifact}.json`.

```
1. Acquire page lock: locks/pages/{page-id}.lock with TTL 5 min.
2. Validate the page folder exists and meta.yaml is parseable.
3. Validate payload against the artifact's schema (artifact-specific validator).
4. Atomic write: pages/{page-id}/{artifact}.json.
5. Append a line to logs/pipeline.ndjson:
   {ts, actor, page_id, artifact, status: "written"}.
6. Release page lock.
7. Return {status: "written", path}.
```

**advance-phase** `{page-id, to-phase, by-actor}` — move a page from its current phase to `to-phase`, validating preconditions.

```
1. Acquire page lock.
2. Read meta.yaml.
3. Verify current phase is the immediate predecessor of to-phase.
4. Verify all artifacts required by to-phase are present.
5. Update meta.yaml: phase = to-phase; phase_history[to-phase] = now.
6. Atomic write meta.yaml.
7. log-event with kind = page.{to-phase}.
8. Release page lock.
```

If preconditions fail, return `{status: "blocked", missing: [...]}` without mutating.

**log-revision** `{page-id, content, author}` — append a transcript-edit revision to `pages/{page-id}/revisions/{ts}-{author}.json`. Append-only; revisions are immutable.

**log-pipeline-run** `{actor, page_id, artifact, status, duration_ms, error?}` — append to `logs/pipeline.ndjson`.

**log-llm-call** `{actor, page_id?, task, provider, model, tokens, latency_ms, status, prompt_excerpt?, error?}` — append to `logs/llm-calls.ndjson`.

**log-skill-run** `{skill, args, outcome, duration_ms}` — append to `logs/skills.ndjson`. No lock needed.

**finalize-batch** `{actor, kind, count, max_timestamp}` (called by intake/orchestrator at end of run)

Under the `state.json` lock:

```
1. Bump counters.events_total by count.
2. Bump counters.events_by_kind[kind] by count.
3. If kind == "page.intake" and count > 0: update last_intake_at to max_timestamp.
4. If first_intake_at is null: set to now.
5. Append to logs/activity.ndjson:
   {ts, actor, event: "events.batch.ingested", kind, count, max_timestamp}.
```

**log-synthesis** `{kind, date|week|month|project, json, md, evidence?, reprocess?}` — write the json + md pair to the appropriate location. `evidence` (optional object) is merged into the emitted `synthesis.*` event's `evidence`; the synthesis skills pass their counts (resolved/carried/new, focus outcomes, …) here:

| kind                | Path                                          |
| ------------------- | --------------------------------------------- |
| `synthesis.daily`   | `daily/{date}.{json,md}`                      |
| `synthesis.weekly`  | `weekly/{iso-week}.{json,md}`                 |
| `synthesis.monthly` | `monthly/{YYYY-MM}.{json,md}`                 |
| `synthesis.project` | `projects/{project-slug}/{date}.{json,md}`    |

Update `state.json:last_synthesis_at.{daily,weekly,monthly,by_project[slug]}` under the lock. Emit a corresponding event via `log-event`. If the target json already exists, refuse unless the caller passes `reprocess: true`, in which case overwrite both files and also emit a `correction` event (`evidence.correction_type: "reprocess"`, `evidence.target: <path>`).

**log-longitudinal** `{kind, json, md?}` — for `kind: themes`:

```
1. date = json.generated_at as a calendar date in identity.timezone
2. Atomic write longitudinal/themes/{date}.json         (tmp + rename; same-day rerun overwrites that day's file only)
3. Atomic copy  → longitudinal/themes.json              (the latest pointer; byte-identical to step 2)
4. Atomic write longitudinal/themes.md from md          (required for themes; refuse the whole write if md is missing so the md can never lag the json)
5. Update state.json:last_longitudinal_at under the lock
6. Emit themes.refreshed (evidence as passed by the caller: counts, snapshot_path, previous_snapshot, delta_counts)
```

For `kind: trajectory | patterns` the behaviour is unchanged: write `longitudinal/{kind}.json`, update `last_longitudinal_at`, emit `themes.refreshed`. Earlier snapshots under `longitudinal/themes/` are never touched.

**append-ledger** `{file, row}` — append one JSON row to `longitudinal/{file}.ndjson`, `file ∈ decisions | commitments | people | verdicts`.

```
1. Validate row is a JSON object and serialises to a single line < 4 KB. Refuse otherwise.
2. Open with O_WRONLY | O_APPEND | O_CREAT; write the line + "\n"; close. No lock (POSIX atomic append, as for the logs).
3. Return {status: "appended", path, line_no}.
```

Append-only: there is no edit or delete operation for ledger rows. A row that supersedes an earlier one is a new row (for `verdicts`, a later verdict on the same `target_id` wins). The desktop aggregator rebuilds `decisions`, `commitments` and `people` wholesale with tmp + rename; `append-ledger` is for incremental writers such as `notella-review` on `verdicts`.

**log-verdict** `{row}` → `append-ledger {file: verdicts, row}` after checking the row has `ts, target_kind, target_id, target_text, verdict`. Does not emit the `correction` event — the caller (`notella-review`) logs that itself via `log-event` with `evidence.correction_type: "review-verdict"`, so a duplicate verdict is caught by the event id before the ledger is touched.

**update-manifest** `{add_projects?: [{slug, name, description, keywords}], add_people_aliases?: [{canonical, aliases}], set?: {facility.owner|facility.timezone: value}}` — the only sanctioned manifest write. Takes `locks/manifest.yaml.lock`, validates slug format `^[a-z0-9][a-z0-9-]{1,40}$` and uniqueness, never removes or renames existing entries, writes tmp + rename, appends `manifest.edited` to `activity.ndjson` with the fields changed and a `manifest.yaml.bak-{date}` backup path. Callers (orchestrator project discovery, notella-review) must hold an explicit user confirmation before calling it.

**write-log** `{path, content}` — overwrite a rendered view under `logs/` (today only `logs/review-pending.md`) with tmp + rename. `path` must be inside `logs/` and must not be one of the append-only `.ndjson` files; refuse otherwise. Views are not evidence and are not logged to `activity.ndjson`.

**rebuild-events-index** `date` — read every JSON file in `events/YYYY-MM-DD/`, regenerate `events/YYYY-MM-DD.jsonl`. Use when the index is missing or corrupted.

**rebuild-state-counters** — walk every page and every event, recompute counters from scratch, write `state.json`. Use when the file is corrupted or counters drift. Slow; not a daily operation.

**rebuild-page-index** — re-derive `state.json:counters.pages_by_phase` by walking `pages/*/meta.yaml`.

### Page-lock operations

**acquire-page-lock** `{page-id, actor}` → atomic create `locks/pages/{page-id}.lock` with `{actor, acquired, ttl_seconds: 300}`. Returns `{status: "acquired"}` or `{status: "held", actor, expires_at}`.

**release-page-lock** `{page-id, actor}` → delete `locks/pages/{page-id}.lock` if `actor` matches. Returns `{status: "released"}` or `{status: "not-held"}`.

### Canonical write events (logged to activity.ndjson)

| Operation                            | Event name                       |
| ------------------------------------ | -------------------------------- |
| Facility initialized                 | `facility.initialized`           |
| Single event written                 | (not logged individually)        |
| Page artifact written                | (not logged individually)        |
| Phase advanced                       | (the page.{phase} event covers it) |
| Batch ingested                       | `events.batch.ingested`          |
| Synthesis written                    | `synthesis.{daily,weekly,monthly,project}.generated` |
| Longitudinal rebuilt                 | `longitudinal.{kind}.rebuilt` (evidence carries `snapshot_path`) |
| Ledger row appended                  | (not logged individually)        |
| Validation run                       | `state.validated`                |
| Index rebuilt                        | `index.rebuilt`                  |
| State counters rebuilt               | `state.counters.rebuilt`         |
| Manifest edited                      | `manifest.edited`                |

## Concurrency discipline (enforced from CONCURRENCY.md)

- **Per-event writes are lock-free** — deterministic ids + atomic file creation = idempotent, safe, parallel.
- **state.json and manifest.yaml writes use advisory lockfiles** — `locks/state.json.lock`, `locks/manifest.yaml.lock`, 5-minute TTL.
- **Per-page writes use a per-page lock** — `locks/pages/{page-id}.lock`, 5-minute TTL. Held for one stage's duration.
- **Append-only logs and ledgers use O_APPEND** — `logs/*.ndjson`, `events/*.jsonl`, and `longitudinal/{decisions,commitments,people,verdicts}.ndjson`; single-line writes < 4 KB are atomic per POSIX.
- **Atomic renames for singletons** — `tmp + rename`, never overwrite in place. This includes `longitudinal/themes.json` (copied from the dated snapshot) and the aggregator's wholesale ledger rebuilds.
- **Snapshots are immutable** — files under `longitudinal/themes/` are written once per refresh day and never edited or removed.
- **Idempotency is mandatory** — every operation must be safe to retry.

## What this skill does NOT do

- **Does not intake.** That's `notella-intake`.
- **Does not run any AI prompt.** That's per-agent skills (`notella-classify`, `notella-transcribe`, etc.).
- **Does not generate digests, reports, or syntheses.** That's `notella-daily-synthesis`, `-weekly-synthesis`, `-monthly-synthesis`, `-project-synthesis`, `-themes`.
- **Does not judge.** Review verdicts are decided by the user in `notella-review`; this skill only appends the row and the `correction` event.
- **Does not classify, attribute, or rename projects.** Accepts whatever the caller passes; reattribution comes via correction events.
- **Does not delete pages or events.** Evidence is immutable. Period.
- **Does not advance a page's phase autonomously.** The caller (a pipeline skill or the orchestrator) requests the advance after writing the required artifact.

## Examples

### "Init the facility"

```
1. Confirm ~/notella/ does not exist.
2. Create directory tree.
3. Copy references/scaffold/* → ~/notella/.
4. Append facility.initialized to logs/activity.ndjson.
5. Return {status: "initialized", path: "~/notella"}.
```

### "Log a transcribe.json for page 2026-05-02-x7k2"

Caller (`notella-transcribe`) calls `log-page-artifact` with the validated payload. notella-state acquires the page lock, writes the artifact, appends to pipeline.ndjson, releases the lock.

### "Advance page 2026-05-02-x7k2 to phase=transcribed"

Caller calls `advance-phase` with `to-phase: "transcribed"`. notella-state checks: current phase is `classified`, `classify.json` exists, `transcribe.json` exists. If all green, updates meta.yaml and emits `page.transcribed` event.

### "What pages are stuck in classified?"

```
list-pages --phase=classified
```

The orchestrator uses this to find pages that need `notella-transcribe` to run.

### "How many pages did I capture this week broken down by project?"

```
count-pages --since=2026-04-26 --until=2026-05-03 → {total, by_phase, by_project, by_entry}
```

### "Get the previous themes snapshot"

```
get-themes-snapshot previous → {path: "longitudinal/themes/2026-05-09.json", json: {...}}
```

`notella-themes` measures its delta against this; `notella-monthly-synthesis` uses it for `theme_arc` start weights.

### "Record a verdict"

Caller (`notella-review`) calls `log-event` with `kind: correction`, `evidence.correction_type: "review-verdict"` and the row as evidence; when that returns `written` (not `duplicate`) it calls `log-verdict {row: {ts, target_kind, target_id, target_text, verdict, note, source_ref}}`, which appends to `longitudinal/verdicts.ndjson`.

### "Validate the facility"

Walks every invariant from CONCURRENCY.md → "Invariants the validator enforces". Returns a report. Never auto-fixes.

## Reference files

- `references/scaffold/manifest.yaml` — template manifest copied into place on `init`
- `references/scaffold/state.json` — initial empty state.json
- `references/scaffold/SCHEMA.md` — canonical schema, copied into the facility
- `references/scaffold/README.md` — facility README, copied into place
- `references/scaffold/CONCURRENCY.md` — concurrency doc, copied into place

If the reference files are missing, the SKILL.md instructions above are self-sufficient.
