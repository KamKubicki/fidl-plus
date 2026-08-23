FROM python:3.11-slim

# Zainstaluj zależności systemowe
RUN apt-get update && apt-get install -y \
    curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Skopiuj i zainstaluj zależności Pythona (bez Playwright - nie potrzebny w trybie serwerowym)
COPY requirements.txt .
RUN pip install --no-cache-dir fastapi uvicorn jinja2 python-multipart requests beautifulsoup4

# Skopiuj kod aplikacji
COPY app.py lidl_api.py receipt_parser.py price_analyzer.py ./
COPY templates/ templates/
COPY static/ static/

# Katalog na dane (paragony i tokeny montowane jako volume)
RUN mkdir -p /data

# Zmienne środowiskowe
ENV FIDL_TOKENS_FILE=/data/lidl_tokens.json
ENV FIDL_DATA_FILE=/data/wszystkie_paragony_szczegoly.json
ENV FIDL_HOST=0.0.0.0
ENV FIDL_PORT=8000

EXPOSE 8000

CMD ["python", "-u", "app.py", "--docker"]
