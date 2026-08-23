# `~/notella/` — personal notes intelligence facility

This directory turns the daily flow of handwritten notebook pages into running intelligence over time. Drop photos into `inbox/`; specialist skills classify, transcribe, structure, and synthesize them; reports and longitudinal intelligence accumulate in a known-shape directory tree.

The unit of work is a **page**. The unit of value is **synthesis across pages over time**.

## Mental model — three layers

```
┌──────────────────────────────────────────────────────────────────┐
│  Layer 3 — Connective                                            │
│    notella-daily-synthesis, -weekly-synthesis,                   │
│    -project-synthesis, -themes                                   │
│    → daily/*, weekly/*, projects/{slug}/*, longitudinal/*        │
├──────────────────────────────────────────────────────────────────┤
│  Layer 2 — Semantic (what the page means)                        │
│    notella-metadata, notella-first-pass, notella-actions         │
│    → pages/{id}/{metadata,first-pass,actions}.json               │
├──────────────────────────────────────────────────────────────────┤
│  Layer 1 — Surface (what's on the page)                          │
│    notella-classify, -transcribe, -composition,                  │
│    -diagram, -sketch, -table                                     │
│    → pages/{id}/{classify,transcribe,composition,                │
│                   diagram,sketch,table}.json                     │
├──────────────────────────────────────────────────────────────────┤
│  Layer 0 — Intake                                                │
│    notella-intake                                                │
│    → pages/{id}/{meta.yaml, raw/, derived/}                      │
└──────────────────────────────────────────────────────────────────┘
```

Each layer reads from the layer below. Layer 0 (page records) is **durable**; everything above is **regenerable** from the page records.

## Where evidence comes from

| Surface | Mechanism                          | Cadence            |
| ------- | ---------------------------------- | ------------------ |
| Inbox   | User drops photos into `inbox/`    | On orchestrator run |

Future: scheduled folder-watch, photo-app integration, scanner integration. For now, manual drop is the only entry point.

## Skills you can invoke

| Skill                          | What it does                                              |
| ------------------------------ | --------------------------------------------------------- |
| `notella-state`                | Foundation. Reads, writes, validates. Every other skill routes through it. |
| `notella-orchestrator`         | The conductor. Decides what to run next given calendar + state. |
| `notella-intake`               | Drains `inbox/` → mints page records → kicks off pipeline. |
| `notella-classify`             | Diagnoses doc_type, content_mix, route_plan.              |
| `notella-transcribe`           | Vision transcription with marginalia + emphasis spans.    |
| `notella-composition`          | Page-level spatial map (always runs).                     |
| `notella-diagram`              | Diagram structure: nodes, edges, layout, utility (conditional). |
| `notella-sketch`               | Sketch elements: subject, intent, technique, affect (conditional). |
| `notella-table`                | Table extraction: cells, structural type, interpretation (conditional). |
| `notella-metadata`             | Date, page-no., tags, cross-references (always runs).     |
| `notella-first-pass`           | 8-section semantic integration of Layer 1.                |
| `notella-actions`              | Deeper actions extraction (conditional).                  |
| `notella-daily-synthesis`      | All pages indexed to a date → daily intelligence brief.   |
| `notella-project-synthesis`    | All pages attributed to a project → project intelligence. |
| `notella-weekly-synthesis`     | A week of daily syntheses → weekly report.                |
| `notella-themes`               | Longitudinal theme detection across all pages.            |

## Page lifecycle

Each page progresses through ordered phases:

```
intake → classified → transcribed → first-pass-done → enriched → indexed → archived
```

The orchestrator queries which pages are stuck in each phase and re-queues them.

## Invariants

1. **Evidence is immutable.** Once a page artifact or event file is written, it is never edited. Corrections go in as new events.
2. **All writes flow through `notella-state`.** No skill mutates `~/notella/` directly except `notella-state` itself.
3. **Pages are durable; syntheses are regenerable.** Delete `daily/`, `weekly/`, `projects/`, `longitudinal/` and they can be rebuilt from `pages/`.
4. **Idempotent intake.** Re-running intake on the same source files produces zero new pages.
5. **Local first.** Nothing leaves this directory unless an export skill explicitly does so. `raw/` images contain personal handwriting.

## File index

- `manifest.yaml` — identity, projects, focus, model defaults, intake config
- `state.json` — live counters, last-intake / last-synthesis cursors, lock state
- `SCHEMA.md` — canonical schema for every file in the facility
- `CONCURRENCY.md` — write protocol, locking, conflict resolution
- `README.md` — this file

## How processing actually runs

**Manual / on-demand:**

1. Drop photos into `~/notella/inbox/`.
2. Ask Claude: "run the notella orchestrator" or "process my inbox".
3. The orchestrator drains the inbox, then walks the pipeline phase-by-phase, then queues any overdue synthesis.

**Approval-gated by default:** the orchestrator proposes the next batch of work and asks before running it. An `--auto` flag runs the queue without prompts.

**Scheduled:** a Cowork scheduled task can invoke `notella-orchestrator` daily to keep things flowing without manual prompts.

## Bootstrapping

The first time you use the facility:

```bash
# 1. Init (one-time) — invoked through Claude
#    "init the notella facility" → notella-state init
#    Creates ~/notella/, copies scaffold templates, writes initial state.json.

# 2. Set up your projects
#    Edit ~/notella/manifest.yaml — add your projects with slugs and aliases.

# 3. Drop your first photos
#    cp ~/Downloads/IMG_*.HEIC ~/notella/inbox/

# 4. Run the orchestrator
#    "run the notella orchestrator" → notella-orchestrator
```

After the first run, pages will progress through the pipeline. Daily synthesis becomes available once you have ≥1 page reaching phase=indexed for a given date.

## What this system is and is not

**It is:**
- A personal notes-intelligence facility for one human's handwritten notes.
- AI-readable by design — every page artifact, event, and synthesis is structured and queryable.
- Local-first — your handwriting stays on your machine.
- Composable — every skill is replaceable; the schema is the contract.
- Layered — surface evidence is captured once and re-used by semantic and connective layers.

**It is not:**
- A team note-sharing platform.
- A real-time capture app — the workflow is photograph + drop, not live ink.
- A replacement for the notebook itself. The paper notebook remains primary; the facility makes its content queryable and connects pages over time.
- A direct port of notella-the-app. The Next.js UI is replaced by the filesystem + Claude. The intelligence layer is preserved and extended.
