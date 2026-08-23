---
name: notella-kanban
description: "Launch, stop, or check the notella-kanban dashboard — the local Next.js app that visualizes `~/notella/` as a page-lifecycle kanban + dashboard + inventory. Use whenever the user says 'open notella kanban', 'launch notella dashboard', 'show me notella kanban', 'start the kanban', 'open notella inventory', 'is the kanban running', 'stop notella kanban', 'kill the kanban', 'restart notella kanban', or any request to control the kanban dev server. The app is the repo root of `~/WORKSONA/notella-desktop/` (legacy fallbacks: `~/notella/kanban/`, `~/WORKSONA/notella-desktop/`) and runs on port 3344."
---

# notella-kanban — launcher / status / stop

A thin operational skill: starts, stops, checks, and opens the notella-kanban dashboard. The kanban itself is a Next.js app — this skill manages its lifecycle as a long-running background dev server.

## Purpose

Make the kanban a one-command surface. The user says "open notella kanban" and it gets running on `http://localhost:3344` and opens in their browser, regardless of whether dependencies are installed or the dev server is already up.

## Where the kanban app lives

In order of preference:

1. `$NOTELLA_DESKTOP_DIR` if set
2. `~/WORKSONA/notella-desktop/` (canonical — the notella-desktop repo; kanban is the repo root)
3. `~/notella/kanban/` (legacy: kanban nested inside the facility)
4. `~/WORKSONA/notella-desktop/` (legacy: original scaffold location)
5. Anywhere else, if the user supplies `--path=<path>`

The skill checks each candidate path for a `package.json` whose `name` is `notella-kanban`. If none match, it tells the user where to find the scaffold.

## The four operations

### `start` (default) — start the dev server and open it

```
1. Resolve KANBAN_DIR (see "Where the kanban app lives" above).
2. Check whether the server is already running:
     curl -fsS http://localhost:3344 >/dev/null
   If it is: skip to step 6 (open browser) and report "already running".
3. Check for node_modules:
     test -d "${KANBAN_DIR}/node_modules" || npm install --prefix "${KANBAN_DIR}"
4. Start the dev server in the background, redirecting logs:
     mkdir -p "${KANBAN_DIR}/.runtime"
     nohup npm run dev --prefix "${KANBAN_DIR}" \
       > "${KANBAN_DIR}/.runtime/dev.log" 2>&1 &
     echo $! > "${KANBAN_DIR}/.runtime/dev.pid"
5. Wait for the server to bind:
     for i in {1..40}; do
       sleep 0.25
       curl -fsS http://localhost:3344 >/dev/null && break
     done
6. Open the browser:
     open http://localhost:3344
7. Report status: PID, log path, URL.
```

### `status` — is it running, and where

```
PID_FILE="${KANBAN_DIR}/.runtime/dev.pid"
if [ -f "$PID_FILE" ] && kill -0 "$(cat $PID_FILE)" 2>/dev/null; then
  echo "Running — PID $(cat $PID_FILE) — http://localhost:3344"
else
  curl -fsS http://localhost:3344 >/dev/null \
    && echo "Running on port 3344 (started outside this skill)" \
    || echo "Not running"
fi
```

### `stop` — kill the dev server

```
PID_FILE="${KANBAN_DIR}/.runtime/dev.pid"
if [ -f "$PID_FILE" ]; then
  kill "$(cat $PID_FILE)" 2>/dev/null
  rm -f "$PID_FILE"
fi

# Belt and suspenders: kill anything bound to port 3344
lsof -ti :3344 | xargs -r kill 2>/dev/null
```

### `restart` — stop, then start

Equivalent to `stop` followed by `start`.

## How a run executes

The skill maps the user's natural-language intent to one of the four operations:

- "open notella kanban", "launch the kanban", "show me the dashboard", "start kanban" → `start`
- "is the kanban running", "kanban status", "what's the kanban doing" → `status`
- "stop the kanban", "kill the kanban", "shut it down" → `stop`
- "restart the kanban" → `restart`

If the user opens a specific page within the kanban, the skill appends to the URL it opens:

- "open notella inventory" → `start` then `open http://localhost:3344/inventory`
- "open notella dashboard" → `start` then `open http://localhost:3344/dashboard`
- "open notella kanban" (default) → `open http://localhost:3344/`

## Reporting the outcome

After every operation, the skill returns a structured summary the user can read at a glance:

```
notella-kanban started
  path:    ~/WORKSONA/notella-desktop
  port:    3344
  pid:     45291
  url:     http://localhost:3344/
  log:     ~/WORKSONA/notella-desktop/.runtime/dev.log
  opened:  yes
```

Or for stop:

```
notella-kanban stopped
  killed PID 45291
  port 3344 is free
```

## Failure modes

| Failure                                                  | Behavior                                                          |
| -------------------------------------------------------- | ----------------------------------------------------------------- |
| No `package.json` named `notella-kanban` found anywhere  | Tell the user where the scaffold should be and suggest `cd ~/WORKSONA/notella-desktop && npm install`. |
| `npm install` fails                                      | Surface the install log; do not start the server.                 |
| Server fails to bind to 3344 within 10 seconds           | Tail the last 30 lines of `.runtime/dev.log` so the user can see why; do not open the browser. |
| Port 3344 already bound by something else                | Report what's bound (`lsof -i :3344`), suggest stopping it or running `--port=3345`. |
| `nohup` unavailable (rare on macOS)                      | Fall back to `npm run dev &` with `disown`.                       |
| `~/notella/` doesn't exist yet                           | Start the kanban anyway — the kanban handles the empty-facility case with a friendly init prompt. |

## What this skill does NOT do

- **Does not run `next build` or `next start`.** It runs `npm run dev` only — the kanban is a developer-mode dashboard, not a production deployment.
- **Does not write to `~/notella/`.** It only reads via the kanban's API routes; the kanban itself is read-only on the facility.
- **Does not modify the kanban codebase.** Edits to the dashboard live in `kanban/src/`; this skill doesn't touch those.
- **Does not auto-restart on file changes.** Next.js's HMR handles that — the dev server picks up changes automatically.
- **Does not expose the server to the network.** Listens on `localhost:3344` only. If you want to share it on a LAN, run `next dev --hostname 0.0.0.0` directly.

## Examples

### "Open the notella kanban"

```
Resolving KANBAN_DIR... found ~/WORKSONA/notella-desktop
Checking server... not running
Checking dependencies... node_modules present
Starting npm run dev (background)...
Waiting for port 3344... bound after 1.8s
Opening http://localhost:3344/

notella-kanban started
  path:    ~/WORKSONA/notella-desktop
  port:    3344
  pid:     45291
  url:     http://localhost:3344/
  log:     ~/WORKSONA/notella-desktop/.runtime/dev.log
  opened:  yes
```

### "Show me the notella inventory"

Same start sequence, but `open http://localhost:3344/inventory`.

### "Stop the kanban"

```
Killing PID 45291...
Port 3344 is free.

notella-kanban stopped.
```

### "Is the kanban running?"

```
notella-kanban status
  pid:     45291
  port:    3344 (responding)
  uptime:  18m
  url:     http://localhost:3344/
```

### "Restart the kanban"

```
Stopping PID 45291... done
Starting npm run dev... bound after 2.1s
Opened http://localhost:3344/

notella-kanban restarted.
```

## Reference files

- `references/start.sh` — the start script with all the bash exactly as the SKILL.md describes.
- `references/stop.sh` — the stop script.
- `references/status.sh` — the status check.
- `references/path-resolution.md` — how the skill picks `KANBAN_DIR` from the candidate paths.

If reference files are missing, the bash blocks above are self-sufficient.
