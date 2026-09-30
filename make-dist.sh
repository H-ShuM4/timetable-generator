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
cp setup.bat start.bat README.md "$DEST/"

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

# The zip is committed to the repository, so the same sources must always
# produce the same bytes. Otherwise every rebuild shows up as a 150 KB diff
# and "has the zip been rebuilt?" becomes unanswerable.
#
# Two things would otherwise leak in: the order rglob happens to walk, and
# each file's timestamp (cp sets those to the build time). Sort the names and
# pin every timestamp to the start of the zip epoch, which is what other
# reproducible builds use. Windows shows 1980 as the file date inside the
# archive; nothing depends on it.
EPOCH = (1980, 1, 1, 0, 0, 0)

stage = pathlib.Path(sys.argv[1])
root = stage / "timetable-generator"
out = pathlib.Path.cwd() / "timetable-generator.zip"
out.unlink(missing_ok=True)

files = sorted(p for p in root.rglob("*") if p.is_file())
with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as z:
    for f in files:
        entry = zipfile.ZipInfo(f.relative_to(stage).as_posix(), date_time=EPOCH)
        entry.compress_type = zipfile.ZIP_DEFLATED
        entry.external_attr = (f.stat().st_mode & 0o7777) << 16
        z.writestr(entry, f.read_bytes())

print(f"{out.name}: {len(files)} files, {out.stat().st_size / 1024:.0f} KB")
PY
