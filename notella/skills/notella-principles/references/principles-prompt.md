# Principles prompt — the reasoning step

The Claude session executing `notella-principles` performs this step itself over the bundle built in SKILL.md Step 3. If a manifest sets `model_defaults.principles`, a sub-call to that model may be used instead; the prompt and the validation are the same.

## Role

```
You are reading David's handwritten notebook to find the principles he has
written for himself: rules of thumb, stances, decision rules, aphorisms. You
receive pre-clustered emphasised statements (with counts, dates and page ids),
the titles and first-pass summaries of their pages, the previous principles
record with any human verdicts, and the open commitments.

A principle is something David asserts as a rule for how he or his companies
should act or think — "Ship, not spec.", "Revenue → product → raise.",
"No new workflows." It is NOT a goal with a date ("$10k MRR by June"), a
product name, a section heading, a task, a fact, or a theme you infer.

Produce 7–12 principles, fewer if the notebook does not support them.
```

## What qualifies

- **Asserted, not inferred.** There must be at least one page where David writes it (or a recognisable paraphrase) himself. Strong emphasis (intensity 3, box, star, "MOST IMPORTANT", repeated for emphasis) lets a single page qualify. A recurring *label* never qualifies, however often it recurs.
- **General beyond its moment.** "MVP feature freeze Feb 15 must not slip" is a paraphrase of a principle (ship, don't drift), not a principle by itself. A time-boxed rule ("No new projects until March") may be the clearest statement of a durable one — keep his words as a paraphrase and say in `notes` that it was time-boxed.
- **His words.** `statement` reuses his wording, short, imperative or aphoristic. Where his own line is a question ("what is the minimal structure that enables complexity"), the statement may drop the question form; record the original as a paraphrase. Never coin.

## How to work

1. Walk the shortlist strongest first (intensity 3, box/star, MOST IMPORTANT, multi-page, statement_like).
2. For each plausible principle, search transcripts for restatements in plain text — same idea, different words, other months. Those pages are assertions too.
3. Merge candidates that say the same thing; keep the clearest as `statement`, the rest as `paraphrases` (verbatim).
4. Assign `domain`: `product` (what we build and how it behaves), `company` (money, sales, structure, portfolio), `personal` (how David works and lives with the work), `method` (how to think, design and run systems).
5. List every assertion page (for the computed fields) and choose ≤ 8 `evidence_pages` spanning the range — earliest, strongest, latest.
6. Pull 2–4 `evidence_quotes` per principle: ≤ 15 words each, copied verbatim (markdown stripped) from that page's transcript or emphasis spans.
7. **Tensions:** look only at pages dated within the last 60 days of the corpus. Where the pages show behaviour that pulls against the principle, write one plain sentence describing the behaviour and cite the pages. Do not moralise, do not diagnose, do not speculate about what happened off the page.
8. **Implied actions:** from the open commitments, choose the 1–2 most relevant to each live principle (active or contested; dormant only when a tension makes it relevant now). Copy `task_id` and `task` exactly; write `action` as one imperative sentence saying what the principle implies for that task. If the principle implies an action no commitment covers, use `commitment_task_id: null` and say so in `commitment_text`.
9. **Previous record:** reuse ids for continuing principles. Never re-propose a retired one. Keep confirmed statements as they are unless a `rename:` verdict changed them.

## Output

Return JSON only:

```json
{
  "principles": [
    {
      "id": "kebab-case",
      "statement": "…",
      "paraphrases": ["…"],
      "domain": "product|company|personal|method",
      "assertion_pages": ["page-id", "…"],
      "evidence_pages": ["≤ 8 page ids"],
      "evidence_quotes": [{"page_id": "…", "text": "≤ 15 words, verbatim"}],
      "tensions": [{"text": "…", "evidence_pages": ["…"]}],
      "implied_actions": [{"commitment_task_id": "…|null", "commitment_text": "…", "action": "…"}],
      "one_line_implication": "≤ 20 words, for principles-context.md"
    }
  ],
  "notes": ["anything ambiguous: merges, time-boxed rules, candidates rejected and why"]
}
```

The skill — not the model — computes `times_asserted`, `first_seen`, `last_asserted`, `status`, `confirmed`, `pinned` from `assertion_pages`, the corpus window and the verdicts (SKILL.md Step 5), and drops `assertion_pages` and `one_line_implication` from the stored record after rendering (the implication is kept in the context file).

## Grounding rules (checked in Step 6)

- Every page id exists under `pages/`, is not a `duplicate_of` page, and asserts what it is cited for.
- Every quote is found in its page; ≤ 15 words.
- Tension pages are within the last 60 days of the corpus.
- Every `commitment_task_id` exists in `commitments.ndjson` with an open state, and `commitment_text` is its `task` verbatim.
- No principle without an assertion page; no principle that matches a retired one.
