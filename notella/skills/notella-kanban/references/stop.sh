#!/usr/bin/env bash
# notella-kanban stop — kill the dev server.

set -euo pipefail

PORT=3344
KANBAN_DIR=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --path) KANBAN_DIR="$2"; shift 2 ;;
    *) echo "unknown arg: $1" >&2; exit 2 ;;
  esac
done

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

if [ -z "$KANBAN_DIR" ]; then
  KANBAN_DIR="$(resolve_dir || true)"
fi

PID_FILE=""
if [ -n "$KANBAN_DIR" ]; then
  PID_FILE="${KANBAN_DIR}/.runtime/dev.pid"
fi

if [ -n "$PID_FILE" ] && [ -f "$PID_FILE" ]; then
  PID="$(cat "$PID_FILE")"
  if kill -0 "$PID" 2>/dev/null; then
    kill "$PID" 2>/dev/null || true
    sleep 0.5
    if kill -0 "$PID" 2>/dev/null; then
      kill -9 "$PID" 2>/dev/null || true
    fi
  fi
  rm -f "$PID_FILE"
fi

# Belt and suspenders — kill anything bound to the port
lsof -ti :${PORT} 2>/dev/null | xargs -r kill 2>/dev/null || true

if curl -fsS "http://localhost:${PORT}/" >/dev/null 2>&1; then
  echo "warning: something is still bound to port ${PORT}"
  exit 5
fi

echo "notella-kanban stopped"
echo "  port ${PORT} is free"
