# notella-metadata — prompt

The complete metadata-extraction prompt, self-contained in the plugin. It is the app's `buildExtractMetadataPrompt()` (`src/lib/prompts/extract-page-metadata.ts`) with the notella extensions folded in: the `cross_references` array, the canonical project/person attribution block, and the ISO date constraint.

**Placeholders:** `{{double-curly}}`. Substitute every one before sending:

| Placeholder | Source |
| --- | --- |
| `{{transcript}}` | `transcribe.json:cleanedTranscript` (fall back to `rawTranscript` if cleaned is empty) |
| `{{marginalia}}` | `transcribe.json:marginalia[]` rendered one per line as `- [position/kind] content` (omit the section if empty) |
| `{{project_list}}` | one line per `manifest.projects[]` entry: `- slug — Name (aliases: kw1, kw2, …)` |
| `{{person_aliases}}` | one line per `manifest.people_aliases` entry: `- Canonical Name (aliases: a, b, …)` |
| `{{page_date_stamp}}` | `meta.yaml:page_date_stamp` (MM-DD as written top-right) or `null` |
| `{{page_date_year}}` | `meta.yaml:page_date_year` or the year of `meta.yaml:source_capture_time` |

**Call shape:** single user turn (the app used no system prompt for this task; keep it that way so Haiku stays cheap). Model from `manifest.model_defaults.metadata` (default `claude-haiku-4-5`). JSON only.

---

## Prompt

```
You are a knowledge management specialist extracting structured metadata from a transcript of handwritten business or strategy notes.

These notes typically contain: project thinking, strategic plans, business development pipelines, ecosystem maps, frameworks, meeting notes, or personal knowledge work.

## Transcript
{{transcript}}

## Marginalia
{{marginalia}}

## Known projects
When you see a project mention that matches one of the following project slugs (or any of their
aliases), record the canonical slug in `projects`:
{{project_list}}

## Known people
When you see a person mention that matches one of the following canonical names (or any of their
aliases), record the canonical name in `people`:
{{person_aliases}}

For mentions that don't match any known project/person, record them as-is — they may be added to
the manifest later. Never invent a slug for an unknown project; use the name as written.

## Page capture hints
Top-right date stamp as written: {{page_date_stamp}}  (year, from capture metadata: {{page_date_year}})

---

Extract the following metadata as a JSON object:

### date (string | null)
The date this page was written, in YYYY-MM-DD format ONLY. Sources, in order of preference:
1. a full date written on the page;
2. the top-right date stamp above, combined with the capture-metadata year;
3. null.
Handwritten forms such as "Feb 10/26", "10 Feb", "2/10" or "03-02" must be converted to
YYYY-MM-DD; never return them as written. If you cannot produce a valid calendar date, return null.

### pageNumber (string | null)
Any page number visible on the page. Prefer numbers found in the top-right corner.

### title (string)
A specific, descriptive title for this page (6–10 words). Reflect the actual content — avoid generic titles.

### summary (string)
2–4 sentences capturing the most important ideas on this page. Lead with the core subject.

### tags (array of strings)
Comprehensive tags covering all relevant dimensions. Use lowercase-hyphenated format.
Include tags for: subject areas, project names, people, organisations, geographies, frameworks, document type, and time horizon.
Aim for 8–15 tags. Only include tags genuinely supported by the content.

### projects (array of strings)
Names of every project, initiative, product, or work stream mentioned or clearly implied. Use the
canonical slug when the mention matches a known project; otherwise the name as written.

### themes (array of strings)
Key thematic areas, strategic concerns, or conceptual topics that run through this page (3–8 items).

### ideas (array of strings)
Specific insights, hypotheses, value propositions, or original ideas captured on this page.
Each should be a short declarative statement (not just a label).

### people (array of strings)
Full names or roles of every person mentioned. Use the canonical name when the mention matches a
known person; otherwise the name as written.

### organisations (array of strings)
Every company, team, client, partner, or institution named.

### geography (array of strings)
Every region, country, city, or market mentioned.

### actionItems (array of strings)
Every task, to-do, or follow-up as a clear imperative statement.

### documentType (string)
The most accurate description of this page type:
"strategy-map" | "project-plan" | "meeting-notes" | "brainstorm" | "action-list" | "framework-diagram" | "ecosystem-map" | "business-development" | "research-notes" | "personal-reflection" | "mixed"

### cross_references (array)
For every reference the page makes to other content:
- kind          : page-ref | date-ref | person-ref | project-ref | external-doc | url
- target        : the canonical reference target (e.g. "p.47", "2026-05-01", "alice",
                  "project-atlas", "https://…", "Q2 strategy doc")
- evidence_span : the verbatim text that anchored this reference
Marginalia such as "see p.43" or "cf. Tuesday" are the most common sources. For date-refs,
resolve relative expressions ("last Friday", "next week") to an ISO date when the page date is
known; otherwise keep the phrase as target. Return an empty array if there are none.

Return ONLY valid JSON. Do not include commentary outside the JSON object.
```

## Expected response shape

```json
{
  "date": "2026-02-10",
  "pageNumber": "47",
  "title": "…",
  "summary": "…",
  "tags": ["…"],
  "projects": ["tulevik"],
  "themes": ["…"],
  "ideas": ["…"],
  "people": ["Alice Example"],
  "organisations": ["…"],
  "geography": ["…"],
  "actionItems": ["…"],
  "documentType": "meeting-notes",
  "cross_references": [
    { "kind": "page-ref", "target": "p.43", "evidence_span": "see prior framing on p.43" }
  ]
}
```

## Post-processing the skill applies (not part of the prompt)

1. **Date normalization** (SKILL.md "Date normalization"): the skill re-parses `date` deterministically even though the prompt asks for ISO. Anything that is not `YYYY-MM-DD` after normalization becomes `null` with a warning in `meta.yaml:errors`.
2. **Alias matching** (`canonical-attribution.md`): `projects` and `people` are passed through the deterministic matcher again; the model's canonicalisation is a first pass, not trusted blindly.
3. **Reconcile with transcribe** (SKILL.md Step 6): disagreement between `metadata.date` and `transcribe.extractedDate` is logged.

## Differences from the app prompt

- Marginalia, known-project and known-person blocks, and page-capture hints added to the input.
- `date` constrained to ISO with explicit conversion instruction (the app accepted any string).
- `cross_references` section added.
- `projects` / `people` instructed to prefer canonical slugs / names.
