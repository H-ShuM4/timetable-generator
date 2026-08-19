#!/usr/bin/env bash
#
# Start the timetable generator and open it in a browser.
#
# Usage:
#   ./start.sh                 start on port 8000 and open a browser
#   ./start.sh 8080            start on port 8080
#   ./start.sh --no-browser    start without opening a browser
#
# Stop the server with Ctrl+C.

set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$PROJECT_ROOT"

PORT=8000
OPEN_BROWSER=1

for arg in "$@"; do
  case "$arg" in
    --no-browser) OPEN_BROWSER=0 ;;
    [0-9]*)       PORT="$arg" ;;
    -h|--help)    sed -n '3,11p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) echo "Unknown argument: $arg" >&2; exit 2 ;;
  esac
done

UVICORN="$PROJECT_ROOT/.venv/bin/uvicorn"
URL="http://localhost:$PORT/"

# --- Checks -----------------------------------------------------------------

if [ ! -x "$UVICORN" ]; then
  cat >&2 <<MSG
ERROR: uvicorn was not found at
  $UVICORN

The virtual environment is missing or incomplete. Create it and install the
dependencies:

  python3 -m venv .venv
  .venv/bin/pip install -r backend/requirements.txt
MSG
  exit 1
fi

if (exec 3<>"/dev/tcp/127.0.0.1/$PORT") 2>/dev/null; then
  exec 3>&-
  echo "ERROR: port $PORT is already in use." >&2
  echo "Another server may still be running. Use a different port: ./start.sh 8001" >&2
  exit 1
fi

# --- Browser ----------------------------------------------------------------

open_browser() {
  # Wait for the server to accept connections, then open the page.
  for _ in $(seq 1 40); do
    if (exec 3<>"/dev/tcp/127.0.0.1/$PORT") 2>/dev/null; then
      exec 3>&-
      if command -v explorer.exe >/dev/null 2>&1; then
        explorer.exe "$URL" >/dev/null 2>&1 || true   # WSL: opens the Windows browser
      elif command -v xdg-open >/dev/null 2>&1; then
        xdg-open "$URL" >/dev/null 2>&1 || true
      else
        echo "Could not open a browser automatically. Open $URL manually."
      fi
      return
    fi
    sleep 0.25
  done
  echo "Server did not start within 10 seconds. Open $URL manually once it is up."
}

if [ "$OPEN_BROWSER" -eq 1 ]; then
  open_browser &
fi

# --- Run --------------------------------------------------------------------

echo "Timetable generator starting on $URL"
echo "Press Ctrl+C to stop."
echo

cd backend
exec "$UVICORN" app.main:app --host 127.0.0.1 --port "$PORT"
