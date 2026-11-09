---
name: notella-models
description: "Mental models — find the named thinking structures in David's notebook (frameworks, matrices, hierarchies, loops, pipelines, maps, stacks, lenses, metaphors, principle sets) and keep each as a durable record with a lifecycle: glimpse → forming → functional → ready → deployed, plus dormant and contested; provenance borrowed / adapted / original; shape, readiness checklist, decisions it informed, where it was applied and deployed, lineage, and the next step that would move it on. Use whenever the user says 'mental models', 'my frameworks', 'refresh models', 'what frameworks am I using', 'which models are ready to share', 'model of the day', 'models context', 'apply <model> to <project>', or any request about the structures David thinks with. Cadence-driven (monthly, after notella-principles; the orchestrator schedules it). A deterministic pre-pass (`scripts/notella_models.py prepass`) and bundle feed one reasoning step; `finalize` validates the proposal and computes every stage, status and readiness field. Writes `longitudinal/models.json`, a dated snapshot under `longitudinal/models/`, `models.md` and `models-context.md`; emits `models.refreshed`. The desktop app's Models screens read the record."
---

# notella-models — the structures David thinks with

The notebook is full of structures: "revenue → product → raise" boxed on the first page of the year, a REGISTRIES ↔ CONCERNS matrix, the KAMA framework that went from a name in January to a client pilot three weeks later, the three-tier work-state → project-state → company-state hierarchy drawn four times on one day in May. Themes say what David wrote about; principles say what he stands for. This skill keeps the **tools he thinks with** as durable objects, and tracks how far each one has travelled from a glimpse on one page to something deployed outside the notebook.

## Purpose

1. **Find** named, re-usable structures, borrowed or his own, with the pages that draw or name them. No model without evidence pages.
2. **Stage** each by rule, from evidence, with a dated history: glimpse → forming → functional → ready → deployed; dormant after 90 quiet days; contested when recent pages pull against it.
3. **Measure readiness** with an eight-item checklist (named · drawn twice · shape stable · applied · informed a decision · documented · shared · delivered) so the one item blocking the next stage is always named.
4. **Relate** models: lineage (what it grew out of), feeds, shared vocabulary, convergence.
5. **Carry** it: `models-context.md` (≤ 25 lines) for any Claude session; the desktop app's Models screens and Today's model of the day.

Division of labour as in every notella synthesis skill: the script counts, one reasoning step interprets, the script validates and computes, writes go through `notella-state` conventions.

## Inputs and outputs

**Flags:**
- `--dry-run` — pre-pass only: print the stats and the top 40 shortlisted candidates. Writes nothing.
- `--today` — read-only: `notella_models.py today` prints the model of the day (same rule as the desktop app).
- `--context` — read-only: print `longitudinal/models-context.md`.
- `apply <model-id> --project <slug>` — read-only on the record, done by the session (no script): read the model from `models.json` (kind, vocabulary, canonical shape) and the project's open rows from `commitments.ndjson` (pages whose `meta.yaml project_attributions` include the slug) plus its last 30 days of decisions; lay each item into the model's structure by meaning (a matrix cell, a pipeline stage, a hierarchy level), one line of reasoning per item, and write `drafts/models-apply-<model>-<project>-<date>.md`. Say which items did not fit. The desktop app's Apply screen does a deterministic version for matrices, pipelines and hierarchies.
- `export <model-id> --onepager` — `python3 -I "$S" --nl-dir "$NL_DIR" export <model-id>` writes `drafts/<model-id>.md`: name, statement, parts, the canonical drawing (page, node labels, layout), where it was applied, decisions, deployments, quotes, evidence pages, next step. Readiness `documented` counts on the next refresh only once David files it as a document page or records a `document` deployment through review.

**Reads:** `pages/*/{meta.yaml,metadata.json,first-pass.json,transcribe.json,diagram.json,table.json}` (duplicates excluded everywhere), `longitudinal/themes*.json` (`conceptual_evolution`), `longitudinal/{decisions,commitments,people,verdicts}.ndjson`, `manifest.yaml` projects, the previous `longitudinal/models.json`.

**Writes:** `longitudinal/models.json`, `longitudinal/models/{YYYY-MM-DD}.json` (snapshot, byte-identical), `longitudinal/models.md`, `longitudinal/models-context.md`, one `models.refreshed` line in `logs/activity.ndjson`, one `models.refreshed` event.

## How a run executes

```
S=$CLAUDE_PLUGIN_ROOT/skills/notella-models/scripts/notella_models.py
W=$TMPDIR/notella-models-$(date +%F); mkdir -p "$W"
```

### Step 1 — Configuration
`cost-controls.yaml model_defaults.models` (default `opus`). Previous record and `target_kind: model` verdicts are read by the script.

### Step 2 — Deterministic pre-pass
```
python3 -I "$S" --nl-dir "$NL_DIR" prepass --out "$W/candidates.json"
```
Sources: `metadata.ideas[]` that name a construct (framework, matrix, hierarchy, loop, pipeline, stack, flywheel, canvas, tier, layer, map…), titles of framework-diagram / strategy-map / ecosystem-map pages, first-pass `structural_map.clusters`, arrow chains of ≥ 3 named steps in ideas, emphasis and transcripts, compound or construct-line acronyms (LEDGER-RAIL), a dictionary of borrowed models (Eisenhower, 2×2, S-curve, OKR, flywheel, Wardley, Cynefin, Towers of Hanoi, Kanban, first principles, Pareto, OODA, PDCA, SWOT, JTBD…), and themes `conceptual_evolution`. Clustered at token Jaccard ≥ 0.5. Each page carries a role: `drawn` (framework page, a chain on the page, or diagram nodes sharing the construct's words) or `named`. On the 2026-11-08 facility: 421 clusters, 241 shortlisted.

### Step 3 — Bundle
```
python3 -I "$S" --nl-dir "$NL_DIR" bundle --candidates "$W/candidates.json" --out "$W/bundle.md"
```
Shortlist with page titles, summaries and diagram notes; projects; borrowed dictionary; previous record and verdicts; decisions ledger; open commitments; people.

### Step 4 — Reason (one subagent on the `models` alias)
Dispatch one `Agent` (`subagent_type: general-purpose`, `model: <alias>`) with: the facility path, `$W/bundle.md`, `references/models-prompt.md`, and the output path `$W/proposal.json`. It may grep `pages/*/transcribe.json` for restatements. It returns JSON only.

### Step 5 — Validate and compute
```
python3 -I "$S" --nl-dir "$NL_DIR" finalize --proposal "$W/proposal.json" --report "$W/report.json" --dump "$W/record.json"
```
Drops anything ungrounded with a warning (unknown or duplicate pages, quotes not found or > 15 words, decisions not in the ledger, commitments not in the ledger, tensions outside the 60-day window, unknown parents). Hard errors (no valid pages, duplicate ids, no name) refuse the write; one retry of Step 4 with the errors quoted is allowed. Then computes:

| Field | Rule |
|---|---|
| `glimpse` | one assertion page |
| `forming` | two assertion pages ≤ 90 days apart (or named and drawn on separate pages) |
| `functional` | forming, and: informed a ledger decision, generated a commitment, or applied to a project on ≥ 3 pages |
| `ready` | functional, documented (document page or document/one-pager deployment), and shape stable (or < 2 drawings and ≥ 3 assertions) |
| `deployed` | a `client`, `product`, `skill`, `post` or `talk` deployment (earlier stages are back-filled at that date, noted "implied by deployment") |
| `stage_history` | dated transitions with the page that justified each |
| `shape_stability` | mean Jaccard of the content words in node labels between successive drawings (canonical page restricted to `canonical_node_ids`); null with < 2 drawings |
| `readiness.*` | the eight checks, from the computed fields |
| `status` | `retired` by verdict; else `dormant` if last assertion < corpus end − 90 d; else `contested` if a tension exists and no assertion since corpus end − 60 d; else `active` |
| verdicts | `done` confirms (`rename: <text>` renames, old name kept as alias); `wrong`/`drop` retire; `pin` pins; `promote` / `demote` (note `to: <stage>`) set `verdict_stage`, which the app shows instead of the evidence stage; `merge` (note `into: <id>`) retires this id; `borrowed-from` (note = name) sets provenance |

### Step 6 — Write
```
python3 -I "$S" --nl-dir "$NL_DIR" finalize --proposal "$W/proposal.json" --write
```
Writes the snapshot, `models.md`, `models-context.md`, then `models.json` last (tmp + rename each), appends `models.refreshed` to `logs/activity.ndjson`, and writes the event `models.refreshed-{date}-{sha256(generated_at|count|active)[:6]}` under `events/{date}/` plus one line in `events/{date}.jsonl`. Idempotent per `generated_at`.

## Output schema — `longitudinal/models.json`

```yaml
schema_version: "0.1.0"
generated_at: ISO-8601
corpus: { pages, since, until }
rules: { dormant_days: 90, contested_days: 60, forming_window_days: 90, stable_shape_max_change: 0.4, dormant_cutoff, tension_since }
prepass: { stats } | null
models:
  - id: kama-framework                     # kebab-case, stable across refreshes
    name: "KAMA framework"
    aliases: [string]
    kind: matrix | hierarchy | loop | pipeline | map | stack | lens | metaphor | principle-set | architecture
    domain: product | company | method | personal | creative
    provenance: borrowed | adapted | original
    borrowed_from: string | null
    statement: string
    stage: glimpse | forming | functional | ready | deployed      # computed
    status: active | dormant | contested | retired                # computed
    stage_history: [{stage, date, evidence_pages, note?}]
    first_seen: date
    last_asserted: date
    times_drawn: int
    times_named: int
    assertion_pages: [page_id]             # every page, chronological — drives the usage heat
    evidence_pages: [page_id]              # ≤ 8
    evidence_quotes: [{page_id, text}]
    canonical_shape: {page_id, node_ids, edge_ids, representation_type} | null
    shape_signature: {nodes, edges, representation} | null
    shape_stability: float | null
    vocabulary: [string]
    applied_to: [project slug]
    decisions_informed: [{date, decision, source_page_id}]
    commitments_generated: [{task_id, task}]
    people_shared_with: [string]
    deployments: [{kind, target, date, evidence_pages}]
    readiness: {named, drawn_twice, shape_stable, applied, informed_decision, documented, shared, delivered}
    next_step: string | null
    tensions: [{text, evidence_pages}]
    related_models: [{id, relation: feeds | shares-vocabulary | converging | supersedes}]
    lineage: {parent, children, inferred}
    confirmed: bool
    pinned: bool
    verdict_stage: stage | null
notes: [string]
```

The desktop contract is `notella-desktop/src/lib/models-types.ts`; `GET /api/models` serves this file and the snapshots raw.

## Review-loop integration

`notella-review` shows each unconfirmed, unretired model once (section "Proposed models"), and accepts `done | wrong | carry | pin | promote | demote | merge | borrowed-from` for `target_kind: "model"`, `target_id: <model id>`. Notes carry arguments: `promote — to: ready`, `merge — into: three-tier-state`, `borrowed-from — Eisenhower matrix`, `done — rename: The Docket`. Review only records; the next refresh applies.

## Model of the day

Eligible: status active or contested (or confirmed), stage ≥ forming, not retired. Pinned first. Otherwise rank: ready but not delivered → functional but not documented → forming and untouched ≥ 30 days → the rest; among the top rank, rotate by days since 1970-01-01. The desktop app (`pickModelOfTheDay`) and `today` use the same rule.

## Cadence

Monthly, after `notella-principles` (orchestrator step 7b). Ad-hoc refreshes any time; `--today`, `--context`, `apply` and `export` are free of writes to the record. Cost: one reasoning step (~$1–2 on Opus).

## Failure modes

| Failure | Behaviour |
|---|---|
| No `pages/` | Script exits 2. |
| Proposal not JSON / no `models[]` | finalize exits 2; one retry of Step 4. |
| A model has no valid page | Hard error for that model; the write is refused; one retry. |
| Quote, decision, commitment, tension or parent not grounded | Dropped with a warning; the model stays. |
| Previous `models.json` unparseable | Treated as a first run; verdicts still apply by id. |
| `diagram.json` weak or absent on a page | Shape fields stay null; stability needs two drawings with node labels. Transcripts on formerly rotated pages are known to be weak (2026-11-08 eval); shapes improve after re-transcription. |

## What this skill does NOT do

- Does not invent models from tone or from what David "should" use. A model needs pages that draw or name it.
- Does not edit pages, ledgers, principles or syntheses.
- Does not record verdicts (notella-review does) or deploy anything.
- Does not decide stages by judgement: the script computes them; only a human verdict overrides.

## Reference files

- `references/models-prompt.md` — the reasoning prompt, qualification rules and the proposal format.
- `scripts/notella_models.py` — prepass, bundle, finalize, today, context (stdlib, Python 3.9+).
