#!/bin/bash
# Single-container entrypoint: runs FastAPI internally and the Next.js
# standalone server on the externally exposed port (see Dockerfile). If
# either process exits, the other is killed too, so the container as a
# whole exits/restarts instead of silently running in a half-broken state.
set -e

INTERNAL_API_PORT="${INTERNAL_API_PORT:-8000}"
PORT="${PORT:-7860}"

cd /app/backend
python -m uvicorn app.main:app --host 127.0.0.1 --port "$INTERNAL_API_PORT" &
BACKEND_PID=$!

cd /app
PORT="$PORT" HOSTNAME="0.0.0.0" node frontend/server.js &
FRONTEND_PID=$!

trap 'kill -TERM $BACKEND_PID $FRONTEND_PID 2>/dev/null' TERM INT

wait -n "$BACKEND_PID" "$FRONTEND_PID"
EXIT_CODE=$?
kill -TERM $BACKEND_PID $FRONTEND_PID 2>/dev/null
exit $EXIT_CODE
