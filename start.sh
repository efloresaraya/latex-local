#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "$0")" && pwd)/scripts/python-env.sh"
cd "$APP_DIR"
if ! "$PYTHON_BIN" -c 'import fastapi, uvicorn, multipart, httpx' >/dev/null 2>&1; then
  echo "Faltan dependencias. Ejecuta: python -m pip install -r requirements.txt" >&2
  exit 1
fi
if ! command -v latexmk >/dev/null 2>&1; then
  echo "No se encontró latexmk. Instala una distribución TeX y revisa PATH." >&2
  exit 1
fi
PORT="${LATEX_PORT:-8765}"
if ! [[ "$PORT" =~ ^[0-9]{1,5}$ ]] || (( 10#$PORT < 1 || 10#$PORT > 65535 )); then
  echo "LATEX_PORT debe ser un número entre 1 y 65535." >&2
  exit 1
fi
printf 'LaTeX Local — http://127.0.0.1:%s
' "$PORT"
echo "Documentos en su carpeta original. Respaldos en .latex-local/."
exec "$PYTHON_BIN" -m uvicorn backend.main:app --host 127.0.0.1 --port "$PORT"
