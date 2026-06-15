#!/usr/bin/env bash
# Run the whole app locally with ZERO external services.
# Uses the embedded chdb ClickHouse engine and seeds sample data on first run.
#
#   ./scripts/run_local.sh
#
# then open http://localhost:8000
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT/backend"

echo "==> Installing Python dependencies"
pip install -q -r requirements.txt

export CH_BACKEND="${CH_BACKEND:-embedded}"
export CHDB_PATH="${CHDB_PATH:-$ROOT/data/chdb}"
export SEED_SESSIONS="${SEED_SESSIONS:-500000}"
export SEED_USERS="${SEED_USERS:-50000}"
export SEED_PRODUCTS="${SEED_PRODUCTS:-500}"

echo "==> Starting API + dashboard on http://localhost:8000  (backend=$CH_BACKEND)"
exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 1
