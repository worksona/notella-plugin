# Affective signal rules

How to read `affective_signal` from a sketch's execution. Six values: `calm`, `energetic`, `playful`, `serious`, `uncertain`, `frustrated`. The signal is about *how the author drew*, not *what they drew* — a careful rendering of a storm is `calm`; a furious scribble of a smiling sun is `frustrated`. `notella-themes` aggregates this across pages to read the author's state over months, so grading must be stable.

## Observable features

Judge from these, in roughly this order of reliability:

| Feature | What to look at |
| --- | --- |
| **Line weight and pressure** | Thin, even lines vs heavy, variable, dug-in strokes |
| **Speed** | Smooth continuous curves (slow) vs straight jagged segments and overshoots (fast) |
| **Repetition** | Single confident strokes vs the same line retraced several times |
| **Scratch-outs and restarts** | Crossed-out elements, abandoned starts beside the final drawing |
| **Tightness** | Small, controlled, close to the text vs large, loose, spilling into margins |
| **Completeness** | Finished shapes vs open outlines left mid-stroke |
| **Ornament** | Added flourishes, faces on objects, exaggerated proportions |

## The six signals

| Signal | Typical evidence | Often paired with intent |
| --- | --- | --- |
| `calm` | Even line weight, moderate speed, few retraces, closed shapes, sits neatly in its space | illustrative, mnemonic |
| `energetic` | Heavy pressure, fast strokes, large and loose, many arrows or motion lines, but *not* retraced or scratched out — directed force | explanatory, exploratory |
| `playful` | Cartoon exaggeration, faces on things, humorous captions, ornament for its own sake, light pressure | decorative, mnemonic |
| `serious` | Measured, technical, ruled or near-ruled lines, labels in neat capitals, proportion attempted | explanatory (mock-ups, plans) |
| `uncertain` | Multiple light attempts at the same form, open outlines, faint pressure, question marks nearby, hesitant wobble | exploratory |
| `frustrated` | Heavy retracing of the same stroke, scratch-outs, torn or dug-in paper, abandoned restarts, a drawing crossed out and redone smaller | exploratory, or a decorative doodle during a meeting |

## Decision order when features conflict

1. Scratch-outs or heavy retracing present → `frustrated` beats everything else.
2. Multiple faint attempts with no scratch-out → `uncertain`.
3. Heavy pressure, fast, directed → `energetic`.
4. Cartoon exaggeration or ornament → `playful`.
5. Technical, measured → `serious`.
6. Otherwise → `calm`.

## Calibration notes

- **Habitual doodlers** produce many `playful`/`calm` decorative faces. That is baseline, not signal; themes compares against the author's own distribution.
- **Pen vs pencil.** Pencil shows pressure more clearly; pen shows speed. Do not read a ballpoint's uniform line as `calm` by default — look at speed and completeness.
- **Photo quality.** Low contrast flattens pressure cues. When the image is poor, lean on speed, repetition and scratch-outs, and lower `confidence`.
- **One signal per sketch.** When a page has several sketches with different signals, each gets its own; first-pass and themes read the distribution.
- **Not the text.** Angry words beside a calm drawing do not make the drawing `frustrated`. The text's mood is captured by first-pass from the transcript.

## How downstream reads it

- `notella-first-pass` mentions a `frustrated` or `uncertain` sketch in `content_summary` only when the page's text corroborates (a blocked task, an open question); otherwise it stays in `diagram_semantics.ambiguity`.
- `notella-daily-synthesis` may cite affect in `momentum_signals` when two or more sketches on a day share `frustrated` or `energetic`.
- `notella-themes` tracks the monthly distribution of signals as part of `conceptual_evolution`; a shift from `uncertain` to `serious` on a project's pages is a measurable maturation signal.
