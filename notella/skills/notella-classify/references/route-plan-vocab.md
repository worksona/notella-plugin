# route_plan vocabulary

Every entry the classifier may put in `classify.json:route_plan`, the condition under which it belongs there, and the specialist skill that consumes it. The orchestrator (notella-orchestrator, step 2) reads this array to decide which Layer-1 and Layer-2 skills to fan out per page. The authoritative list on a given machine is `manifest.yaml:route_plan_vocab`; this file explains the entries.

| Entry | Include when | Consumer | Always / conditional |
| --- | --- | --- | --- |
| `transcription` | Every page. | `notella-transcribe` | always |
| `semantic_structuring` | Text content is present (`content_mix.text >= 10`). Signals that the cleaned transcript should carry hierarchy (headings, nested bullets) rather than a flat text dump. | `notella-transcribe` (shapes `cleanedTranscript`), `notella-first-pass` | conditional (near-always) |
| `diagram_interpretation` | `content_mix.diagram + content_mix.symbolic >= 15` and the visual content is structural: boxes and arrows, flowchart, mind-map, swim-lanes, network, Venn, matrix of relations. | `notella-diagram` | conditional; the orchestrator additionally requires `content_mix.diagram >= 15` before spending a Sonnet vision call, else writes a stub |
| `sketch_interpretation` | The page contains freeform drawings distinct from structural diagrams: faces, figures, scenes, doodles, icons, process metaphors, illustrations. May co-occur with `diagram_interpretation`. | `notella-sketch` | conditional; orchestrator requires `diagram + symbolic >= 10` |
| `table_extraction` | `doc_type == table`, or `content_mix.table >= 15`. Covers 2×2s, decision grids, comparison matrices, Eisenhower boxes, data tables. | `notella-table` | conditional; orchestrator requires `content_mix.table >= 1` |
| `action_decision` | The page visibly contains tasks, to-dos, checkboxes, deadlines, owners, or decisions. | `notella-actions` (only if `first-pass.action_intelligence.length >= 2`), `notella-first-pass` emphasis | conditional |
| `value_signal` | The page appears to contain ideas, hypotheses, insights, value propositions or plans rather than only records. | `notella-metadata` (`ideas`), `notella-first-pass` (`tags`, `follow_up_queries`), `notella-themes` | conditional |
| `composition` | Every page. Page-level spatial map. | `notella-composition` | always |
| `tagging` | Every page. | `notella-metadata` | always |

## Minimum viable route

```
["transcription", "composition", "tagging"]
```

The skill enforces these three after validation regardless of what the model returned (Step 6 of the SKILL.md). Everything else is additive.

## Order

The array is ordered by the classifier as a hint of importance, but the orchestrator ignores the order: stage order is fixed by phase (`transcribe` → L1 fan-out → `first-pass` → `actions`). Downstream skills test membership only.

## Disambiguation notes

- **diagram vs sketch.** A flowchart with hand-drawn stick figures as node icons is a diagram (the structure carries the meaning). A drawing of two people handing over a box, with a caption, is a sketch (the scene carries the meaning). When both are present on one page, include both entries. When genuinely ambiguous, prefer `diagram_interpretation`: the structural treatment is more useful and `notella-diagram` returns `diagram_count: 0` cleanly if it finds no structure.
- **table vs diagram.** A grid whose cells hold values is a table. A grid whose cells are labelled regions with arrows between them (a 2×2 strategy map with flows) is both: include both entries.
- **checklist and action_decision.** `doc_type: checklist` should almost always carry `action_decision`; a checklist without it is a classification inconsistency the orchestrator flags.
- **Low confidence.** When `confidence < 0.60` the classifier's `fallback_strategy` typically says "treat as handwritten_text". The route_plan then collapses to the minimum set plus `semantic_structuring`; specialists can be added later with `--reprocess`.

## Stub artifacts

When the orchestrator skips a conditional specialist because the content_mix signal is below its threshold, it writes a stub (`{ "<kind>_count": 0, "layout_semantics": "<one line>" }`) so the integrity gate before first-pass is satisfied without a model call. The route_plan entry stays in `classify.json`; the stub records that the entry was honoured cheaply.
