#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "$0")" && pwd)/python-env.sh"
cd "$APP_DIR"
export PYTHONDONTWRITEBYTECODE=1
"$PYTHON_BIN" -m pytest -q -p no:cacheprovider
for test_file in tests/test_*.cjs; do
  node "$test_file"
done
