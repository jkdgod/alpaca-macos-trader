#!/bin/bash
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="${PROJECT_DIR}/.venv"
PYTHON_BIN="${PYTHON_BIN:-python3.12}"
MACOS_LOG_DIR="${HOME}/Library/Logs/TradingBot"

if ! command -v "${PYTHON_BIN}" >/dev/null 2>&1; then
  echo "Error: ${PYTHON_BIN} was not found. Install Python 3.12+ and rerun."
  exit 1
fi

"${PYTHON_BIN}" - <<'PY'
import sys
if sys.version_info < (3, 12):
    raise SystemExit(f"Python 3.12+ is required; found {sys.version.split()[0]}")
PY

mkdir -p "${PROJECT_DIR}/logs" "${PROJECT_DIR}/runtime" "${MACOS_LOG_DIR}"

if [[ ! -d "${VENV_DIR}" ]]; then
  "${PYTHON_BIN}" -m venv "${VENV_DIR}"
fi

"${VENV_DIR}/bin/python" -m pip install --upgrade pip wheel setuptools
"${VENV_DIR}/bin/python" -m pip install --requirement "${PROJECT_DIR}/requirements.txt"

if [[ ! -f "${PROJECT_DIR}/.env" ]]; then
  cp "${PROJECT_DIR}/.env.example" "${PROJECT_DIR}/.env"
  chmod 600 "${PROJECT_DIR}/.env"
  echo "Created ${PROJECT_DIR}/.env. Add your Alpaca PAPER credentials before running a health check."
else
  chmod 600 "${PROJECT_DIR}/.env"
fi

chmod +x "${PROJECT_DIR}/setup.sh"

echo "Setup complete."
echo "Edit: ${PROJECT_DIR}/.env"
echo "Test: ${VENV_DIR}/bin/python -m unittest discover -s tests -v"
echo "Health check: ${VENV_DIR}/bin/python main.py healthcheck"
