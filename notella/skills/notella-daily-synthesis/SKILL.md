---
name: notella-daily-synthesis
description: "Produce a daily intelligence brief from all notella pages indexed to a date — new decisions, unresolved questions, top priorities, momentum signals, key entities active, synthesis notes. Use whenever the user says 'daily brief for today', 'synthesize today's notes', 'daily intelligence for 2026-05-02', 'what happened today', 'today's standup brief', or any request to consolidate a single day's pages into a coherent operational picture. Reads through `notella-state`; writes `daily/{date}.{json,md}`. Emits `synthesis.daily` event."
---

# notella-daily-synthesis — the daily intelligence brief

First Layer-3 deriver. Reads every page indexed to a date and produces a daily intelligence brief — the operational picture of what happened, what was decided, what remains open.

## Purpose

Turn a day's pages into a brief. The day is the natural granularity for human review: "what did I think about today, what did I decide, what's open, what should tomorrow focus on."

## Inputs and outputs

**Input:** A date. Reads every page where `meta.yaml:phase >= indexed` and the page's authoritative date is the target date.

The page's authoritative date is, in order: `metadata.json:date`, then `transcribe.json:extractedDate`, then `meta.yaml:source_capture_time`, then `meta.yaml:ingested_at` (the latter only as last resort).

**Output:**
- `daily/{date}.json` — `DailyIntelligenceSchema`
- `daily/{date}.md` — human-readable narrative rendering of the same content
- `synthesis.daily` event
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

### Step 3 — Build the prompt

Use notella-the-app's `DAILY_INTELLIGENCE_SYSTEM` and `buildDailyIntelligencePrompt()` from `src/lib/prompts/daily-intelligence.ts` verbatim. Pass the bundle as the `analysesJson` input, with a small format adjustment so the model can see metadata + actions per page, not just first-pass.

### Step 4 — Call the model

Default: `claude-opus-4-6` (synthesis-heavy, reasoning depth pays).

**Use prompt caching** (`cache_control: { type: "ephemeral" }`) on the system prompt block. Daily synthesis often gets re-run (catch-up batches, `--reprocess`, multiple back-to-back days), and the Opus system prompt is large. A single batch covering 7-10 dates pays the system-prompt cost once instead of N times — ~80-90% discount on the cached portion for runs 2..N.

### Step 5 — Validate

```yaml
date: "YYYY-MM-DD"
generated_at: ISO-8601
pages_analyzed: int
new_decisions:
  - decision, source_page_id, confidence
unresolved_questions:
  - question, context, source_page_id
top_priorities:
  - priority, urgency, source_page_id
momentum_signals: [string]
key_entities_active:
  - name, entity_type, activity_summary
synthesis_notes: string
```

Sanity:
- `pages_analyzed` matches the input bundle count.
- Every `source_page_id` exists in the input bundle.
- `urgency` is one of `high | medium | low`.

### Step 6 — Render the markdown

Format the JSON into a human-readable narrative using the template in `references/daily-md-template.md`. Sections in order:

```markdown
# Daily Intelligence — {date}

**{N} pages analyzed**

## Synthesis Notes

{synthesis_notes}

## Top Priorities

{for each priority, urgency-emoji + text + source-page link}

## New Decisions

{decisions with confidence pct + source page}

## Unresolved Questions

{questions with context}

## Momentum Signals

{plain bullets}

## Key Entities Active

{entities grouped by type, with activity_summary}

---
*Generated {generated_at} from pages {ids}*
```

### Step 7 — Write the synthesis

```
notella-state log-synthesis {
  kind: synthesis.daily,
  date: {date},
  json: <validated>,
  md: <rendered markdown>
}
```

This single call:
- Writes `daily/{date}.json` and `daily/{date}.md` atomically
- Emits the `synthesis.daily` event
- Updates `state.json:last_synthesis_at.daily`

### Step 8 — Advance pages to archived

For each page in the input bundle:

```
notella-state advance-phase {page-id, to-phase: archived, by-actor: notella-daily-synthesis}
```

Each emits a `page.archived` event referencing this synthesis.

## Idempotency

- Re-running for a date with `daily/{date}.json` already present: no-op unless `--reprocess`.
- `--reprocess`: overwrite, emit `correction` event, do NOT re-archive pages (they stay archived from first run).

## Failure modes

| Failure                                                  | Behavior |
| -------------------------------------------------------- | -------- |
| No pages indexed for the date                            | Skip cleanly with `{status: "no-pages-for-date"}`. |
| Pages exist but none reach phase=indexed                 | Skip; orchestrator should run pipeline catch-up first. |
| Model returns inconsistent source_page_ids               | Refuse the write; surface diagnostics. |
| Single page in bundle (sparse day)                       | Run anyway; the brief is short; this is correct behavior. |

## What this skill does NOT do

- Does not run on weekly or project scopes — those are `notella-weekly-synthesis` and `notella-project-synthesis`.
- Does not edit page artifacts.
- Does not modify the manifest.

## Examples

### "Daily synthesis for 2026-05-02"

```
Pages found at phase=indexed for 2026-05-02: 4
Synthesizing with claude-opus-4-6...
Generated daily/2026-05-02.json (8 sections, 4 priorities, 3 questions)
Generated daily/2026-05-02.md (1842 words)
Advanced 4 pages to phase=archived.
synthesis.daily event emitted.
```

### "Re-synthesize today's brief"

```
daily/2026-05-02.json exists. Pass --reprocess to overwrite.
```

## Reference files

- `references/daily-md-template.md` — markdown rendering template.
- `references/daily-intelligence-prompt.md` — full system + user prompt with adjusted input format.
