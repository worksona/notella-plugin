#!/usr/bin/env python3
"""Compare re-processed page artifacts with the versions they replaced.

    NL_DIR=~/Documents/notella python3 evals/pilot/compare.py \
        --pages ~/Documents/notella/evals/2026-11-08/pilot/pilot-pages.json \
        --before ~/Documents/notella/evals/2026-11-08/pilot/before [--json out.json]

For each page: transcript agreement between the old and new transcribe.json
(order-insensitive word F1 and key-token recall from evals/transcription/score.py),
and, once metadata / first-pass are redone, how much the meaning layer moved:
project and people attributions gained or lost, and the share of first-pass
entities that survived. Bands: F1 >= .6 "agree", .35-.6 "partly", < .35 "replaced".
"""

from __future__ import annotations

import argparse
import json
import os
import statistics
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / 'transcription'))
import score  # noqa: E402


def load(p: Path):
    try:
        d = json.loads(p.read_text('utf-8'))
        return d if isinstance(d, dict) else None
    except (OSError, ValueError):
        return None


def setof(v) -> set:
    return {str(x).strip().lower() for x in v} if isinstance(v, list) else set()


def entities(fp) -> set:
    if not fp:
        return set()
    sm = fp.get('structural_map') or {}
    return setof(sm.get('entities') if isinstance(sm, dict) else [])


def band(f1: float) -> str:
    return 'agree' if f1 >= 0.6 else ('partly' if f1 >= 0.35 else 'replaced')


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument('--pages', required=True, type=Path)
    ap.add_argument('--before', required=True, type=Path)
    ap.add_argument('--root', type=Path, default=Path(os.environ.get('NL_DIR', '~/notella')).expanduser())
    ap.add_argument('--json', type=Path)
    a = ap.parse_args()

    pages = json.loads(a.pages.read_text())
    rows = []
    for pg in pages:
        pid = pg['id']
        old_t, new_t = load(a.before / pid / 'transcribe.json'), load(a.root / 'pages' / pid / 'transcribe.json')
        if not old_t or not new_t or not new_t.get('reprocessed_at'):
            rows.append({'page': pid, 'stratum': pg.get('stratum'), 'status': 'not-reprocessed'})
            continue
        s = score.score_pair(score.text_of(new_t), score.text_of(old_t))
        row = {'page': pid, 'stratum': pg.get('stratum'), 'status': 'reprocessed', 'model_id': new_t.get('model_id'),
               'word_f1': s['bag_f1'], 'key_recall_old_vs_new': s['key_recall'], 'band': band(s['bag_f1']),
               'new_words': s['ref_words'], 'new_confidence': new_t.get('transcriptConfidence')}
        old_m, new_m = load(a.before / pid / 'metadata.json'), load(a.root / 'pages' / pid / 'metadata.json')
        if new_m and new_m.get('reprocessed_at'):
            for k in ('projects', 'people'):
                o, n = setof((old_m or {}).get(k)), setof(new_m.get(k))
                row[f'{k}_added'], row[f'{k}_removed'] = sorted(n - o), sorted(o - n)
        old_f, new_f = load(a.before / pid / 'first-pass.json'), load(a.root / 'pages' / pid / 'first-pass.json')
        if new_f and new_f.get('reprocessed_at'):
            o, n = entities(old_f), entities(new_f)
            row['entities_kept'] = round(len(o & n) / len(o), 3) if o else None
            row['old_summary'] = (old_f or {}).get('content_summary', '')[:220]
            row['new_summary'] = new_f.get('content_summary', '')[:220]
        rows.append(row)

    done = [r for r in rows if r['status'] == 'reprocessed']
    print(f'{len(done)}/{len(rows)} pages re-processed\n')
    print(f'{"stratum":18} {"pages":>5} {"F1 old~new":>11} {"agree":>6} {"partly":>7} {"replaced":>9}')
    for st in sorted({r['stratum'] for r in done}) + ['ALL']:
        rs = [r for r in done if st == 'ALL' or r['stratum'] == st]
        c = Counter(r['band'] for r in rs)
        print(f'{st:18} {len(rs):>5} {statistics.mean(r["word_f1"] for r in rs):>11.2f} {c["agree"]:>6} {c["partly"]:>7} {c["replaced"]:>9}')
    meta = [r for r in done if 'projects_added' in r]
    if meta:
        ch = sum(1 for r in meta if r['projects_added'] or r['projects_removed'])
        cp = sum(1 for r in meta if r['people_added'] or r['people_removed'])
        print(f'\nmetadata redone on {len(meta)}: project attribution changed on {ch}, people on {cp}')
    fp = [r for r in done if r.get('entities_kept') is not None]
    if fp:
        print(f'first-pass redone on {len(fp)}: mean share of old entities kept {statistics.mean(r["entities_kept"] for r in fp):.2f}')
    print('\nLowest agreement (old transcript most likely wrong):')
    for r in sorted(done, key=lambda r: r['word_f1'])[:8]:
        print(f'  {r["page"]}  F1 {r["word_f1"]:.2f}  {r["stratum"]}')
    if a.json:
        a.json.write_text(json.dumps(rows, indent=1))
    return 0


if __name__ == '__main__':
    sys.exit(main())
