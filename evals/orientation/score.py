#!/usr/bin/env python3
"""Score orientation answers against known truth.

    python3 evals/orientation/score.py --run ~/Documents/notella/evals/2026-11-08/orientation

Each <run>/<model>.json is {"model_id", "answers": {page: {rotate, flip, confidence, evidence}}}.
Truth (cases.json) is the clockwise rotation that makes the raw photo upright, taken from pages
whose fix was verified visually (stamp-position heuristic + spot checks) or that were already upright.
Reports exact accuracy, "upright vs not" accuracy (would the gate have caught it), and how
calibrated the confidence is (accuracy among answers with confidence >= 0.7).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument('--run', required=True, type=Path)
    ap.add_argument('--cases', type=Path, default=Path(__file__).with_name('cases.json'))
    a = ap.parse_args()
    truth = {c['id']: c['truth_rotate'] for c in json.loads(a.cases.read_text())}
    print(f'{len(truth)} pages · truth = clockwise rotation that makes the raw photo upright\n')
    print(f'{"model":8} {"model id":22} {"exact":>7} {"turned?":>8} {"conf>=.7 exact":>15} {"missed turned":>14} {"false alarms":>13}')
    for f in sorted(a.run.glob('*.json')):
        d = json.loads(f.read_text())
        ans = d.get('answers', {})
        exact = sum(1 for p, t in truth.items() if int(ans.get(p, {}).get('rotate', -1)) == t)
        turned = sum(1 for p, t in truth.items() if (int(ans.get(p, {}).get('rotate', 0)) != 0) == (t != 0))
        conf = [(p, t) for p, t in truth.items() if float(ans.get(p, {}).get('confidence', 0)) >= 0.7]
        conf_ok = sum(1 for p, t in conf if int(ans[p].get('rotate', -1)) == t)
        missed = [p for p, t in truth.items() if t != 0 and int(ans.get(p, {}).get('rotate', 0)) == 0]
        false = [p for p, t in truth.items() if t == 0 and int(ans.get(p, {}).get('rotate', 0)) != 0]
        print(f'{f.stem:8} {str(d.get("model_id"))[:22]:22} {exact:>3}/{len(truth):<3} {turned:>4}/{len(truth):<3} '
              f'{conf_ok:>6}/{len(conf):<8} {len(missed):>14} {len(false):>13}')
        for p, t in truth.items():
            r = ans.get(p, {})
            if int(r.get('rotate', -1)) != t:
                print(f'         wrong {p}: truth {t}, said {r.get("rotate")} (conf {r.get("confidence")}) — {str(r.get("evidence"))[:90]}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
