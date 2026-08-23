---
name: notella-project-synthesis
description: "Produce a project intelligence report for a notella project — timeline, commitments assessment, drift signals, blockers, momentum, recommended next actions, risk summary. Use whenever the user says 'synthesize project X', 'how is Project Atlas going', 'project intelligence brief for X', 'project health check for X', or any request to consolidate every page attributed to a project. Reads through `notella-state`; writes `projects/{slug}/{date}.{json,md}`. Emits `synthesis.project` event."
---

# notella-project-synthesis — the project intelligence brief

Reads every page attributed to a project (in any time window) and produces a project health assessment.

## Purpose

Provide a project-level operational picture: where the project started, where it is now, what's on track, what's drifting, what's blocked, what's the strongest signal of momentum, what's the biggest risk. Grounded strictly in the page corpus.

## Inputs and outputs

**Input:** A project slug (and optional `--since`/`--until` time window). Reads every page where `meta.yaml:project_attributions` contains the slug.

**Output:**
- `projects/{slug}/{date}.json` — `ProjectIntelligenceSchema` (where `{date}` is today's date in the user's timezone)
- `projects/{slug}/{date}.md` — narrative rendering
- `synthesis.project` event with `project_slug` set
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

### Step 3 — Build the prompt

Use notella-the-app's `PROJECT_INTELLIGENCE_SYSTEM` and `buildProjectIntelligencePrompt()` from `src/lib/prompts/project-intelligence.ts` verbatim. Pass `projectName` from `manifest.projects.<slug>.name`. Pass the chronological bundle as `analysesJson`.

### Step 4 — Call the model

Default: `claude-opus-4-6`.

### Step 5 — Validate

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
```

Sanity:
- Every commitment's `evidence` appears in at least one source page.
- `pages_analyzed` matches the input bundle count.

### Step 6 — Render the markdown

Sections: title with project name and date, executive paragraph (synthesis notes), Timeline, Commitments table, Drift Signals, Blockers, Momentum, Next Actions, Risk Summary, footer with source page-ids and date range.

### Step 7 — Write the synthesis

```
notella-state log-synthesis {
  kind: synthesis.project,
  project_slug: {slug},
  date: <today>,
  json, md
}
```

Updates `state.json:last_synthesis_at.by_project[slug]`. Does NOT advance any page phases (project synthesis is incremental — each run consumes the current state but doesn't archive pages, since they're still active in the project).

## Idempotency

- Re-running the same day for the same project: overwrites today's file (last-writer-wins).
- Re-running on a future day creates a new file under that date.
- The `projects/{slug}/` folder accumulates one file per synthesis run; older briefs are evidence of the project's evolution.

## Failure modes

| Failure                                              | Behavior |
| ---------------------------------------------------- | -------- |
| Slug not in manifest                                 | Abort with status=unknown-project; suggest the user add it. |
| Project has only 1 page                              | Run anyway; the brief is sparse; surface a note. |
| Pages span > 6 months                                | Use the full window unless `--since` is set; the timeline_summary should reflect the extended history. |
| Most pages lack first-pass.json                      | Abort with status=blocked; orchestrator runs pipeline catch-up first. |

## What this skill does NOT do

- Does not modify pages.
- Does not edit the manifest.
- Does not aggregate across multiple projects — one slug per call.
- Does not perform task tracking or assignment — only proposes next_actions with optional owners.

## Examples

### "Synthesize project-sunshine"

```
Pages attributed to project-sunshine: 14 (2026-04-12 → 2026-05-02)
Synthesizing with claude-opus-4-6...
Generated projects/project-sunshine/2026-05-02.json (7 sections, 4 commitments, 2 blockers)
Generated projects/project-sunshine/2026-05-02.md (2104 words)
Overall risk: moderate
synthesis.project event emitted.
```

### "Project synthesis for project-sunshine since 2026-04-15"

Filters the page list to that window. Same output shape; brief reflects the narrower scope.

## Reference files

- `references/project-intelligence-prompt.md` — full prompt.
- `references/project-md-template.md` — markdown rendering.
