"""
Lidl Plus API Client - interakcja z mobilnym API Lidl Plus
Implements the OAuth2 PKCE flow and receipt retrieval.
"""

import base64
import hashlib
import json
import secrets
import uuid
from urllib.parse import urlencode

import requests


class LidlPlusAPI:
    """Klient API Lidl Plus"""

    # Endpoints
    AUTH_BASE = "https://accounts.lidl.com"
    TICKETS_BASE = "https://tickets.lidlplus.com"
    PROFILE_BASE = "https://profile.lidlplus.com"

    # OAuth2 Config
    CLIENT_ID = "LidlPlusNativeClient"
    CLIENT_SECRET = "secret"
    REDIRECT_URI = "com.lidlplus.app://callback"
    SCOPES = "openid profile offline_access lpprofile lpapis"

    def __init__(self, country: str = "PL"):
        """
        Inicjalizacja klienta API

        Args:
            country: Kod kraju (PL, DE, etc.)
        """
        self.country = country
        self.access_token: str | None = None
        self.refresh_token: str | None = None
        self.id_token: str | None = None
        self.device_id = str(uuid.uuid4()).upper()

        self.session = requests.Session()
        self._setup_headers()

    def _setup_headers(self):
        """Set default headers so requests look like the mobile app."""
        self.session.headers.update({
            "User-Agent": "LidlSocialInternacional/16.40.20 (com.lidl.eci.lidl.plus; build:1378; iOS 17.3.1) Alamofire/5.10.2",
            "Accept": "*/*",
            "Accept-Language": f"{self.country.lower()}-{self.country};q=1.0",
            "Accept-Encoding": "gzip, deflate, br",
            "App-Version": "16.40.20",
            "Operating-System": "iOS",
            "App": "com.lidl.eci.lidl.plus",
            "Deviceid": self.device_id,
            "Brand": "Apple"
        })

    def _generate_pkce_params(self) -> dict[str, str]:
        """
        Generuje parametry PKCE dla OAuth2

        Returns:
            Dict z code_verifier i code_challenge
        """
        # Random code_verifier (43-128 characters)
        code_verifier = base64.urlsafe_b64encode(
            secrets.token_bytes(32)
        ).decode('utf-8').rstrip('=')

        # code_challenge is the SHA256 hash of the code_verifier
        code_challenge = base64.urlsafe_b64encode(
            hashlib.sha256(code_verifier.encode('utf-8')).digest()
        ).decode('utf-8').rstrip('=')

        return {
            'code_verifier': code_verifier,
            'code_challenge': code_challenge
        }

    def get_authorization_url(self) -> tuple[str, str, str]:
        """
Build the authorization URL used for the browser login.

        Returns:
            Tuple: (authorization_url, state, code_verifier)
        """
        pkce_params = self._generate_pkce_params()
        state = secrets.token_urlsafe(32)
        nonce = secrets.token_urlsafe(32)

        params = {
            'client_id': self.CLIENT_ID,
            'redirect_uri': self.REDIRECT_URI,
            'response_type': 'code',
            'scope': self.SCOPES,
            'state': state,
            'nonce': nonce,
            'code_challenge': pkce_params['code_challenge'],
            'code_challenge_method': 'S256',
            'language': f'{self.country}-{self.country}',
            'Country': self.country,
            'track': 'true'
        }

        auth_url = f"{self.AUTH_BASE}/connect/authorize?{urlencode(params)}"
        return auth_url, state, pkce_params['code_verifier']

    def exchange_code_for_token(self, authorization_code: str, code_verifier: str) -> dict:
        """
        Wymienia authorization code na access token

        Args:
            authorization_code: Kod autoryzacyjny z callback URL
            code_verifier: Code verifier z PKCE

        Returns:
            Dict z tokenami (access_token, refresh_token, id_token)
        """
        # Przygotuj Basic Auth header
        credentials = f"{self.CLIENT_ID}:{self.CLIENT_SECRET}"
        basic_auth = base64.b64encode(credentials.encode()).decode()

        headers = {
            "Authorization": f"Basic {basic_auth}",
            "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8"
        }

        data = {
            'grant_type': 'authorization_code',
            'code': authorization_code,
            'code_verifier': code_verifier,
            'redirect_uri': self.REDIRECT_URI
        }

        response = self.session.post(
            f"{self.AUTH_BASE}/connect/token",
            headers=headers,
            data=data
        )
        response.raise_for_status()

        token_data = response.json()

        # Zapisz tokeny
        self.access_token = token_data['access_token']
        self.refresh_token = token_data.get('refresh_token')
        self.id_token = token_data.get('id_token')

        return token_data

    def refresh_access_token(self) -> dict:
        """
Refresh the access token using the refresh token.

        Returns:
            Dict z nowymi tokenami
        """
        if not self.refresh_token:
            raise ValueError("Brak refresh token")

        credentials = f"{self.CLIENT_ID}:{self.CLIENT_SECRET}"
        basic_auth = base64.b64encode(credentials.encode()).decode()

        headers = {
            "Authorization": f"Basic {basic_auth}",
            "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8"
        }

        data = {
            'grant_type': 'refresh_token',
            'refresh_token': self.refresh_token
        }

        response = self.session.post(
            f"{self.AUTH_BASE}/connect/token",
            headers=headers,
            data=data
        )
        response.raise_for_status()

        token_data = response.json()

        self.access_token = token_data['access_token']
        if 'refresh_token' in token_data:
            self.refresh_token = token_data['refresh_token']

        return token_data

    def _get_auth_headers(self) -> dict[str, str]:
        """Authorization headers for API calls."""
        if not self.access_token:
            raise ValueError("Brak access token. Najpierw zaloguj się.")

        return {
            "Authorization": f"Bearer {self.access_token}"
        }

    def get_tickets(self, page: int = 1, only_favorite: bool = False) -> dict:
        """
Fetch a page of receipts.

        Args:
            page: Numer strony
            only_favorite: Czy tylko ulubione

        Returns:
            Dict z paragonami
        """
        url = f"{self.TICKETS_BASE}/api/v2/{self.country}/tickets"
        params = {
            'onlyFavorite': str(only_favorite).lower(),
            'pageNumber': page
        }

        response = self.session.get(
            url,
            params=params,
            headers=self._get_auth_headers()
        )
        response.raise_for_status()

        return response.json()

    def get_ticket_details(self, ticket_id: str) -> dict:
        """
Fetch a single receipt with its products and prices.

        Args:
            ticket_id: ID paragonu

        Returns:
            Receipt details, including itemsLine with the products
        """
        # IMPORTANT: receipt details live in API v3, not v2.
        url = f"{self.TICKETS_BASE}/api/v3/{self.country}/tickets/{ticket_id}"

        # The v3 detail endpoint needs a different 'Accept-Language' header
        headers = self._get_auth_headers()
        headers['Accept-Language'] = self.country.lower()

        response = self.session.get(
            url,
            headers=headers
        )
        response.raise_for_status()

        return response.json()

    def get_all_tickets(self, max_pages: int = 10) -> list[dict]:
        """
Fetch every receipt, following pagination.

        Args:
            max_pages: Maksymalna liczba stron do pobrania

        Returns:
            All receipts
        """
        all_tickets = []
        page = 1

        while page <= max_pages:
            try:
                result = self.get_tickets(page=page)
                tickets = result.get('tickets', [])  # FIXED: klucz to 'tickets' nie 'records'

                if not tickets:
                    break

                all_tickets.extend(tickets)
                page += 1

                # Check whether more pages follow
                total_count = result.get('totalCount', 0)
                if len(all_tickets) >= total_count:
                    break

            except Exception as e:
                print(f"Błąd pobierania strony {page}: {e}")
                break

        return all_tickets

    def get_profile(self) -> dict:
        """
Fetch the user profile.

        Returns:
            Dict z danymi profilu
        """
        url = f"{self.PROFILE_BASE}/api/v1/{self.country}/profile"

        response = self.session.get(
            url,
            headers=self._get_auth_headers()
        )
        response.raise_for_status()

        return response.json()

    def save_tokens(self, filepath: str = "lidl_tokens.json"):
        """Zapisuje tokeny do pliku"""
        tokens = {
            'access_token': self.access_token,
            'refresh_token': self.refresh_token,
            'id_token': self.id_token,
            'device_id': self.device_id
        }

        with open(filepath, 'w') as f:
            json.dump(tokens, f, indent=2)

        print(f"Tokeny zapisane do {filepath}")

    def load_tokens(self, filepath: str = "lidl_tokens.json"):
        """Wczytuje tokeny z pliku"""
        try:
            with open(filepath) as f:
                tokens = json.load(f)

            self.access_token = tokens.get('access_token')
            self.refresh_token = tokens.get('refresh_token')
            self.id_token = tokens.get('id_token')

            if 'device_id' in tokens:
                self.device_id = tokens['device_id']
                self.session.headers['Deviceid'] = self.device_id

            print(f"Tokeny wczytane z {filepath}")
            return True
        except FileNotFoundError:
            print(f"Plik {filepath} nie istnieje")
            return False
