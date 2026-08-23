---
name: notella-metadata
description: "Extract structured metadata from a notella page transcript — date, page number, title, summary, tags, projects, themes, ideas, people, organisations, geography, action items, document type, cross-references. Use whenever the user says 'extract metadata for page X', 'tag this page', 'who is mentioned', 'what projects appear', 'summarize this page', or any request to derive structured fields from a transcript. Always runs. Reads through `notella-state`; writes `metadata.json`."
---

# notella-metadata — the metadata extractor

Layer-2 specialist that reads the transcript and produces structured fields downstream layers depend on.

## Purpose

Pull out the structured signal a transcript carries — title, summary, tags, every project/person/place mentioned, every action item, the type of document it is. Plus typed cross-references (which the transcribe skill leaves as inline cues; this skill promotes them).

## Inputs and outputs

**Input:** Page at `phase=transcribed`. Reads `transcribe.json`, optional `composition.json`.

**Output:**
- `pages/{page-id}/metadata.json`
- Mirror `tags`, `project_attributions`, `person_attributions` into `meta.yaml` for fast filtering
- No phase advance (Layer-2 specialist; phase advances are managed by orchestrator after enrichment fan-out completes).

## How a run executes

### Step 1 — Read configuration & page

```
notella-state get-manifest → manifest.model_defaults.metadata, manifest.projects, manifest.people_aliases
notella-state get-page-artifact {page-id, artifact: transcribe}
```

### Step 2 — Acquire the page lock

### Step 3 — Build the prompt

Use notella-the-app's `buildExtractMetadataPrompt()` from `src/lib/prompts/extract-page-metadata.ts` verbatim, with one extension: the `cross_references` array.

```
## cross_references (array)
For every reference to other content the page makes:
- kind: page-ref | date-ref | person-ref | project-ref | external-doc | url
- target: the canonical reference target (e.g., "p.47", "2026-05-01",
          "alice", "project-atlas", "https://...", "Q2 strategy doc")
- evidence_span: the verbatim text that anchored this reference
```

Pass `manifest.projects` aliases and `manifest.people_aliases` so the model can attribute mentions to canonical slugs. The prompt explicitly instructs:

```
When you see a project mention that matches one of the following project
slugs (or any of their aliases), record the canonical slug:
{project-list}

When you see a person mention that matches one of the following canonical
names (or any of their aliases), record the canonical name:
{person-aliases}

For mentions that don't match any known project/person, record them as-is —
they may be added to the manifest later.
```

### Step 4 — Call the model

Default: `claude-haiku-4-5` (text-only task; cheap).

### Step 5 — Validate

```yaml
date: "YYYY-MM-DD" | null
pageNumber: string | null
title: string                   # 6-10 words
summary: string                 # 2-4 sentences
tags: [string]                  # 8-15
projects: [string]              # canonical slugs preferred
themes: [string]
ideas: [string]
people: [string]                # canonical names preferred
organisations: [string]
geography: [string]
actionItems: [string]
documentType: strategy-map | project-plan | meeting-notes | brainstorm | action-list | framework-diagram | ecosystem-map | business-development | research-notes | personal-reflection | mixed
cross_references:
  - kind, target, evidence_span
```

### Step 6 — Reconcile date

If `metadata.date` is non-null AND differs from `transcribe.json:extractedDate`:
- If both are confident, prefer the metadata extraction's date but log the disagreement to `meta.yaml:errors` for review.
- If transcribe date had higher confidence, prefer that one.

### Step 7 — Mirror into meta.yaml

```
notella-state update-page-meta {page-id, fields: {tags, project_attributions: projects, person_attributions: people}}
```

### Step 8 — Write the artifact & release lock

```
notella-state log-page-artifact {page-id, artifact: metadata, payload: <validated>}
notella-state release-page-lock {page-id, actor: notella-metadata}
```

## Idempotency

Standard.

## Failure modes

| Failure                                                       | Behavior |
| ------------------------------------------------------------- | -------- |
| Project mention is ambiguous between two manifest projects    | Record both as candidates; surface in pipeline.ndjson; user can clarify by editing manifest aliases. |
| Person mention has no manifest match                          | Record as written; user may add to `manifest.people_aliases` later. |
| Cross-reference target is fuzzy ("see last week's note")      | Record kind=date-ref with target as best-effort ISO date; downstream may resolve via search. |

## What this skill does NOT do

- Does not perform synthesis — that's `notella-first-pass`.
- Does not extract actions deeply — `notella-actions` does that with full context.
- Does not edit the manifest. New projects / people are surfaced for the user to confirm.

## Examples

### "Extract metadata for page 2026-05-02-x7k2"

```json
{
  "date": "2026-05-02",
  "pageNumber": "47",
  "title": "Q2 prioritization grid for sovereign infrastructure roadmap",
  "summary": "A 2x2 of effort vs. value covering five candidate workstreams. Three are flagged as quick wins; one is marked as 'avoid'. Open questions remain about resource overlap with Project Sunshine.",
  "tags": ["q2-planning", "prioritization", "project-sunshine", "infrastructure", "sovereignty", "2x2", "effort-value", "roadmap"],
  "projects": ["project-sunshine"],
  "themes": ["prioritization", "sovereignty"],
  "people": ["alice"],
  "documentType": "framework-diagram",
  "cross_references": [
    { "kind": "page-ref", "target": "p.43", "evidence_span": "see prior framing on p.43" }
  ]
}
```

## Reference files

- `references/metadata-prompt.md` — full prompt with cross_references extension.
- `references/canonical-attribution.md` — how alias matching works.
