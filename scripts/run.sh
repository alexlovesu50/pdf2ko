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
# 한글 입출력의 운영체제별 기본 인코딩 차이 방지
exec "$RUNTIME_PYTHON" -X utf8 "$SCRIPT_DIR/pipeline.py" "$@"
