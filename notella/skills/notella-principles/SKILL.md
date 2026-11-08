---
name: notella-principles
description: "Guiding Dave — distil the principles David states and re-states in his notebook into a durable, evidence-grounded list: each principle with its paraphrases, when it was first and last asserted, how often, whether it is active, dormant or contested, where recent pages pull against it, and what it implies for the open commitments. Use whenever the user says 'guiding principles', 'what are my principles', 'guiding dave', 'refresh principles', 'which principles apply today', 'principles context', 'what do I keep saying', or any request to surface the rules David has written for himself. Cadence-driven (monthly, after notella-themes; the orchestrator schedules it). Runs a deterministic candidate pre-pass (`scripts/extract_candidates.py`), then the Claude session reasons over the candidates; writes `longitudinal/principles.json`, `longitudinal/principles.md` and the paste-anywhere `longitudinal/principles-context.md` through `notella-state`. Emits `principles.refreshed` event."
---

# notella-principles — Guiding Dave

The notebook already says what David believes about how to work: "Focus: ship, not spec" boxed on the first page of the year, "revenue → product → raise" underlined three times, "enforce good agentics" circled under MOST IMPORTANT THEME. The syntheses describe what happened. This skill keeps what David *said he stands for* as a durable object, so a Today screen, a morning review or any Claude session can hold today's work up against it.

## Purpose

1. **Capture** principles as David writes them — short, imperative or aphoristic — with the pages that say so. No principle exists without evidence pages; nothing is invented from tone.
2. **Track** each one over time: first seen, last asserted, times asserted, and a status the skill computes by rule (active / dormant / contested).
3. **Confront** each one with recent behaviour (tensions: pages from the last 60 days of the corpus that pull against it) and with the open commitments (implied actions: what the principle says to do about a real `task_id`).
4. **Carry** it into context: `principles-context.md` is ≤ 25 lines that any Claude session can load or paste, and the desktop Today screen shows three a day.

Division of labour, as in every notella synthesis skill: the script does the counting, the Claude session executing this skill does the reasoning, and every write goes through `notella-state`.

## Inputs and outputs

**Input flags:**
- `--dry-run` — run the pre-pass only; print the yield (spans seen, gated, dropped by reason, clusters, multi-page clusters) and the top 40 candidates. Writes nothing.
- `--today` — read-only. Print the three principles for today (rotation below) with their implied action and tension flag. No model reasoning, no write.
- `--context` — read-only. Print `longitudinal/principles-context.md`.
- `--since YYYY-MM-DD` — restrict the candidate window (default: whole corpus). Status windows are still measured from the corpus end.

**Reads (through `notella-state`, or directly as read-only files):**
- `pages/*/transcribe.json` — `emphasis[]` spans (the pre-pass) and the transcript text (`cleanedTranscript`, else `structured_markdown`, else `verbatim`) to verify quotes
- `pages/*/metadata.json` (title, date) and `pages/*/first-pass.json` (`content_summary`) of evidence pages — context for the model step
- `pages/*/meta.yaml` — pages with `duplicate_of:` are excluded everywhere
- `weekly/*.json` — `ideas_and_insights[]`
- `longitudinal/themes/*.json` and `longitudinal/themes.json` — `conceptual_evolution[]`
- `longitudinal/commitments.ndjson` — open rows (`state` in `proposed | owner_confirmed | in_progress`) for implied actions
- `longitudinal/verdicts.ndjson` — rows with `target_kind: "principle"` (the review loop, below)
- the previous `longitudinal/principles.json`, if any — ids, confirmed/pinned/retired flags carry forward

**Output:**
- `longitudinal/principles.json` — the record (schema below)
- `longitudinal/principles.md` — readable, rendered from the json every run
- `longitudinal/principles-context.md` — one line per live principle, ≤ 25 lines
- one `principles.refreshed` line in `logs/activity.ndjson` and one `principles.refreshed` event

## How a run executes

### Step 1 — Read configuration and the previous record

```
notella-state get-manifest                      → identity.timezone, model_defaults.principles (if set)
notella-state read-ledger {file: verdicts}      → keep rows with target_kind == "principle"
read longitudinal/principles.json               → previous record, may be absent (first run)
```

Resolve the corpus window: `since = --since or min(page date)`, `until = max(page date)` over non-duplicate pages, where page date = `metadata.json:date` if ISO, else the page id's `YYYY-MM-DD` prefix. Compute `dormant_cutoff = until − 90 days` and `tension_since = until − 60 days`.

### Step 2 — Deterministic candidate pre-pass

```
python3 "$CLAUDE_PLUGIN_ROOT/skills/notella-principles/scripts/extract_candidates.py" \
  --nl-dir "$NL_DIR" --out "$TMPDIR/principles-candidates.json"
```

Stdlib only, Python 3.9+. Rules in `references/candidate-extraction.md`; in short:

- **Emphasis gate:** a typed span passes when `intensity ≥ 2` or `mark_type ∈ {star, box, double-underline, circle}`. Untyped spans (bare strings — older transcribe runs wrote these for Feb–Apr 2026) carry no mark, pass, and are flagged `typed: false`; `--typed-only` excludes them.
- **Other sources:** every `weekly/*.json` `ideas_and_insights[]` item and every `conceptual_evolution[].concept` from the themes snapshots (key_pages become evidence).
- **Filters (counted by reason):** date, numeric-only, names-only (every content token is a known person / project / organisation), label (< 2 content tokens), owned-task (a task imperative with an owner marker such as `Name:`, `@x`, `(Name)`, `→ Name`, or a checkbox).
- **Clustering:** normalise (lowercase, strip accents and punctuation, `→` = "to", light plural stemming), then greedy clustering at token Jaccard ≥ 0.6.
- **Per cluster:** representative text, variants, `assertions`, `distinct_pages`, `first_seen`, `last_seen`, ≤ 8 `evidence_pages` (strongest marks first, then chronological spread), `sources`, `max_intensity`, `mark_types`, `statement_like` (reads as a claim, not a label).

`--dry-run` prints the `stats` block and the top 40 candidates, then stops.

### Step 3 — Build the reasoning bundle

The candidate list is mostly labels (project names, product names, section headings); principles are the minority. Give the model step:

1. **Shortlist:** every cluster with `distinct_pages ≥ 2`, or `statement_like`, or `max_intensity ≥ 3`, or a star/double-underline mark, or a weekly/themes source. On the 2026-11-08 facility that is 256 of 699 clusters.
2. **Page context** for each shortlisted cluster's evidence pages: `metadata.title` and the first 300 characters of `first-pass.content_summary`.
3. **Transcript search:** the session may — and should — grep transcripts for paraphrases of a promising candidate, because a principle stated once with emphasis is often restated elsewhere in plain text (e.g. "ORCHESTRATION LIVES as STATE, not SKILLS" on two pages; "REGISTRIES DETERMINE TRUTH" four months earlier).
4. **Previous record** (ids, statements, paraphrases, confirmed / pinned / retired) and the principle verdicts.
5. **Open commitments**, newest first, as `task_id | source_date | task`.

### Step 4 — Reason: write the principles

The Claude session executing the skill does this step itself, following `references/principles-prompt.md`. Rules that matter most:

- **Statement as David writes it.** Prefer his exact words ("Ship, not spec.", "No new workflows."). Combine two of his phrases only when one alone is unclear; never coin a slogan he did not write.
- **Grounding.** Every principle cites ≤ 8 real page ids, and every page cited must assert the principle or a paraphrase. Quoted evidence snippets are ≤ 15 words and must appear in that page's transcript or emphasis spans.
- **7–12 principles.** Fewer when the corpus does not support more. A principle stated once with strong emphasis qualifies; a recurring label does not.
- **Reuse ids.** A continuing principle keeps its previous `id`. Retired principles are never re-proposed (statement or paraphrase Jaccard ≥ 0.6 against a retired one → suppress).
- **Tensions** cite pages from `tension_since` onward where behaviour pulls against the principle. Describe the behaviour, do not moralise.
- **Implied actions** pick the 1–2 open commitments most relevant to each live principle and say, in one imperative sentence, what the principle implies for that `task_id`.

### Step 5 — Compute the deterministic fields (not the model)

For each principle, from its full list of assertion pages (which may exceed the 8 evidence pages):

| Field | Rule |
|---|---|
| `times_asserted` | distinct non-duplicate pages asserting the statement or a paraphrase |
| `first_seen` / `last_asserted` | min / max page date over those pages |
| `status: dormant` | `last_asserted < dormant_cutoff` (no assertion in the last 90 days of the corpus) |
| `status: contested` | not dormant, no assertion since `tension_since`, and tensions cite ≥ 3 distinct pages since `tension_since` |
| `status: active` | otherwise |
| `status: retired` | latest principle verdict is `wrong` — overrides all of the above |
| `confirmed` | latest principle verdict is `done` (sticky) |
| `pinned` | a `pin` verdict exists and no later `wrong` |

### Step 6 — Validate

Any failure refuses the write and allows exactly one retry of Step 4 with the failures quoted:

1. **Grounding** — every id in `evidence_pages`, `tensions[].evidence_pages` exists under `pages/` and is not a duplicate; evidence ≤ 8.
2. **Quotes** — every `evidence_quotes[].text` is ≤ 15 words and found (case- and whitespace-insensitive, markdown stripped) in that page's transcript or emphasis.
3. **Tension window** — every tension page date ≥ `tension_since`.
4. **Commitments** — every non-null `commitment_task_id` exists in `commitments.ndjson` and is open; `commitment_text` equals its `task`.
5. **Shape** — ids are unique kebab-case; `domain ∈ {product, company, personal, method}`; status matches Step 5.

### Step 7 — Render

`references/principles-md-template.md` defines both renders. `principles.md`: per principle — statement, status line, why it is yours (quoted snippets with page ids), tensions, implied actions; retired principles listed by name only at the end. `principles-context.md`: a dated header, one sentence saying these are David's own stated principles to keep in mind, then `- <statement> — <one-line implication for current work>` per active (and contested, marked) principle; ≤ 25 lines total.

### Step 8 — Write and emit

```
notella-state log-longitudinal {kind: principles, json, md, context}
```

Until `notella-state` lists `principles` as a longitudinal kind, the skill writes each file atomically itself (write `*.tmp` in the same directory, then rename), then:

```
append logs/activity.ndjson:
  {"ts", "actor": "notella-principles@0.1.0", "event": "principles.refreshed", "count": N, "active": A}

notella-state log-event {
  id: "principles.refreshed-{date}-{hash6}",        # hash6 = first 6 hex of sha256("{generated_at}|{count}|{active}")
  kind: "principles.refreshed",
  timestamp, page_id: null, entry_id: null, project_slug: null,
  evidence: {count: N, active: A, path: "longitudinal/principles.json"},
  ingested_at, harvester_version: "notella-principles@0.1.0"
}                                                    # → events/{date}/{id}.json + one line in events/{date}.jsonl
```

`active` counts principles whose status is `active` (contested and dormant are not counted).

## Output schema — `longitudinal/principles.json`

```yaml
schema_version: "0.1.0"
generated_at: ISO-8601
corpus: { pages: int, since: date, until: date }
rules: { dormant_days: 90, tension_days: 60, dormant_cutoff: date, tension_since: date }
prepass: { ...stats block from extract_candidates.py }
principles:
  - id: ship-not-spec                       # kebab-case, stable across refreshes
    statement: "Ship, not spec."            # as David writes it
    paraphrases: [string]                   # his other wordings, verbatim
    domain: product | company | personal | method
    first_seen: date
    last_asserted: date
    times_asserted: int
    evidence_pages: [page_id]               # ≤ 8, all real, non-duplicate
    evidence_quotes: [{page_id, text}]      # ≤ 15 words each, verifiable
    status: active | dormant | contested | retired
    confirmed: false                        # true after a `done` verdict
    pinned: false                           # true after a `pin` verdict
    tensions: [{text, evidence_pages}]      # pages within the last 60 days of the corpus
    implied_actions: [{commitment_task_id | null, commitment_text, action}]
notes: [string]
```

## Review-loop integration

`notella-review` records principle verdicts in the shared verdict shape (`longitudinal/verdicts.ndjson`, `correction` event) with `target_kind: "principle"`, `target_id: <principle id>`, `target_text: <statement>`. This skill reads them on its next refresh; `notella-review` itself is unchanged by this document.

| Verdict | Effect on the next refresh | On the Today screen |
|---|---|---|
| `done` | confirm: `confirmed: true`, sticky. A note `rename: <text>` replaces the statement and keeps the old one as a paraphrase. | always eligible for rotation (even when dormant); drawn solid |
| `wrong` | retire: `status: retired`, kept in the json so it is never re-proposed | never shown |
| `carry` | keep as proposed (`confirmed: false`); hides the item from review for 7 days, as for every carry | eligible while active/contested; drawn dotted |
| `pin` (new verb) | `pinned: true` | shown every day, taking one of the three slots |
| `drop` | not offered for principles; if recorded, treated as `wrong` | — |

Review shows each unconfirmed, unretired principle once (until a verdict exists), so a fresh refresh of 7–12 principles costs one short review.

**Today rotation (desktop app, read-only):** three principles a day. Pinned first; remaining slots filled from eligible principles (active or contested, plus any confirmed) by least-recently-shown, ties broken by `times_asserted` descending, then id. A read-only app that cannot keep a shown-log uses the equivalent deterministic rotation: sort eligible by (`times_asserted` desc, id) and take a window of three starting at `(days since 1970-01-01 × 3) mod n`. Each card shows the statement, one implied action and a tension flag when `tensions` is non-empty; click-through opens the evidence pages. Confirmed = solid border, unconfirmed = dotted.

## Idempotency

- `principles.json`, `.md` and `-context.md` are regenerated together every run; the md files can never disagree with the json.
- Ids are stable: a continuing principle keeps its id, so verdicts keep applying. Retired principles stay in the json.
- The event id is deterministic over `(generated_at, count, active)`; re-emitting the same refresh writes nothing new. A second refresh on the same day is a new event (new `generated_at`) and overwrites the three files — the activity log and events keep both.
- The pre-pass is pure: same facility, same output (apart from `generated_at`).

## Cadence

Monthly, after `notella-themes` (it reads the fresh themes snapshot's `conceptual_evolution`). The orchestrator integrates the call; this skill only needs the themes refresh to have happened first. Ad-hoc refreshes (`refresh principles`) are fine at any time; `--today` and `--context` are free.

## Failure modes

| Failure | Behavior |
|---|---|
| No `pages/` under NL_DIR | Script exits 2; nothing written. |
| Pre-pass yields < 20 clusters | Proceed; output may hold fewer than 7 principles. Say so in `notes`. |
| Emphasis is untyped (bare strings) for a whole period | Included and flagged `typed: false`; counted in `stats.spans_untyped`. Do not treat those spans as weaker or stronger than typed ones. |
| A candidate principle appears in the notebook only once with no emphasis | Not a principle. Leave it out. |
| Model cites a page that does not exist or is a duplicate | Validation fails → one retry → still failing: `{status: "ungrounded"}`, nothing written. |
| Quote not found in the page | Same as above. Shorten to a verbatim span. |
| Commitment id not found or not open | Drop that implied action, set `commitment_task_id: null` only when the action stands without a task. |
| Previous `principles.json` unparseable | Proceed as a first run; record the error in `notes`; verdicts still apply by id. |
| `notella-state` does not yet support `kind: principles` | Atomic tmp + rename writes, as in Step 8. |
| Context file would exceed 25 lines | Keep pinned and confirmed first, then active by `times_asserted`; append "… N more in principles.md". |

## What this skill does NOT do

- Does not invent principles from tone, themes or the model's view of what David *should* believe. A principle needs his words on a page.
- Does not edit pages, commitments, verdicts or any synthesis. It reads `commitments.ndjson` and writes only the three principle files, one activity line and one event.
- Does not record verdicts — `notella-review` does. It does not change `notella-review`.
- Does not diagnose. Tensions describe what pages show; they never judge.
- Does not rotate the Today screen — it defines the rule; the desktop app applies it.
- Does not run the orchestrator or themes; it expects a recent themes snapshot but works without one.

## Examples

### "Refresh principles"

```
Corpus: 397 pages (15 duplicates skipped) 2025-12-01 → 2026-05-05
Pre-pass: 1294 spans (556 typed, 738 untyped), 85 gated out, 496 dropped
          (label 290, names 154, date 26, numeric 16, empty 5, owned-task 5)
          + 62 weekly ideas + 4 themes concepts → 699 clusters, 54 multi-page
Shortlist: 256 clusters → reasoning over candidates, page summaries, transcripts
Validated: grounding ✓ quotes ✓ tension window ✓ commitments ✓
Wrote longitudinal/principles.json (12 principles: 9 active, 1 contested, 2 dormant)
Rendered principles.md, principles-context.md (15 lines)
principles.refreshed event emitted.
```

### "Which principles apply today?"

`--today`: reads `principles.json`, applies the rotation, prints three cards (statement, implied action, tension flag). No write.

### "What do I keep saying?"

Read-only: print every live principle with `times_asserted`, `first_seen → last_asserted`, sorted by `times_asserted`.

### "Principles context"

`--context`: prints `longitudinal/principles-context.md` so it can be pasted into a session, or loaded by a session-start hook.

## Reference files

- `references/candidate-extraction.md` — the pre-pass rules, output format and the measured yield on the facility.
- `references/principles-prompt.md` — the reasoning prompt for Step 4, the bundle format and the grounding rules.
- `references/principles-md-template.md` — the `principles.md` and `principles-context.md` renders.
- `scripts/extract_candidates.py` — the pre-pass (stdlib, Python 3.9+).
