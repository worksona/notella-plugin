# Path resolution for notella-kanban

Two paths matter: where the **dev server repo** is (`KANBAN_DIR`), and which **facility** both the dev server and the desktop app read (`NL_DIR`).

## The desktop app

`/Applications/Notella.app`. Fixed location; `open -a Notella` finds it through Launch Services, so no resolution is needed. If it is absent the skill says so and offers the dev server instead. The app is built from `~/WORKSONA/notella-desktop/desktop/` (PyInstaller; see that folder's README) — this skill never builds it.

## KANBAN_DIR — the dev server repo

Resolution order:

1. **Explicit override** — `--path=<path>` on the invocation.
2. **`$NOTELLA_DESKTOP_DIR`** — environment variable, for people who keep the repo elsewhere.
3. **Canonical** — `~/WORKSONA/notella-desktop/`. The repo root is the Next.js app (there is no nested `kanban/` folder).

That is the whole list. The legacy `~/notella/kanban/` location (the kanban nested inside the facility) and the older `~/Desktop/notella/kanban/` scaffold are **gone** and are no longer searched; a facility folder should hold data only.

### Validating a candidate

```bash
test -f "${candidate}/package.json" \
  && grep -q '"name": *"notella-kanban"' "${candidate}/package.json"
```

The package name (`notella-kanban`, unchanged from the original scaffold) disambiguates from any other project at the same path.

### Not found

Report the canonical path and suggest:

```
git clone <notella-desktop remote> ~/WORKSONA/notella-desktop && cd ~/WORKSONA/notella-desktop && npm install
```

or `export NOTELLA_DESKTOP_DIR=/wherever/it/is`.

## NL_DIR — the facility

The facility's **default path is `~/notella`**. This machine keeps it at **`/Users/davidolsson/Documents/notella`** and selects it with `NL_DIR`. Every notella-* skill, the dev server (`src/lib/notella-dir.ts:getNLDir()`) and the desktop app honour the variable.

Resolution each surface applies, first match with a `manifest.yaml` wins:

| Order | Dev server | Notella.app |
| --- | --- | --- |
| 1 | `$NL_DIR` | `$NL_DIR` |
| 2 | — | `~/Library/Application Support/Notella/config.json` → `"nl_dir"` |
| 3 | `~/notella` | `~/notella` |
| 4 | `~/Documents/notella` | `~/Documents/notella` |

Consequences:

- **Launching the app from Finder or Spotlight** does not carry a shell's `NL_DIR`. Either write the path into the config file once —
  ```bash
  mkdir -p ~/Library/Application\ Support/Notella
  printf '{ "nl_dir": "/Users/davidolsson/Documents/notella" }\n' > ~/Library/Application\ Support/Notella/config.json
  ```
  — or always launch via this skill (`app.sh`), which exports `NL_DIR` before `open -a`.
- **The dev server** reads `NL_DIR` from the shell that ran `npm run dev`. `start.sh` exports it explicitly (`${NL_DIR:-$HOME/notella}`), so a shell without the variable starts a server on `~/notella`, which on this machine is empty. Put `export NL_DIR=/Users/davidolsson/Documents/notella` in `~/.zshrc` to make every surface agree.
- **Scheduled orchestrator runs** need the variable in their own environment (launchd `EnvironmentVariables`, or a wrapper script); see `notella-orchestrator` → "Headless invocation".
- `status.sh` prints the facility each running surface is actually reading (dev server: `GET /api/state`; app: its config file and the process environment when visible), so a mismatch is caught at a glance.

## Why no broader search

- Searching the filesystem is slow and ambiguous (multiple checkouts would all match).
- Two environment variables plus one canonical path and one fixed app location cover every real layout; the `--path` escape hatch handles the rest.
- Keeping the facility free of code (no `~/notella/kanban/`) is what lets `NL_DIR` point anywhere, including a synced folder, without dragging `node_modules` along.
