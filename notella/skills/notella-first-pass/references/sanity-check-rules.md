# Sanity-check rules — hallucination vs legitimate inference

Step 6 of `notella-first-pass` cross-validates the model output against the Layer-1 artifacts it was given. The checks catch invented content without punishing the inference first-pass exists to do. Outcomes are: **refuse** (schema violations only), **warn** (append to `pipeline.ndjson`, keep the write), or **pass**.

## Principle

Layer 1 says what is on the page. First-pass says what it means. Meaning legitimately includes things not literally written: an implied owner, a cluster label, a question the page raises without asking. So the checks test *groundedness* — can the claim be traced to something on the page — not literal presence.

## Checks

### 1. Entities are grounded

For each `structural_map.entities[]` value, normalise (lowercase, strip punctuation, collapse whitespace) and look for it in:

- `transcribe.json:rawTranscript` or `cleanedTranscript` (substring, or every token of a multi-word entity present within 40 characters of each other);
- `transcribe.json:marginalia[].content`;
- `metadata.json:projects | people | organisations | geography | tags`;
- `diagram.json:nodes[].label`, `sketch.json:sketches[].subject`, `table.json` headers / row labels / cell content.

| Outcome | Condition |
| --- | --- |
| pass | found in any source |
| pass | a manifest canonical form of a mention found in a source (`tulevik` for "Tulevik dashboard") |
| warn `ungrounded-entity` | not found anywhere |

Allowance: up to 2 ungrounded entities per page pass silently when the page has `documentType` in {`strategy-map`, `ecosystem-map`, `brainstorm`} — these pages name concepts by implication. Beyond 2, warn each.

### 2. Diagram references resolve

For each `diagram_semantics[].diagram_id`:

| Outcome | Condition |
| --- | --- |
| pass | matches a `diagram.json:nodes[].id`, a `sketch.json:sketches[].id`, a `table.json:tables[].id`, or a generated label (`diagram_N`, `table_N`, `sketch_N`) with N ≤ the corresponding `*_count` |
| warn `diagram-id-unresolved` | `diagram.json` present with `diagram_count > 0` and the id matches nothing |
| warn `diagram-without-source` | `diagram_semantics` non-empty but no diagram/sketch/table artifact exists and `classify.content_mix.diagram + table + symbolic < 10` |
| pass | `diagram_semantics` non-empty, no L1 visual artifact, but content_mix says visual content exists (the specialist was skipped or stubbed; first-pass interpreting from the transcript's `[Diagram: …]` markers is legitimate) |

### 3. Actions are grounded

For each `action_intelligence[].task`, extract its content words (drop the leading verb, stopwords, and words under 4 characters). Grounded if ≥ 50% of the remaining words (minimum 1) appear in the transcript, marginalia, or `metadata.json:actionItems`.

| Outcome | Condition |
| --- | --- |
| pass | grounded |
| pass | task's `confidence` ≤ 0.6 and ungrounded — the model already flagged it as inferred |
| warn `ungrounded-action` | `confidence` > 0.6 and ungrounded |

Owner candidates are not checked against the page: "David" (the facility owner) and roles are legitimate inferences. They *are* checked against obvious fabrication: an owner that is a full name not present anywhere in the corpus manifest or the page is warned `invented-owner`.

### 4. Tags are a near-subset of metadata tags

Let `M` = `metadata.json:tags`. For each first-pass tag `t`:

| Outcome | Condition |
| --- | --- |
| pass | `t.name ∈ M` (after normalisation) |
| pass | `t.name ∉ M` and `t.confidence > 0.7` and its rationale names something grounded by check 1 or 3 |
| warn `low-confidence-new-tag` | `t.name ∉ M` and `t.confidence ≤ 0.7` — drop the tag from the artifact (this is the one check that edits output; the system prompt already forbids these) |
| warn `tag-flood` | more than 5 new tags on one page |

### 5. Summary mentions nothing foreign

Proper nouns in `content_summary` (capitalised tokens not at sentence start) are run through check 1. Fails warn `ungrounded-summary-noun`. This catches the most damaging hallucination — a confident summary naming a project the page never mentions — which otherwise flows straight into daily briefs.

### 6. Follow-up queries are questions

Each `follow_up_queries[]` entry must end in `?` or begin with an interrogative (what / where / who / when / why / how / which / is / are / does / should). Otherwise warn `non-question-follow-up`. Not refused: the content is usually fine, only the form.

## Refusals

Only these refuse the write (Step 5, not Step 6):

- Missing required section (`content_summary`, `structural_map`, `tags`, `follow_up_queries`; `diagram_semantics` and `action_intelligence` may be empty arrays but must exist).
- `content_summary` under 2 sentences or over 8.
- Any `confidence` outside 0.0–1.0.
- `tags` empty.
- Non-JSON or extra commentary outside the JSON.

One retry with the same prompt plus a one-line reminder of the violated rule; on a second failure, surface the error and leave the page at `phase=transcribed`.

## What the warnings are for

Warnings accumulate in `pipeline.ndjson` as `{"actor": "notella-first-pass", "page_id", "check", "detail"}`. Nobody reads them per page. They are read:

- by `notella-orchestrator`'s report, which counts warnings per check per batch — a spike in `ungrounded-summary-noun` after a model change is the signal to look;
- by `notella-review`, which can surface a page whose first-pass drew three or more warnings for a `wrong` verdict;
- by anyone deciding whether `--reprocess` on a page is worth the spend.

## Examples

| Model output | Page evidence | Verdict |
| --- | --- | --- |
| entity "Project Sunshine" | transcript: "overlap w/ Sunshine?" | pass (token match, manifest alias) |
| entity "JP Morgan" | nothing on page; `tulevik` in metadata.projects whose keywords include `jp-morgan` | warn `ungrounded-entity` — a manifest keyword is not page evidence |
| action "Confirm Alice's Q2 bandwidth" conf 0.85 | marginalia "Alice?" beside "Q2 capacity" | pass |
| action "Schedule board review" conf 0.8 | no "board", no "review" | warn `ungrounded-action` |
| action "Schedule board review" conf 0.5 | same | pass (model flagged it as inferred) |
| tag `pricing-strategy` conf 0.9, not in metadata.tags | transcript discusses "price tiers" | pass |
| tag `hiring` conf 0.6, not in metadata.tags | — | dropped, warn `low-confidence-new-tag` |
| summary names "Decima" | page is about dante; "decima" nowhere on page | warn `ungrounded-summary-noun` |
