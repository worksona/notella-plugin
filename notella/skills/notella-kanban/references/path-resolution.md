# Path resolution for notella-kanban

The launch skill needs to find the kanban scaffold reliably regardless of where the user keeps it. Resolution order:

1. **Explicit override** — if the caller passes `--path=<path>`, use it. Validate by checking for `<path>/package.json` with `"name": "notella-kanban"`.

2. **Canonical location** — `~/WORKSONA/notella-desktop/` (the notella-desktop repo root; also honoured via `$NOTELLA_DESKTOP_DIR`). Legacy fallback `~/Desktop/notella/kanban/` is where the scaffold was first created and where most users will leave it.

3. **Mirror-the-facility location** — `~/notella/kanban/`. This is the location that mirrors `~/work-state/kanban/`'s pattern of "kanban app lives inside the facility". Users who prefer that layout will move the scaffold here.

4. **Not found** — surface a clear error pointing at `~/WORKSONA/notella-desktop/` and suggest `cd ~/Desktop/notella/kanban && npm install`.

## Why not check more places

- We don't search the filesystem broadly because that's slow and ambiguous (multiple checkouts on the same machine would all match).
- We don't read a config file because the skill should work zero-config out of the box.
- The two candidate paths cover the two natural homes — workspace folder and facility-adjacent — and the `--path` escape hatch handles everything else.

## Validating a candidate

```bash
test -f "${candidate}/package.json" \
  && grep -q '"name": *"notella-kanban"' "${candidate}/package.json"
```

The grep on the package name is what disambiguates from a sibling project that happens to have a package.json at the same path.
