# notella model evals

How we decide which Claude model runs each pipeline stage. Re-run when a new
model ships or a prompt changes. Page images and transcripts never enter this
repo: only page ids (`cases.json`) and the scoring code. Run outputs live in
the facility under `evals/<date>/`.

## transcription/

16 pages chosen to span what the notebook actually contains: dense text,
diagram-heavy, mixed, low-contrast scans, pages that were stored upside down
or sideways (now fixed), a sketch page and a sparse page.

1. Each arm (one model) transcribes every case from `pages/<id>/derived/page.jpg`
   with `notella-transcribe/references/transcribe-prompt.md`, reading nothing
   else, and writes `<run>/<model>/<id>.json` with a `model_id` field. In
   Claude Code an arm is a subagent started with the Agent tool's `model`
   (`haiku`, `sonnet`, `opus`, `fable`), two batches of 8 pages per model.
2. `python3 evals/transcription/score.py --run <run> --reference fable`
   scores every other arm, plus the facility's existing transcripts, against
   the reference: word error rate, character similarity, recall of key tokens
   (numbers, dates, money, acronyms, proper nouns) and length ratio, overall
   and per page group.

The reference is the strongest model, not a human-checked transcript. A model
that scores close to it may share its mistakes; a few pages should be checked
by hand (the report lists the pages where arms disagree most).

## orientation/

12 original photos (`raw/page.jpg`) with known truth: 8 that were stored
turned (3 × 180°, 3 × 90°, 2 × 270°, all verified when fixed) and 4 upright.
Each arm answers the clockwise rotation that makes the page upright.
`python3 evals/orientation/score.py --run <run>` reports exact accuracy,
whether a turned page would have been caught, and accuracy among confident
answers (the classify skill auto-fixes at confidence ≥ 0.7).

## Cost

Each arm's token total comes from the subagent's completion report. Divide by
the pages in the batch for a per-page figure; it includes Claude Code's own
overhead (instructions, tool calls), which is what production runs pay.
