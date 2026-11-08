---
name: notella-project-synthesis
description: "Produce a project intelligence report for a notella project — timeline, commitments assessment, what changed since the last brief, drift signals, blockers, momentum, recommended next actions, risk summary. Use whenever the user says 'synthesize project X', 'how is Project Atlas going', 'project intelligence brief for X', 'project health check for X', 'what changed on X since last time', or any request to consolidate every page attributed to a project. Reads the previous brief for the slug and any review verdicts on its commitments through `notella-state`; writes `projects/{slug}/{date}.{json,md}`. Emits `synthesis.project` event."
---

# notella-project-synthesis — the project intelligence brief

Reads every page attributed to a project (in any time window), plus the previous brief for that project, and produces a project health assessment that says what moved since last time.

## Purpose

Provide a project-level operational picture: where the project started, where it is now, what's on track, what's drifting, what's blocked, what's the strongest signal of momentum, what's the biggest risk. Grounded strictly in the page corpus.

The `projects/{slug}/` folder already accumulates one brief per run. What it lacked was a delta: each brief re-assessed every commitment from scratch, so a commitment that went from `on_track` to `blocked` was two unrelated sentences in two files. `since_last` makes that transition a first-class fact, and lets a human verdict (`done`, `drop`, `wrong`) retire a commitment instead of having the model re-litigate it every run.

## Inputs and outputs

**Input:** A project slug (and optional `--since`/`--until` time window). Reads every page where `meta.yaml:project_attributions` contains the slug.

**Context inputs** (optional):

| Input | Source | Role |
| --- | --- | --- |
| Previous brief | the latest `projects/{slug}/{d}.json` with `d` strictly before today (may be null) | Baseline for `since_last` |
| Review verdicts | `longitudinal/verdicts.ndjson` rows with `target_kind: commitment` whose `target_id` equals `task_id(commitment)` for any commitment in the previous brief, with `ts` after the previous brief's `generated_at` | `done`/`drop`/`wrong` retire a commitment; `carry` leaves it |

`task_id(text)` is the commitments-ledger hash defined in `notella-review` (lowercase, collapse non-alphanumerics to single spaces, trim, FNV-1a 32-bit hex). The same function keys the ledger, so a verdict given on a ledger row and a verdict given on a brief's commitment text meet when the wording matches.

**Output:**
- `projects/{slug}/{date}.json` — `ProjectIntelligenceSchema` (where `{date}` is today's date in the user's timezone; every pre-existing field kept; `since_last` added)
- `projects/{slug}/{date}.md` — narrative rendering
- `synthesis.project` event with `project_slug` set and `evidence: {pages_analyzed, pages_added, commitments_changed, risk_delta}`
- `state.json:last_synthesis_at.by_project[slug]` updated

## How a run executes

### Step 1 — Read configuration & pages

```
notella-state get-manifest → manifest.model_defaults.project_synthesis, manifest.projects.<slug>
notella-state list-pages --project={slug} --since=<since?> --until=<until?>
```

Verify the slug exists in `manifest.projects`. If not, abort with `{status: "unknown-project", slug}`. (The orchestrator can suggest adding it.)

If the page list is empty, abort with `{status: "no-pages-for-project"}`.

### Step 2 — Read each page's record

```
notella-state get-page-artifact {page-id, artifact: first-pass}
notella-state get-page-artifact {page-id, artifact: actions}        # optional
notella-state get-page-artifact {page-id, artifact: metadata}
```

Sort by date (metadata.date or fallback chain). Build the input bundle ordered chronologically — the timeline matters for project synthesis.

### Step 3 — Read the previous brief and its verdicts

```
previous = notella-state get-project-synthesis {slug}                  # most recent; null if none
           # if its date == today (same-day re-run), take the most recent file dated before today instead:
           # get-project-synthesis {slug, date: <latest earlier date in projects/{slug}/>}
verdicts = notella-state read-ledger {file: verdicts, since: previous.generated_at}   # {status: "absent"} → []
           filtered to target_kind == commitment
           and target_id ∈ { task_id(c.commitment) for c in previous.commitments_assessment }
```

Compute before the model is called:

- `pages_added` = pages in the bundle whose `meta.yaml:ingested_at` is after `previous.generated_at`. (Ingest time, not page date — a late upload of an older page is still new to the brief.)
- **Retired commitments** — previous commitments with a `done` verdict (to_status `done`), a `drop` verdict (to_status `dropped`), or a `wrong` verdict (to_status `removed`, with the note). These are passed to the model as "do not re-assess; already settled" and listed in `since_last.commitments_changed` with `evidence: "verdict:{target_id} — {note}"`.
- **Baseline** — the remaining previous commitments with their statuses, previous `drift_signals`, previous `overall_risk_level`.

### Step 4 — Build the prompt

Use notella-the-app's `PROJECT_INTELLIGENCE_SYSTEM` and `buildProjectIntelligencePrompt()` from `src/lib/prompts/project-intelligence.ts` as the base. Pass `projectName` from `manifest.projects.<slug>.name`. Pass the chronological bundle as `analysesJson`.

Append a **memory block** with the baseline, the retired commitments, `pages_added` and `previous_brief_date`, and this guidance:

```
A previous brief exists. Continue it:

- For every baseline commitment, reuse its wording verbatim and re-assess its
  status from the pages. If the status changed, say which page shows the change.
- Do not re-list retired commitments. Do not resurrect a commitment marked
  wrong.
- A drift signal is new only if the previous brief did not name it (same
  substance, any wording).
- since_last.note is one or two sentences on what the delta means — the
  single most important change, or "no material change" if that is true.
```

When `previous` is null, omit the block; the brief is a first assessment.

### Step 5 — Call the model

Default: `claude-opus-4-6`.

### Step 6 — Validate

```yaml
project_name: string
project_slug: string
generated_at: ISO-8601
date_range: { since, until }
pages_analyzed: int
timeline_summary: string                  # 2-4 sentences
commitments_assessment:
  - commitment: string
    owner: string?                        # optional
    status: on_track | at_risk | blocked
    evidence: string
drift_signals: [string]
blockers: [string]
momentum_assessment: string               # one paragraph
next_actions:
  - action: string
    priority: high | medium | low
    owner: string?
risk_summary: string                      # one paragraph
overall_risk_level: low | moderate | high | critical
since_last:                               # NEW — null when no previous brief
  previous_brief_date: "YYYY-MM-DD"
  pages_added: int
  commitments_changed:
    - commitment: string                  # previous wording, verbatim
      from_status: on_track | at_risk | blocked
      to_status: on_track | at_risk | blocked | done | dropped | removed
      evidence: string                    # page quote + page-id, or "verdict:{task_id} — {note}"
  new_drift_signals: [string]             # subset of drift_signals absent from the previous brief
  risk_delta: up | same | down            # ordinal compare of overall_risk_level
  note: string
```

Derivations applied after the model returns:
- `since_last.risk_delta` from `low < moderate < high < critical` against `previous.overall_risk_level`. Computed here, not asked of the model.
- `since_last.commitments_changed` is checked, not trusted: every baseline commitment whose status differs between `previous` and the new `commitments_assessment` must have a row; retired commitments must have a row; no other rows are allowed.
- A commitment in `commitments_changed` with `to_status` in `done | dropped | removed` must be absent from `commitments_assessment`.

Sanity:
- Every commitment's `evidence` appears in at least one source page (or begins with `verdict:` in `since_last` rows).
- `pages_analyzed` matches the input bundle count.
- Every `since_last.new_drift_signals[]` is in `drift_signals` and matches nothing in `previous.drift_signals` (normalised text).
- `since_last` is null if and only if no previous brief exists.

On a sanity failure, retry once with the violations named; refuse the write on a second failure.

### Step 7 — Render the markdown

Sections: title with project name and date, executive paragraph (synthesis notes), **Since last brief**, Timeline, Commitments table, Drift Signals, Blockers, Momentum, Next Actions, Risk Summary, footer with source page-ids and date range.

```markdown
## Since last brief ({previous_brief_date})

{note}

- Pages added: {pages_added}
- Risk: {previous level} → {current level} ({risk_delta})
- Commitments changed:
  - {commitment}: {from_status} → {to_status} — {evidence}
- New drift signals:
  - {signal}
```

When `since_last` is null the section reads "First brief for this project; no predecessor." Commitments retired by verdict render with "(review verdict)" in place of a page link.

### Step 8 — Write the synthesis

```
notella-state log-synthesis {
  kind: synthesis.project,
  project_slug: {slug},
  date: <today>,
  json, md,
  evidence: {pages_analyzed, pages_added, commitments_changed: len(...), risk_delta}
}
```

Updates `state.json:last_synthesis_at.by_project[slug]`. Does NOT advance any page phases (project synthesis is incremental — each run consumes the current state but doesn't archive pages, since they're still active in the project).

## Idempotency

- Re-running the same day for the same project: overwrites today's file (last-writer-wins). The predecessor is still the latest brief dated **before** today — never today's own earlier output — so the delta stays anchored to the last distinct day.
- Re-running on a future day creates a new file under that date, with `since_last` relative to the newest earlier file.
- The `projects/{slug}/` folder accumulates one file per synthesis run; older briefs are evidence of the project's evolution and are never rewritten.

## Failure modes

| Failure                                              | Behavior |
| ---------------------------------------------------- | -------- |
| Slug not in manifest                                 | Abort with status=unknown-project; suggest the user add it. |
| Project has only 1 page                              | Run anyway; the brief is sparse; surface a note. |
| Pages span > 6 months                                | Use the full window unless `--since` is set; the timeline_summary should reflect the extended history. |
| Most pages lack first-pass.json                      | Abort with status=blocked; orchestrator runs pipeline catch-up first. |
| No previous brief for the slug                       | `since_last: null`; the memory block is omitted. |
| Previous brief predates `since_last` (legacy shape)  | Still a valid baseline: its `commitments_assessment`, `drift_signals` and `overall_risk_level` are all that is needed. |
| `pages_added == 0` and no verdicts since last brief  | Run anyway if invoked explicitly; `note` should say "no new pages". The orchestrator's staleness check is what normally prevents this run. |
| Model reassesses a retired commitment                | Validation failure (present in `commitments_assessment` while `to_status` is done/dropped/removed); retry once; then refuse. |
| Model rewords a baseline commitment                  | Row in `commitments_changed` cannot be matched; validation fails; retry once naming the pair; then refuse. |
| `--since` narrows the window below the previous brief's | `since_last` still compares against the previous brief as written; note the window difference in `note`. |

## What this skill does NOT do

- Does not modify pages.
- Does not edit the manifest.
- Does not aggregate across multiple projects — one slug per call.
- Does not perform task tracking or assignment — only proposes next_actions with optional owners.
- Does not write to the commitments ledger or `verdicts.ndjson`. It reads verdicts; `notella-review` records them; the ledger aggregator owns `commitments.ndjson`.

## Examples

### "Synthesize project-sunshine"

```
Pages attributed to project-sunshine: 14 (2026-04-12 → 2026-05-02)
Previous brief: projects/project-sunshine/2026-04-25.json (4 commitments, risk moderate)
Verdicts on its commitments since then: 1 (done)
Pages added since previous brief: 5
Synthesizing with claude-opus-4-6...
Generated projects/project-sunshine/2026-05-02.json (8 sections, 3 commitments, 2 blockers)
  since last: 1 commitment done (verdict), 1 on_track → at_risk, 1 new drift signal, risk moderate → high (up)
Generated projects/project-sunshine/2026-05-02.md (2104 words)
Overall risk: high
synthesis.project event emitted.
```

### "Project synthesis for project-sunshine since 2026-04-15"

Filters the page list to that window. Same output shape; brief reflects the narrower scope; `since_last` still compares with the 2026-04-25 brief.

### First brief for a new slug

```
Pages attributed to allsafe: 2
Previous brief: none
Generated projects/allsafe/2026-05-08.json — since_last: null
```

## Reference files

- `references/project-intelligence-prompt.md` — full prompt including the memory block.
- `references/project-md-template.md` — markdown rendering.
