# notella-project-synthesis — prompt

The complete project-synthesis prompt, self-contained in the plugin. It is the app's `PROJECT_INTELLIGENCE_SYSTEM` and `buildProjectIntelligencePrompt()` (`src/lib/prompts/project-intelligence.ts`) with the notella input bundle (chronological pages carrying first-pass, metadata and actions), the manifest's project description as context, and — when a previous brief for the slug exists — the **memory block** of Step 3: the baseline commitments with their last statuses, the commitments retired by human verdict, the previous drift signals and risk level, and the count of pages added since. The brief it produces says what moved since last time in a `since_last` block.

**Placeholders:** `{{double-curly}}`. Blocks marked *(conditional)* are omitted, heading included, when their input is absent.

| Placeholder | Source |
| --- | --- |
| `{{project_name}}` | `manifest.projects[slug].name` |
| `{{project_slug}}` | the slug |
| `{{project_description}}` | `manifest.projects[slug].description` |
| `{{project_keywords}}` | `manifest.projects[slug].keywords` joined with `, ` |
| `{{since}}`, `{{until}}` | the date window actually covered by the bundle |
| `{{page_count}}` | number of pages in the bundle |
| `{{pages_json}}` | the bundle (shape below), oldest first |
| `{{previous_brief_date}}` | date of the most recent `projects/{slug}/*.json` strictly before today; null when none |
| `{{previous_generated_at}}` | its `generated_at` |
| `{{baseline_json}}` | the previous brief's `commitments_assessment` minus retired commitments, each as `{commitment, owner, status, evidence}` |
| `{{retired_json}}` | previous commitments closed by a verdict since `previous_generated_at`: `[{commitment, from_status, to_status: done \| dropped \| removed, evidence: "verdict:{task_id} — {note}"}]` |
| `{{previous_drift_json}}` | the previous brief's `drift_signals` |
| `{{previous_risk}}` | the previous brief's `overall_risk_level` |
| `{{previous_blockers_json}}`, `{{previous_next_actions_json}}` | the previous brief's `blockers` and `next_actions`, context only |
| `{{pages_added}}` | pages in the bundle whose `meta.yaml:ingested_at` is after `previous_generated_at` |
| `{{pages_added_ids}}` | their page ids |

**Call shape:** system block (cacheable across a multi-project batch), one user turn. Model from `manifest.model_defaults.project_synthesis` (default `claude-opus-4-6`). When the bundle is large (> 60 pages), keep every page's `date`, `title`, `content_summary` and `actions`, and drop `metadata_summary` and `structural_map` for pages older than the most recent 20; the memory block is never trimmed. JSON only.

---

## Input bundle shape (`{{pages_json}}`)

```json
[
  {
    "page_id": "2026-04-12-k3p9",
    "date": "2026-04-12",
    "ingested_at": "2026-04-12T21:04:11Z",
    "title": "…",
    "document_type": "project-plan",
    "content_summary": "…",
    "structural_map": { "entities": ["…"], "clusters": ["…"] },
    "metadata_summary": "…",
    "people": ["…"],
    "action_intelligence": [ { "task": "…", "owner_candidates": ["…"], "due_hint": "…", "confidence": 0.8 } ],
    "actions": [ { "task": "…", "owner_candidates": ["…"], "due_hint": "…", "blockers": ["…"], "expected_outcome": "…", "confidence": 0.85 } ],
    "follow_up_queries": ["…"]
  }
]
```

`date` is the page's authoritative date (metadata → transcribe → capture → ingest). `actions` omitted when `actions.json` is absent. `ingested_at` is what `pages_added` was computed from; it is in the bundle so the model can tell a late upload of an old page from a new page.

## Retired commitments

Computed in Step 3 from `verdicts.ndjson` rows with `target_kind: commitment` whose `target_id` equals `task_id(c.commitment)` for a commitment `c` in the previous brief and whose `ts` is after `previous_generated_at`. `task_id(text)` is the `notella-review` hash: lowercase, collapse runs of non-alphanumerics to one space, trim, FNV-1a 32-bit, 8 hex digits. Latest verdict per `target_id` wins.

| verdict | `to_status` | note |
| --- | --- | --- |
| `done` | `done` | the commitment was met off the page |
| `drop` | `dropped` | it will not happen and stops being tracked |
| `wrong` | `removed` | it was a misreading; it never existed as stated — never resurrect it |
| `carry` | — | stays in the baseline, status unchanged |

Each retired row's `evidence` is `"verdict:{task_id} — {note}"` and its `from_status` is the previous brief's status.

## System prompt (`PROJECT_INTELLIGENCE_SYSTEM`, extended)

```
You are a project intelligence analyst for a personal knowledge management system. Your role is to analyze all notes referencing a specific project and produce a comprehensive project health assessment covering its timeline, commitments, momentum, risks, recommended next actions — and, when a previous assessment exists, what changed since it.

Your analysis must be grounded strictly in the provided intelligence data. Do not invent commitments, blockers, or decisions that are not evidenced by the source material.

## Your responsibilities:

### Timeline Summary
Build a narrative timeline of the project based on the date-ordered notes. Describe when the project started (if visible), what major phases or milestones have been reached, and where the project currently stands. Keep this to 2–4 sentences.

### Commitments Assessment
Identify every explicit or implicit commitment made about the project: promises to deliver something, agreed deadlines, accepted responsibilities, and resource allocations. For each commitment:
- Write a clear commitment statement
- Identify the owner if a person was named or implied
- Assess its status: on_track (evidence of progress matching the commitment), at_risk (progress is slower than needed or timeline is tight), or blocked (an explicit obstacle prevents progress)
- Provide a brief evidence statement from the notes, naming the page id and date it comes from

### Drift Signals
Identify signs that the project has shifted from its original scope, schedule, or goals. Drift includes: scope creep (new features or requirements added), schedule slippage (dates pushed), priority changes (deprioritized or re-prioritized), team changes, budget changes, or goal ambiguity. Express each as a plain descriptive string.

### Blockers
List all explicit obstacles, dependencies, or constraints that are preventing the project from moving forward. Include technical blockers, resource gaps, pending decisions, external dependencies, and interpersonal obstacles.

### Momentum Assessment
Write a single paragraph describing the current momentum of the project. Is it accelerating, stable, or decelerating? What evidence supports this assessment? What is the strongest positive signal? What is the biggest risk to continued momentum?

### Next Actions
Recommend the most important actions that should be taken for this project, ordered by priority. For each:
- Write a specific, actionable statement (not vague like "review the project")
- Assign priority: high (must happen immediately to avoid risk), medium (important for continued progress), or low (useful but not urgent)
- Identify the recommended owner if determinable from the notes

### Risk Summary
Write a concise paragraph summarizing the top risks facing the project. Address: delivery risk, dependency risk, resource risk, and strategic risk (is this still the right thing to build?). Conclude with an overall risk level: low, moderate, high, or critical.

### Since Last
When a memory block is supplied, fill since_last:
- previous_brief_date: as given
- pages_added: as given
- commitments_changed: one row per BASELINE commitment whose status you assess
  differently from the baseline, as {commitment (baseline wording verbatim),
  from_status, to_status, evidence (page quote + page id)}; plus every RETIRED
  commitment copied exactly as given. A baseline commitment the new pages show
  completed gets to_status done with the page that shows it, and is then left out
  of commitments_assessment. No other rows.
- new_drift_signals: the subset of your drift_signals that the previous brief did
  not name (same substance, any wording).
- risk_delta: leave null; it is computed from the two risk levels.
- note: one or two sentences on what the delta means — the single most important
  change, or "no material change" if that is true.
When no memory block is supplied, since_last is null.

## Continuing a previous brief
A previous brief exists. Continue it:

- For every baseline commitment, reuse its wording verbatim and re-assess its
  status from the pages. If the status changed, say which page shows the change.
- Do not re-list retired commitments. Do not resurrect a commitment marked
  wrong.
- A drift signal is new only if the previous brief did not name it (same
  substance, any wording).
- since_last.note is one or two sentences on what the delta means — the
  single most important change, or "no material change" if that is true.

Also:
- A baseline commitment with no new evidence keeps its status; its evidence says
  "no new evidence since {previous_brief_date}" rather than inventing progress.
- New commitments (not in the baseline) are added to commitments_assessment as usual;
  they are not since_last rows.
- If overall risk moved relative to the previous level given, say why in risk_summary.
- Pages whose ingested_at is before the previous brief were already assessed; they
  are context for the timeline, not news.
```

## User prompt (`buildProjectIntelligencePrompt()` extended)

```
Analyze all notes referencing the project "{{project_name}}" ({{project_slug}}) and produce a comprehensive project intelligence report.

## Project (from the manifest)
{{project_description}}
Keywords: {{project_keywords}}

## Pages attributed to this project — {{page_count}} pages, {{since}} → {{until}}, oldest first
{{pages_json}}

## Memory — previous brief {{previous_brief_date}}                     (conditional)
See "Continuing a previous brief". {{pages_added}} of the pages above were ingested after it{{#if pages_added}}: {{pages_added_ids}}{{/if}}.

### Baseline commitments (re-assess each; wording verbatim)
{{baseline_json}}

### Retired by review verdict (do not re-assess; copy into since_last.commitments_changed as given)   (conditional)
{{retired_json}}

### Previous drift signals
{{previous_drift_json}}

### Previous risk level
{{previous_risk}}

### Previous blockers and next actions (context only)
{{previous_blockers_json}}
{{previous_next_actions_json}}

Produce the complete ProjectIntelligenceSchema output. Set project_name to "{{project_name}}" and project_slug to "{{project_slug}}". Set pages_analyzed to {{page_count}}. {{#if previous_brief_date}}Set since_last.previous_brief_date to "{{previous_brief_date}}" and since_last.pages_added to {{pages_added}}; leave since_last.risk_delta null.{{else}}Set since_last to null.{{/if}} Be specific and evidence-based — reference actual content, page ids and page dates from the notes when assessing commitment status, drift, or blockers.
```

## Expected response shape (`ProjectIntelligenceSchema`)

```json
{
  "project_name": "Tulevik",
  "project_slug": "tulevik",
  "pages_analyzed": 14,
  "timeline_summary": "…",
  "commitments_assessment": [
    { "commitment": "Deliver staleness dashboard to JP Morgan contact", "owner": "David", "status": "blocked", "evidence": "waiting on data access, 2026-04-28 (2026-04-28-m2q7)" },
    { "commitment": "Weekly name-matching accuracy report", "owner": null, "status": "on_track", "evidence": "no new evidence since 2026-04-25" }
  ],
  "drift_signals": ["Dashboard scope now includes a freshness SLA that the April plan did not mention (2026-05-01-h8s3)"],
  "blockers": ["…"],
  "momentum_assessment": "…",
  "next_actions": [ { "action": "…", "priority": "high", "owner": "…" } ],
  "risk_summary": "…",
  "overall_risk_level": "high",
  "since_last": {
    "previous_brief_date": "2026-04-25",
    "pages_added": 5,
    "commitments_changed": [
      { "commitment": "Deliver staleness dashboard to JP Morgan contact", "from_status": "on_track", "to_status": "blocked", "evidence": "\"no access until legal signs\" — 2026-04-28-m2q7" },
      { "commitment": "Send the April accuracy numbers to Alice", "from_status": "at_risk", "to_status": "done", "evidence": "verdict:3f9a1c2e — sent 2026-04-30" }
    ],
    "new_drift_signals": ["Dashboard scope now includes a freshness SLA that the April plan did not mention (2026-05-01-h8s3)"],
    "risk_delta": null,
    "note": "The dashboard went from on track to blocked on legal, which is what moved risk from moderate to high."
  }
}
```

Set by the skill, not the model: `generated_at`, `date_range`, and `since_last.risk_delta` — `up | same | down` from the ordinal `low < moderate < high < critical` against `previous.overall_risk_level`.

## Validation the prompt is written to pass

Mirrors Step 6 of the SKILL.md.

- `since_last` is null if and only if no previous brief exists.
- `since_last.commitments_changed` is checked, not trusted: every baseline commitment whose status differs between the previous brief and the new `commitments_assessment` has a row; every retired commitment has a row with the given `to_status` and `evidence`; no other rows.
- A row with `to_status` in `done | dropped | removed` has no matching entry in `commitments_assessment`; a row with `to_status` in `on_track | at_risk | blocked` has one, with that status.
- Every `commitments_changed[].commitment` matches a baseline or retired commitment verbatim (a reworded baseline commitment is the SKILL.md's "model rewords a baseline commitment" failure).
- Every `new_drift_signals[]` entry is in `drift_signals` and matches nothing in the previous `drift_signals` (normalised text).
- Every commitment's `evidence` appears in at least one source page, or begins with `verdict:` (since_last rows only); every `commitments_changed[].evidence` names a page id or begins `verdict:`.
- `pages_analyzed` equals the bundle count.

A failure refuses the write and allows one retry with the violations appended under `## Violations in your previous answer`.

## Differences from the app prompt

- Manifest description and keywords added as project context.
- Bundle carries metadata, actions, `ingested_at` per page, dated and ordered, not first-pass alone.
- Memory block: baseline commitments, verdict-retired commitments, previous drift and risk, pages added, and the continuation guidance verbatim from the SKILL.md.
- New `since_last` block; `risk_delta` derived by the skill.
- `project_slug` and explicit `pages_analyzed` supplied; evidence asked to carry page ids and dates so the markdown renderer can link them.
