#!/bin/bash
set -euo pipefail

DATA_DIR="${DATA_DIR:-/data}"
PUID="${PUID:-1000}"
PGID="${PGID:-1000}"

# When started as root, take ownership of the data volume and then drop
# privileges. Without this a NAS bind mount owned by root is unwritable for the
# unprivileged user and the first token write fails. Chromium must not run as
# root either, so the application always ends up running as PUID:PGID.
if [ "$(id -u)" = "0" ]; then
    mkdir -p "${DATA_DIR}"

    if [ "$(stat -c '%u:%g' "${DATA_DIR}")" != "${PUID}:${PGID}" ]; then
        echo "Adjusting ownership of ${DATA_DIR} to ${PUID}:${PGID}..."
        chown -R "${PUID}:${PGID}" "${DATA_DIR}" || \
            echo "WARNING: could not chown ${DATA_DIR}; is it a read-only mount?"
    fi

    # Keep the fidl account in sync with the requested ids so file ownership on
    # the host matches what the user asked for.
    if [ "${PGID}" != "$(id -g fidl)" ]; then
        groupmod -o -g "${PGID}" fidl
    fi
    if [ "${PUID}" != "$(id -u fidl)" ]; then
        usermod -o -u "${PUID}" fidl
    fi

    exec setpriv --reuid "${PUID}" --regid "${PGID}" --init-groups "$0" "$@"
fi

export HOME="${HOME:-/home/fidl}"
export DISPLAY="${DISPLAY:-:99}"
SCREEN="${SCREEN_SIZE:-1280x900x24}"
VNC_PORT="${VNC_PORT:-5900}"
NOVNC_PORT="${NOVNC_PORT:-6080}"
APP_PORT="${APP_PORT:-8000}"

if ! touch "${DATA_DIR}/.write-test" 2>/dev/null; then
    echo "ERROR: ${DATA_DIR} is not writable by uid $(id -u)."
    echo "       On Linux/NAS run: chown -R $(id -u):$(id -g) <host directory>"
    echo "       or start the container with PUID/PGID matching that directory."
    exit 1
fi
rm -f "${DATA_DIR}/.write-test"

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
