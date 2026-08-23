---
name: notella-first-pass
description: "Produce the focused first-pass intelligence output for a notella page — content_summary, structural_map (entities/clusters), diagram_semantics, action_intelligence, tags, follow_up_queries. Doc-type-aware: meeting-notes emphasize action_intelligence; brainstorms emphasize tags; project-plans emphasize entities. Use whenever the user says 'analyze page X', 'first-pass intelligence on page X', 'what's the meaning of this page'. Reads through `notella-state`; writes `first-pass.json`; advances phase to `first-pass-done`."
---

# notella-first-pass — the semantic integrator

The bridge between Layer 1 (what's on the page) and Layer 3 (synthesis across pages). First-pass reads every Layer-1 artifact and produces the eight-section meaning layer.

## Purpose

Take all of Layer 1 — transcribe, composition, diagram, sketch, table, metadata — and produce a coherent semantic picture. The eight sections are the input shape that downstream synthesis (daily, project, weekly, themes) consumes; they're how a single page's meaning becomes queryable across the corpus.

## Inputs and outputs

**Input:** Page at `phase=transcribed` with all required Layer-1 artifacts present (transcribe + composition + metadata at minimum; diagram/sketch/table conditionally).

**Output:**
- `pages/{page-id}/first-pass.json` carrying the 8-section schema
- Page advanced to `phase=first-pass-done`
- `page.first-pass-done` event

## How a run executes

### Step 1 — Read configuration & all Layer-1 artifacts

```
notella-state get-manifest → manifest.model_defaults.first_pass
notella-state get-page-artifact {page-id, artifact: transcribe}
notella-state get-page-artifact {page-id, artifact: composition}
notella-state get-page-artifact {page-id, artifact: metadata}
notella-state get-page-artifact {page-id, artifact: diagram}     # optional
notella-state get-page-artifact {page-id, artifact: sketch}      # optional
notella-state get-page-artifact {page-id, artifact: table}       # optional
notella-state get-page-artifact {page-id, artifact: classify}
```

Verify `phase == transcribed`. Verify required Layer-1 artifacts are present per route_plan; if any are missing and route_plan says they should run, abort with `{status: "blocked", missing: [...]}`.

### Step 2 — Acquire the page lock

### Step 3 — Build the prompt

Use notella-the-app's `FIRST_PASS_SYSTEM` and `buildFirstPassPrompt()` from `src/lib/prompts/first-pass.ts` verbatim. Extend the user prompt to include all Layer-1 artifacts, not just the transcript:

```
## Classification context
{classify.json:doc_type}, content_mix={...}, route_plan={...}

## Transcript (cleaned)
{transcribe.json:cleanedTranscript}

## Marginalia
{transcribe.json:marginalia[] formatted as bullet list}

## Emphasis
{transcribe.json:emphasis[] formatted as "<span_text>: <mark_type> (intensity N)"}

## Page composition
zones: {composition.json:zones short labels}
dominant_flow: {composition.json:dominant_flow}
visual_hierarchy: {composition.json:visual_hierarchy top 3 prominent zones}

## Diagram structure                              ← only if diagram.json present
{diagram.json:layout_semantics}
nodes: {N nodes labeled}
edges: {M edges labeled}
utility: {utility_statement}

## Sketches                                        ← only if sketch.json present
{sketch.json:sketches[].subject + intent + affective_signal}

## Tables                                          ← only if table.json present
{table.json:tables[].interpretation}

## Metadata
title: {metadata.json:title}
summary: {metadata.json:summary}
projects: {metadata.json:projects}
people: {metadata.json:people}
documentType: {metadata.json:documentType}
cross_references: {N refs}
```

The first-pass model reads all of this and produces a coherent semantic integration.

### Step 4 — Call the model

Default: `claude-sonnet-4-6`. **Always use prompt caching** (`cache_control: { type: "ephemeral" }`) on the system prompt block — the system prompt is large (~5-7k tokens) and identical across every page in a batch. Cache TTL of 5 minutes covers a typical orchestrator batch and yields ~90% discount on cached input tokens for the second through Nth call.

### Step 5 — Validate against the focused six-section schema

```yaml
content_summary: string                 # 3-5 sentences — primary surface for kanban cards & daily synthesis
structural_map:
  entities: [string]                    # consumed by themes; drives entity recurrence detection
  clusters: [string]                    # high-level groupings inside the page
  # NOTE: relationships removed — were "A → verb → B" strings with no graph store consuming them.
diagram_semantics:                      # may reference diagram.json ids; only required if diagram.json present and non-empty
  - diagram_id, purpose, representation_type, utility, actionability, ambiguity
action_intelligence:
  - task, owner_candidates, due_hint, dependencies, blockers, expected_outcome, confidence
tags:
  - name, confidence, rationale         # confidence threshold 0.7 for new tags
follow_up_queries: [string]             # 0-3 max; consolidated at synthesis layer
```

**Removed sections** (rationale: produced but never consumed downstream):
- `value_hypotheses` — speculative; never resurfaced in synthesis. Use the synthesis layer's interpretation instead.
- `uncertainty_register` — useful for QA; if needed, log to pipeline.ndjson as warnings instead of polluting the artifact.

Output drops from ~1500 → ~1000 tokens per page (~33% savings on output spend).

Refuse to write if any required section is missing. Optional sections (diagram_semantics, action_intelligence) may be empty arrays when their inputs are absent.

### Step 5a — Doc-type-specific emphasis

Branch the prompt's "primary focus" instruction by `classify.doc_type`:

| doc_type             | Emphasize                                         | De-emphasize             |
| -------------------- | ------------------------------------------------- | ------------------------ |
| `meeting-notes`      | action_intelligence (decisions, owners, deadlines)| diagram_semantics         |
| `brainstorm`         | tags, structural_map.clusters                     | action_intelligence       |
| `project-plan`       | structural_map.entities, action_intelligence      | follow_up_queries         |
| `strategy-map`       | structural_map (entities + clusters), diagram_semantics | tags             |
| `action-list`        | action_intelligence (every line is an action)     | structural_map            |
| `personal-reflection`| content_summary, follow_up_queries                | action_intelligence       |
| `framework-diagram` / `ecosystem-map` | diagram_semantics, structural_map | action_intelligence |
| `research-notes`     | tags, follow_up_queries                           | action_intelligence       |
| `mixed` / unknown    | full schema, no emphasis bias                     | —                         |

This produces specialist-quality output at non-specialist cost — a `meeting-notes` page returns rich actions; a `brainstorm` returns rich tags; same call, same model, sharper signal.

### Step 6 — Cross-validate against Layer 1

Sanity checks that catch hallucination:

- Every entity in `structural_map.entities` appears either in transcribe.json's transcript text or in metadata.json's projects/people/organisations/geography.
- Every diagram referenced in `diagram_semantics` has a matching `diagram_id` in `diagram.json` (if present).
- Every action in `action_intelligence` is grounded in transcript text or marginalia.
- Tags are a subset of metadata.json:tags ∪ a small number of newly-discovered tags (confidence > 0.7 required for new ones).

If a sanity check fails, log a warning to pipeline.ndjson but do not refuse the write — first-pass occasionally surfaces inferences that aren't literally in Layer 1, and that's part of its job. Hard refusal only on schema violations.

### Step 7 — Write the artifact

```
notella-state log-page-artifact {page-id, artifact: first-pass, payload: <validated>}
```

### Step 8 — Advance phase

```
notella-state advance-phase {page-id, to-phase: first-pass-done, by-actor: notella-first-pass}
```

Emits `page.first-pass-done` event:

```yaml
evidence:
  entities_count: 12
  clusters_count: 4
  actions_count: 5
  tags_count: 6
  follow_up_queries_count: 3
  doc_type_emphasis: "meeting-notes"      # which prompt branch was taken
  cached_input_tokens: 5800               # for cost telemetry
  fresh_input_tokens: 2400
  output_tokens: 980
```

### Step 9 — Release the page lock

## Idempotency

Standard. With `--reprocess`: overwrite, emit `correction`, downstream synthesis layers may need re-run if their inputs changed materially.

## Failure modes

| Failure                                                  | Behavior |
| -------------------------------------------------------- | -------- |
| Required Layer-1 artifact missing                        | Abort with status=blocked, list missing artifacts. Orchestrator re-runs the missing specialist. |
| Model returns 6 sections instead of 8                    | Refuse the write; surface the gap; one retry; on second failure, log error. |
| Hallucinated entity (not in Layer 1)                     | Logged as a warning, not refused; the entity may still be a legitimate inference. |
| Page is mostly empty (e.g. a single sketch)              | All eight sections may be sparse; minimums are: content_summary present, tags >= 1, follow_up_queries >= 1. |

## What this skill does NOT do

- Does not run on multi-page or daily scopes — that's the synthesis layer.
- Does not write to the KG (deferred).
- Does not change Layer-1 artifacts. If first-pass disagrees with a Layer-1 specialist, it logs a warning to `pipeline.ndjson` rather than overwriting.

## Examples

### "First-pass page 2026-05-02-x7k2"

```json
{
  "content_summary": "A Q2 prioritization grid (2x2 of effort vs value) covering five workstreams in the sovereign infrastructure roadmap. Three workstreams are categorized as quick wins, one as 'avoid'. The page raises explicit concerns about resource overlap with Project Sunshine and asks whether Alice has bandwidth.",
  "structural_map": {
    "entities": ["Project Sunshine", "Alice", "sovereign infrastructure roadmap", "Q2"],
    "clusters": ["prioritization workstreams", "open questions"]
  },
  "action_intelligence": [
    {
      "task": "Confirm Alice's bandwidth for Project Sunshine in Q2",
      "owner_candidates": ["David"],
      "due_hint": "before Q2 starts",
      "confidence": 0.85
    }
  ],
  "follow_up_queries": [
    "What is Alice's actual capacity for Q2?",
    "Where is workstream-3 documented in detail?"
  ],
  "...": "..."
}
```

## Reference files

- `references/first-pass-prompt.md` — full prompt extended to read all Layer-1 artifacts.
- `references/sanity-check-rules.md` — what counts as hallucination vs legitimate inference.
