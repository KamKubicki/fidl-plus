"""
Logowanie do Lidl Plus przez prawdziwy Chrome
Używa persistent context z prawdziwym Chrome - omija reCAPTCHA v3
"""
import sys
import os
import time

try:
    from playwright.sync_api import sync_playwright
except ImportError:
    print("Brak biblioteki Playwright!")
    print("Zainstaluj: pip install playwright && playwright install chromium")
    sys.exit(1)

from lidl_api import LidlPlusAPI
from urllib.parse import urlparse, parse_qs

CHROME_BINARY = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
CHROME_PROFILE = os.path.expanduser("~/.lidl_chrome_profile")


def login_with_browser() -> dict:
    """
    Otwiera prawdziwy Chrome, czeka na ręczne zalogowanie,
    przechwytuje kod OAuth i wymienia na tokeny mobilnego API.

    Returns:
        Dict z tokenami lub None
    """
    api = LidlPlusAPI(country="PL")
    auth_url, state, code_verifier = api.get_authorization_url()

    os.makedirs(CHROME_PROFILE, exist_ok=True)

    state_box = {'code': None}

    with sync_playwright() as p:
        browser = p.chromium.launch_persistent_context(
            user_data_dir=CHROME_PROFILE,
            executable_path=CHROME_BINARY,
            headless=False,
            args=[
                '--disable-blink-features=AutomationControlled',
                '--no-first-run',
                '--no-default-browser-check',
            ],
            viewport={'width': 390, 'height': 844},
            locale='pl-PL',
            timezone_id='Europe/Warsaw',
        )

        page = browser.pages[0] if browser.pages else browser.new_page()

        def on_request(req):
            if req.url.startswith('com.lidlplus.app://'):
                parsed = urlparse(req.url)
                params = parse_qs(parsed.query)
                code = params.get('code', [None])[0]
                if code:
                    state_box['code'] = code

        def on_response(resp):
            # Czasem redirect trafia jako response zamiast request
            if resp.url.startswith('com.lidlplus.app://'):
                parsed = urlparse(resp.url)
                params = parse_qs(parsed.query)
                code = params.get('code', [None])[0]
                if code:
                    state_box['code'] = code

        page.on('request', on_request)
        page.on('response', on_response)

        print("\nOtwieram stronę logowania Fidl Plus...")
        page.goto(auth_url, wait_until='domcontentloaded', timeout=15000)

        print("\n" + "="*60)
        print("Zaloguj się w oknie przeglądarki.")
        print("Token zostanie przechwycony automatycznie.")
        print("="*60 + "\n")

        for i in range(180):
            if state_box['code']:
                break
            # Sprawdz tez URL strony - czasem Chrome zmienia URL na deep link
            try:
                current_url = page.url
                if current_url.startswith('com.lidlplus.app://'):
                    parsed = urlparse(current_url)
                    params = parse_qs(parsed.query)
                    code = params.get('code', [None])[0]
                    if code:
                        state_box['code'] = code
                        break
            except Exception:
                pass
            if i > 0 and i % 30 == 0:
                print(f"   Czekam na zalogowanie... ({i}s)")
            time.sleep(1)

        browser.close()

    if not state_box['code']:
        print("Nie zalogowano w ciągu 3 minut.")
        return None

    print("Przechwycono kod - wymieniam na tokeny...")
    try:
        token_data = api.exchange_code_for_token(state_box['code'], code_verifier)
        api.save_tokens()
        print("Tokeny zapisane do lidl_tokens.json")
        return token_data
    except Exception as e:
        print(f"Blad wymiany tokenu: {e}")
        return None


def main():
    print("\n" + "="*60)
    print("LIDL PLUS - LOGOWANIE")
    print("="*60)

    tokens = login_with_browser()

    if tokens:
        print("\nSUKCES! Mozesz teraz uzywac:")
        print("  python simple_usage.py")
    else:
        print("\nLogowanie nie powiodlo sie. Sprobuj ponownie.")


if __name__ == "__main__":
    main()
