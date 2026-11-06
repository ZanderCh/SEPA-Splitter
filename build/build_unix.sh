#!/usr/bin/env bash
# Baut das portable Paket für Linux oder macOS (auf dem jeweiligen Zielsystem ausführen).
set -euo pipefail
cd "$(dirname "$0")/.."
OS="$(uname -s)"; ARCH="$(uname -m)"
python3 -m venv .venv-build
. .venv-build/bin/activate
pip install -r requirements-dev.txt
python -m unittest discover -s tests -v          # Build bricht bei fehlgeschlagenen Tests ab
rm -rf dist build/work
pyinstaller --noconfirm --clean --windowed --name SEPA-Splitter --workpath build/work \
    --collect-submodules lxml run_sepa_splitter.py
if [ "$OS" = "Darwin" ]; then
  OUT="dist/SEPA-Splitter-macOS-$ARCH"; mkdir -p "$OUT"
  mv dist/SEPA-Splitter.app "$OUT/"; rm -rf dist/SEPA-Splitter
else
  OUT="dist/SEPA-Splitter-Linux-$ARCH"; mkdir -p "$OUT"
  mv dist/SEPA-Splitter/* "$OUT/"; rmdir dist/SEPA-Splitter
fi
cp SEPA-Splitter.ini "$OUT/"; cp -r schemas "$OUT/"
echo "Fertig: $OUT"
# macOS: Signierung/Notarisierung siehe BUILD.md
