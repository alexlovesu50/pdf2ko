#!/bin/sh
set -eu
SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
BUNDLED="$HOME/.cache/codex-runtimes/codex-primary-runtime/dependencies"
RUNTIME_PYTHON=${PDF2KO_PYTHON:-"$BUNDLED/python/bin/python3"}
"$RUNTIME_PYTHON" -c 'import pypdf, pdfplumber, reportlab; print("pdf2ko dependencies: OK")'
"$SCRIPT_DIR/run.sh" init
