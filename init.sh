#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="${REPO_ROOT}/.venv"
SANDBOX_DIR="${UUMA_DATA_DIR:-${REPO_ROOT}/.uuma-local}"
if [[ -n "${PYTHON_BIN:-}" ]]; then
  PYTHON_COMMAND=("${PYTHON_BIN}")
elif command -v py >/dev/null 2>&1; then
  PYTHON_COMMAND=(py -3.12)
elif command -v python3 >/dev/null 2>&1; then
  PYTHON_COMMAND=(python3)
else
  PYTHON_COMMAND=(python)
fi

if [[ ! -d "${VENV_DIR}" ]]; then
  "${PYTHON_COMMAND[@]}" -m venv "${VENV_DIR}"
fi

if [[ -x "${VENV_DIR}/Scripts/python.exe" ]]; then
  VENV_PYTHON="${VENV_DIR}/Scripts/python.exe"
else
  VENV_PYTHON="${VENV_DIR}/bin/python"
fi

if [[ "${VENV_PYTHON}" == *.exe ]] && command -v cygpath >/dev/null 2>&1; then
  export UUMA_DATA_DIR="$(cygpath -w "${SANDBOX_DIR}")"
  export UUMA_FIXTURE_PATH="$(cygpath -w "${SANDBOX_DIR}/fixtures/seed-data.json")"
else
  export UUMA_DATA_DIR="${SANDBOX_DIR}"
  export UUMA_FIXTURE_PATH="${SANDBOX_DIR}/fixtures/seed-data.json"
fi

cd "${REPO_ROOT}"
"${VENV_PYTHON}" -m pip install -e ".[dev]"
mkdir -p "${SANDBOX_DIR}/fixtures"
cp "${REPO_ROOT}/test-fixtures/seed-data.json" "${UUMA_FIXTURE_PATH}"

"${VENV_PYTHON}" -c \
  'from uuma.settings import Settings; from uuma.service import ControlPlane; from uuma.knowledge_store import KnowledgeStore; s = Settings.from_env(); ControlPlane(s).bootstrap(); KnowledgeStore(s.knowledge_database_path()); print(f"Initialized isolated UuMA data at {s.data_dir}")'

if [[ "${1:-}" == "--serve" ]]; then
  exec "${VENV_PYTHON}" -m uuma.api
fi

echo "Environment ready. Run: ${VENV_PYTHON} -m pytest"
