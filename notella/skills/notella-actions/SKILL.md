---
name: notella-actions
description: "Extract every action, task, decision, and commitment from a notella page transcript with rich structured metadata. Use whenever the user says 'extract actions from page X', 'what are the tasks on page X', 'pull out commitments', 'find action items', or any request for deep action extraction with owners, dependencies, blockers, due hints, and confidence. Conditional: runs when classify.json:route_plan includes action_decision. Reads through `notella-state`; writes `actions.json`."
---

# notella-actions — the action specialist

Layer-2 specialist that goes deeper on actions than first-pass alone. Where first-pass surfaces 3-5 high-level actions inside its 8-section integration, this skill produces a complete action register: every explicit task, every implicit task, every deferred decision, every promised follow-up.

## Purpose

Capture the action surface of a page completely so the corpus can answer "what's open across all my pages from this week" without missing implicit work.

## Inputs and outputs

**Input:** Page at `phase=first-pass-done` with `route_plan` containing `action_decision`. Reads `transcribe.json`, `first-pass.json`.

**Output:**
- `pages/{page-id}/actions.json`
- No phase advance (Layer-2 specialist; orchestrator advances to `enriched` after fan-out completes).

## How a run executes

### Step 1 — Read configuration & artifacts

```
notella-state get-manifest → manifest.model_defaults.actions
notella-state get-page-artifact {page-id, artifact: transcribe}
notella-state get-page-artifact {page-id, artifact: first-pass}
notella-state get-page-artifact {page-id, artifact: classify}
```

Verify `phase >= first-pass-done` and `route_plan` includes `action_decision`. Skip cleanly if not.

### Step 2 — Acquire the page lock

### Step 3 — Build the prompt

Use notella-the-app's `ACTIONS_SYSTEM` and `buildActionsPrompt()` from `src/lib/prompts/actions.ts` verbatim. Pass the transcript and the first-pass `action_intelligence` array as context (so the actions skill can be exhaustive without contradicting first-pass on the obvious ones).

```
## First-pass action_intelligence (for grounding)
{first-pass.json:action_intelligence as JSON}

## Transcript
{transcribe.json:cleanedTranscript}

## Marginalia (often carries actions)
{transcribe.json:marginalia[] formatted}
```

### Step 4 — Call the model

Default: `claude-sonnet-4-6`.

### Step 5 — Validate

```yaml
actions:
  - task: string                          # imperative sentence
    owner_candidates: [string]
    due_hint: string                      # optional
    dependencies: [string]
    blockers: [string]
    expected_outcome: string              # optional
    confidence: 0.0-1.0
total_actions: int
high_confidence_count: int
```

Sanity:
- `total_actions == len(actions)`
- `high_confidence_count == count(actions where confidence >= 0.7)`
- Every action's `task` starts with a verb

### Step 6 — Reconcile with first-pass

Mark actions that overlap with `first-pass.json:action_intelligence` so consumers don't double-count. Add a `source` field per action: `"first-pass"` (already there) or `"actions-extension"` (newly surfaced by this skill).

### Step 7 — Write & release lock

```
notella-state log-page-artifact {page-id, artifact: actions, payload}
notella-state release-page-lock {page-id, actor: notella-actions}
```

## Idempotency

Standard.

## Failure modes

| Failure                                                | Behavior |
| ------------------------------------------------------ | -------- |
| Page contains 30+ actions (every line is a task)       | Expected for action-list document type; no special handling. |
| Owner candidates are ambiguous ("someone should...")   | Empty owner_candidates array; record in expected_outcome that ownership is unassigned. |
| Implicit actions only ("the database is too slow")     | Convert to explicit imperative ("Investigate database performance"); confidence ≤ 0.6 since it's implied. |

## What this skill does NOT do

- Does not modify first-pass.json — actions extension is additive, recorded separately.
- Does not assign owners autonomously — only proposes candidates.
- Does not produce a TODO list — `notella-daily-synthesis` and `-project-synthesis` aggregate actions across pages for that.

## Examples

### "Extract actions from page 2026-05-02-x7k2"

```json
{
  "actions": [
    {
      "task": "Confirm Alice's bandwidth for Project Sunshine in Q2",
      "owner_candidates": ["David"],
      "due_hint": "before Q2 starts",
      "dependencies": [],
      "blockers": [],
      "expected_outcome": "Clear yes/no on Alice having Q2 capacity",
      "confidence": 0.85,
      "source": "first-pass"
    },
    {
      "task": "Document workstream-3 in detail",
      "owner_candidates": [],
      "due_hint": "",
      "dependencies": ["Identify workstream-3 owner"],
      "blockers": [],
      "expected_outcome": "Workstream-3 has a written brief",
      "confidence": 0.55,
      "source": "actions-extension"
    }
  ],
  "total_actions": 2,
  "high_confidence_count": 1
}
```

## Reference files

- `references/actions-prompt.md` — full prompt.
- `references/implicit-action-rules.md` — when to promote a stated problem to an action.
