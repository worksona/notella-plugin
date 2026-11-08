# Page-id derivation

Step 5 of `notella-intake`. Page ids are deterministic over the source file so re-running a drain, or dropping the same photo twice, never creates a second page. Entry ids follow the same principle over their member pages.

## Page-id format

```
{YYYY-MM-DD}-{4 chars}
2026-05-02-x7k2
```

- The date is the page's **authoritative capture date** (see `exif-extraction.md`: on-page stamp with resolved year → EXIF → mtime), in `manifest.facility.timezone`. It is a readable prefix, not a uniqueness guarantee.
- The four characters are a hash fragment in Crockford-style base32 with a reduced alphabet so ids are unambiguous when read aloud or handwritten.

## Alphabet

```
abcdefghjkmnpqrstuvwxyz23456789
```

Lowercase, 31 symbols. Omitted: `i`, `l`, `o` (confusable with `1`, `1`, `0`), `0` and `1` (confusable with `o`, `l`). Four symbols give 31⁴ ≈ 923,000 values per date; collisions within one date are handled below.

## Seed

```python
import hashlib

date_str = authoritative_date.strftime("%Y-%m-%d")
digest   = hashlib.sha256(file_bytes).hexdigest()[:16]     # first 16 hex of the raw file's sha256
seed     = f"{date_str}|{digest}"
```

`file_bytes` are the **raw inbox file**, not the decoded JPG — decoders are not byte-stable across versions. The date is part of the seed so an identical scan re-dated by a stamp correction gets a new id on purpose (the old folder is then an orphan the validator flags).

## Hash → short id

```python
ALPHABET = "abcdefghjkmnpqrstuvwxyz23456789"

def short_id(seed: str, n: int = 4) -> str:
    h = hashlib.sha256(seed.encode("utf-8")).digest()
    value = int.from_bytes(h[:8], "big")
    out = []
    for _ in range(n):
        value, r = divmod(value, len(ALPHABET))
        out.append(ALPHABET[r])
    return "".join(out)

page_id = f"{date_str}-{short_id(seed)}"
```

The function is the specification; any implementation (bash with `shasum`, Node, Python) must produce identical output for the same seed. A fixture: `seed = "2026-05-02|0123456789abcdef"` must yield the same four characters every time on every machine — record the result in `SCHEMA.md` the first time a facility is initialised and have the validator check it.

## Collision handling

Before writing, check `pages/{page_id}/`:

| Situation | Action |
| --- | --- |
| Folder absent | Create it. |
| Folder present and `raw/page.*` has the same sha256 as the inbox file | Duplicate drop. Skip the file, remove it from the inbox, count `pages_skipped_duplicate`. |
| Folder present and sha256 differs | Genuine 4-char collision (rare) **or** the same page re-photographed. Extend the id: `short_id(seed, 5)` → `2026-05-02-x7k2m`. Log `page-id-extended` with both digests. Never overwrite. |

Re-photographed pages (same physical page, new photo) are legitimately different pages with different ids; the 15 duplicate raw images the validator found in this facility are that case. Dedup by content hash catches exact copies only; near-duplicates are a `notella-review` question, not an intake decision.

## Entry-id format

```
ent_{YYYY-MM-DD}-{4 chars}
ent_2026-05-02-aab1
```

- Date: the authoritative date of the entry's earliest page.
- Seed: `f"{earliest_capture_time_iso}|{first_member_filename}"` where `earliest_capture_time_iso` is the earliest member's `source_capture_time` (or mtime ISO when null) and `first_member_filename` is the sorted-first inbox filename.
- Same `short_id()` function.

Re-running with the same files produces the same entry id. Adding a file to an already-drained batch produces a **new** entry for the newcomer rather than mutating the existing entry — entries are append-only like everything else; the validator can propose merging entries whose capture times fall inside the grouping window.

## Event ids

`page.intake` events use `{kind}-{date}-{6 hex}` where the hex is `sha256(page_id + "|" + source_filename + "|" + str(size_bytes))[:6]`. Deterministic, so a second write of the same event is a no-op at `notella-state`.

## What the id is not

- Not a sequence number. Pages on one date have no implied order from their ids; `entries/{entry-id}/meta.yaml:page_order` and `meta.yaml:page_number_daily` carry order.
- Not stable across a date correction. If `page_date_stamp` is later corrected and the date changes, the page keeps its id (folders are never renamed); the mismatch between the id prefix and `metadata.date` is cosmetic and expected. New ids are only minted at intake.
- Not derived from the decoded JPG, the thumbnail, or EXIF text — only the raw bytes and the date.

## Reference implementation in bash

```bash
digest=$(shasum -a 256 "$file" | cut -c1-16)
seed="${date_str}|${digest}"
short=$(python3 -I -c '
import sys, hashlib
A="abcdefghjkmnpqrstuvwxyz23456789"
v=int.from_bytes(hashlib.sha256(sys.argv[1].encode()).digest()[:8],"big")
o=""
for _ in range(4):
    v,r=divmod(v,len(A)); o+=A[r]
print(o)' "$seed")
page_id="${date_str}-${short}"
```
