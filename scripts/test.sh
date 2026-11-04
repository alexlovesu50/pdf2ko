#!/bin/sh
set -eu
SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
BUNDLED="$HOME/.cache/codex-runtimes/codex-primary-runtime/dependencies"
if [ -n "${PDF2KO_PYTHON:-}" ]; then
  RUNTIME_PYTHON=$PDF2KO_PYTHON
elif [ -x "$BUNDLED/python/bin/python3" ]; then
  RUNTIME_PYTHON="$BUNDLED/python/bin/python3"
elif [ -x "$BUNDLED/python/python.exe" ]; then
  RUNTIME_PYTHON="$BUNDLED/python/python.exe"
else
  RUNTIME_PYTHON=python3
fi
cd "$SCRIPT_DIR/.."
exec "$RUNTIME_PYTHON" -X utf8 -m unittest discover -s tests -v
