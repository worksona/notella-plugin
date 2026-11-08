# Emphasis rules

How to grade `transcribe.json:emphasis[]` entries: which `mark_type` to choose and what `intensity` 1 / 2 / 3 mean. Emphasis is one of the strongest signals in handwritten strategy notes — the author telling their future self what mattered — so first-pass, daily synthesis and themes all read it. Consistent grading across pages is what makes it comparable.

## One entry per mark

A span that is circled and starred gets two entries (`circle`, `star`) with the same `span_id`. Consumers sum per span; the prompt does not ask the model to merge. The exception is `intensity: 3`, which may be assigned to a single entry when the marks are too tangled to separate (see below).

## mark_type

| mark_type | Looks like | Notes |
| --- | --- | --- |
| `underline` | One line under a word, phrase or whole line | Includes wavy underlines. |
| `double-underline` | Two or more parallel lines under the same text | Stronger than `underline`; typically intensity 2. |
| `circle` | An oval or loop enclosing text | Includes loops around a single number or name. |
| `star` | An asterisk or five-point star beside or above text | A star in the margin beside a line counts for that line. Three stars = one `star` entry at intensity 3. |
| `box` | A rectangle drawn around text | Boxed headings are emphasis; boxed table cells are not (they are tables). |
| `color` | Highlighter, a second pen colour, shading over text | Use when colour is the primary mark. A coloured underline is `underline` with intensity raised one step. |
| `exclamation` | `!`, `!!`, `!!!` beside or after text | `!!!` is one entry at intensity 3. |
| `arrow-to` | An arrow whose head points at a span, with no text at its tail | If the tail has text, it is marginalia of kind `arrow-to`, not emphasis. Both may be recorded when the arrow is both pointing and heavy. |

### Not emphasis

- Bullet markers, dashes, checkboxes (empty or ticked). Ticks are action state, read by `notella-actions`.
- Diagram arrows between nodes (go to `notella-diagram`).
- Table borders and grid lines.
- The box around the whole page or a section divider line.
- Strikethrough — that is a `correction` in marginalia.

## intensity

| Intensity | Meaning | Typical evidence |
| --- | --- | --- |
| 1 — light | The author marked it in passing | A single thin underline; a small star; a single `!`; a faint circle |
| 2 — clear | A deliberate, unambiguous mark | A heavy or coloured underline; a double underline; a solid box or circle; a prominent star; `!!` |
| 3 — heavy | Multiple marks or an emphatic one on the same span | Circle plus star plus underline; double underline plus box; `!!!`; colour fill plus box; the mark is retraced several times |

Rules of thumb:

- Pen pressure and retracing raise intensity one step; a hesitant single stroke lowers it.
- A mark that covers a whole line is not automatically heavier than one covering a word. Judge the mark, not its length.
- When several marks stack on one span and the model records them as separate entries, each entry takes its own intensity (an underline at 1, a star at 2). When it records one combined entry, that entry is intensity 3.
- A page where every line is underlined (some people underline as a writing habit) has intensity 1 for all of them. Uniform emphasis is no emphasis; first-pass is told to treat `emphasis_count > 30` with near-uniform intensity as low signal.

## span_text

The exact text under the mark, which may be a fragment of the span ("Friday" out of "ship by Friday"). First-pass uses `span_text` to find what the author stressed inside a long line; keep it tight.

## How downstream reads it

- `notella-first-pass` formats each entry as `"<span_text>: <mark_type> (intensity N)"` and uses intensity ≥ 2 as a reason to promote the span's content into `content_summary` or `action_intelligence`.
- `notella-daily-synthesis` treats intensity-3 spans as candidate `top_priorities` and intensity-2+ decisions as candidate `new_decisions`.
- `notella-themes` counts intensity-weighted mentions when ranking theme weight.

Grading drift (a run that gives everything 3) therefore inflates priorities downstream; when reviewing a page, check that the intensity distribution looks like the page.
