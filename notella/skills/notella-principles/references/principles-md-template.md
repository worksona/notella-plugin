# Rendering — principles.md and principles-context.md

Both files are rendered deterministically from the validated `principles.json` on every run, and written together with it.

## `longitudinal/principles.md`

```
# Guiding Dave — principles from the notebook
**Generated {generated_at} | {corpus.pages} pages | {corpus.since} → {corpus.until} | {count} principles: {active} active, {contested} contested, {dormant} dormant**

These are principles David has written in his notebook, in his words, with the pages that say so. Unconfirmed until confirmed in `notella review`. Status: active = asserted in the last 90 days of the corpus; dormant = not; contested = recent pages (last 60 days) pull against it and it has not been re-asserted since.

## Active                        ← one subsection per principle, ordered by times_asserted desc
## Contested
## Dormant
## Retired                       ← names only: "- {statement} (retired {date of verdict})"; "None." when empty
## Notes                         ← notes[] as bullets
```

Each principle subsection:

```
### {statement}
`{id}` · {domain} · asserted {times_asserted}× · {first_seen} → {last_asserted} · {confirmed ? "confirmed" : "unconfirmed"}{pinned ? " · pinned" : ""}

Also written as: {paraphrases joined with " · "}            ← omitted when empty

**Why it is yours**
- "{quote}" — {page_id}                                     ← every evidence_quotes item
Evidence pages: {evidence_pages joined with ", "}

**Tensions**                                                ← "None in the last 60 days." when empty
- {text} ({evidence_pages joined with ", "})

**Implied actions**                                         ← "None." when empty
- {action} — commitment `{commitment_task_id}`: {commitment_text}
```

Empty sections render a single line "None." so the section set is constant.

## `longitudinal/principles-context.md`

Meant to be pasted into, or loaded by, any Claude session. ≤ 25 lines including the header. Plain markdown, no tables.

```
# Guiding Dave — {until-of-run date, i.e. generated_at date}
These are David's own principles, stated in his notebook ({corpus.since} → {corpus.until}); keep them in mind and name it when a plan pulls against one.

- {statement} — {one-line implication for current work}
- {statement} (contested) — {implication}
…
(Full evidence: ~/notella/longitudinal/principles.md)
```

Order: pinned, then confirmed, then active by `times_asserted` desc, then contested. Dormant and retired principles are not listed. The implication is one line (≤ 20 words), concrete to the current open work — it names a project or commitment when one is relevant. If the list would exceed 25 lines, cut from the end and add "… N more in principles.md".
