"""
Lidl Plus login through a real browser (Chrome / Chromium).

After a successful login Lidl redirects to a custom scheme:
    com.lidlplus.app://callback?code=...

That deep link is captured two ways:
1. CDP / Playwright - listening on browser requests and navigations,
2. an xdg-open handler that writes the URL to a file (Linux/Docker only).

Inside Docker, Chromium runs under Xvfb and its window is exposed over
noVNC on port 6080.
"""
import os
import shutil
import sys
import tempfile
import time
from urllib.parse import parse_qs, urlparse

try:
    from playwright.sync_api import sync_playwright
except ImportError:
    print("Brak biblioteki Playwright! Zainstaluj: pip install playwright")
    sys.exit(1)

from lidl_api import LidlPlusAPI

# ---------------------------------------------------------------------------
# Konfiguracja
# ---------------------------------------------------------------------------

DATA_DIR = os.getenv("DATA_DIR", os.path.join(os.path.dirname(os.path.abspath(__file__)), "data"))

# W Dockerze ustawiane przez ENV na /usr/bin/chromium.
_MACOS_CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
CHROME_BINARY = os.getenv(
    "CHROME_BINARY",
    _MACOS_CHROME if sys.platform == "darwin" else "/usr/bin/chromium",
)

TOKENS_FILE = os.path.join(DATA_DIR, "lidl_tokens.json")

# Plik zapisywany przez lidl-callback-handler (xdg-open).
CALLBACK_FILE = os.getenv("CALLBACK_FILE", "/tmp/fidl-lidl-callback")

LOGIN_TIMEOUT = int(os.getenv("LOGIN_TIMEOUT", "180"))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _extract_code(url: str) -> str | None:
    """Extract the authorization code from com.lidlplus.app://callback?code=..."""
    if not url or not url.startswith("com.lidlplus.app://"):
        return None
    return parse_qs(urlparse(url).query).get("code", [None])[0]


def _clear_callback_file():
    """Drop the callback from a previous login so a stale code is never reused."""
    try:
        os.remove(CALLBACK_FILE)
    except FileNotFoundError:
        pass
    except OSError as e:
        print(f"Nie można usunąć starego callbacka: {e}")


def _read_callback_file() -> str | None:
    try:
        with open(CALLBACK_FILE) as f:
            return f.read().strip()
    except FileNotFoundError:
        return None
    except OSError as e:
        print(f"Błąd odczytu callbacka: {e}")
        return None


# ---------------------------------------------------------------------------
# Login
# ---------------------------------------------------------------------------

def login_with_browser() -> dict | None:
    api = LidlPlusAPI(country="PL")
    auth_url, _state, code_verifier = api.get_authorization_url()

    os.makedirs(DATA_DIR, exist_ok=True)
    _clear_callback_file()

    # Always a fresh profile: Chromium leaves a SingletonLock behind, which
    # makes the next login fail with "Failed to create a ProcessSingleton".
    # Tokens are stored separately in TOKENS_FILE anyway.
    chrome_profile = tempfile.mkdtemp(prefix="fidl-chrome-", dir=DATA_DIR)

    found = {"code": None}

    def capture(url: str, source: str) -> None:
        if found["code"]:
            return
        code = _extract_code(url)
        if code:
            found["code"] = code
            print(f"Przechwycono kod ({source}).")

    try:
        with sync_playwright() as p:
            browser = None
            try:
                browser = p.chromium.launch_persistent_context(
                    user_data_dir=chrome_profile,
                    executable_path=CHROME_BINARY,
                    headless=False,
                    args=[
                        "--disable-blink-features=AutomationControlled",
                        "--no-first-run",
                        "--no-default-browser-check",
                    ],
                    viewport={"width": 390, "height": 844},
                    locale="pl-PL",
                    timezone_id="Europe/Warsaw",
                )
                page = browser.pages[0] if browser.pages else browser.new_page()

                # Primary path: CDP also sees redirects to the custom scheme,
                # which Playwright does not always report.
                cdp = browser.new_cdp_session(page)
                cdp.send("Network.enable")

                def on_request_sent(event):
                    capture(event.get("request", {}).get("url", ""), "CDP request")
                    headers = event.get("redirectResponse", {}).get("headers", {})
                    location = headers.get("location") or headers.get("Location") or ""
                    capture(location, "CDP redirect")

                cdp.on("Network.requestWillBeSent", on_request_sent)

                # Backup listeners.
                page.on("request", lambda req: capture(req.url, "request"))
                page.on("framenavigated", lambda frame: capture(frame.url, "nawigacja"))

                def on_popup(popup):
                    popup.on("framenavigated", lambda f: capture(popup.url, "popup"))
                    popup.on("request", lambda r: capture(r.url, "popup request"))

                page.on("popup", on_popup)

                print("\nOtwieram stronę logowania Lidl Plus...")
                page.goto(auth_url, wait_until="domcontentloaded", timeout=15000)

                print("\n" + "=" * 60)
                print("Zaloguj się w oknie przeglądarki.")
                print("Token zostanie przechwycony automatycznie.")
                print("=" * 60 + "\n")

                deadline = time.time() + LOGIN_TIMEOUT
                last_report = 0.0

                while time.time() < deadline:
                    if found["code"]:
                        break

                    # Fallback: the xdg-open handler wrote the deep link to a file.
                    callback_url = _read_callback_file()
                    if callback_url:
                        capture(callback_url, "xdg-open callback")
                        if found["code"]:
                            break

                    time.sleep(0.2)

                    elapsed = LOGIN_TIMEOUT - (deadline - time.time())
                    if elapsed - last_report >= 10:
                        last_report = elapsed
                        print(f"   Czekam... ({int(elapsed)}s / {LOGIN_TIMEOUT}s)")
            finally:
                if browser:
                    try:
                        browser.close()
                    except Exception as e:
                        print(f"Błąd zamykania przeglądarki: {e}")
    except Exception as e:
        print(f"\nBłąd uruchamiania przeglądarki ({CHROME_BINARY}): {e}")
        return None
    finally:
        shutil.rmtree(chrome_profile, ignore_errors=True)
        _clear_callback_file()

    if not found["code"]:
        print(f"Nie zalogowano w ciągu {LOGIN_TIMEOUT} s.")
        return None

    print("Przechwycono kod - wymieniam na tokeny...")
    try:
        token_data = api.exchange_code_for_token(found["code"], code_verifier)
        api.save_tokens(TOKENS_FILE)
        print(f"Tokeny zapisane do {TOKENS_FILE}")
        return token_data
    except Exception as e:
        print(f"Błąd wymiany tokenu: {e}")
        return None


def main():
    print("\n" + "=" * 60)
    print("FIDL PLUS - LOGOWANIE")
    print("=" * 60)

    if login_with_browser():
        print("\nSUKCES! Uruchom aplikację:")
        print("  python3 app.py")
    else:
        print("\nLogowanie nie powiodło się. Spróbuj ponownie.")
        sys.exit(1)


if __name__ == "__main__":
    main()
