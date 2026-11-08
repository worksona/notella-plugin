#!/usr/bin/env python3
"""Score notella transcription runs against a reference model.

    python3 evals/transcription/score.py --run ~/Documents/notella/evals/2026-11-08/transcription \
        --reference fable [--json out.json]

Layout of a run folder:  <run>/<model>/<page-id>.json  with at least
`rawTranscript` (verbatim) and optionally `cleanedTranscript`, `model_id`.
A pseudo-model "existing" is read from the facility's own transcribe.json
(pages/<id>/transcribe.json under --root, any of the historical field names).

Metrics per page, candidate vs reference (both normalised: lower case,
punctuation folded to spaces, whitespace collapsed):
  wer           word error rate = word-level Levenshtein / reference words
  char_sim      difflib SequenceMatcher ratio on the normalised characters
  key_recall    share of the reference's key tokens found in the candidate:
                numbers and dates, money, ALL-CAPS acronyms (2+ letters),
                Capitalised words not at a line start, emails/urls
  len_ratio     candidate words / reference words
Stdlib only, Python 3.9+. Page content never leaves the machine; only the
case list (page ids) is kept in the repo.
"""

from __future__ import annotations

import argparse
import difflib
import json
import os
import re
import statistics
import sys
from pathlib import Path

TEXT_FIELDS = ('rawTranscript', 'verbatim', 'cleanedTranscript', 'structured_markdown', 'structured_md')


def text_of(d: dict) -> str:
    for k in TEXT_FIELDS:
        v = d.get(k)
        if isinstance(v, str) and v.strip():
            return v
    return ''


LAYOUT = set('top bottom left right middle center centre upper lower side column columns margin margins '
             'boxed box circled underlined double underline struck strike through crossed out arrow arrows '
             'diagram label labels sketch region area corner block note rotated vertical horizontal page '
             'probably illegible unclear uncertain written in near under above below beside'.split())


def strip_layout(s: str) -> str:
    """Drop positional / markup tags the models add ("[top-right]", "[boxed]") but keep the
    content of "[boxed: Wednesday]" or "[probably: Hanif]", so layout style is not scored."""
    def repl(m):
        inner = m.group(1)
        if ':' in inner:
            head, _, body = inner.partition(':')
            if set(re.findall(r'[a-z]+', head.lower())) <= LAYOUT:
                return ' ' + body + ' '
            return ' ' + inner + ' '
        words = re.findall(r'[a-z]+', inner.lower())
        return ' ' if words and set(words) <= LAYOUT else ' ' + inner + ' '
    return re.sub(r'\[([^\]\n]{0,120})\]', repl, s)


def bag_f1(ref: list, hyp: list) -> float:
    """Order-insensitive word overlap (multiset F1): did the model read the same words,
    regardless of the order it laid side columns out in."""
    from collections import Counter
    if not ref and not hyp:
        return 1.0
    common = sum((Counter(ref) & Counter(hyp)).values())
    if not common:
        return 0.0
    p, r = common / len(hyp), common / len(ref)
    return 2 * p * r / (p + r)


def norm_words(s: str) -> list:
    s = strip_layout(s).lower()
    s = re.sub(r'[`*_#>\[\]()|{}~^]', ' ', s)            # markdown furniture
    s = re.sub(r"[^\w$%@./:'-]+", ' ', s)
    s = re.sub(r"(?<!\w)['./:-]+|['./:-]+(?!\w)", ' ', s)  # edge punctuation
    return s.split()


def key_tokens(s: str) -> set:
    keys = set()
    for m in re.finditer(r'\$?\d[\d,./:-]*%?', s):
        keys.add(m.group().strip('.,:/-').lower())
    for m in re.finditer(r'\b[A-Z][A-Z0-9&-]{1,}\b', s):
        keys.add(m.group().lower())
    for line in s.splitlines():
        words = re.findall(r"[A-Za-z][\w'-]*", line)
        for w in words[1:]:
            if w[0].isupper() and len(w) > 2:
                keys.add(w.lower())
    for m in re.finditer(r'\b[\w.+-]+@[\w-]+\.[\w.]+|\b[\w-]+\.(?:io|com|ai|ca|org|net)\b', s):
        keys.add(m.group().lower())
    return {k for k in keys if k}


def wer(ref: list, hyp: list) -> float:
    if not ref:
        return 0.0 if not hyp else 1.0
    prev = list(range(len(hyp) + 1))
    for i, r in enumerate(ref, 1):
        cur = [i] + [0] * len(hyp)
        for j, h in enumerate(hyp, 1):
            cur[j] = min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (r != h))
        prev = cur
    return prev[-1] / len(ref)


def score_pair(ref_text: str, hyp_text: str) -> dict:
    rw, hw = norm_words(ref_text), norm_words(hyp_text)
    rk, hk_text = key_tokens(strip_layout(ref_text)), ' '.join(hw)
    found = sum(1 for k in rk if k in hk_text)
    return {
        'bag_f1': round(bag_f1(rw, hw), 4),
        'wer': round(wer(rw, hw), 4),
        'char_sim': round(difflib.SequenceMatcher(None, ' '.join(rw), ' '.join(hw), autojunk=False).ratio(), 4),
        'key_recall': round(found / len(rk), 4) if rk else None,
        'key_total': len(rk),
        'len_ratio': round(len(hw) / len(rw), 3) if rw else None,
        'ref_words': len(rw),
    }


def load(run: Path, model: str, root: Path, pid: str):
    if model == 'existing':
        p = root / 'pages' / pid / 'transcribe.json'
    else:
        p = run / model / f'{pid}.json'
    try:
        d = json.loads(p.read_text('utf-8'))
    except (OSError, ValueError):
        return None
    return d if isinstance(d, dict) else None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument('--run', required=True, type=Path)
    ap.add_argument('--reference', default='fable')
    ap.add_argument('--root', type=Path, default=Path(os.environ.get('NL_DIR', '~/notella')).expanduser())
    ap.add_argument('--cases', type=Path, default=Path(__file__).with_name('cases.json'))
    ap.add_argument('--json', type=Path)
    a = ap.parse_args()

    cases = json.loads(a.cases.read_text())
    models = sorted(d.name for d in a.run.iterdir() if d.is_dir() and d.name != a.reference) + ['existing']
    per_page, missing = [], []
    for c in cases:
        ref = load(a.run, a.reference, a.root, c['id'])
        if not ref or not text_of(ref):
            missing.append((a.reference, c['id']))
            continue
        for m in models:
            hyp = load(a.run, m, a.root, c['id'])
            if hyp is None:
                missing.append((m, c['id']))
                continue
            row = score_pair(text_of(ref), text_of(hyp))
            row.update(model=m, page=c['id'], group=c['group'], model_id=hyp.get('model_id'))
            per_page.append(row)

    def agg(rows):
        out = {}
        for k in ('bag_f1', 'wer', 'char_sim', 'key_recall', 'len_ratio'):
            vals = [r[k] for r in rows if r[k] is not None]
            out[k] = round(statistics.mean(vals), 3) if vals else None
            out[k + '_worst'] = (round(max(vals), 3) if k == 'wer' else round(min(vals), 3)) if vals else None
        out['pages'] = len(rows)
        return out

    summary = {m: agg([r for r in per_page if r['model'] == m]) for m in models}
    groups = sorted({r['group'] for r in per_page})
    by_group = {m: {g: agg([r for r in per_page if r['model'] == m and r['group'] == g]) for g in groups} for m in models}

    print(f'Reference: {a.reference} · {len(cases)} pages · metrics vs reference (lower WER / higher similarity is closer)\n')
    print(f'{"model":10} {"pages":>5} {"word F1":>8} {"worst":>7} {"key recall":>11} {"worst":>7} {"WER":>7} {"char sim":>9} {"len":>6}')
    for m in models:
        s = summary[m]
        print(f'{m:10} {s["pages"]:>5} {s["bag_f1"]!s:>8} {s["bag_f1_worst"]!s:>7} {s["key_recall"]!s:>11} {s["key_recall_worst"]!s:>7} {s["wer"]!s:>7} {s["char_sim"]!s:>9} {s["len_ratio"]!s:>6}')
    print('\nWord F1 by page group (order-insensitive, layout tags ignored):')
    print(f'{"group":30} ' + ' '.join(f'{m:>9}' for m in models))
    for g in groups:
        print(f'{g[:30]:30} ' + ' '.join(f'{by_group[m][g]["bag_f1"]!s:>9}' for m in models))
    print('\nKey-token recall by page group (numbers, dates, names, acronyms):')
    print(f'{"group":30} ' + ' '.join(f'{m:>9}' for m in models))
    for g in groups:
        print(f'{g[:30]:30} ' + ' '.join(f'{by_group[m][g]["key_recall"]!s:>9}' for m in models))
    if missing:
        print(f'\nMissing: {len(missing)} ' + ', '.join(f'{m}/{p}' for m, p in missing[:12]))
    if a.json:
        a.json.write_text(json.dumps({'reference': a.reference, 'summary': summary, 'by_group': by_group,
                                      'per_page': per_page, 'missing': missing}, indent=1))
    return 0


if __name__ == '__main__':
    sys.exit(main())
