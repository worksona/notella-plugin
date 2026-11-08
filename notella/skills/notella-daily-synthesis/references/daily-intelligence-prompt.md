# notella-daily-synthesis — prompt

The complete daily-synthesis prompt, self-contained in the plugin. It is the app's `DAILY_INTELLIGENCE_SYSTEM` and `buildDailyIntelligencePrompt()` (`src/lib/prompts/daily-intelligence.ts`) with the input format adjusted as the SKILL.md describes — each page contributes first-pass **and** metadata **and** (when present) actions — and extended with the **memory block** of Step 3: the carry pool built from the previous brief and the latest closed weekly, the verdict-driven pre-resolved and pre-dropped lists, yesterday's `watch_tomorrow` and the monthly watchlist. The brief it produces continues the one before it: items are `new`, `carried`, `resolved` or `dropped`, and the day opens with a theme and closes with what to watch tomorrow.

**Placeholders:** `{{double-curly}}`. Blocks marked *(conditional)* are omitted, heading included, when their input is absent.

| Placeholder | Source |
| --- | --- |
| `{{date}}` | the target date, `YYYY-MM-DD` |
| `{{weekday}}` | weekday name for `{{date}}` in `identity.timezone` |
| `{{pages_json}}` | the input bundle (shape below) serialised as JSON |
| `{{page_count}}` | number of entries in the bundle |
| `{{previous_date}}` | date of the predecessor brief — the most recent `daily/{d}.json` with `d < date` (gaps skipped: a Monday reads the previous Friday); null on the first brief |
| `{{previous_synthesis_notes}}` | `previous.synthesis_notes` |
| `{{previous_momentum_json}}` | `previous.momentum_signals` |
| `{{carry_pool_json}}` | the carry pool (shape below): every item of `previous.new_decisions`, `previous.unresolved_questions`, `previous.top_priorities` whose status is not `resolved` or `dropped`, plus every `action_items_open[]` item of the latest closed weekly not already in the pool (match on normalised text), minus items a `wrong` verdict removed |
| `{{weekly_week}}` | ISO week of the weekly that supplied the pool's `weekly_action` entries |
| `{{pre_resolved_json}}` | pool items a `done` verdict closed: `[{item, origin_date, evidence: "verdict:{target_id} — {note}"}]` |
| `{{pre_dropped_json}}` | pool items a `drop` verdict closed: `[{item, section, carried_since}]` |
| `{{yesterday_watch_json}}` | `previous.watch_tomorrow` (`[]` for legacy predecessors) |
| `{{monthly_month}}`, `{{monthly_watchlist_json}}` | `[w.prediction for w in latest monthly.next_month_watchlist]` |

**Call shape:** system block with `cache_control: {type: "ephemeral"}` (identical across a catch-up batch), one user turn. Model from `manifest.model_defaults.daily_synthesis` (default `claude-opus-4-6`). Respect `cost-controls.yaml:per_task_caps.daily_synthesis` (50k input / 3k output); when over the input cap, drop `actions` from the bundle first, then truncate each `first_pass.content_summary` to 2 sentences; the memory block is never trimmed. JSON only.

---

## Input bundle shape (`{{pages_json}}`)

```json
[
  {
    "page_id": "2026-05-02-x7k2",
    "page_number": "47",
    "projects": ["tulevik"],
    "first_pass": {
      "content_summary": "…",
      "structural_map": { "entities": ["…"], "clusters": ["…"] },
      "action_intelligence": [ { "task": "…", "owner_candidates": [], "due_hint": "", "confidence": 0.8 } ],
      "tags": ["…"],
      "follow_up_queries": ["…"]
    },
    "metadata": {
      "title": "…", "summary": "…", "documentType": "meeting-notes",
      "people": ["…"], "organisations": ["…"], "themes": ["…"], "ideas": ["…"],
      "cross_references": [ { "kind": "page-ref", "target": "p.43" } ]
    },
    "actions": [ { "task": "…", "owner_candidates": ["…"], "due_hint": "…", "blockers": [], "confidence": 0.85, "source": "actions-extension" } ],
    "emphasis_top": [ "\"ship Friday\": box (intensity 3)" ]
  }
]
```

`first_pass.tags` is flattened to names. `actions` is omitted when `actions.json` is absent. `emphasis_top` is the up-to-5 highest-intensity `transcribe.json:emphasis[]` entries — the author's own highlighting is the cheapest priority signal there is.

## Carry pool shape (`{{carry_pool_json}}`)

Built deterministically in Step 3, before the model sees anything. One entry per open item, in the order: decisions, questions, priorities, then weekly actions.

```json
[
  {
    "section": "new_decisions",
    "text": "Treat workstreams 1, 2 and 5 as quick wins",
    "carried_since": "2026-04-30",
    "source_page_id": "2026-04-30-p2m8",
    "origin": "daily",
    "extra": { "confidence": 0.9 }
  },
  {
    "section": "unresolved_questions",
    "text": "Does workstream-3 overlap with Project Sunshine's data layer?",
    "carried_since": "2026-05-01",
    "source_page_id": "2026-05-01-x7k2",
    "origin": "daily",
    "extra": { "context": "Raised beside the 2x2; no answer on the page" }
  },
  {
    "section": "top_priorities",
    "text": "Follow up with JP Morgan contact on data access",
    "carried_since": "2026-04-28",
    "source_page_id": null,
    "origin": "weekly_action",
    "extra": { "urgency": "high" }
  }
]
```

- `section` is where the item lives in the brief. A weekly action lands in `top_priorities` (it is an open action, which is what a priority is); its `extra.urgency` is the weekly's.
- `carried_since` is the predecessor item's `carried_since` when present, else the predecessor's `date`; for a weekly action, the action's `source_date`. It never moves forward.
- `source_page_id` is the predecessor item's; null for a weekly action (which has a `source_date`, not a page).
- Legacy predecessors (no `status` fields): every item enters the pool with `carried_since: previous.date`.
- Verdicts applied before the pool is serialised: `done` → entry moved to `{{pre_resolved_json}}`; `drop` → moved to `{{pre_dropped_json}}`; `wrong` → removed silently; `carry` → unchanged. A verdict `done` for an item in no pool is ignored.

## System prompt (`DAILY_INTELLIGENCE_SYSTEM`, extended)

```
You are a daily synthesis analyst for a personal knowledge management system. Your role is to review all first-pass intelligence outputs from a single day and produce a coherent operational picture of what actually happened, what was decided, what was closed, what remains open, and where energy is flowing.

Your analysis must be grounded strictly in the provided intelligence data. Do not invent decisions, questions, or entities that are not clearly indicated by the source material.

## Your responsibilities:

### Theme of the Day
One sentence naming the dominant thread across today's pages — what the day was actually about. A sentence, not a list, not a headline fragment.

### New Decisions
Identify explicit and implicit decisions made during the day. A decision is any commitment to a course of action, a choice between alternatives, or a conclusion reached. Assign each decision to its source page and estimate your confidence (0.0–1.0) based on how unambiguous the language is. Every decision carries a status: new today, or carried from the pool (see "Continuing the brief").

### Unresolved Questions
Surface questions that were raised but not answered within the day's notes. Include questions that were deferred, incomplete thoughts that need follow-up, and areas where the author expressed uncertainty. Provide context so the question is meaningful when reviewed later. Every question carries a status.

### Top Priorities
Rank the most important things that need to happen based on urgency signals in the notes: deadlines mentioned, blockers, high-stakes decisions, and items marked explicitly as important (the emphasis_top entries are the author's own marks — weight them). Classify urgency as high (within 24 hours or critical), medium (within a week or important), or low (important but not time-sensitive). Reference the source page for each. Every priority carries a status.

### Resolved Today
Pool items that today's pages closed: a question answered, a priority completed, a decision superseded. Each row names the item in the pool's wording, the date it first appeared (origin_date), the page that closes it (evidence_page_id) and the words on that page that close it (evidence). Items the memory block lists as pre-resolved are copied in as given.

### Momentum Signals
Identify topics, projects, or themes that are gaining or losing energy today. A gaining-momentum signal might be: multiple notes on the same topic, accelerating action items, new people joining a discussion. A losing-momentum signal might be: a project not mentioned despite previous prominence, deferred decisions, stalled actions. Express each as a plain descriptive string.

### Key Entities Active
Identify the most active people, projects, organizations, and concepts in today's notes. For each, write a brief activity_summary describing what role they played today. Use the entity types: person, project, organization, concept, place, task, decision.

### Synthesis Notes
Write a concise executive paragraph (3–5 sentences) summarizing the overall shape of the day: what major themes dominated, what the most significant development was, what the biggest open risk or question is, and what tomorrow's most important focus should be. When yesterday's brief said what to watch for, say in one clause whether today's pages showed it. This paragraph should read as a daily intelligence brief.

### Watch Tomorrow
1 to 3 complete sentences a person can check against tomorrow's pages and mark true or false. Prefer items that follow from today's open threads.

## Continuing the brief
When a memory block is supplied you are continuing a brief, not starting one. The block
holds a CARRY POOL (what the previous brief and the latest weekly left open), a
PRE-RESOLVED list and a PRE-DROPPED list (settled by human verdicts before you were
called), yesterday's WATCH TOMORROW and, when one exists, the month's WATCHLIST.

1. CARRY, DON'T RE-STATE. If today's pages touch an item from the carry pool,
   reuse the pool wording verbatim and mark it status=carried with its
   carried_since. Only write a new item when the substance is new. An item
   that is merely rephrased is carried, not new. If the pages do not mention a
   pool item at all, carry it anyway — silence is not resolution.

2. RESOLVED NEEDS PAGE EVIDENCE. Mark a pool item resolved only when a page in
   today's bundle answers the question, completes the priority, or supersedes
   the decision. Quote the page (evidence) and name it (evidence_page_id).
   "Probably done by now" is not evidence; carry it instead.

3. DROPPED IS RARE. Mark a pool item dropped only when a page explicitly
   abandons it. Otherwise carry it.

4. THEME OF THE DAY is one sentence naming the dominant thread across the
   pages — what the day was actually about — not a list.

5. WATCH TOMORROW is 1–3 statements a person can check against tomorrow's
   pages and mark true or false: "A date is set for the NRCAN demo", not
   "Keep an eye on AIMQC". Prefer items that follow from today's open threads.

6. Items already in the pre-resolved list go in resolved_today as given. Items
   in the pre-dropped list appear once more in their section with
   status=dropped and nowhere else.

Placement rules that follow from the above:
- A carried item stays in the section the pool gives it (a weekly action is a
  top_priorities item). Its source_page_id is the page that re-raised it today,
  or the pool's source_page_id when no page mentioned it.
- A resolved item appears in resolved_today and ALSO once more in its own
  section with status=resolved, so the section shows what closed. It never
  appears as new.
- A dropped item appears once in its own section with status=dropped and its
  carried_since; it is not a resolved_today row.
- An item from the month's watchlist that a page speaks to is mentioned in
  synthesis_notes; the watchlist is context, never a source of items.
- When no memory block is supplied (first brief), every item is status=new,
  resolved_today is empty, and carried_since is omitted everywhere.
```

## User prompt (`buildDailyIntelligencePrompt()` extended)

```
Synthesize the following first-pass intelligence outputs from {{date}} ({{weekday}}) into a daily intelligence report.

## Pages from {{date}} ({{page_count}} pages)
Each entry carries the page's first-pass analysis, extracted metadata, the deeper action register
when one was produced, and the author's strongest emphasis marks.
{{pages_json}}

## Memory — continuing the brief of {{previous_date}}                 (conditional: previous brief or weekly actions exist)
See "Continuing the brief". The previous brief's closing paragraph and momentum, for context only:
{{previous_synthesis_notes}}
{{previous_momentum_json}}

### Carry pool ({{count carry_pool}} items; weekly actions from {{weekly_week}})
Open items from the previous brief and the latest closed weekly. Each must come back as carried,
resolved or dropped — never silently vanish, never re-appear as new.
{{carry_pool_json}}

### Pre-resolved by review verdict                                    (conditional)
Copy these into resolved_today exactly as given (evidence_page_id null, evidence as written).
{{pre_resolved_json}}

### Pre-dropped by review verdict                                     (conditional)
Each appears once more in its section with status=dropped and its carried_since, then nowhere else.
{{pre_dropped_json}}

### Yesterday said to watch for                                       (conditional)
Confirm or deny each in synthesis_notes where today's pages speak to it.
{{yesterday_watch_json}}

### Month watchlist ({{monthly_month}})                                (conditional)
Context only. Mention in synthesis_notes when a page speaks to one of these.
{{monthly_watchlist_json}}

Produce the complete DailyIntelligenceSchema output. Set date to "{{date}}". Set pages_analyzed to {{page_count}}. Every source_page_id must be one of the page_id values above, except on a carried item no page mentioned, where it is the pool's. Every carried item's text and carried_since must match the pool entry. Every resolved_today row must name a pool or pre-resolved item. watch_tomorrow has 1 to 3 entries. Be specific and grounded — use exact language from the source material where it adds precision.
```

When the memory heading is omitted (no predecessor and no open weekly actions) the final paragraph still applies; its carry clauses are vacuous.

## Expected response shape (`DailyIntelligenceSchema`)

```json
{
  "date": "2026-05-02",
  "generated_at": "2026-05-02T19:00:47Z",
  "pages_analyzed": 4,
  "theme_of_day": "Locking the AIMQC Sprint 3 scope before the NRCAN call.",
  "new_decisions": [
    { "decision": "Treat workstreams 1, 2 and 5 as quick wins", "source_page_id": "2026-04-30-p2m8", "confidence": 0.9, "status": "carried", "carried_since": "2026-04-30" },
    { "decision": "Sprint 3 ships without the export path", "source_page_id": "2026-05-02-x7k2", "confidence": 0.85, "status": "new" }
  ],
  "unresolved_questions": [
    { "question": "Does workstream-3 overlap with Project Sunshine's data layer?", "context": "Raised beside the 2x2; no answer on the page", "source_page_id": "2026-05-02-w9m3", "status": "resolved", "carried_since": "2026-05-01" }
  ],
  "top_priorities": [
    { "priority": "Follow up with JP Morgan contact on data access", "urgency": "high", "source_page_id": null, "status": "carried", "carried_since": "2026-04-28" },
    { "priority": "Confirm Alice's Q2 bandwidth before the Sunshine kickoff", "urgency": "high", "source_page_id": "2026-05-02-x7k2", "status": "new" },
    { "priority": "Draft the Toronto office memo", "urgency": "low", "source_page_id": "2026-04-29-r4t1", "status": "dropped", "carried_since": "2026-04-29" }
  ],
  "resolved_today": [
    { "item": "Does workstream-3 overlap with Project Sunshine's data layer?", "origin_date": "2026-05-01", "evidence_page_id": "2026-05-02-w9m3", "evidence": "\"WS3 reads Sunshine's staging tables only — no overlap\" (margin note)" },
    { "item": "Send the NRCAN pre-read", "origin_date": "2026-04-27", "evidence_page_id": null, "evidence": "verdict:7c1e94a0 — sent Thursday by email" }
  ],
  "watch_tomorrow": [
    "A date is set for the NRCAN demo.",
    "Alice answers the Q2 bandwidth question in writing."
  ],
  "momentum_signals": ["…"],
  "key_entities_active": [ { "name": "…", "entity_type": "project", "activity_summary": "…" } ],
  "synthesis_notes": "…"
}
```

Field rules, as Step 6 of the SKILL.md validates them:

- `status` ∈ `new | carried | resolved | dropped` on every item of the three lists. `carried_since` (`YYYY-MM-DD`) is required when `status` is `carried`, `resolved` or `dropped` (it is the pool entry's value) and omitted when `new`.
- `source_page_id` on a `carried` item is the page that re-raised it today, or the predecessor's when no page did; it may be null only for a weekly action no page mentioned.
- `resolved_today[].item` is the pool wording verbatim; `origin_date` equals that entry's `carried_since`; `evidence_page_id` is in the bundle, or null with `evidence` beginning `verdict:`.
- `watch_tomorrow` has 1–3 complete sentences; `theme_of_day` is one non-empty sentence.
- When there is no memory block: every status `new`, `resolved_today` empty (unless a verdict pre-resolved a weekly action, which the pre-resolved list would have shown).

`generated_at` is set by the skill, not the model. Counts for the event (`resolved_count`, `carried_count`, `new_count`) are derived by the skill from `resolved_today` and the three lists' statuses.

## Differences from the app prompt

- Input bundle carries metadata, actions and top emphasis per page, not first-pass alone.
- Memory block: carry pool with `carried_since`, verdict-driven pre-resolved / pre-dropped lists, yesterday's `watch_tomorrow`, the month's watchlist, and the six continuation rules verbatim from the SKILL.md.
- New fields: `theme_of_day`, per-item `status` + `carried_since`, `resolved_today`, `watch_tomorrow`.
- Weekday and explicit `pages_analyzed` supplied rather than asked to be counted.
- Emphasis marks named as a priority signal.
