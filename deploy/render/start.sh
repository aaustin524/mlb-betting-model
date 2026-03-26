#!/usr/bin/env bash
set -euo pipefail

export PORT="${PORT:-10000}"
export API_URL="${API_URL:-${RENDER_EXTERNAL_URL:-http://localhost:${PORT}}}"
export DEPLOY_URL="${DEPLOY_URL:-${RENDER_EXTERNAL_URL:-http://localhost:${PORT}}}"
export MLB_MODEL_DB_PATH="${MLB_MODEL_DB_PATH:-/var/data/mlb_betting_model.sqlite}"
export MLB_MODEL_HISTORY_DIR="${MLB_MODEL_HISTORY_DIR:-/var/data/history}"

mkdir -p "${MLB_MODEL_HISTORY_DIR}"
mkdir -p "$(dirname "${MLB_MODEL_DB_PATH}")"

envsubst '${PORT}' < /etc/nginx/templates/default.conf.template > /etc/nginx/conf.d/default.conf

reflex run --env prod &
REFLEX_PID=$!

cleanup() {
  if kill -0 "${REFLEX_PID}" >/dev/null 2>&1; then
    kill "${REFLEX_PID}" >/dev/null 2>&1 || true
    wait "${REFLEX_PID}" || true
  fi
}

trap cleanup EXIT INT TERM

for _ in $(seq 1 120); do
  if curl -fsS "http://127.0.0.1:3000" >/dev/null 2>&1 && curl -fsS "http://127.0.0.1:8000/ping/" >/dev/null 2>&1; then
    break
  fi
  sleep 1
done

nginx -g 'daemon off;'
