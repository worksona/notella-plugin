---
name: notella-metadata
description: "Extract structured metadata from a notella page transcript — date, page number, title, summary, tags, projects, themes, ideas, people, organisations, geography, action items, document type, cross-references. Use whenever the user says 'extract metadata for page X', 'tag this page', 'who is mentioned', 'what projects appear', 'summarize this page', or any request to derive structured fields from a transcript. Always runs. Reads through `notella-state`; writes `metadata.json`."
---

# notella-metadata — the metadata extractor

Layer-2 specialist that reads the transcript and produces structured fields downstream layers depend on.

## Purpose

Pull out the structured signal a transcript carries — title, summary, tags, every project/person/place mentioned, every action item, the type of document it is. Plus typed cross-references (which the transcribe skill leaves as inline cues; this skill promotes them).

## Inputs and outputs

**Input:** Page at `phase=transcribed`. Reads `transcribe.json`, optional `composition.json`.

**Output:**
- `pages/{page-id}/metadata.json`
- Mirror `tags`, `project_attributions`, `person_attributions` into `meta.yaml` for fast filtering
- No phase advance (Layer-2 specialist; phase advances are managed by orchestrator after enrichment fan-out completes).

## How a run executes

### Step 1 — Read configuration & page

```
notella-state get-manifest → cost-controls.yaml:model_defaults.metadata, manifest.projects, manifest.people_aliases
notella-state get-page-artifact {page-id, artifact: transcribe}
```

### Step 2 — Acquire the page lock

### Step 3 — Build the prompt

Use the prompt in `references/metadata-prompt.md` — the complete prompt shipped with this plugin. Beyond the original app extraction prompt it carries one structural extension, the `cross_references` array, plus the canonical-attribution and ISO-date instructions described below.

```
## cross_references (array)
For every reference to other content the page makes:
- kind: page-ref | date-ref | person-ref | project-ref | external-doc | url
- target: the canonical reference target (e.g., "p.47", "2026-05-01",
          "alice", "project-atlas", "https://...", "Q2 strategy doc")
- evidence_span: the verbatim text that anchored this reference
```

Pass `manifest.projects` aliases and `manifest.people_aliases` so the model can attribute mentions to canonical slugs. The prompt explicitly instructs:

```
When you see a project mention that matches one of the following project
slugs (or any of their aliases), record the canonical slug:
{project-list}

When you see a person mention that matches one of the following canonical
names (or any of their aliases), record the canonical name:
{person-aliases}

For mentions that don't match any known project/person, record them as-is —
they may be added to the manifest later.
```

### Step 4 — Call the model

Runs on the model in `cost-controls.yaml` `model_defaults.metadata` (currently `haiku`, chosen by the 2026-11-08 eval: text-only field extraction). When the orchestrator runs this stage it dispatches a subagent with that model; run directly, it uses the session model.

### Step 5 — Validate

```yaml
date: "YYYY-MM-DD" | null       # ISO only — see Step 5a; non-ISO strings fail validation
date_raw: string | null         # the model's pre-normalization value, kept for audit
pageNumber: string | null
title: string                   # 6-10 words
summary: string                 # 2-4 sentences
tags: [string]                  # 8-15
projects: [string]              # canonical slugs preferred
themes: [string]
ideas: [string]
people: [string]                # canonical names preferred
organisations: [string]
geography: [string]
actionItems: [string]
documentType: strategy-map | project-plan | meeting-notes | brainstorm | action-list | framework-diagram | ecosystem-map | business-development | research-notes | personal-reflection | mixed
cross_references:
  - kind, target, evidence_span
```

### Step 5a — Date normalization (required before validation)

`date` must be ISO `YYYY-MM-DD` or `null`. Nothing else passes validation. The facility has 412 `metadata.json` files whose `date` values mix ISO with handwriting forms such as `"Feb 10/26"`, `"03-02"` and `"'2026-03-0"`, which break the authoritative-date chain daily synthesis depends on. The model is asked for ISO in the prompt, but the skill normalizes deterministically anyway, in this order:

1. **Already ISO** (`^\d{4}-\d{2}-\d{2}$`) and a valid calendar date → keep.
2. **Strip noise**: leading/trailing quotes, apostrophes, whitespace, trailing `.`; `/` and `.` between numeric fields become `-`.
3. **Resolve the year** when the form has none. Year source, in order: `meta.yaml:page_date_year`; the year of `meta.yaml:source_capture_time`; the year of `meta.yaml:ingested_at`. If the resolved month-day is more than 14 days after the capture date, use the previous year (a December page photographed in January).
4. **Recognized forms** (month names match English full or 3-letter abbreviations, case-insensitive):

   | Written | Parse as | Example → result |
   | --- | --- | --- |
   | `MM-DD`, `MM/DD`, `M-D`, `M/D` | month, day; year resolved | `03-02` → `2026-03-02`; `2/10` → `2026-02-10` |
   | `Mon D/YY`, `Mon D/YYYY`, `Mon D, YYYY` | month name, day, year | `Feb 10/26` → `2026-02-10` |
   | `Mon D`, `D Mon`, `Mon DD`, `DD Mon` | month name, day; year resolved | `10 Feb` → `2026-02-10` |
   | `YYYY-MM-D`, `YYYY-M-D` | zero-pad | `2026-3-2` → `2026-03-02` |
   | `YY-MM-DD` with `YY` in 24–29 | expand century | `26-02-10` → `2026-02-10` |
   | `DD-MM-YYYY`, `DD/MM/YYYY`, `MM/DD/YYYY` | resolve by which field exceeds 12; if both ≤ 12, prefer the order that matches `page_date_stamp` | `10/02/2026` → `2026-02-10` when the stamp is `02-10` |

5. **Truncated or impossible** (`'2026-03-0`, `02-30`, `13-45`, a bare year, a weekday name) → normalization fails.
6. **Cross-check**: when `meta.yaml:page_date_stamp` is present and the normalized date's `MM-DD` differs from it, keep the normalized date but log `{"kind": "date-stamp-mismatch", ...}` to `meta.yaml:errors`.

**On failure**: do not write the artifact with the unparsed string. Set `date: null`, append `{"actor": "notella-metadata", "kind": "date-normalization-failed", "raw": "<as returned>", "at": <timestamp>}` to `meta.yaml:errors`, and continue — a null date falls through the authoritative-date chain (`transcribe.extractedDate` → `source_capture_time` → `ingested_at`) rather than poisoning it. Apply the same normalization to `transcribe.json:extractedDate` when reading it in Step 6; a non-ISO value there is treated as absent.

Record the pre-normalization string as `date_raw` in `metadata.json` so a reprocess can audit the conversion.

### Step 6 — Reconcile date

If `metadata.date` is non-null AND differs from `transcribe.json:extractedDate` (both normalized per Step 5a):
- If both are confident, prefer the metadata extraction's date but log the disagreement to `meta.yaml:errors` for review.
- If transcribe date had higher confidence, prefer that one.
- If only one is a valid ISO date, use it.

### Step 7 — Mirror into meta.yaml

```
notella-state update-page-meta {page-id, fields: {tags, project_attributions: projects, person_attributions: people}}
```

### Step 8 — Write the artifact & release lock

```
notella-state log-page-artifact {page-id, artifact: metadata, payload: <validated>}
notella-state release-page-lock {page-id, actor: notella-metadata}
```

## Idempotency

Standard.

## Failure modes

| Failure                                                       | Behavior |
| ------------------------------------------------------------- | -------- |
| Project mention is ambiguous between two manifest projects    | Record both as candidates; surface in pipeline.ndjson; user can clarify by editing manifest aliases. |
| Person mention has no manifest match                          | Record as written; user may add to `manifest.people_aliases` later. |
| Cross-reference target is fuzzy ("see last week's note")      | Record kind=date-ref with target as best-effort ISO date; downstream may resolve via search. |
| `date` cannot be normalized to ISO (`"'2026-03-0"`, `"02-30"`)  | Write `date: null`, keep the raw string in `date_raw`, append a `date-normalization-failed` warning to `meta.yaml:errors`; the authoritative-date chain falls through to transcribe / capture time. |
| `date` disagrees with `meta.yaml:page_date_stamp`              | Keep the normalized date; log `date-stamp-mismatch` to `meta.yaml:errors` for review. |

## What this skill does NOT do

- Does not perform synthesis — that's `notella-first-pass`.
- Does not extract actions deeply — `notella-actions` does that with full context.
- Does not edit the manifest. New projects / people are surfaced for the user to confirm.

## Examples

### "Extract metadata for page 2026-05-02-x7k2"

```json
{
  "date": "2026-05-02",
  "pageNumber": "47",
  "title": "Q2 prioritization grid for sovereign infrastructure roadmap",
  "summary": "A 2x2 of effort vs. value covering five candidate workstreams. Three are flagged as quick wins; one is marked as 'avoid'. Open questions remain about resource overlap with Project Sunshine.",
  "tags": ["q2-planning", "prioritization", "project-sunshine", "infrastructure", "sovereignty", "2x2", "effort-value", "roadmap"],
  "projects": ["project-sunshine"],
  "themes": ["prioritization", "sovereignty"],
  "people": ["alice"],
  "documentType": "framework-diagram",
  "cross_references": [
    { "kind": "page-ref", "target": "p.43", "evidence_span": "see prior framing on p.43" }
  ]
}
```

## Reference files

- `references/metadata-prompt.md` — full prompt with cross_references extension.
- `references/canonical-attribution.md` — how alias matching works.

Date normalization rules live in Step 5a above; they are deliberately in the SKILL.md because every run applies them.
