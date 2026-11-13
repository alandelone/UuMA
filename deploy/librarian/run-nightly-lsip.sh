#!/usr/bin/env bash
set -euo pipefail

# Production runner for Librarian LSIP Nightly Pipeline
VENV_PYTHON="/home/alandelone/.local/share/uuma/production/librarian/releases/semantic-8fc891ce62a14449bd088e9d579b8d72/venv/bin/python"
if [ ! -f "${VENV_PYTHON}" ]; then
    VENV_PYTHON="/usr/bin/python3"
fi
RELEASE_SRC="/home/alandelone/.local/share/uuma/production/librarian/releases/lsip-20261112/src"

SEMANTIC_DB="/home/alandelone/.local/share/uuma/production/librarian/semantic-archive/librarian_semantic.db"
CATALOG_DIR="/home/alandelone/.local/share/uuma/production/librarian/semantic-archive"
CONFIG_FILE="/home/alandelone/.local/share/uuma/production/librarian/lsip_sources.json"

mkdir -p "$(dirname "${SEMANTIC_DB}")" "${CATALOG_DIR}"

# Create default source configuration if missing
if [ ! -f "${CONFIG_FILE}" ]; then
    cat << 'EOF' > "${CONFIG_FILE}"
{
    "yonc_db": "/home/alandelone/.local/share/uuma/production/yonc/project_graph.sqlite3",
    "uuma_db": "/home/alandelone/.local/share/uuma/data/uuma.db",
    "brainstormer_json": "/home/alandelone/.local/share/uuma/production/brainstormer/state.json",
    "codex_sessions_dir": "/home/alandelone/.codex/sessions"
}
EOF
fi

echo "[$(date -u +%FT%TZ)] Starting Librarian LSIP Nightly Pipeline..."
PYTHONPATH="${RELEASE_SRC}" "${VENV_PYTHON}" -m uuma.librarian_nightly_pipeline \
    --db "${SEMANTIC_DB}" \
    --output-dir "${CATALOG_DIR}" \
    --config "${CONFIG_FILE}"

echo "[$(date -u +%FT%TZ)] Librarian LSIP Nightly Pipeline completed successfully."
