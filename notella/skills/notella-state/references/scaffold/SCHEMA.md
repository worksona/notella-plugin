# SCHEMA — `~/notella/`

**The contract every skill obeys.** If a file in `~/notella/` doesn't match this schema, `notella-state validate` will flag it.

## Directory layout

```
~/notella/
├── manifest.yaml                # identity, projects, focus, model defaults
├── state.json                   # live counters, cursors, lock state
├── SCHEMA.md                    # this file
├── README.md                    # tour of the facility
├── CONCURRENCY.md               # write protocol, locking, conflict resolution
│
├── inbox/                       # photos drop here; notella-intake drains it
│
├── pages/                       # the durable record per page (a folder per page)
│   └── {page-id}/
│       ├── meta.yaml            # phase, attributions, links
│       ├── raw/                 # immutable original photo
│       │   └── page.{ext}
│       ├── derived/
│       │   ├── page.jpg         # converted from HEIC at intake
│       │   └── thumb.jpg
│       ├── classify.json        # Layer 1 — diagnosis
│       ├── transcribe.json      # Layer 1 — text + marginalia + emphasis
│       ├── composition.json     # Layer 1 — page-level spatial map
│       ├── diagram.json         # Layer 1 — diagrams (conditional)
│       ├── sketch.json          # Layer 1 — sketches (conditional)
│       ├── table.json           # Layer 1 — tables (conditional)
│       ├── metadata.json        # Layer 2 — date, page-no., tags, refs
│       ├── first-pass.json      # Layer 2 — semantic integration (8 sections)
│       ├── actions.json         # Layer 2 — deeper actions (conditional)
│       └── revisions/           # human edits to transcripts, append-only
│
├── entries/                     # multi-page session records
│   └── {entry-id}/
│       └── meta.yaml
│
├── events/                      # atomic evidence — append-only, never edited
│   ├── 2026-05-02/
│   │   ├── page.intake-2026-05-02-a3f9c1.json
│   │   ├── page.classified-2026-05-02-7e2b04.json
│   │   └── ...
│   └── 2026-05-02.jsonl         # daily index — one line per event
│
├── daily/                       # daily intelligence reports
│   ├── 2026-05-02.md
│   └── 2026-05-02.json
│
├── weekly/
│   ├── 2026-W18.md
│   └── 2026-W18.json
│
├── projects/
│   └── {project-slug}/
│       ├── 2026-05-02.md
│       └── 2026-05-02.json
│
├── longitudinal/                # rolling intelligence (rebuilt weekly)
│   ├── themes.json
│   ├── trajectory.json
│   └── patterns.json
│
├── logs/
│   ├── activity.ndjson          # every state mutation
│   ├── pipeline.ndjson          # page-stage runs (was the queue page)
│   └── llm-calls.ndjson         # full audit trail (was the history page)
│
└── locks/
    ├── state.json.lock
    ├── manifest.yaml.lock
    └── pages/
        └── {page-id}.lock       # held only while a stage writes a page artifact
```

---

## Page id format

`{date}-{shortuuid4}` — example: `2026-05-02-x7k2`.

- `date`: ISO-8601 calendar date the page was *captured* (from EXIF if present, otherwise intake date).
- `shortuuid4`: 4 characters from the alphabet `abcdefghjkmnpqrstuvwxyz23456789` (Crockford-flavored, no `i/l/o/0/1` to avoid ambiguity). ~700K combinations per day.

Re-running intake on the same source file produces the same page-id (the hash is over EXIF capture-time + file-content-hash, not wall clock).

## Entry id format

`ent_{date}-{shortuuid4}` — same alphabet. Generated when intake decides to group multiple photos into one entry by EXIF capture-time window.

## Event id format

`{kind}-{date}-{hash}` — example: `page.transcribed-2026-05-02-a4b2c1`.

`hash` is the first 6 hex chars of `sha256(canonical_payload)` where canonical_payload is a sorted-keys JSON of the event's `evidence` plus `page_id`.

---

## Page record — `pages/{page-id}/meta.yaml`

```yaml
schema_version: "0.1.0"
id: 2026-05-02-x7k2
entry_id: ent_2026-05-02-aab1
phase: enriched                          # one of: intake | classified | transcribed | first-pass-done | enriched | indexed | archived
phase_history:
  intake: 2026-05-02T09:14:22Z
  classified: 2026-05-02T09:14:38Z
  transcribed: 2026-05-02T09:15:12Z
  first-pass-done: 2026-05-02T09:15:48Z
  enriched: 2026-05-02T09:16:21Z
source_filename: IMG_4421.HEIC
source_capture_time: 2026-05-02T09:13:51Z   # from EXIF, may be null
ingested_at: 2026-05-02T09:14:22Z
content_mix:                              # mirrored from classify.json for fast filter
  text: 60
  diagram: 25
  table: 0
  symbolic: 5
confidence: 0.86                          # mirrored from classify.json
tags: [project-atlas, q2-planning, strategy]
project_attributions: [project-atlas]
person_attributions: [alice, bob]
links_to: [2026-05-01-q4n9]               # other page-ids
errors: []                                # any pipeline errors that didn't recover
```

## Layer 1 artifacts

### `classify.json`

```yaml
schema_version: "0.1.0"
doc_type: handwritten_text | mixed_text_diagram | diagram | sketch | table | checklist | whiteboard | unknown
content_mix:
  text: 0-100
  diagram: 0-100
  table: 0-100
  symbolic: 0-100
route_plan:                               # subset of route_plan_vocab from manifest
  - transcription
  - composition
  - tagging
  - diagram_interpretation                # only if diagram + symbolic >= 15%
  - sketch_interpretation                 # only if sketch elements present
  - table_extraction                      # only if table doc_type or table content
  - action_decision                       # only if visible tasks/decisions
  - value_signal                          # only if hypotheses/insights present
confidence: 0.0-1.0
fallback_strategy: string | "none"
```

### `transcribe.json`

```yaml
schema_version: "0.1.0"
rawTranscript: string
cleanedTranscript: string                 # markdown
extractedDate: "YYYY-MM-DD" | null
extractedDateConfidence: 0.0-1.0
extractedPageNumber: string | null
extractedPageNumberSource: top-right | other | inferred | null
transcriptConfidence: 0.0-1.0
marginalia:
  - position: top | bottom | left | right | inline
    content: string
    target_span_id: string | null
    kind: annotation | callout | arrow-to | correction | aside
    bbox_pct: [x0, y0, x1, y1]
emphasis:
  - span_id: string
    span_text: string
    mark_type: underline | double-underline | circle | star | box | color | exclamation | arrow-to
    intensity: 1 | 2 | 3
```

### `composition.json` (page-level spatial map; always runs)

```yaml
schema_version: "0.1.0"
zones:
  - id: z1
    region: top | top-left | top-right | left | center | right | bottom | bottom-left | bottom-right | margin-top | margin-bottom | margin-left | margin-right | full-width
    bbox_pct: [x0, y0, x1, y1]
    content_summary: string
    dominant_kind: text | diagram | sketch | table | mixed | empty
    visual_element_ids: [ve_001, ve_002]
dominant_flow: top-down | left-right | right-left | bottom-up | radial | scattered | centered | none
reading_order: [z1, z2, z3]
visual_hierarchy:
  - zone_id: z1
    prominence: 1-5
    reasoning: string
cross_zone_connections:
  - from: z1
    to: z3
    kind: arrow | line | dotted-line | implicit | repeated-motif
    evidence_element_id: ve_017
whitespace_signal: dense | balanced | sparse | very-sparse
```

### `diagram.json` (conditional)

```yaml
schema_version: "0.1.0"
nodes:
  - id: n1
    label: string
    role: container | process | decision | flow | dependency | unknown
    description: string                   # optional
    visual_element_id: ve_004
edges:
  - from: n1
    to: n2
    label: string                         # optional
    relation_type: causal | flow | dependency | sequence | association
    visual_element_id: ve_005
layout_semantics: string
utility_statement: string
actionability_score: 0.0-1.0
ambiguities: [string]
diagram_count: int
```

### `sketch.json` (conditional)

```yaml
schema_version: "0.1.0"
sketches:
  - id: sk_001
    bbox_pct: [x0, y0, x1, y1]
    subject: string                       # "human face", "abstract scene", "process metaphor"
    technique: line | shading | cartoon | technical | mixed
    intent: decorative | illustrative | explanatory | exploratory | mnemonic
    elements:
      - kind: figure | shape | line | annotation
        bbox_pct: [...]
        label: string                     # optional
        visual_element_id: ve_011
    text_association:
      adjacent_to_zone: z2 | null
      relationship: explains | illustrates | decorates | unrelated
    affective_signal: calm | energetic | playful | serious | uncertain | frustrated
    confidence: 0.0-1.0
sketch_count: int
```

### `table.json` (conditional)

```yaml
schema_version: "0.1.0"
tables:
  - id: tb_001
    bbox_pct: [x0, y0, x1, y1]
    structural_type: comparison-matrix | decision-grid | eisenhower | 2x2 | data-table | unknown
    column_headers: [string]
    row_labels: [string]
    cells:
      - row: int
        col: int
        content: string
        visual_element_id: ve_023
    units: string | null
    interpretation: string
table_count: int
```

### Shared primitive: `visual_element`

Used inside `composition.json`, `diagram.json`, `sketch.json`, and `table.json` to refer to spatial regions consistently across artifacts.

```yaml
{
  id: "ve_001",                           # stable per page; sequential per artifact
  kind: "node" | "edge" | "figure" | "shape" | "line" | "symbol" | "text-block" | "cell",
  bbox_pct: [x0, y0, x1, y1],            # 0.0-1.0, top-left origin
  label: string                           # optional
}
```

## Layer 2 artifacts

### `metadata.json`

```yaml
schema_version: "0.1.0"
date: "YYYY-MM-DD" | null
pageNumber: string | null
title: string                             # 6-10 words, specific to content
summary: string                           # 2-4 sentences
tags: [string]                            # lowercase-hyphenated, 8-15
projects: [string]
themes: [string]
ideas: [string]
people: [string]
organisations: [string]
geography: [string]
actionItems: [string]
documentType: strategy-map | project-plan | meeting-notes | brainstorm | action-list | framework-diagram | ecosystem-map | business-development | research-notes | personal-reflection | mixed
cross_references:
  - kind: page-ref | date-ref | person-ref | project-ref | external-doc | url
    target: string
    evidence_span: string
```

### `first-pass.json`

Carries notella's existing 8-section schema:

```yaml
schema_version: "0.1.0"
content_summary: string                   # 3-5 sentences, signal-dense
structural_map:
  entities: [string]
  relationships:
    - "A → verb → B"
  clusters: [string]
diagram_semantics:                        # may reference diagram.json ids
  - diagram_id: string
    purpose: string
    representation_type: flowchart | mind-map | timeline | matrix | venn | sketch
    utility: string
    actionability: string
    ambiguity: string
action_intelligence:
  - task: string
    owner_candidates: [string]
    due_hint: string
    dependencies: [string]
    blockers: [string]
    expected_outcome: string
    confidence: 0.0-1.0
value_hypotheses:
  - hypothesis: string
    value_type: strategic | operational | technical | personal | financial | creative
    confidence: 0.0-1.0
tags:
  - name: string
    confidence: 0.0-1.0
    rationale: string
uncertainty_register:
  - span: string
    issue: string
    severity: low | medium | high
follow_up_queries: [string]
```

### `actions.json` (conditional)

```yaml
schema_version: "0.1.0"
actions:
  - task: string
    owner_candidates: [string]
    due_hint: string                      # optional
    dependencies: [string]
    blockers: [string]
    expected_outcome: string              # optional
    confidence: 0.0-1.0
total_actions: int
high_confidence_count: int
```

---

## Event envelope — `events/YYYY-MM-DD/{id}.json`

```json
{
  "schema_version": "0.1.0",
  "id": "page.transcribed-2026-05-02-a4b2c1",
  "kind": "page.transcribed",
  "timestamp": "2026-05-02T09:15:12Z",
  "page_id": "2026-05-02-x7k2",
  "entry_id": "ent_2026-05-02-aab1",
  "project_slug": null,
  "evidence": {
    "transcript_confidence": 0.86,
    "extracted_date": "2026-05-02",
    "char_count": 1842
  },
  "ingested_at": "2026-05-02T09:15:13Z",
  "harvester_version": "notella-transcribe@0.1.0"
}
```

### Required fields

| Field               | Type     | Notes                                         |
| ------------------- | -------- | --------------------------------------------- |
| `id`                | string   | `{kind}-{date}-{hash}`. Deterministic.        |
| `kind`              | enum     | See "Event kinds" below.                      |
| `timestamp`         | ISO-8601 | When the event happened (not when ingested).  |
| `page_id`           | string?  | Required for all `page.*` kinds.              |
| `entry_id`          | string?  | Optional.                                     |
| `project_slug`      | string?  | Optional; one of `manifest.yaml:projects.*.slug`. |
| `evidence`          | object   | Kind-specific structured proof.               |
| `ingested_at`       | ISO-8601 | When notella-state wrote the event.           |
| `harvester_version` | string   | Semver of the calling skill.                  |

### Event kinds

| Kind                    | Meaning                                          |
| ----------------------- | ------------------------------------------------ |
| `page.intake`           | New page minted from inbox.                      |
| `page.classified`       | classify.json written.                           |
| `page.transcribed`      | transcribe.json written.                         |
| `page.first-pass-done`  | first-pass.json written.                         |
| `page.enriched`         | All route_plan'd specialists complete.           |
| `page.indexed`          | Attributions written.                            |
| `page.archived`         | Pulled into ≥1 daily synthesis.                  |
| `synthesis.daily`       | Daily intelligence written.                      |
| `synthesis.project`     | Project intelligence written.                    |
| `synthesis.weekly`      | Weekly synthesis written.                        |
| `themes.refreshed`      | Longitudinal themes rebuilt.                     |
| `inbox.drained`         | Intake processed the inbox.                      |
| `manifest.edited`       | Manifest updated.                                |
| `correction`            | Correction to an earlier event/artifact.         |

---

## State.json

```json
{
  "schema_version": "0.1.0",
  "first_intake_at": null,
  "last_intake_at": null,
  "last_synthesis_at": {
    "daily": null,
    "weekly": null,
    "by_project": {}
  },
  "last_longitudinal_at": null,
  "last_orchestrator_run": null,
  "counters": {
    "pages_total": 0,
    "pages_by_phase": { "intake": 0, "classified": 0, "transcribed": 0, "first-pass-done": 0, "enriched": 0, "indexed": 0, "archived": 0 },
    "entries_total": 0,
    "events_total": 0,
    "events_by_kind": {}
  },
  "active_locks": []
}
```

---

## Daily synthesis (`daily/YYYY-MM-DD.json`)

Carries notella's existing `DailyIntelligenceSchema`:

```yaml
schema_version: "0.1.0"
date: "2026-05-02"
generated_at: ISO-8601
pages_analyzed: int
new_decisions:
  - decision: string
    source_page_id: string
    confidence: 0.0-1.0
unresolved_questions:
  - question: string
    context: string
    source_page_id: string
top_priorities:
  - priority: string
    urgency: high | medium | low
    source_page_id: string
momentum_signals: [string]
key_entities_active:
  - name: string
    entity_type: person | project | organization | concept | place | task | decision
    activity_summary: string
synthesis_notes: string
```

The matching `daily/YYYY-MM-DD.md` is the human-readable narrative.

## Weekly synthesis (`weekly/YYYY-Www.json`)

Same shape as the existing notella weekly report: executive summary, key themes evolved, projects progressed, people and relationships, ideas and insights, action items, suggested focus for next week.

## Project synthesis (`projects/{slug}/{date}.json`)

Carries notella's existing `ProjectIntelligenceSchema`: timeline_summary, commitments_assessment, drift_signals, blockers, momentum_assessment, next_actions, risk_summary.

## Activity log entry

```json
{"ts": "2026-05-02T09:15:13Z", "actor": "notella-transcribe", "event": "events.batch.ingested", "kind": "page.transcribed", "count": 1, "summary": "Transcribed page 2026-05-02-x7k2"}
```

## Pipeline log entry

```json
{"ts": "2026-05-02T09:15:12Z", "actor": "notella-transcribe", "page_id": "2026-05-02-x7k2", "artifact": "transcribe", "status": "written", "duration_ms": 4823}
```

## LLM call log entry

```json
{"ts": "2026-05-02T09:15:08Z", "actor": "notella-transcribe", "page_id": "2026-05-02-x7k2", "task": "transcribe", "provider": "anthropic", "model": "claude-sonnet-4-6", "tokens": {"input": 1842, "output": 2103}, "latency_ms": 4391, "status": "complete"}
```

---

## Ground rules

1. **Evidence is immutable.** Once a page artifact or event file is written, it is never edited. Corrections go in via a new event with `kind: "correction"` referencing the original.
2. **All writes flow through `notella-state`.** No skill mutates `~/notella/` directly except `notella-state` itself.
3. **Per-day directories.** Events are filed under `events/YYYY-MM-DD/` to keep directories from getting absurdly large.
4. **Daily JSONL is regenerable.** If `events/2026-05-02.jsonl` is lost, `notella-state rebuild-events-index 2026-05-02` recreates it from the per-event JSONs.
5. **Schema versions are explicit.** Every file declares its `schema_version`. Migrations are versioned.
6. **Pages are the durable record.** Synthesis layers may be deleted and rebuilt from page records without loss.

## What this schema does NOT cover

- **Theme inference rules** — that's `notella-themes`'s job.
- **Project attribution rules** — `notella-state` accepts whatever the caller decided; corrections via `correction` events.
- **Privacy / redaction policy** — covered separately. Default: nothing leaves `~/notella/` unless an export skill does so explicitly.
- **KG materialization** — deferred. The data exists in `first-pass.json:structural_map`; a future `notella-kg` will materialize.
