# Fidl Plus

[![CI](https://github.com/KamKubicki/fidl-plus/actions/workflows/ci.yml/badge.svg)](https://github.com/KamKubicki/fidl-plus/actions/workflows/ci.yml)
[![Obraz Docker](https://github.com/KamKubicki/fidl-plus/actions/workflows/docker.yml/badge.svg)](https://github.com/KamKubicki/fidl-plus/actions/workflows/docker.yml)

Lokalna aplikacja webowa do przeglądania paragonów z aplikacji Lidl Plus.
Pobiera dane przez mobilne API Lidl Plus i wyświetla je w przeglądarce.

## Funkcje

- **Dashboard** – statystyki wydatków, ulubiony sklep, ostatnie zakupy
- **Lista paragonów** – wszystkie zakupy z filtrowaniem po sklepie i dacie
- **Szczegóły paragonu** – pełna lista produktów z cenami i rabatami
- **Wyszukiwarka** – znajdź produkt po nazwie, zobacz ile razy kupiony
- **Historia ceny** – wykres zmiany ceny produktu w czasie
- **Normalizacja nazw** – ten sam produkt pod różnymi nazwami jest scalany po kodzie kreskowym

## Screenshoty

| Dashboard | Insights |
|---|---|
| ![Dashboard](docs/screenshots/dashboard.png) | ![Insights](docs/screenshots/insights.png) |

| Top produkty | Historia ceny |
|---|---|
| ![Top produkty](docs/screenshots/top_products_v2.png) | ![Wykres](docs/screenshots/product_chart.png) |

| Paragony | Szczegóły paragonu |
|---|---|
| ![Paragony](docs/screenshots/receipts.png) | ![Szczegóły](docs/screenshots/receipt_detail.png) |

## Uruchomienie w Dockerze (zalecane)

Działa na dowolnym systemie – nie wymaga Chrome ani Pythona na hoście.
Gotowy obraz jest budowany dla `linux/amd64` i `linux/arm64`.

```bash
mkdir fidl-plus && cd fidl-plus
curl -O https://raw.githubusercontent.com/KamKubicki/fidl-plus/master/docker-compose.yml
docker compose up -d
```

Albo z gita, jeśli chcesz budować u siebie:

```bash
git clone https://github.com/KamKubicki/fidl-plus.git
cd fidl-plus
docker compose up -d --build
```

Wejdź na `http://localhost:8000/login` i kliknij **Zaloguj się**.
Otworzy się druga karta z podglądem przeglądarki uruchomionej w kontenerze
(noVNC, port 6080) – zaloguj się tam ręcznie do Lidl Plus. Token zostanie
przechwycony automatycznie i zapisany w `./data/lidl_tokens.json`.

Następnie kliknij **Odśwież dane**, żeby pobrać paragony.

> **Uwaga na bezpieczeństwo.** Aplikacja nie ma uwierzytelniania, a noVNC
> działa bez hasła. Kto dojdzie do portu 8000, zobaczy wszystkie paragony;
> kto dojdzie do 6080, steruje przeglądarką wewnątrz twojej sieci.
> Trzymaj oba porty w LAN i nie przekierowuj ich na routerze.

Zmienne środowiskowe:

| Zmienna | Domyślnie | Opis |
|---|---|---|
| `DATA_DIR` | `/data` | katalog na tokeny i paragony |
| `NOVNC_PORT` | `6080` | port podglądu przeglądarki |
| `NOVNC_URL` | – | pełny adres noVNC, gdy stoisz za reverse proxy |
| `LOGIN_TIMEOUT` | `180` | ile sekund czekać na zalogowanie |

---

## Synology / NAS przez Portainer

Obraz jest publikowany do GitHub Container Registry przy każdym pushu
na `master`:

```
ghcr.io/kamkubicki/fidl-plus:latest
```

W Portainerze: **Stacks → Add stack → Web editor**, wklej poniższe
i kliknij *Deploy*.

```yaml
services:
  fidl-plus:
    image: ghcr.io/kamkubicki/fidl-plus:latest
    container_name: fidl-plus
    restart: unless-stopped
    ports:
      - "8000:8000"
      - "6080:6080"
    volumes:
      - /volume1/docker/fidl-plus:/data   # dostosuj ścieżkę do swojego NAS-a
    environment:
      TZ: Europe/Warsaw
      DATA_DIR: /data
      NOVNC_PORT: "6080"
    shm_size: "1gb"
```

Uwagi:

- **`shm_size: 1gb` jest wymagane.** Domyślne 64 MB na `/dev/shm` powoduje,
  że Chromium wywala się przy starcie.
- Katalog z wolumenu musi istnieć i być zapisywalny dla UID 1000 –
  kontener działa jako użytkownik `fidl`, nie root.
- Obraz waży ok. 2 GB (Chromium + fonty).
- Aktualizacja: w Portainerze *Stacks → fidl-plus → Update* z zaznaczonym
  **Re-pull image**.

### Synology DSM – Container Manager

Bez Portainera, wprost w DSM:

1. **Container Manager** → **Project** → **Create**
2. wskaż katalog z projektem (musi zawierać `docker-compose.yml`)
3. upewnij się, że katalog `data` istnieje na NAS-ie
4. uruchom projekt

### Gdy logowanie w przeglądarce zawiedzie

Na stronie `/login` jest druga metoda: uruchom logowanie raz lokalnie na
komputerze z Chrome (`python3 browser_login.py`) i wgraj powstały plik
`lidl_tokens.json` przez formularz. Przydaje się, gdy Lidl zablokuje
logowanie z adresu IP serwera.

Refresh token jest ważny 30 dni i aplikacja odświeża go przy każdej
synchronizacji, więc czynność powtarza się rzadko.

### Zmiana portu

```yaml
ports:
  - "8080:8000"
```

### Bez rejestru, obrazem z pliku

Jeśli wolisz nie korzystać z GHCR, zbuduj obraz pod architekturę NAS-a
i wgraj go przez *Portainer → Images → Import*:

```bash
docker buildx build --platform linux/amd64 -t fidl-plus:latest --load .
docker save fidl-plus:latest | gzip > fidl-plus-amd64.tar.gz
```

---

## Instalacja lokalna (bez Dockera)

### Wymagania

- Python 3.11+
- Google Chrome (macOS) lub Chromium (Linux) – do logowania

### Instalacja

```bash
git clone https://github.com/KamKubicki/fidl-plus.git
cd fidl-plus

python3 -m venv .venv
source .venv/bin/activate

pip install -r requirements.txt
```

Na macOS używana jest domyślna ścieżka do Google Chrome. Na innych systemach
albo przy nietypowej lokalizacji wskaż binarkę zmienną `CHROME_BINARY`:

```bash
export CHROME_BINARY=/usr/bin/chromium
```

## Użycie

### 1. Zaloguj się do Lidl Plus

```bash
python3 browser_login.py
```

Otworzy się okno Chrome z formularzem logowania Lidl Plus (Fidl Plus).
Zaloguj się ręcznie – token zostanie automatycznie przechwycony
i zapisany do `data/lidl_tokens.json`.

> Token jest ważny ~1 godzinę. Refresh token pozwala go odświeżyć
> przez 30 dni bez ponownego logowania.

### 2. Uruchom aplikację

```bash
python3 app.py
```

Aplikacja otworzy się automatycznie na `http://localhost:8000`.

### 3. Pobierz paragony

Wejdź na stronę `/sync` lub kliknij **Odśwież dane** w nawigacji.
Pobieranie wszystkich paragonów może potrwać kilka minut.

---

## Struktura projektu

```
├── app.py                  # Serwer FastAPI – wszystkie endpointy
├── lidl_api.py             # Klient mobilnego API Lidl Plus (OAuth2 PKCE)
├── browser_login.py        # Logowanie przez prawdziwy Chrome/Chromium
├── receipt_parser.py       # Parser HTML paragonów + normalizacja nazw
├── price_analyzer.py       # Analiza zmian cen
├── Dockerfile              # Chromium + Xvfb + noVNC + aplikacja
├── docker-compose.yml
├── docker-entrypoint.sh    # Start Xvfb / x11vnc / noVNC / uvicorn
├── lidl-callback-handler   # Handler schematu com.lidlplus.app://
├── templates/              # Szablony Jinja2
│   ├── base.html
│   ├── index.html
│   ├── receipts.html
│   ├── receipt_detail.html
│   ├── receipt_print.html
│   ├── search.html
│   ├── product.html
│   ├── login.html
│   └── sync.html
├── requirements.txt
├── data/                   # Tokeny i paragony: receipts.json, lidl_tokens.json
│                           # (poza repozytorium)
└── docs/
    └── screenshots/
```

## Jak działa logowanie

Lidl Plus używa **OAuth2 PKCE** z `client_id=LidlPlusNativeClient`.
Formularz logowania jest chroniony przez **reCAPTCHA Enterprise v3**,
która blokuje automatyczne requesty HTTP.

Rozwiązanie: `browser_login.py` uruchamia prawdziwą przeglądarkę przez
Playwright – dostaje ona dobry score od reCAPTCHA. Po zalogowaniu Lidl
przekierowuje na deep link `com.lidlplus.app://callback?code=...`, który
przechwytujemy trzema drogami:

1. **CDP** (`Network.requestWillBeSent`) – widzi też przekierowania 302
   na custom scheme, których Playwright czasem nie raportuje,
2. zdarzenia Playwright – `request`, `framenavigated`, `popup`,
3. **handler `xdg-open`** – system oddaje URL skryptowi
   `lidl-callback-handler`, który zapisuje go do pliku (Linux/Docker).

Kod jest następnie wymieniany na tokeny.

## Ceny i rabaty

Paragony rozróżniają dwie ceny:

- **cena podstawowa** – `currentUnitPrice`, cena regularna z półki,
- **cena promocyjna** – kwota faktycznie zapłacona, po odliczeniu kuponów
  Lidl Plus.

Statystyki, wykresy i rankingi liczone są na cenach promocyjnych.

> `totalAmount` zwracane przez API jest już **po** odliczeniu rabatów –
> `totalDiscount` służy tylko do pokazania, ile zaoszczędzono.

## Dane

Paragony (`receipts.json`) i tokeny (`lidl_tokens.json`) są przechowywane
lokalnie w katalogu `data/`, konfigurowalnym przez `DATA_DIR`. Katalog nie
jest commitowany do repozytorium (`.gitignore`).

> Starsza nazwa `wszystkie_paragony_szczegoly.json` jest nadal wczytywana,
> więc aktualizacja nie gubi danych – aplikacja tylko ostrzeże w logu.

API zwraca dwa formaty paragonów:
- **JSON** (`itemsLine`) – nowsze paragony, pełna struktura produktów
- **HTML** (`htmlPrintedReceipt`) – starsze paragony, `receipt_parser.py`
  parsuje je do tego samego formatu, razem z liniami rabatów

## Rozwój

```bash
pip install -r requirements-dev.txt

pytest          # testy
ruff check .    # lint
ruff check --fix .
```

Testy używają wyłącznie syntetycznych paragonów (`tests/conftest.py`) –
prawdziwe dane nigdy nie trafiają do repozytorium. Pokrywają logikę,
która najłatwiej cicho się psuje: parsowanie rabatów z HTML, przypisanie
kuponu do właściwej pozycji, towary na wagę oraz renderowanie szablonów.

CI (GitHub Actions) uruchamia lint i testy na Pythonie 3.11 i 3.12,
a po merge'u na `master` buduje i publikuje obraz `linux/amd64` +
`linux/arm64` do GHCR.

## Technologie

- **FastAPI** + **Uvicorn** – backend
- **Jinja2** – szablony HTML
- **HTMX** – dynamiczne UI bez pisania JS
- **Chart.js** – wykresy zmian cen
- **Playwright** – logowanie przez Chrome/Chromium
- **BeautifulSoup4** – parsowanie HTML paragonów
- **Xvfb + noVNC** – podgląd okna przeglądarki w Dockerze
