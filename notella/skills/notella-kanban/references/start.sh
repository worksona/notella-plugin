#!/usr/bin/env bash
# notella-kanban start — start the dev server (idempotent), open browser.
# Usage:  start.sh [--path PATH] [--url URL_PATH]
#   --path PATH     override KANBAN_DIR (default: auto-resolve)
#   --url URL_PATH  open this path on localhost:3344 (default: /)

set -euo pipefail

PORT=3344
URL_PATH="/"
KANBAN_DIR=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --path) KANBAN_DIR="$2"; shift 2 ;;
    --url)  URL_PATH="$2"; shift 2 ;;
    *) echo "unknown arg: $1" >&2; exit 2 ;;
  esac
done

# Resolve KANBAN_DIR from candidate paths if not supplied
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
  if ! KANBAN_DIR="$(resolve_dir)"; then
    echo "error: notella-kanban scaffold not found at ~/WORKSONA/notella-desktop, ~/notella/kanban or ~/Desktop/notella/kanban" >&2
    exit 3
  fi
fi

PID_DIR="${KANBAN_DIR}/.runtime"
PID_FILE="${PID_DIR}/dev.pid"
LOG_FILE="${PID_DIR}/dev.log"
mkdir -p "$PID_DIR"

# Already running?
if curl -fsS "http://localhost:${PORT}/" >/dev/null 2>&1; then
  echo "notella-kanban already running on port ${PORT}"
  open "http://localhost:${PORT}${URL_PATH}" >/dev/null 2>&1 || true
  exit 0
fi

# Install if missing
if [ ! -d "${KANBAN_DIR}/node_modules" ]; then
  echo "installing dependencies..."
  npm install --prefix "$KANBAN_DIR" >&2
fi

# Start in background
nohup npm run dev --prefix "$KANBAN_DIR" > "$LOG_FILE" 2>&1 &
echo $! > "$PID_FILE"

# Wait for port
for _ in $(seq 1 40); do
  sleep 0.25
  if curl -fsS "http://localhost:${PORT}/" >/dev/null 2>&1; then
    open "http://localhost:${PORT}${URL_PATH}" >/dev/null 2>&1 || true
    echo "notella-kanban started"
    echo "  path: $KANBAN_DIR"
    echo "  port: $PORT"
    echo "  pid:  $(cat $PID_FILE)"
    echo "  url:  http://localhost:${PORT}${URL_PATH}"
    echo "  log:  $LOG_FILE"
    exit 0
  fi
done

echo "error: server failed to bind on port ${PORT} within 10s" >&2
echo "--- last 30 log lines: ---" >&2
tail -n 30 "$LOG_FILE" >&2 || true
exit 4
