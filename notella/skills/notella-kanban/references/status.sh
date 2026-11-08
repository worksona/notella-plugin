#!/usr/bin/env bash
# notella-kanban status — is the dev server running, is the app running, which facility does each read?

set -euo pipefail

PORT=3344

resolve_dir() {
  for candidate in \
    "${NOTELLA_DESKTOP_DIR:-}" \
    "${HOME}/WORKSONA/notella-desktop"
  do
    [ -n "$candidate" ] || continue
    if [ -f "${candidate}/package.json" ] && \
       grep -q '"name": *"notella-kanban"' "${candidate}/package.json" 2>/dev/null; then
      echo "$candidate"
      return 0
    fi
  done
  return 1
}

KANBAN_DIR="$(resolve_dir || true)"
PID_FILE=""
[ -n "$KANBAN_DIR" ] && PID_FILE="${KANBAN_DIR}/.runtime/dev.pid"

echo "notella status"

# --- dev server -----------------------------------------------------------
server_facility() {
  # Ask the running server which facility it serves; fall back to what start.sh recorded.
  local f
  f="$(curl -fsS "http://localhost:${PORT}/api/state" 2>/dev/null \
       | python3 -I -c 'import json,sys
d=json.load(sys.stdin)
print(d.get("facility") or d.get("nl_dir") or "")' 2>/dev/null || true)"
  if [ -z "$f" ] && [ -n "$KANBAN_DIR" ] && [ -f "${KANBAN_DIR}/.runtime/dev.nl_dir" ]; then
    f="$(cat "${KANBAN_DIR}/.runtime/dev.nl_dir")"
  fi
  echo "${f:-unknown}"
}

if [ -n "$PID_FILE" ] && [ -f "$PID_FILE" ] && kill -0 "$(cat "$PID_FILE")" 2>/dev/null; then
  echo "  dev server:   running — PID $(cat "$PID_FILE") — http://localhost:${PORT}/ — facility $(server_facility)"
  echo "                path $KANBAN_DIR"
elif curl -fsS "http://localhost:${PORT}/" >/dev/null 2>&1; then
  echo "  dev server:   running on ${PORT} (started outside this skill) — PID $(lsof -ti :${PORT} 2>/dev/null | head -n1 || echo unknown) — facility $(server_facility)"
else
  echo "  dev server:   not running${KANBAN_DIR:+   (repo: $KANBAN_DIR)}"
fi

# --- desktop app ----------------------------------------------------------
APP="/Applications/Notella.app"
if [ ! -d "$APP" ]; then
  echo "  Notella.app:  not installed"
elif pgrep -f "Notella.app/Contents/MacOS" >/dev/null 2>&1; then
  CFG="$HOME/Library/Application Support/Notella/config.json"
  CFG_DIR=""
  [ -f "$CFG" ] && CFG_DIR="$(python3 -I -c 'import json,sys; print(json.load(open(sys.argv[1])).get("nl_dir",""))' "$CFG" 2>/dev/null || true)"
  echo "  Notella.app:  running — facility ${NL_DIR:-${CFG_DIR:-~/notella or ~/Documents/notella (default chain)}}"
else
  echo "  Notella.app:  not running"
fi

# --- environment ----------------------------------------------------------
echo "  NL_DIR:       ${NL_DIR:-<unset — default ~/notella>}"
