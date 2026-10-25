#!/usr/bin/env bash
# Sourced by the launchers; accepts both executable paths and command names.
APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
if [[ -n "${LATEX_PYTHON:-}" ]]; then
  PYTHON_BIN="$LATEX_PYTHON"
elif [[ -x "$APP_DIR/.venv/bin/python" ]]; then
  PYTHON_BIN="$APP_DIR/.venv/bin/python"
else
  PYTHON_BIN="$(command -v python3 || true)"
fi
if [[ -z "$PYTHON_BIN" ]] || ! command -v "$PYTHON_BIN" >/dev/null 2>&1; then
  echo "No se encontró Python 3.10 o superior. Revisa LATEX_PYTHON." >&2
  exit 1
fi
if ! "$PYTHON_BIN" -c 'import sys; sys.exit(sys.version_info < (3, 10))'; then
  echo "Se requiere Python 3.10 o superior." >&2
  exit 1
fi
export PATH="/Library/TeX/texbin:$PATH"
