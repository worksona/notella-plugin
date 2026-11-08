# Marginalia rules

How to choose `kind` and `position` for each `transcribe.json:marginalia[]` entry, and how to decide what is marginalia at all. These rules are what the prompt compresses into one line per kind; use them when reviewing output or when a reprocess disagrees with a prior run.

## What counts as marginalia

Marginalia is text that sits outside the page's main reading flow and comments on, extends, or interrupts it. Tests, in order:

1. **Position.** It is in a margin (`left`, `right`, `top`, `bottom`), squeezed between lines, or boxed off from the body. Text that is simply the next bullet in a list is body, not marginalia, even if it is small.
2. **Timing cues.** Different pen, different ink pressure, different slant, cramped lettering — all suggest it was added after the body was written. Later additions are nearly always marginalia.
3. **Grammatical independence.** It reads as a comment on something ("check", "no!", "see p.43", "ask Alice") rather than as content in its own right.

A page's title and date stamp are not marginalia. The top-right `MM-DD` stamp and page number go to `extractedDate` / `extractedPageNumber`; the bottom-right series number is read at intake.

## position

| Value | Use when |
| --- | --- |
| `top` | Above the first body line, excluding the date/page stamp |
| `bottom` | Below the last body line |
| `left` | In the left margin or gutter |
| `right` | In the right margin |
| `inline` | Between body lines, above/below a word, or inside a box drawn within the body area |

When a note spans two positions (starts in the right margin and wraps under the last line), choose where it starts.

## kind

Decide in this order; the first match wins.

| Order | kind | Signal |
| --- | --- | --- |
| 1 | `correction` | The note replaces, strikes or inserts body text: a caret with a word above it, a crossed-out phrase with a replacement beside it, "not X, Y". The body transcript should reflect the corrected reading; the correction entry records that an edit happened. |
| 2 | `arrow-to` | A drawn arrow or line physically connects the note to a body span. Set `target_span_id` to that span. Beats `annotation` because the author made the link explicit. |
| 3 | `callout` | The note is boxed, starred, circled, or set apart with emphasis and reads as a conclusion, reminder, or headline ("DECISION: ship Friday", "!! budget"). Callouts frequently also appear in `emphasis[]` — that is expected, record both. |
| 4 | `annotation` | A comment that clearly refers to adjacent body content but with no drawn connector: "check this", "?", "wrong", "cf. Tuesday", a name beside a task. Set `target_span_id` to the nearest span when the adjacency is unambiguous, else null. |
| 5 | `aside` | Self-contained content unrelated to the adjacent body: a phone number, a grocery item, a sudden unrelated idea, a doodle caption. `target_span_id` is null. |

### Edge cases

- **A question mark alone** in the margin is an `annotation` with `content: "?"`. It is signal (the author doubted the adjacent line) and downstream first-pass reads it.
- **Names in the margin beside tasks** ("Alice", "DO") are `annotation`s; `notella-actions` promotes them to `owner_candidates`.
- **Page references** ("p.43", "→ 12-14") are `annotation`s; `notella-metadata` promotes them to `cross_references` of kind `page-ref` or `date-ref`.
- **Tally marks or numbers** with no referent are `aside`.
- **Strikethrough of a whole bullet** with nothing written in its place is a `correction` with `content: "[struck]"` and the span id of the struck line; the cleanedTranscript keeps the line with `~~strikethrough~~`.
- **Marginal notes that are themselves long** (a paragraph in the bottom margin) are still one entry. Do not split by sentence.

## target_span_id

Set it when the model can name the span with reasonable confidence: an arrow terminus, the line directly beside the note at the same vertical position, a caret insertion point. Leave null otherwise. A wrong target is worse than no target because first-pass will ground the note to the wrong content.

## bbox_pct

Top-left origin, `[x0, y0, x1, y1]` as fractions of page width and height. Tight around the ink of the note, not around the whole margin. Used by composition to link margin zones and by the desktop app to draw hover regions; precision to about 0.02 is enough.

## Counting

`page.transcribed` event evidence carries `marginalia_count`. Pages with more than ~15 marginalia entries are usually review passes over earlier notes; that is normal for this corpus and not a signal to reprocess.
