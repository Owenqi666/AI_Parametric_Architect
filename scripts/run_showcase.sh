#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKEND_HOST="${SHOWCASE_BACKEND_HOST:-127.0.0.1}"
BACKEND_PORT="${SHOWCASE_BACKEND_PORT:-8000}"
FRONTEND_HOST="${SHOWCASE_FRONTEND_HOST:-127.0.0.1}"
FRONTEND_PORT="${SHOWCASE_FRONTEND_PORT:-3000}"
BACKEND_URL="http://${BACKEND_HOST}:${BACKEND_PORT}"
FRONTEND_URL="http://${FRONTEND_HOST}:${FRONTEND_PORT}"
backend_pid=""
frontend_pid=""

cleanup() {
  trap - EXIT INT TERM
  if [[ -n "${frontend_pid}" ]] && kill -0 "${frontend_pid}" 2>/dev/null; then
    kill "${frontend_pid}" 2>/dev/null || true
  fi
  if [[ -n "${backend_pid}" ]] && kill -0 "${backend_pid}" 2>/dev/null; then
    kill "${backend_pid}" 2>/dev/null || true
  fi
  [[ -n "${frontend_pid}" ]] && wait "${frontend_pid}" 2>/dev/null || true
  [[ -n "${backend_pid}" ]] && wait "${backend_pid}" 2>/dev/null || true
}

trap cleanup EXIT INT TERM

for command_name in uv node npm; do
  if ! command -v "${command_name}" >/dev/null 2>&1; then
    echo "Missing required command: ${command_name}" >&2
    exit 1
  fi
done

node -e '
const [major, minor] = process.versions.node.split(".").map(Number);
if (major < 22 || (major === 22 && minor < 13)) {
  console.error(`Node >=22.13.0 is required; found ${process.versions.node}.`);
  process.exit(1);
}
'

cd "${ROOT_DIR}"
uv sync --dev --locked
uv run python -c '
import sys
if not ((3, 12) <= sys.version_info[:2] < (3, 14)):
    raise SystemExit(f"Python >=3.12,<3.14 is required; found {sys.version.split()[0]}.")
'

(
  cd frontend
  npm ci
)

uv run uvicorn ai_parametric_architect.backend.api:app \
  --host "${BACKEND_HOST}" \
  --port "${BACKEND_PORT}" &
backend_pid=$!

(
  cd frontend
  SHOWCASE_API_ORIGIN="${BACKEND_URL}" npm run dev -- \
    --host "${FRONTEND_HOST}" \
    --port "${FRONTEND_PORT}"
) &
frontend_pid=$!

echo "AI Parametric Architect Studio is starting."
echo "Studio: ${FRONTEND_URL}"
echo "FastAPI: ${BACKEND_URL}"
echo "Press Ctrl+C to stop both processes."

while kill -0 "${backend_pid}" 2>/dev/null && kill -0 "${frontend_pid}" 2>/dev/null; do
  sleep 1
done

echo "A showcase process stopped unexpectedly." >&2
exit 1

