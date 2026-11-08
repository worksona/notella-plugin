# Implicit action rules — when a stated problem becomes an action

`notella-actions` is asked to be exhaustive, which means promoting things that are not written as tasks into imperative actions. Done carelessly this produces a register full of "Consider X" noise that drowns the real commitments in the ledger. These rules say when to promote, how to phrase, and what confidence to give.

## The promotion test

Promote a non-imperative statement to an action only if **all three** hold:

1. **A gap is named.** The text describes something wrong, missing, undecided, or unfinished — not merely a fact. "Latency is 400 ms" is a fact; "latency is too high" names a gap.
2. **A resolution is implied by the author's framing**, not only by the reader's helpfulness. Emphasis marks, a question mark, "need", "should", "must", "still", "yet", "?", "!!", a box or star around it, or placement in a list of to-dos all signal the author saw it as something to act on.
3. **Someone in the author's world could act on it.** "The market is slowing" fails; "our pricing is confusing customers" passes.

If any test fails, leave it out. The page's content_summary and first-pass already preserve the observation.

## Phrasing the promoted task

| Statement pattern | Verb to use | Example |
| --- | --- | --- |
| "X is too slow / broken / unclear / wrong" | Investigate / Fix / Clarify | "The DB is too slow" → "Investigate database performance" |
| "X is missing / we don't have X" | Create / Obtain / Define | "No pricing page yet" → "Create the pricing page" |
| "Need to decide X" / "X or Y?" | Decide | "Monthly or annual billing?" → "Decide between monthly and annual billing" |
| "Should we do X?" | Evaluate | "Should we open a Toronto office?" → "Evaluate opening a Toronto office" |
| "Waiting on X from Y" | Follow up with Y on X | "Waiting on contract from legal" → "Follow up with legal on the contract" |
| "Ask Y about X" / "Y?" beside a line | Ask Y about X | marginal "Alice?" beside "Q2 capacity" → "Ask Alice about Q2 capacity" |
| "Revisit / circle back / park X" | Revisit X | "Park the API redesign" → "Revisit the API redesign" with due_hint from context |
| "X depends on Y" (no task for Y) | Confirm Y | "Launch depends on legal sign-off" → "Confirm legal sign-off for launch" |
| "Idea: X" / "What if X" | Explore X | "What if we bundle support?" → "Explore bundling support" — confidence ≤ 0.4 |

Keep the author's nouns. Do not add scope ("…and present to the board") that is not on the page.

## Confidence for implicit actions

The system prompt's bands apply; these anchor the implicit cases:

| Signal | Confidence ceiling |
| --- | --- |
| Problem statement with emphasis (intensity ≥ 2) or in a to-do list | 0.65 |
| Problem statement, no emphasis, no list context | 0.5 |
| Question written by the author (ends in `?`) | 0.6 |
| Dependency stated without a task for the dependency | 0.55 |
| Idea / "what if" | 0.4 |
| Stated problem plus a named person beside it | add 0.1 (owner evidence) |
| Struck through or ticked | keep the action, confidence unchanged, note completion in `expected_outcome` |

An implicit action never exceeds 0.69. If the model wants to score higher, the action is explicit and should be phrased from the text as written.

## Owners for implicit actions

- A name in the margin, or in the same line → `owner_candidates: [name]`.
- First person ("I should", "my call") → the note-taker (`manifest.facility.owner`).
- "We" with no further cue → empty array; record in `expected_outcome` that ownership is unassigned. Do not default "we" to the note-taker.
- Role words ("legal", "the designer") → the role as written.

## Due hints for implicit actions

Only when the page gives one: a date on the line, "by Friday", "before launch", "Q2". An emphasis mark is urgency, not a date — leave `due_hint` out and let confidence carry the signal.

## Do not promote

- Observations about the world with no gap ("Competitor X raised a round").
- Completed past events ("Shipped v2 on Monday").
- Content inside a diagram node or table cell unless the node/cell is a to-do by form (checkbox, "TODO").
- Headings and section labels ("Risks", "Next steps") — the items under them, yes; the heading, no.
- Meeting attendee lists, dates, page references.
- A problem the same page already resolves two lines later.

## Duplicates and near-duplicates

Before emitting, merge actions whose task text overlaps ≥ 70% by token with another on the same page: keep the more specific phrasing, the union of owners, dependencies and blockers, and the higher confidence. Across pages, duplicates are expected — the ledger aggregator (`aggregate-ledgers.mjs`) and `notella-review` handle recurrence; this skill only de-duplicates within a page.

## Reconciliation marker

After the model returns, the skill tags each action with `source`:

- `first-pass` — overlaps ≥ 70% with a `first-pass.json:action_intelligence[].task`
- `actions-extension` — newly surfaced here

Consumers count `actions-extension` entries to judge whether the deeper run earned its cost; the orchestrator's rule to skip `notella-actions` when first-pass found fewer than 2 actions comes from this telemetry.
