#!/usr/bin/env bash
# notella-kanban status — running? where? on what port?

set -euo pipefail

PORT=3344

resolve_dir() {
  for candidate in \
    "${NOTELLA_DESKTOP_DIR:-}" \
    "${HOME}/WORKSONA/notella-desktop" \
    "${HOME}/notella/kanban" \
    "${HOME}/Desktop/notella/kanban"
  do
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
if [ -n "$KANBAN_DIR" ]; then
  PID_FILE="${KANBAN_DIR}/.runtime/dev.pid"
fi

# Tracked PID alive?
if [ -n "$PID_FILE" ] && [ -f "$PID_FILE" ]; then
  PID="$(cat "$PID_FILE")"
  if kill -0 "$PID" 2>/dev/null; then
    echo "notella-kanban running"
    echo "  path: $KANBAN_DIR"
    echo "  port: $PORT"
    echo "  pid:  $PID"
    echo "  url:  http://localhost:${PORT}/"
    exit 0
  fi
fi

# Untracked but bound?
if curl -fsS "http://localhost:${PORT}/" >/dev/null 2>&1; then
  echo "notella-kanban running (started outside this skill)"
  echo "  port: $PORT (responding)"
  echo "  pid:  $(lsof -ti :${PORT} 2>/dev/null | head -n1 || echo unknown)"
  echo "  url:  http://localhost:${PORT}/"
  exit 0
fi

echo "notella-kanban not running"
[ -n "$KANBAN_DIR" ] && echo "  scaffold: $KANBAN_DIR"
exit 1
