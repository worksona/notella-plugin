# notella-plugin

Claude Code plugin marketplace for **notella** — handwritten note intelligence, local-first.

```
/plugin marketplace add worksona/notella-plugin
/plugin install notella@notella-plugin
```

Then `/notella-state init` to create `~/notella/`, drop page photos in `~/notella/inbox/`, and run `/notella-orchestrator`. For unattended runs: `NL_DIR=~/notella claude -p "/notella-orchestrator --auto" --dangerously-skip-permissions`.

Skills (19): `/notella-actions` · `/notella-classify` · `/notella-composition` · `/notella-daily-synthesis` · `/notella-diagram` · `/notella-first-pass` · `/notella-intake` · `/notella-kanban` · `/notella-metadata` · `/notella-monthly-synthesis` · `/notella-orchestrator` · `/notella-project-synthesis` · `/notella-review` · `/notella-sketch` · `/notella-state` · `/notella-table` · `/notella-themes` · `/notella-transcribe` · `/notella-weekly-synthesis`

| Skill | What it does |
| --- | --- |
| `notella-state` | The memory layer — sole reader/writer of the facility: manifest, page lifecycle, events, syntheses, logs |
| `notella-orchestrator` | Walks the ten-step checklist (inbox → pipeline → daily → weekly → project → themes → monthly → stuck archive → ledgers → review); `--auto` for scheduled runs |
| `notella-intake` | Drains `inbox/` into page folders: HEIC→JPG, thumbnails, EXIF + on-page date stamp, deterministic page-ids |
| `notella-classify` | doc_type, content_mix and the route_plan that gates the specialists |
| `notella-transcribe` | Verbatim + structured transcript, marginalia[] and emphasis[] as typed spans |
| `notella-composition` | Page-level spatial map: zones, flow, hierarchy, connections |
| `notella-diagram` | Nodes, edges, layout semantics, utility and actionability of structural diagrams |
| `notella-sketch` | Subject, intent and affective signal of freeform drawings |
| `notella-table` | Cells and structural type of hand-drawn tables, 2×2s and grids |
| `notella-metadata` | Title, summary, tags, projects, people, cross-references; ISO date normalization |
| `notella-first-pass` | Six-section semantic integration of every Layer-1 artifact — what synthesis reads |
| `notella-actions` | Exhaustive action register with owners, due hints, blockers, confidence |
| `notella-daily-synthesis` | Daily brief: decisions, open questions, priorities, momentum, entities — with yesterday as memory |
| `notella-weekly-synthesis` | Weekly brief from the dailies: themes evolved, projects, people, open actions, focus |
| `notella-project-synthesis` | Per-project health: timeline, commitments, drift, blockers, risk |
| `notella-themes` | Longitudinal themes over the whole corpus; dated snapshots with a measured delta |
| `notella-monthly-synthesis` | Month-in-review: theme arc, commitment aging, forecast scorecard and next-month watchlist |
| `notella-review` | Human verdict loop — done / drop / carry / wrong on open items — feeding `verdicts.ndjson` and the ledgers |
| `notella-kanban` | Opens the read-only desktop app (`/Applications/Notella.app`) or runs the Next.js dev server on :3344 |

The facility defaults to `~/notella`; set `NL_DIR` to point the skills (and the desktop app) at another folder.

This repo is the canonical source of the notella skills — edit them here, under `notella/skills/`. The app that displays their output is [worksona/notella-desktop](https://github.com/worksona/notella-desktop).
