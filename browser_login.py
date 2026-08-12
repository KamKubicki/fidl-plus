"""
Logowanie do Lidl Plus przez prawdziwy Chrome.
Używa CDP (Chrome DevTools Protocol) do przechwycenia deep linka.
"""
import sys
import os
import time
import json

try:
    from playwright.sync_api import sync_playwright
except ImportError:
    print("Brak biblioteki Playwright!")
    print("Zainstaluj: pip install playwright && playwright install chromium")
    sys.exit(1)

from lidl_api import LidlPlusAPI
from urllib.parse import urlparse, parse_qs

CHROME_BINARY = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
CHROME_PROFILE = os.path.expanduser("~/.fidl_chrome_profile")


def _extract_code_from_url(url: str) -> str | None:
    if not url.startswith("com.lidlplus.app://"):
        return None
    params = parse_qs(urlparse(url).query)
    return params.get("code", [None])[0]


def login_with_browser() -> dict:
    api = LidlPlusAPI(country="PL")
    auth_url, state, code_verifier = api.get_authorization_url()
    os.makedirs(CHROME_PROFILE, exist_ok=True)

    code = None

    with sync_playwright() as p:
        browser = p.chromium.launch_persistent_context(
            user_data_dir=CHROME_PROFILE,
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

        # Włącz CDP i nasłuchuj na wszystkie nawigacje łącznie z custom scheme
        cdp = browser.new_cdp_session(page)
        cdp.send("Network.enable")

        def on_request_will_be_sent(event):
            nonlocal code
            url = event.get("request", {}).get("url", "")
            if not code:
                code = _extract_code_from_url(url)
            # Sprawdź też redirectResponse
            redirect = event.get("redirectResponse", {})
            loc = redirect.get("headers", {}).get("location", "") or \
                  redirect.get("headers", {}).get("Location", "")
            if loc and not code:
                code = _extract_code_from_url(loc)

        cdp.on("Network.requestWillBeSent", on_request_will_be_sent)

        # Backup: zwykły on('request') - działa dla http/https
        def on_request(req):
            nonlocal code
            if not code:
                code = _extract_code_from_url(req.url)

        page.on("request", on_request)

        print("\nOtwieram stronę logowania Fidl Plus...")
        page.goto(auth_url, wait_until="domcontentloaded", timeout=15000)

        print("\n" + "=" * 60)
        print("Zaloguj się w oknie przeglądarki.")
        print("Token zostanie przechwycony automatycznie.")
        print("=" * 60 + "\n")

        for i in range(180):
            if code:
                break
            if i > 0 and i % 10 == 0:
                print(f"   Czekam... ({i}s)")
            time.sleep(1)

        browser.close()

    if not code:
        print("Nie zalogowano w ciągu 3 minut.")
        return None

    print("Przechwycono kod - wymieniam na tokeny...")
    try:
        token_data = api.exchange_code_for_token(code, code_verifier)
        api.save_tokens()
        print("Tokeny zapisane do lidl_tokens.json")
        return token_data
    except Exception as e:
        print(f"Blad wymiany tokenu: {e}")
        return None


def main():
    print("\n" + "=" * 60)
    print("FIDL PLUS - LOGOWANIE")
    print("=" * 60)

    tokens = login_with_browser()

    if tokens:
        print("\nSUKCES! Uruchom aplikacje:")
        print("  python3 app.py")
    else:
        print("\nLogowanie nie powiodlo sie. Sprobuj ponownie.")


if __name__ == "__main__":
    main()
