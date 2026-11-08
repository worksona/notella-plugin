# notella-first-pass — prompt

The complete first-pass prompt, self-contained in the plugin. It is the app's `FIRST_PASS_SYSTEM` and `buildFirstPassPrompt()` (`src/lib/prompts/first-pass.ts`) extended, as the SKILL.md describes, so the user turn carries every Layer-1 artifact rather than the transcript alone. The doc-type emphasis table from the app is reproduced in full so the skill can branch without the app repo.

**Placeholders:** `{{double-curly}}`. Blocks marked *(conditional)* are omitted entirely — heading included — when the artifact is absent or empty.

| Placeholder | Source |
| --- | --- |
| `{{page_id}}` | `meta.yaml:id` |
| `{{doc_type}}`, `{{content_mix}}`, `{{route_plan}}` | `classify.json` |
| `{{document_type}}` | `metadata.json:documentType` — this is what selects the emphasis block |
| `{{emphasis_block}}` | from the table below, keyed on `{{document_type}}`; empty string for `mixed` / unknown |
| `{{cleaned_transcript}}` | `transcribe.json:cleanedTranscript` |
| `{{marginalia_lines}}` | `transcribe.json:marginalia[]` as `- [position/kind → target_span_id] content` |
| `{{emphasis_lines}}` | `transcribe.json:emphasis[]` as `- "<span_text>": <mark_type> (intensity N)` |
| `{{zones}}` | `composition.json:zones[]` as `zN (region, dominant_kind): content_summary` |
| `{{dominant_flow}}`, `{{whitespace_signal}}` | `composition.json` |
| `{{hierarchy_top3}}` | the three highest-prominence `visual_hierarchy` entries as `zN prominence P — reasoning` |
| `{{layout_semantics}}`, `{{utility_statement}}`, `{{actionability_score}}` | `diagram.json` |
| `{{node_lines}}`, `{{edge_lines}}` | `diagram.json:nodes[]` as `id (role): label`; `edges[]` as `from → to [relation_type] label` |
| `{{diagram_ambiguities}}` | `diagram.json:ambiguities[]` one per line |
| `{{sketch_lines}}` | `sketch.json:sketches[]` as `id: subject — intent, affective_signal (confidence)` |
| `{{table_lines}}` | `table.json:tables[]` as `id (structural_type): interpretation` followed by a compact markdown rendering of headers + cells |
| `{{title}}`, `{{summary}}`, `{{tags}}`, `{{projects}}`, `{{people}}`, `{{organisations}}` | `metadata.json` |
| `{{cross_reference_count}}`, `{{cross_reference_lines}}` | `metadata.json:cross_references[]` as `kind → target ("evidence_span")` |

**Call shape:** system block with `cache_control: {type: "ephemeral"}` (it is identical across every page in a batch), one user turn. Model from `manifest.model_defaults.first_pass` (default `claude-sonnet-4-6`). JSON only. Respect `cost-controls.yaml:per_task_caps.first_pass` (20k input / 1.5k output); when the assembled user turn exceeds the input cap, truncate `{{cleaned_transcript}}` first, then `{{node_lines}}`/`{{edge_lines}}`, never the metadata block.

---

## System prompt (`FIRST_PASS_SYSTEM`)

```
You are a senior knowledge-intelligence analyst. You are given the transcript(s) of one
or more handwritten note pages and you must produce a focused first-pass analysis.

Your output MUST be a single JSON object that conforms exactly to the FirstPassIntelligenceSchema.
Do not include any commentary or text outside the JSON.

## Output sections

### content_summary (string)
Write 3–5 sentences that distil the full content of the page(s). Lead with the most important
idea, decision, or finding. Avoid restating obvious things; aim for signal density.
This is the primary surface for kanban cards, search results, and daily synthesis input.

### structural_map (object)
Map the knowledge structure present in the notes:
- entities : Named people, projects, systems, organisations, tools, or concepts explicitly
             mentioned or clearly implied (strings, singular or proper noun form). These feed
             entity-recurrence detection in the longitudinal themes layer.
- clusters : Thematic groups or topic clusters visible in the notes (e.g. "roadmap items",
             "open questions", "meeting participants"). One short label per cluster.

### diagram_semantics (array)
For each diagram, sketch, flowchart, table, or visual element in the notes:
- diagram_id         : Short label, e.g. "diagram_1", "flowchart_2", "table_1". When a
                       "Diagram structure", "Sketches" or "Tables" section is supplied below,
                       reuse the ids given there (node/sketch/table ids) so artifacts cross-link.
- purpose            : What the diagram is trying to communicate.
- representation_type: e.g. "flowchart", "mind-map", "timeline", "matrix", "venn", "sketch".
- utility            : How this diagram is useful to the note-taker or a future reader.
- actionability      : Whether the diagram suggests next steps or decisions (explain if so).
- ambiguity          : Any unclear elements, missing labels, or uncertain interpretations.
If no diagrams are present, return an empty array.

### action_intelligence (array)
Extract every explicit or implied action, task, decision, or commitment:
- task              : Clear, imperative statement of the action (e.g. "Send proposal to Alice").
- owner_candidates  : Names or roles likely responsible (empty array if not determinable).
- due_hint          : Any date, deadline, or time expression mentioned; empty string if none.
- dependencies      : Other tasks or conditions this action depends on (empty array if none).
- blockers          : Obstacles or blockers explicitly mentioned (empty array if none).
- expected_outcome  : What success looks like for this action.
- confidence        : 0.0–1.0 confidence that this is genuinely an action item vs. noise.
If no actions are found, return an empty array.

### tags (array)
Suggest tags for categorising these notes:
- name       : Short, lowercase, hyphenated tag (e.g. "project-atlas", "q2-planning").
- confidence : 0.0–1.0 confidence in this tag being a good fit. Only emit new tags
               (i.e. tags not already in metadata.tags) when confidence > 0.7.
- rationale  : One sentence explaining why this tag is relevant.
Return 3–10 tags, ordered by confidence descending.

### follow_up_queries (array of strings)
List 0–3 specific, answerable questions a reader or assistant should ask to resolve gaps,
validate assumptions, or deepen understanding. Quality over quantity — each query should
be one a synthesis layer could meaningfully act on. Return [] if the page raises none.

## Using the Layer-1 inputs
You receive more than the transcript: marginalia, emphasis marks, the page's spatial
composition, and (when present) structured diagram, sketch and table extractions plus
extracted metadata. Use them:
- Emphasis with intensity 2–3 marks what the author considered important; let it steer
  content_summary and promote emphasised tasks and decisions in action_intelligence.
- Marginalia often carries owners ("Alice"), doubts ("?"), and cross-references; fold them in.
- Prefer entities already named in the Metadata block; add new ones only when the transcript
  clearly supports them.
- Do not re-describe diagram structure the Diagram block already gives; interpret it.
- If the inputs contradict each other, follow the transcript and note the conflict in
  the relevant ambiguity field.
```

## Doc-type emphasis block

Insert `{{emphasis_block}}` into the user prompt. Choose by `metadata.json:documentType`; when it is `mixed` or not in this table, the block is empty.

```
## Emphasis (doc_type = {{document_type}})
{{guidance}}
- Amplify: {{amplify}}
- Keep terse or empty: {{damp}}
```

| documentType | guidance | amplify | damp |
| --- | --- | --- | --- |
| `meeting-notes` | Meeting notes are decision and commitment records. Pull every owner, deadline, and decision into action_intelligence with high precision; keep diagram_semantics minimal. | action_intelligence (decisions, owners, deadlines); content_summary | diagram_semantics; follow_up_queries |
| `brainstorm` | Brainstorms are exploratory. Prioritise rich tagging and cluster identification; only call out actions when explicitly intended; surface the open questions the brainstorm raised. | tags; structural_map.clusters; follow_up_queries | action_intelligence |
| `project-plan` | Project plans are structured artifacts. Capture every entity, every action with its dependencies, and the structural meaning of any diagrams. Few open questions — the plan is the answer. | structural_map.entities; action_intelligence; diagram_semantics | follow_up_queries |
| `strategy-map` | Strategy maps express relationships between concepts. Focus on entities, clusters, and diagram semantics that explain WHY things connect; tags are secondary. | structural_map (entities + clusters); diagram_semantics | tags |
| `action-list` | An action list is a list of actions. Treat every meaningful line as a separate action_intelligence entry. Other sections can be sparse. | action_intelligence (every line is an action) | structural_map; diagram_semantics; follow_up_queries |
| `personal-reflection` | Personal reflections are narrative thinking. Distil the substance in content_summary; identify the open questions the reflection surfaced; do not invent actions. | content_summary; follow_up_queries | action_intelligence; diagram_semantics |
| `framework-diagram` | Framework diagrams encode conceptual structure. The diagram IS the value — describe its purpose, representation, and utility precisely. Light on actions and tags. | diagram_semantics; structural_map | action_intelligence; tags |
| `ecosystem-map` | Ecosystem maps catalogue entities and their relationships. Maximise entity capture and explain the diagram's structural intent. Few actions; the map is descriptive. | diagram_semantics; structural_map.entities | action_intelligence |
| `research-notes` | Research notes are evidence-gathering. Capture topical tags carefully; record open research questions; summarise findings. Actions are usually only "investigate further". | tags; follow_up_queries; content_summary | action_intelligence |
| `business-development` | BD notes track relationships and follow-ups. Capture every person and organisation; surface every action with owner_candidates; light on diagrams. | action_intelligence; structural_map.entities (people, orgs); content_summary | diagram_semantics |

Record the branch taken as `doc_type_emphasis` in the `page.first-pass-done` event evidence (`"mixed"` when no block was inserted).

## User prompt (`buildFirstPassPrompt()` extended)

```
Perform a first-pass intelligence analysis of the following note page.
Scope: page {{page_id}}
{{emphasis_block}}
## Classification context
doc_type={{doc_type}}, content_mix={{content_mix}}, route_plan={{route_plan}}

## Transcript (cleaned)
{{cleaned_transcript}}

## Marginalia                                   (conditional)
{{marginalia_lines}}

## Emphasis                                     (conditional)
{{emphasis_lines}}

## Page composition
zones:
{{zones}}
dominant_flow: {{dominant_flow}}
whitespace_signal: {{whitespace_signal}}
visual_hierarchy (top 3):
{{hierarchy_top3}}

## Diagram structure                            (conditional — diagram.json present, diagram_count > 0)
{{layout_semantics}}
nodes:
{{node_lines}}
edges:
{{edge_lines}}
utility: {{utility_statement}} (actionability {{actionability_score}})
ambiguities:
{{diagram_ambiguities}}

## Sketches                                     (conditional — sketch.json present, sketch_count > 0)
{{sketch_lines}}

## Tables                                       (conditional — table.json present, table_count > 0)
{{table_lines}}

## Metadata
title: {{title}}
summary: {{summary}}
tags: {{tags}}
projects: {{projects}}
people: {{people}}
organisations: {{organisations}}
documentType: {{document_type}}
cross_references ({{cross_reference_count}}):
{{cross_reference_lines}}

Return the analysis as a single JSON object matching FirstPassIntelligenceSchema exactly.
Cover all six sections: content_summary, structural_map, diagram_semantics,
action_intelligence, tags, follow_up_queries.
```

## Expected response shape (`FirstPassIntelligenceSchema`)

```json
{
  "content_summary": "…",
  "structural_map": { "entities": ["…"], "clusters": ["…"] },
  "diagram_semantics": [
    { "diagram_id": "n1", "purpose": "…", "representation_type": "flowchart", "utility": "…", "actionability": "…", "ambiguity": "…" }
  ],
  "action_intelligence": [
    { "task": "…", "owner_candidates": ["…"], "due_hint": "", "dependencies": [], "blockers": [], "expected_outcome": "…", "confidence": 0.0 }
  ],
  "tags": [ { "name": "…", "confidence": 0.0, "rationale": "…" } ],
  "follow_up_queries": ["…"]
}
```

## Differences from the app prompt

- The app accepted several transcripts in one call (`--- Page N ---`); the skill runs one page per call so the daily layer can attribute by `page_id`. `scope` is therefore always `page {{page_id}}`.
- Marginalia, emphasis, composition, diagram, sketch, table and metadata blocks added to the user turn; a "Using the Layer-1 inputs" section added to the system prompt to tell the model what to do with them.
- `diagram_semantics.diagram_id` is asked to reuse Layer-1 ids so the sanity check in `sanity-check-rules.md` can cross-link.
- The emphasis block is keyed on `metadata.json:documentType` (the SKILL.md table) rather than on a caller-supplied `docType`; same strings.
