#!/bin/bash
set -euo pipefail

export DISPLAY="${DISPLAY:-:99}"
SCREEN="${SCREEN_SIZE:-1280x900x24}"
VNC_PORT="${VNC_PORT:-5900}"
NOVNC_PORT="${NOVNC_PORT:-6080}"
APP_PORT="${APP_PORT:-8000}"

cleanup() {
    jobs -p | xargs -r kill 2>/dev/null || true
}
trap cleanup EXIT

echo "Starting Xvfb on ${DISPLAY} (${SCREEN})..."
Xvfb "${DISPLAY}" -screen 0 "${SCREEN}" -ac +extension GLX +render -noreset \
    > /tmp/xvfb.log 2>&1 &
XVFB_PID=$!

# Wait until the display is really up: a fixed `sleep 1` is too short on slower
# hardware and Chromium then dies with "cannot open display".
for _ in $(seq 1 30); do
    if xdpyinfo -display "${DISPLAY}" >/dev/null 2>&1; then
        break
    fi
    if ! kill -0 "${XVFB_PID}" 2>/dev/null; then
        echo "ERROR: Xvfb failed to start"
        cat /tmp/xvfb.log
        exit 1
    fi
    sleep 0.5
done

echo "Starting x11vnc on port ${VNC_PORT}..."
x11vnc -display "${DISPLAY}" -forever -shared -nopw \
    -listen 0.0.0.0 -rfbport "${VNC_PORT}" \
    > /tmp/x11vnc.log 2>&1 &

echo "Starting noVNC on port ${NOVNC_PORT}..."
websockify --web=/usr/share/novnc "${NOVNC_PORT}" "localhost:${VNC_PORT}" \
    > /tmp/websockify.log 2>&1 &

echo "Starting Fidl Plus on port ${APP_PORT}..."
exec uvicorn app:app --host 0.0.0.0 --port "${APP_PORT}"
