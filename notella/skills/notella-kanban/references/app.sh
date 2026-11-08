#!/usr/bin/env bash
# notella-kanban app — open the read-only desktop app with the facility path in its environment.
# Usage:  app.sh [--nl-dir PATH]
#   --nl-dir PATH   facility to show (default: $NL_DIR, else ~/notella)

set -euo pipefail

APP="/Applications/Notella.app"
NL="${NL_DIR:-}"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --nl-dir) NL="$2"; shift 2 ;;
    *) echo "unknown arg: $1" >&2; exit 2 ;;
  esac
done

if [ ! -d "$APP" ]; then
  echo "error: ${APP} not installed." >&2
  echo "  build it from ~/WORKSONA/notella-desktop/desktop (see desktop/README.md)," >&2
  echo "  or run the dev server instead: references/start.sh" >&2
  exit 3
fi

# Resolve the facility the same way the app will, so the report is truthful.
if [ -z "$NL" ]; then
  CFG="$HOME/Library/Application Support/Notella/config.json"
  if [ -f "$CFG" ]; then
    NL="$(python3 -I -c 'import json,sys; print(json.load(open(sys.argv[1])).get("nl_dir",""))' "$CFG" 2>/dev/null || true)"
    SRC="config.json"
  fi
  if [ -z "$NL" ]; then
    for cand in "$HOME/notella" "$HOME/Documents/notella"; do
      if [ -f "$cand/manifest.yaml" ]; then NL="$cand"; SRC="default"; break; fi
    done
  fi
else
  SRC="NL_DIR"
fi

WAS_RUNNING="not running"
pgrep -f "Notella.app/Contents/MacOS" >/dev/null 2>&1 && WAS_RUNNING="already running"

if [ -n "$NL" ]; then
  NL_DIR="$NL" open -a Notella
else
  open -a Notella
fi

echo "notella app opened"
echo "  app:      $APP"
echo "  facility: ${NL:-<none found — app will show its init prompt>}${SRC:+   ($SRC)}"
echo "  state:    $WAS_RUNNING → launched"
