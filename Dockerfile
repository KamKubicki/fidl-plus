FROM python:3.11-bookworm

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONUNBUFFERED=1 \
    DISPLAY=:99

WORKDIR /app

# Chromium + Xvfb (virtual screen) + x11vnc/noVNC (browser preview in a tab)
RUN apt-get update && apt-get install -y --no-install-recommends \
        chromium \
        xvfb \
        x11-utils \
        x11vnc \
        novnc \
        websockify \
        xdg-utils \
        desktop-file-utils \
        ca-certificates \
        fonts-liberation \
        fonts-noto-color-emoji \
        fonts-noto-cjk \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Handler for the com.lidlplus.app:// scheme: it writes the OAuth deep link to
# a file that browser_login.py reads. Registered system-wide rather than with
# `xdg-mime default`, which only records the setting for the root user.
RUN install -m 755 /app/lidl-callback-handler /usr/local/bin/lidl-callback-handler \
    && mkdir -p /usr/share/applications \
    && printf '%s\n' \
        '[Desktop Entry]' \
        'Name=Lidl Plus Callback' \
        'Comment=Fidl Plus Lidl OAuth callback handler' \
        'Exec=/usr/local/bin/lidl-callback-handler %u' \
        'Terminal=false' \
        'Type=Application' \
        'NoDisplay=true' \
        'MimeType=x-scheme-handler/com.lidlplus.app;' \
        > /usr/share/applications/lidl-callback.desktop \
    && printf '%s\n' \
        '[Default Applications]' \
        'x-scheme-handler/com.lidlplus.app=lidl-callback.desktop' \
        > /usr/share/applications/mimeapps.list \
    && update-desktop-database /usr/share/applications || true

# Chromium refuses to start as root without --no-sandbox
RUN useradd --create-home --uid 1000 --shell /bin/bash fidl \
    && mkdir -p /data \
    && chmod +x /app/docker-entrypoint.sh \
    && chown -R fidl:fidl /app /data

ENV CHROME_BINARY=/usr/bin/chromium \
    DATA_DIR=/data \
    NOVNC_PORT=6080

USER fidl

VOLUME ["/data"]

EXPOSE 8000 6080

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s \
    CMD python -c "import urllib.request;urllib.request.urlopen('http://127.0.0.1:8000/')" || exit 1

ENTRYPOINT ["/app/docker-entrypoint.sh"]
