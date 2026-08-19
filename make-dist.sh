#!/usr/bin/env bash
#
# Build timetable-generator.zip for distribution to office PCs.
#
# The zip contains only what is needed to run the system on Windows: the
# application, its configuration, the frontend, the launcher scripts and the
# README. It deliberately excludes the virtual environment, the tests, the
# documentation, the API key and every runtime artefact.
#
# Usage:  ./make-dist.sh

set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$PROJECT_ROOT"

STAGE="$(mktemp -d)"
trap 'rm -rf "$STAGE"' EXIT
DEST="$STAGE/timetable-generator"

mkdir -p "$DEST/backend"
cp -r backend/app "$DEST/backend/app"
cp -r backend/config "$DEST/backend/config"
cp backend/requirements.txt "$DEST/backend/"
cp -r frontend "$DEST/frontend"
cp setup.bat start.bat README.txt "$DEST/"

# Strip anything Python left behind while we were running it.
find "$DEST" -name __pycache__ -type d -exec rm -rf {} + 2>/dev/null || true
find "$DEST" -name '*.pyc' -delete 2>/dev/null || true

# Refuse to ship secrets, a foreign virtual environment, or dev artefacts.
for forbidden in .env .venv data logs tests; do
  if find "$DEST" -name "$forbidden" | grep -q .; then
    echo "ERROR: '$forbidden' found in the staged tree. Refusing to build." >&2
    exit 1
  fi
done

python3 - "$STAGE" <<'PY'
import pathlib, sys, zipfile

stage = pathlib.Path(sys.argv[1])
root = stage / "timetable-generator"
out = pathlib.Path.cwd() / "timetable-generator.zip"
out.unlink(missing_ok=True)

files = sorted(p for p in root.rglob("*") if p.is_file())
with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as z:
    for f in files:
        z.write(f, f.relative_to(stage).as_posix())

print(f"{out.name}: {len(files)} files, {out.stat().st_size / 1024:.0f} KB")
PY
