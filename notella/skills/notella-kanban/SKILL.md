---
name: notella-kanban
description: "Open the notella desktop app, or start, stop, restart and check the notella dev server. The shipped viewer is Notella.app in /Applications — a read-only Python desktop app that shows the facility as Dashboard, Kanban, Browse and Intel (`open -a Notella`). The Next.js dev server (`npm run dev` in ~/WORKSONA/notella-desktop, port 3344) is the developer surface only. Use whenever the user says 'open notella', 'open the notella app', 'show me the kanban', 'notella dashboard', 'start the notella dev server', 'is the kanban running', 'stop notella kanban', 'restart the dev server', 'open notella inventory', or any request to look at the facility in a window. The facility is `~/notella` by default; this machine uses NL_DIR=/Users/davidolsson/Documents/notella."
---

# notella-kanban — open the app / drive the dev server

A thin operational skill. Two surfaces show the same facility:

| Surface | What it is | When to use it |
| --- | --- | --- |
| **Notella.app** (`/Applications/Notella.app`) | Standalone, read-only macOS app: bundled Python 3.12 + pywebview + PyYAML, a stdlib HTTP server on 127.0.0.1 serving the static UI, API re-implemented in Python. No Node, no browser, no network. Dashboard, Kanban, Browse, Intel. | Looking at the corpus. The default. |
| **Dev server** (`npm run dev` in `~/WORKSONA/notella-desktop`, port 3344) | The same React UI from source, with the full fifteen screens and twenty-six API routes including the write/trigger routes (`/api/aggregate`, `/api/budget`, …). | Developing the UI, or when a skill needs an API route the app does not serve (ledgers aggregation, budget snapshot). |

Neither surface writes to the facility on its own; the desktop app returns `405` for every write or trigger route. Pipeline work is done by the notella-* skills in Claude Code.

## Purpose

Make seeing the facility a one-command act: "open notella" launches the app; "start the dev server" brings up :3344 and opens it in the browser. The skill never guesses which one the user meant — the vocabulary below maps intent to operation.

## Where things live

| Thing | Path | Notes |
| --- | --- | --- |
| Desktop app | `/Applications/Notella.app` | launched with `open -a Notella`; ad-hoc signed, Apple Silicon |
| Dev server repo | `~/WORKSONA/notella-desktop/` (canonical) or `$NOTELLA_DESKTOP_DIR` | `package.json` `name` is `notella-kanban`; the legacy `~/notella/kanban/` location is gone |
| Facility | `$NL_DIR`, else `~/notella` | **this machine: `NL_DIR=/Users/davidolsson/Documents/notella`**. Both surfaces resolve the folder the same way: `NL_DIR` → `~/Library/Application Support/Notella/config.json` (app only) → `~/notella` → `~/Documents/notella`, first with a `manifest.yaml` wins |
| Dev server runtime files | `~/WORKSONA/notella-desktop/.runtime/dev.{pid,log}` | written by `start`, read by `status`/`stop` |

Full resolution rules: `references/path-resolution.md`.

## The five operations

### `app` (default) — open the desktop app

```
1. test -d /Applications/Notella.app || report "Notella.app not installed — build it with
   ~/WORKSONA/notella-desktop/desktop/scripts (see desktop/README.md) or use `start` for the dev server"
2. Export NL_DIR if the facility is not at ~/notella:
     NL_DIR=/Users/davidolsson/Documents/notella open -a Notella
   (`open -a` passes the environment to the launched process; without NL_DIR the app falls
   back to its config.json, then ~/notella, then ~/Documents/notella.)
3. Report: app path, facility it will read, whether it was already running.
```

The app has no URL and no port to wait for. If it is already running, `open -a` brings it to the front.

### `start` — start the dev server and open it in the browser

```
1. Resolve KANBAN_DIR (references/path-resolution.md).
2. Already running?  curl -fsS http://localhost:3344 >/dev/null  → skip to step 6, report "already running".
3. Dependencies:     test -d "${KANBAN_DIR}/node_modules" || npm install --prefix "${KANBAN_DIR}"
4. Start in the background with the facility path in the environment:
     mkdir -p "${KANBAN_DIR}/.runtime"
     NL_DIR="${NL_DIR:-$HOME/notella}" nohup npm run dev --prefix "${KANBAN_DIR}" \
       > "${KANBAN_DIR}/.runtime/dev.log" 2>&1 &
     echo $! > "${KANBAN_DIR}/.runtime/dev.pid"
5. Wait for the port (up to 10 s):
     for i in {1..40}; do sleep 0.25; curl -fsS http://localhost:3344 >/dev/null && break; done
6. open http://localhost:3344${URL_PATH}
7. Report: PID, log path, URL, NL_DIR in effect.
```

### `status` — is the dev server running, and against which facility

```
PID_FILE="${KANBAN_DIR}/.runtime/dev.pid"
if [ -f "$PID_FILE" ] && kill -0 "$(cat $PID_FILE)" 2>/dev/null; then
  echo "dev server running — PID $(cat $PID_FILE) — http://localhost:3344"
else
  curl -fsS http://localhost:3344 >/dev/null \
    && echo "dev server running on 3344 (started outside this skill)" \
    || echo "dev server not running"
fi
pgrep -fl Notella.app >/dev/null && echo "Notella.app is running" || echo "Notella.app not running"
```

`status` also reports the facility: `curl -fsS http://localhost:3344/api/state | jq .facility` when the server is up.

### `stop` — stop the dev server

```
PID_FILE="${KANBAN_DIR}/.runtime/dev.pid"
[ -f "$PID_FILE" ] && kill "$(cat $PID_FILE)" 2>/dev/null; rm -f "$PID_FILE"
lsof -ti :3344 | xargs -r kill 2>/dev/null        # belt and suspenders
```

`stop` never quits Notella.app — the user closes the app window. (`osascript -e 'quit app "Notella"'` if they ask for it explicitly.)

### `restart` — stop, then start the dev server

Equivalent to `stop` followed by `start`. Does not touch the app.

## How a run executes

Map the user's words to one operation:

| Said | Operation |
| --- | --- |
| "open notella", "open the notella app", "show me notella", "show me the kanban", "notella dashboard", "open notella inventory" | `app` |
| "start the dev server", "run the kanban dev server", "npm run dev for notella", "open the kanban in the browser", "open localhost:3344" | `start` |
| "is the kanban running", "is the dev server up", "notella status", "which facility is the app reading" | `status` |
| "stop the dev server", "stop the kanban", "kill 3344" | `stop` |
| "restart the dev server", "restart the kanban" | `restart` |

Ambiguous phrasings ("open the kanban") default to `app`. If the user then asks for something only the dev server has (an API route, HMR, a screen not in the app's four), suggest `start`.

Screen deep-links apply to the dev server only (the app opens on Dashboard):

- "open notella inventory in the browser" → `start` then `open http://localhost:3344/inventory`
- "open the dashboard in the browser" → `start` then `open http://localhost:3344/dashboard`

## Reporting the outcome

```
notella app opened
  app:      /Applications/Notella.app
  facility: /Users/davidolsson/Documents/notella   (NL_DIR)
  state:    launched (was not running)
```

```
notella dev server started
  path:     ~/WORKSONA/notella-desktop
  port:     3344
  pid:      45291
  url:      http://localhost:3344/
  facility: /Users/davidolsson/Documents/notella   (NL_DIR)
  log:      ~/WORKSONA/notella-desktop/.runtime/dev.log
  opened:   yes
```

```
notella dev server stopped
  killed PID 45291
  port 3344 is free
  Notella.app: still running (not touched)
```

## Failure modes

| Failure | Behavior |
| --- | --- |
| `/Applications/Notella.app` missing | Say so; point at `~/WORKSONA/notella-desktop/desktop/README.md` for the build; offer `start` instead. |
| App opens on an empty facility | `NL_DIR` was not in the environment of `open -a`. Re-run with `NL_DIR=… open -a Notella`, or write the path into `~/Library/Application Support/Notella/config.json` once so the Finder launch finds it too. |
| No `package.json` named `notella-kanban` at the canonical path | Tell the user the repo is expected at `~/WORKSONA/notella-desktop` (or set `NOTELLA_DESKTOP_DIR`), suggest `git clone` + `npm install`. The legacy `~/notella/kanban/` location is no longer searched. |
| `npm install` fails | Surface the install log; do not start the server. |
| Server fails to bind to 3344 within 10 seconds | Tail the last 30 lines of `.runtime/dev.log`; do not open the browser. |
| Port 3344 already bound by something else | Report what's bound (`lsof -i :3344`), suggest stopping it or `--port=3345`. |
| Dev server shows a different facility than the app | One of them has a different `NL_DIR`. `status` prints both; set the variable in the shell profile so every launch agrees. |
| `~/notella/` (or `$NL_DIR`) doesn't exist yet | Both surfaces handle the empty-facility case with an init prompt; run `/notella-state init` to create it. |

## What this skill does NOT do

- **Does not build or install Notella.app.** PyInstaller packaging lives in `~/WORKSONA/notella-desktop/desktop/`; this skill launches what is in `/Applications`.
- **Does not run `next build` or `next start`.** The dev server is `npm run dev` only — a developer surface, not a deployment.
- **Does not write to the facility.** Both surfaces are read-only on `$NL_DIR`; the app refuses writes with `405`.
- **Does not modify the desktop codebase.**
- **Does not expose the server to the network.** Both bind `127.0.0.1`.

## Examples

### "Open notella"

```
Checking /Applications/Notella.app... present
Facility: /Users/davidolsson/Documents/notella (NL_DIR)
Launching: NL_DIR=/Users/davidolsson/Documents/notella open -a Notella

notella app opened
  app:      /Applications/Notella.app
  facility: /Users/davidolsson/Documents/notella
  state:    launched
```

### "Start the notella dev server"

```
Resolving KANBAN_DIR... found ~/WORKSONA/notella-desktop
Checking server... not running
Checking dependencies... node_modules present
Starting npm run dev (background, NL_DIR=/Users/davidolsson/Documents/notella)...
Waiting for port 3344... bound after 1.8s
Opening http://localhost:3344/

notella dev server started
  path:     ~/WORKSONA/notella-desktop
  port:     3344
  pid:      45291
  url:      http://localhost:3344/
  facility: /Users/davidolsson/Documents/notella
  log:      ~/WORKSONA/notella-desktop/.runtime/dev.log
  opened:   yes
```

### "Is the kanban running?"

```
notella status
  dev server:   running — PID 45291 — http://localhost:3344/ — facility /Users/davidolsson/Documents/notella
  Notella.app:  running
```

### "Stop the dev server"

```
Killing PID 45291...
Port 3344 is free.
Notella.app left running.

notella dev server stopped.
```

## Reference files

- `references/app.sh` — open the desktop app with `NL_DIR` in its environment.
- `references/start.sh` — start the dev server (idempotent), open the browser.
- `references/stop.sh` — stop the dev server.
- `references/status.sh` — dev server and app status, with the facility each is reading.
- `references/path-resolution.md` — how `KANBAN_DIR` and the facility path are resolved.

If reference files are missing, the bash blocks above are self-sufficient.
