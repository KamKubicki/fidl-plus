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

Nie musisz nic budować ani instalować Chrome'a. Gotowy obraz leży w GitHub
Container Registry:

```
ghcr.io/kamkubicki/fidl-plus:latest
```

Jest to obraz **multi-arch** – pod jednym tagiem siedzą wersje `linux/amd64`
(Synology, zwykłe PC, serwery) i `linux/arm64` (Apple Silicon, Raspberry Pi).
Docker sam pobiera właściwą, więc niczego nie wybierasz.

### Start w dwóch poleceniach

```bash
mkdir fidl-plus && cd fidl-plus
curl -O https://raw.githubusercontent.com/KamKubicki/fidl-plus/master/docker-compose.yml
docker compose up -d
```

Pierwsze pobranie trwa chwilę – obraz waży ok. 2 GB, bo zawiera Chromium.

### Logowanie

1. Otwórz `http://localhost:8000/login`
2. Kliknij **Otwórz przeglądarkę i zaloguj się**
3. Otworzy się druga karta z obrazem przeglądarki działającej w kontenerze
   (noVNC, port 6080). Zaloguj się w niej normalnie do Lidl Plus.
4. Token zostanie przechwycony sam i zapisany w `./data/lidl_tokens.json`
5. Wróć na `http://localhost:8000` i kliknij **Odśwież dane**

Logujesz się ręcznie, w widocznym oknie, bo Lidl potrafi zażądać kodu SMS
albo captchy – tryb w pełni automatyczny by na tym poległ.

Jeśli Lidl zablokuje logowanie z adresu twojego serwera, na stronie `/login`
jest **Metoda 2**: uruchom logowanie raz na komputerze z Chrome
(`python3 browser_login.py`) i wgraj powstały `lidl_tokens.json` formularzem.

### Aktualizacja

```bash
docker compose pull && docker compose up -d
```

### Budowanie z własnych źródeł

```bash
git clone https://github.com/KamKubicki/fidl-plus.git
cd fidl-plus
docker compose -f docker-compose.yml -f docker-compose.dev.yml up -d --build
```

---

## Synology NAS – krok po kroku

### Sposób 1: Container Manager (DSM 7.2 i nowszy)

1. **File Station** → utwórz folder na dane, np. `docker/fidl-plus`
2. **Container Manager** → **Projekt** → **Utwórz**
3. Nazwa projektu: `fidl-plus`, ścieżka: folder z punktu 1
4. Źródło: **Utwórz plik docker-compose.yml** i wklej:

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
      - /volume1/docker/fidl-plus/data:/data
    environment:
      TZ: Europe/Warsaw
      PUID: "1026"     # patrz niżej
      PGID: "100"
    shm_size: "1gb"
```

5. Kliknij **Dalej** → **Gotowe**. Pierwsze uruchomienie potrwa kilka minut
   (pobieranie 2 GB).
6. Otwórz `http://IP-NAS-a:8000/login` i zaloguj się jak wyżej

### Sposób 2: Portainer

**Stacks** → **Add stack** → **Web editor**, wklej ten sam YAML co wyżej
i kliknij **Deploy the stack**.

Aktualizacja: **Stacks** → `fidl-plus` → **Update** z zaznaczonym
**Re-pull image**.

### Sposób 3: SSH

```bash
mkdir -p /volume1/docker/fidl-plus && cd /volume1/docker/fidl-plus
curl -O https://raw.githubusercontent.com/KamKubicki/fidl-plus/master/docker-compose.yml
docker compose up -d
```

### PUID i PGID – jak ustalić właściwe

Synology nadaje użytkownikom nietypowe identyfikatory (często `1026`, `1027`).
Kontener domyślnie używa `1000:1000`. Jeśli twój folder należy do kogoś innego,
podaj właściwe wartości – sprawdzisz je przez SSH:

```bash
id twoja_nazwa_uzytkownika
# uid=1026(kamil) gid=100(users)
```

Nie musisz nic robić ręcznie z uprawnieniami: kontener startuje jako root
wyłącznie po to, żeby ustawić właściciela `/data`, po czym schodzi do
`PUID:PGID`. Sama aplikacja i Chromium nigdy nie działają jako root.

### Gdy coś nie działa

| Objaw | Przyczyna |
|---|---|
| Kontener restartuje się w kółko | Brakuje `shm_size: "1gb"` – Chromium nie wstanie na domyślnych 64 MB |
| `ERROR: /data is not writable` | Zły `PUID`/`PGID` – sprawdź `id` przez SSH |
| Strona działa, noVNC nie | Port 6080 nie został przekierowany |
| Puste okno noVNC | Odśwież kartę; Chromium wstaje kilka sekund |

Logi: **Container Manager** → `fidl-plus` → **Dziennik**, albo
`docker logs fidl-plus`.

---

## Konfiguracja

| Zmienna | Domyślnie | Opis |
|---|---|---|
| `DATA_DIR` | `/data` | katalog na tokeny i paragony |
| `PUID` / `PGID` | `1000` | właściciel plików w `/data` |
| `NOVNC_PORT` | `6080` | port podglądu przeglądarki |
| `NOVNC_URL` | – | pełny adres noVNC, gdy stoisz za reverse proxy |
| `LOGIN_TIMEOUT` | `180` | ile sekund czekać na zalogowanie |
| `TZ` | – | strefa czasowa, np. `Europe/Warsaw` |

Zmiana portu aplikacji – w `docker-compose.yml`:

```yaml
ports:
  - "8080:8000"
```

> **Uwaga na bezpieczeństwo.** Aplikacja nie ma uwierzytelniania, a noVNC
> działa bez hasła. Kto dojdzie do portu 8000, zobaczy wszystkie paragony;
> kto dojdzie do 6080, steruje przeglądarką wewnątrz twojej sieci.
> Trzymaj oba porty w LAN i nie przekierowuj ich na routerze.

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
├── docker-compose.yml      # gotowy obraz z GHCR
├── docker-compose.dev.yml  # nakładka do budowania lokalnie
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
